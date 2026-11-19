"""
Xin WebRTC Signaling Engine
Handles real-time session negotiation between phone and laptop.
Supports both WebSocket and HTTP polling fallback with message queuing.
"""

import json
import threading
import time
import uuid


class SignalingHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.waiting_queue = []          # list of user_id strings
        self.rooms = {}                  # room_id -> {"peers": [id1, id2], "initiator": id1, "created": float}
        self.user_to_room = {}           # user_id -> room_id
        self.user_ws = {}                # user_id -> websocket
        self.user_messages = {}          # user_id -> list of message dicts
        self.user_last_seen = {}         # user_id -> float timestamp

    def touch(self, user_id):
        self.user_last_seen[user_id] = time.time()

    def register_client(self, user_id, ws=None):
        with self.lock:
            self.touch(user_id)
            if ws is not None:
                self.user_ws[user_id] = ws
            if user_id not in self.user_messages:
                self.user_messages[user_id] = []

    def unregister_client(self, user_id):
        with self.lock:
            self._cleanup_user(user_id, notify_partner=True)

    def _send_to_user(self, user_id, msg):
        """Internal helper to dispatch message to a user via WebSocket or queue."""
        self.touch(user_id)
        ws = self.user_ws.get(user_id)
        delivered = False
        if ws:
            try:
                ws.send(json.dumps(msg))
                delivered = True
            except Exception:
                self.user_ws.pop(user_id, None)

        if not delivered:
            if user_id not in self.user_messages:
                self.user_messages[user_id] = []
            self.user_messages[user_id].append(msg)
            # Cap message queue length
            if len(self.user_messages[user_id]) > 50:
                self.user_messages[user_id].pop(0)

    def find_match(self, user_id):
        """Pair the user with another waiting peer, or put them in the queue."""
        with self.lock:
            self.touch(user_id)
            # Remove any current room assignment
            self._leave_room(user_id, notify_partner=True)

            # Clean waiting queue of stale users
            now = time.time()
            self.waiting_queue = [
                uid for uid in self.waiting_queue
                if uid != user_id and (now - self.user_last_seen.get(uid, 0) < 60)
            ]

            if self.waiting_queue:
                partner_id = self.waiting_queue.pop(0)
                room_id = f"room-{uuid.uuid4().hex[:8]}"
                self.rooms[room_id] = {
                    "peers": [partner_id, user_id],
                    "initiator": partner_id,
                    "created": now
                }
                self.user_to_room[partner_id] = room_id
                self.user_to_room[user_id] = room_id

                # Notify partner (initiator creates offer)
                self._send_to_user(partner_id, {
                    "type": "matched",
                    "room_id": room_id,
                    "peer_id": user_id,
                    "is_initiator": True,
                    "message": "Connected with peer. Initiating WebRTC handshake."
                })
                # Notify newcomer (waits for offer)
                self._send_to_user(user_id, {
                    "type": "matched",
                    "room_id": room_id,
                    "peer_id": partner_id,
                    "is_initiator": False,
                    "message": "Connected with peer. Awaiting offer."
                })
                return {"status": "matched", "room_id": room_id, "peer_id": partner_id}
            else:
                if user_id not in self.waiting_queue:
                    self.waiting_queue.append(user_id)
                self._send_to_user(user_id, {
                    "type": "waiting",
                    "message": "In lobby queue. Waiting for remote peer to connect."
                })
                return {"status": "waiting"}

    def relay_signal(self, sender_id, target_id, signal_data):
        """Relay SDP Offer, Answer, or ICE candidate directly to the peer."""
        with self.lock:
            self.touch(sender_id)
            # Verify they share a room
            sender_room = self.user_to_room.get(sender_id)
            target_room = self.user_to_room.get(target_id)
            if not sender_room or sender_room != target_room:
                return False

            self._send_to_user(target_id, {
                "type": "signal",
                "sender_id": sender_id,
                "data": signal_data
            })
            return True

    def relay_chat(self, sender_id, target_id, user_name, text):
        """Relay real-time chat message to the peer."""
        with self.lock:
            self.touch(sender_id)
            sender_room = self.user_to_room.get(sender_id)
            target_room = self.user_to_room.get(target_id)
            if not sender_room or sender_room != target_room:
                return False

            chat_msg = {
                "type": "chat",
                "sender_id": sender_id,
                "user": user_name,
                "text": text,
                "time": time.strftime("%H:%M")
            }
            self._send_to_user(target_id, chat_msg)
            return True

    def relay_event(self, sender_id, target_id, event_type, extra_data=None):
        """Relay custom events such as chat_request, chat_accept, chat_decline."""
        with self.lock:
            self.touch(sender_id)
            sender_room = self.user_to_room.get(sender_id)
            target_room = self.user_to_room.get(target_id)
            if not sender_room or sender_room != target_room:
                return False

            msg = {
                "type": event_type,
                "sender_id": sender_id,
                "time": time.strftime("%H:%M")
            }
            if extra_data and isinstance(extra_data, dict):
                msg.update(extra_data)
            self._send_to_user(target_id, msg)
            return True

    def next_peer(self, user_id):
        """Cycle to a new partner."""
        return self.find_match(user_id)

    def leave(self, user_id):
        """Disconnect from active room."""
        with self.lock:
            self.touch(user_id)
            self._leave_room(user_id, notify_partner=True)
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
            return {"status": "disconnected"}

    def _leave_room(self, user_id, notify_partner=True):
        room_id = self.user_to_room.pop(user_id, None)
        if room_id and room_id in self.rooms:
            room = self.rooms.pop(room_id, None)
            if room:
                for peer_id in room["peers"]:
                    if peer_id != user_id:
                        self.user_to_room.pop(peer_id, None)
                        if notify_partner:
                            self._send_to_user(peer_id, {
                                "type": "peer_disconnected",
                                "message": "Remote peer has disconnected."
                            })

    def _cleanup_user(self, user_id, notify_partner=True):
        if user_id in self.waiting_queue:
            self.waiting_queue.remove(user_id)
        self._leave_room(user_id, notify_partner=notify_partner)
        self.user_ws.pop(user_id, None)
        self.user_messages.pop(user_id, None)
        self.user_last_seen.pop(user_id, None)

    def poll_messages(self, user_id):
        """HTTP polling endpoint to retrieve any queued messages."""
        with self.lock:
            self.touch(user_id)
            msgs = self.user_messages.get(user_id, [])
            self.user_messages[user_id] = []
            return msgs

    def get_diagnostics(self):
        with self.lock:
            now = time.time()
            active_users = sum(1 for ts in self.user_last_seen.values() if now - ts < 60)
            return {
                "active_users": active_users,
                "waiting_in_lobby": len(self.waiting_queue),
                "active_rooms": len(self.rooms),
                "connected_websockets": len(self.user_ws)
            }


signaling_hub = SignalingHub()

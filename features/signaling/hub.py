"""
Xin WebRTC Signaling Engine
Handles real-time session negotiation between phone and laptop.
Provides instant auto-matchmaking so any 2 devices online meet immediately.
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
        self.last_partner = {}           # user_id -> last paired peer_id

    def touch(self, user_id):
        if user_id:
            self.user_last_seen[user_id] = time.time()

    def register_client(self, user_id, ws=None):
        with self.lock:
            self.touch(user_id)
            if ws is not None:
                self.user_ws[user_id] = ws
            if user_id not in self.user_messages:
                self.user_messages[user_id] = []

    def unregister_client(self, user_id, ws=None):
        with self.lock:
            if ws is not None:
                current_ws = self.user_ws.get(user_id)
                if current_ws is not None and current_ws is not ws:
                    return
                if current_ws is ws:
                    self.user_ws.pop(user_id, None)
                    return
            self._cleanup_user(user_id, notify_partner=True)

    def _send_to_user(self, user_id, msg):
        """Internal helper to dispatch message to a user via WebSocket or queue."""
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
            if len(self.user_messages[user_id]) > 50:
                self.user_messages[user_id].pop(0)

    def _purge_stale_locked(self):
        """Remove users who haven't polled or pinged in 8 seconds."""
        now = time.time()
        stale_timeout = 8.0
        stale_users = [
            uid for uid, ts in self.user_last_seen.items()
            if (now - ts) > stale_timeout
        ]
        for uid in stale_users:
            self._cleanup_user(uid, notify_partner=True)

    def _try_match_waiting_locked(self):
        """Match pairs from the waiting queue immediately."""
        now = time.time()
        # Clean queue of stale, duplicates, or already-paired users
        clean_queue = []
        for uid in self.waiting_queue:
            if uid in self.user_to_room:
                continue
            if (now - self.user_last_seen.get(uid, 0)) <= 8.0:
                if uid not in clean_queue:
                    clean_queue.append(uid)
        self.waiting_queue = clean_queue

        matched_pairs = []
        while len(self.waiting_queue) >= 2:
            u1 = self.waiting_queue.pop(0)
            # If 2+ other users remain, prefer someone other than u1's last partner
            u2 = None
            if len(self.waiting_queue) >= 2:
                last_p = self.last_partner.get(u1)
                for idx, candidate in enumerate(self.waiting_queue):
                    if candidate != u1 and candidate != last_p:
                        u2 = self.waiting_queue.pop(idx)
                        break
            if u2 is None:
                u2 = self.waiting_queue.pop(0)

            if u1 == u2:
                continue

            room_id = f"room-{uuid.uuid4().hex[:8]}"
            self.rooms[room_id] = {
                "peers": [u1, u2],
                "initiator": u1,
                "created": now
            }
            self.user_to_room[u1] = room_id
            self.user_to_room[u2] = room_id
            self.last_partner[u1] = u2
            self.last_partner[u2] = u1

            # u1 is initiator (creates SDP offer)
            self._send_to_user(u1, {
                "type": "matched",
                "room_id": room_id,
                "peer_id": u2,
                "is_initiator": True,
                "message": "Connected with peer. Initiating WebRTC handshake."
            })
            # u2 is receiver (awaits SDP offer)
            self._send_to_user(u2, {
                "type": "matched",
                "room_id": room_id,
                "peer_id": u1,
                "is_initiator": False,
                "message": "Connected with peer. Awaiting offer."
            })
            matched_pairs.append((u1, u2))

        return matched_pairs

    def _resolve_target_locked(self, sender_id, target_id):
        if target_id and target_id in self.user_last_seen:
            return target_id
        room_id = self.user_to_room.get(sender_id)
        if room_id and room_id in self.rooms:
            peers = self.rooms[room_id].get("peers", [])
            for p in peers:
                if p != sender_id and p in self.user_last_seen:
                    return p
        return None

    def find_match(self, user_id):
        """Put the user in queue and immediately pair with any available peer."""
        with self.lock:
            self.touch(user_id)
            self._purge_stale_locked()
            self._leave_room_locked(user_id, notify_partner=True)

            if user_id not in self.waiting_queue:
                self.waiting_queue.append(user_id)

            self._try_match_waiting_locked()

            if user_id in self.user_to_room:
                room_id = self.user_to_room[user_id]
                room = self.rooms.get(room_id, {})
                peers = room.get("peers", [])
                partner = peers[1] if peers and peers[0] == user_id else (peers[0] if peers else None)
                return {"status": "matched", "room_id": room_id, "peer_id": partner}
            else:
                self._send_to_user(user_id, {
                    "type": "waiting",
                    "queue_count": len(self.waiting_queue),
                    "message": "In lobby queue. Waiting for remote peer to connect."
                })
                return {"status": "waiting", "queue_count": len(self.waiting_queue)}

    def heartbeat(self, user_id):
        """Called on WebSocket ping to keep session alive, purge ghosts, and auto-match."""
        with self.lock:
            self.touch(user_id)
            self._purge_stale_locked()
            if user_id not in self.user_to_room and user_id not in self.waiting_queue:
                self.waiting_queue.append(user_id)
            self._try_match_waiting_locked()
            return {
                "type": "pong",
                "in_room": user_id in self.user_to_room,
                "queue_count": len(self.waiting_queue)
            }

    def relay_signal(self, sender_id, target_id, signal_data):
        """Relay SDP Offer, Answer, or ICE candidate directly to the peer."""
        with self.lock:
            self.touch(sender_id)
            resolved = self._resolve_target_locked(sender_id, target_id)
            if not resolved:
                return False

            self._send_to_user(resolved, {
                "type": "signal",
                "sender_id": sender_id,
                "data": signal_data
            })
            return True

    def relay_chat(self, sender_id, target_id, user_name, text):
        """Relay real-time chat message to the peer."""
        with self.lock:
            self.touch(sender_id)
            resolved = self._resolve_target_locked(sender_id, target_id)
            if not resolved:
                return False

            chat_msg = {
                "type": "chat",
                "sender_id": sender_id,
                "user": user_name,
                "text": text,
                "time": time.strftime("%H:%M")
            }
            self._send_to_user(resolved, chat_msg)
            return True

    def relay_event(self, sender_id, target_id, event_type, extra_data=None):
        """Relay custom events such as chat_request, chat_accept, chat_decline."""
        with self.lock:
            self.touch(sender_id)
            resolved = self._resolve_target_locked(sender_id, target_id)
            if not resolved:
                return False

            msg = {
                "type": event_type,
                "sender_id": sender_id,
                "time": time.strftime("%H:%M")
            }
            if extra_data and isinstance(extra_data, dict):
                msg.update(extra_data)
            self._send_to_user(resolved, msg)
            return True

    def next_peer(self, user_id):
        """Cycle to a new partner."""
        return self.find_match(user_id)

    def leave(self, user_id):
        """Disconnect from active room."""
        with self.lock:
            self._cleanup_user(user_id, notify_partner=True)
            return {"status": "disconnected"}

    def _leave_room_locked(self, user_id, notify_partner=True):
        now = time.time()
        room_id = self.user_to_room.pop(user_id, None)
        if room_id and room_id in self.rooms:
            room = self.rooms.pop(room_id, None)
            if room:
                for peer_id in room["peers"]:
                    if peer_id != user_id:
                        self.user_to_room.pop(peer_id, None)
                        is_alive = (now - self.user_last_seen.get(peer_id, 0)) <= 8.0
                        if notify_partner and is_alive:
                            self._send_to_user(peer_id, {
                                "type": "peer_disconnected",
                                "room_id": room_id,
                                "message": "Remote peer has disconnected."
                            })
                            if peer_id not in self.waiting_queue:
                                self.waiting_queue.append(peer_id)

    def _cleanup_user(self, user_id, notify_partner=True):
        if user_id in self.waiting_queue:
            self.waiting_queue.remove(user_id)
        self._leave_room_locked(user_id, notify_partner=notify_partner)
        self.user_ws.pop(user_id, None)
        self.user_messages.pop(user_id, None)
        self.user_last_seen.pop(user_id, None)
        self.last_partner.pop(user_id, None)

    def poll_messages(self, user_id):
        """HTTP polling endpoint with auto-queue and auto-matchmaking."""
        with self.lock:
            self.touch(user_id)
            self._purge_stale_locked()

            # If user has no room and is not in queue, add to queue and match
            if user_id not in self.user_to_room and user_id not in self.waiting_queue:
                self.waiting_queue.append(user_id)
                self._send_to_user(user_id, {
                    "type": "waiting",
                    "queue_count": len(self.waiting_queue),
                    "message": "In lobby queue. Waiting for remote peer to connect."
                })

            self._try_match_waiting_locked()

            msgs = self.user_messages.get(user_id, [])
            self.user_messages[user_id] = []
            return msgs

    def get_diagnostics(self):
        with self.lock:
            now = time.time()
            active_users = sum(1 for ts in self.user_last_seen.values() if now - ts < 8.0)
            return {
                "active_users": active_users,
                "waiting_in_lobby": len(self.waiting_queue),
                "active_rooms": len(self.rooms),
                "connected_websockets": len(self.user_ws)
            }


signaling_hub = SignalingHub()

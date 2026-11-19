"""
Xin WebRTC Signaling Routes
Exposes WebSocket endpoint (/ws/signal) and HTTP REST endpoints for signaling.
"""

import json
from flask import Blueprint, request, jsonify
from features.signaling.hub import signaling_hub

signaling_bp = Blueprint("signaling", __name__)


def register_socket_routes(sock):
    """Register WebSocket route using flask-sock."""

    @sock.route("/ws/signal")
    def handle_websocket(ws):
        user_id = None
        try:
            # First incoming message should register user ID
            initial_raw = ws.receive()
            if not initial_raw:
                return
            initial_data = json.loads(initial_raw)
            user_id = initial_data.get("user_id")
            if not user_id:
                ws.close()
                return

            signaling_hub.register_client(user_id, ws=ws)
            ws.send(json.dumps({
                "type": "registered",
                "user_id": user_id,
                "message": "WebRTC signaling socket connected."
            }))

            # Auto-queue or process registration action
            action = initial_data.get("action", "join")
            if action == "join":
                signaling_hub.find_match(user_id)

            while True:
                msg_raw = ws.receive()
                if not msg_raw:
                    break
                payload = json.loads(msg_raw)
                msg_type = payload.get("type")

                if msg_type == "join":
                    signaling_hub.find_match(user_id)

                elif msg_type == "signal":
                    target_id = payload.get("target_id")
                    data = payload.get("data")
                    signaling_hub.relay_signal(user_id, target_id, data)

                elif msg_type == "chat":
                    target_id = payload.get("target_id")
                    user_name = payload.get("user", "You")
                    text = payload.get("text", "")
                    signaling_hub.relay_chat(user_id, target_id, user_name, text)

                elif msg_type == "next":
                    signaling_hub.next_peer(user_id)

                elif msg_type == "leave":
                    signaling_hub.leave(user_id)

                elif msg_type == "ping":
                    signaling_hub.touch(user_id)
                    ws.send(json.dumps({"type": "pong"}))

        except Exception:
            pass
        finally:
            if user_id:
                signaling_hub.unregister_client(user_id)


# HTTP REST Fallback Endpoints

@signaling_bp.route("/api/signaling/join", methods=["POST"])
def http_join():
    data = request.json or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id", "code": 400}), 400
    signaling_hub.register_client(user_id)
    res = signaling_hub.find_match(user_id)
    return jsonify(res)


@signaling_bp.route("/api/signaling/signal", methods=["POST"])
def http_signal():
    data = request.json or {}
    sender_id = data.get("sender_id")
    target_id = data.get("target_id")
    signal_data = data.get("data")
    if not sender_id or not target_id or signal_data is None:
        return jsonify({"error": "Invalid signal payload", "code": 400}), 400

    ok = signaling_hub.relay_signal(sender_id, target_id, signal_data)
    return jsonify({"status": "delivered" if ok else "not_routed"})


@signaling_bp.route("/api/signaling/chat", methods=["POST"])
def http_chat():
    data = request.json or {}
    sender_id = data.get("sender_id")
    target_id = data.get("target_id")
    user_name = data.get("user", "You")
    text = data.get("text", "")
    if not sender_id or not target_id or not text.strip():
        return jsonify({"error": "Invalid chat payload", "code": 400}), 400

    ok = signaling_hub.relay_chat(sender_id, target_id, user_name, text.strip())
    return jsonify({"status": "delivered" if ok else "not_routed"})


@signaling_bp.route("/api/signaling/poll", methods=["GET"])
def http_poll():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id", "code": 400}), 400
    msgs = signaling_hub.poll_messages(user_id)
    return jsonify({"messages": msgs})


@signaling_bp.route("/api/signaling/next", methods=["POST"])
def http_next():
    data = request.json or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id", "code": 400}), 400
    res = signaling_hub.next_peer(user_id)
    return jsonify(res)


@signaling_bp.route("/api/signaling/leave", methods=["POST"])
def http_leave():
    data = request.json or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id", "code": 400}), 400
    res = signaling_hub.leave(user_id)
    return jsonify(res)


@signaling_bp.route("/api/signaling/stats", methods=["GET"])
def http_stats():
    return jsonify(signaling_hub.get_diagnostics())

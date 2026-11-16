from flask import Blueprint, request, jsonify
from features.chat.service import chat_service

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/api/chat", methods=["GET", "POST"])
def handle_chat():
    if request.method == "POST":
        data = request.json or {}
        user = data.get("user", "Anonymous").strip() or "Anonymous"
        text = data.get("text", "").strip()
        if text:
            msg = chat_service.add_message(user, text)
            return jsonify({"status": "ok", "msg": msg})
        return jsonify({"error": "Empty text payload", "code": 400}), 400

    return jsonify(chat_service.get_messages())

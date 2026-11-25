from flask import Blueprint, request, jsonify
from features.chat.service import chat_service

chat_bp = Blueprint("chat", __name__)


def _sanitize_text(val: str, max_len: int = 2000) -> str:
    if not isinstance(val, str):
        return ""
    cleaned = val.replace("<", "").replace(">", "").strip()
    return cleaned[:max_len]


@chat_bp.route("/api/chat", methods=["GET", "POST"])
def handle_chat():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        user = _sanitize_text(data.get("user", "Anonymous"), 48) or "Anonymous"
        text = _sanitize_text(data.get("text", ""), 2000)
        if text:
            msg = chat_service.add_message(user, text)
            return jsonify({"status": "ok", "msg": msg})
        return jsonify({"error": "Empty text payload", "code": 400}), 400

    return jsonify(chat_service.get_messages())

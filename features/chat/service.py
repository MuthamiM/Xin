import threading
import time

class ChatService:
    def __init__(self):
        self.lock = threading.Lock()
        self.messages = [
            {"user": "System", "text": "Xin session open. Direct peer link active.", "time": "00:00"},
            {"user": "Partner", "text": "Signal linked via Android camera stream.", "time": "00:01"},
        ]

    def add_message(self, user, text):
        msg = {
            "user": user,
            "text": text,
            "time": time.strftime("%H:%M")
        }
        with self.lock:
            self.messages.append(msg)
            if len(self.messages) > 100:
                self.messages.pop(0)
        return msg

    def get_messages(self):
        with self.lock:
            return list(self.messages)

chat_service = ChatService()

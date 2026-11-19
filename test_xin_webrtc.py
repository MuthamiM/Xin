import sys
import os

sys.path.insert(0, r"C:\Users\cantroll\.gemini\antigravity\scratch\Xin")

from core.app import create_app
from core.config import Config

print("[TEST] Creating Xin Flask application...")
app = create_app()
client = app.test_client()

print("[TEST 1] GET / (Index page with WebRTC and getUserMedia)...")
res = client.get("/")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
html = res.data.decode("utf-8")
assert "getUserMedia" in html, "Missing getUserMedia in index.html"
assert "RTCPeerConnection" in html, "Missing RTCPeerConnection in index.html"
assert "remoteVideo" in html, "Missing remoteVideo in index.html"
assert "localVideo" in html, "Missing localVideo in index.html"
assert "toggleMic" in html or "toggleMicrophone" in html, "Missing mic toggle in index.html"
assert "toggleCam" in html or "toggleCamera" in html, "Missing cam toggle in index.html"
assert "flipCam" in html or "switchCamera" in html, "Missing flip camera in index.html"
assert "cycleViewMode" in html or "layout-split" in html, "Missing view mode switcher in index.html"
print("PASS: Index contains all WebRTC audio/video elements and view controls.")

print("[TEST 2] GET /studio redirects to / ...")
res = client.get("/studio")
assert res.status_code == 302, f"Expected 302 redirect, got {res.status_code}"
print("PASS: /studio redirects cleanly to /.")

print("[TEST 3] GET /api/status...")
res = client.get("/api/status")
assert res.status_code == 200
data = res.get_json()
assert data["platform"] == "Xin"
assert data["status"] == "ONLINE"
assert "signaling" in data
print(f"PASS: API status verified. Signaling info: {data['signaling']}")

print("[TEST 4] Signaling Handshake Simulation (Phone & Laptop)...")
# User 1 (Laptop) joins
res1 = client.post("/api/signaling/join", json={"user_id": "laptop_user_1"})
assert res1.status_code == 200
d1 = res1.get_json()
assert d1["status"] == "waiting", f"Expected waiting, got {d1}"
print("PASS: Laptop user joined lobby, placed in waiting queue.")

# User 2 (Phone) joins
res2 = client.post("/api/signaling/join", json={"user_id": "phone_user_2"})
assert res2.status_code == 200
d2 = res2.get_json()
assert d2["status"] == "matched", f"Expected matched, got {d2}"
assert d2["peer_id"] == "laptop_user_1"
print(f"PASS: Phone user joined and automatically matched with Laptop! Room: {d2['room_id']}")

# Check messages for Laptop user
res_poll1 = client.get("/api/signaling/poll?user_id=laptop_user_1")
msgs1 = res_poll1.get_json()["messages"]
assert any(m.get("type") == "matched" and m.get("peer_id") == "phone_user_2" for m in msgs1)
print("PASS: Laptop received matched notification for Phone.")

# Laptop sends SDP Offer to Phone
offer_sdp = {"type": "offer", "sdp": "v=0\r\no=- 12345 2 IN IP4 127.0.0.1\r\nm=audio 5000\r\nm=video 5002"}
res_sig = client.post("/api/signaling/signal", json={
    "sender_id": "laptop_user_1",
    "target_id": "phone_user_2",
    "data": offer_sdp
})
assert res_sig.status_code == 200
assert res_sig.get_json()["status"] == "delivered"
print("PASS: SDP Offer successfully routed from Laptop to Phone.")

# Phone polls and receives SDP Offer
res_poll2 = client.get("/api/signaling/poll?user_id=phone_user_2")
msgs2 = res_poll2.get_json()["messages"]
signal_msg = next((m for m in msgs2 if m.get("type") == "signal"), None)
assert signal_msg is not None
assert signal_msg["data"]["sdp"] == offer_sdp["sdp"]
print("PASS: Phone received SDP Offer.")

# Phone sends SDP Answer to Laptop
answer_sdp = {"type": "answer", "sdp": "v=0\r\nm=audio 5000\r\nm=video 5002"}
res_ans = client.post("/api/signaling/signal", json={
    "sender_id": "phone_user_2",
    "target_id": "laptop_user_1",
    "data": answer_sdp
})
assert res_ans.status_code == 200
print("PASS: SDP Answer sent back from Phone to Laptop.")

# Chat message exchange between phone and laptop
res_chat = client.post("/api/signaling/chat", json={
    "sender_id": "phone_user_2",
    "target_id": "laptop_user_1",
    "user": "Phone User",
    "text": "Hello from my mobile camera and mic!"
})
assert res_chat.status_code == 200

# Laptop polls chat message
res_poll_chat = client.get("/api/signaling/poll?user_id=laptop_user_1")
chat_msgs = res_poll_chat.get_json()["messages"]
assert any(m.get("type") == "chat" and "Hello from my mobile" in m.get("text", "") for m in chat_msgs)
print("PASS: Real-time chat message successfully exchanged between peers.")

print("\nALL 4 WEBRTC & SIGNALING TESTS PASSED PERFECTLY!")

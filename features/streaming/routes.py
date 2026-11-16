import time
from flask import Blueprint, Response, request, jsonify
from features.streaming.engine import StreamEngine
from features.security.geofence import enforce_regional_lock

streaming_bp = Blueprint("streaming", __name__)
stream_engine = StreamEngine()

def generate_video_stream():
    while True:
        frame = stream_engine.get_jpeg()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.03)

@streaming_bp.route("/video_feed")
@enforce_regional_lock
def video_feed():
    return Response(generate_video_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@streaming_bp.route("/api/control", methods=["POST"])
def stream_control():
    payload = request.json or {}
    if "source" in payload:
        stream_engine.set_source(payload["source"])
    if "filter" in payload:
        stream_engine.set_filter(payload["filter"])
    return jsonify({"status": "ok", "source": stream_engine.source_mode, "filter": stream_engine.filter_mode})

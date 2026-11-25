import os
import time
from flask import Flask, render_template, redirect, jsonify, request
from flask_sock import Sock
from core.config import Config
from features.security.middleware import attach_security_middleware, security_controller
from features.security.error_handlers import register_error_handlers
from features.streaming.routes import streaming_bp
from features.chat.routes import chat_bp
from features.signaling.routes import signaling_bp, register_socket_routes
from features.signaling.hub import signaling_hub

THEMES = [
    {"id": "electric-blue", "name": "Electric Blue", "accent": "#2563eb", "default": True},
    {"id": "cobalt-deep", "name": "Cobalt Deep", "accent": "#1d4ed8", "default": False},
    {"id": "obsidian-steel", "name": "Obsidian Steel", "accent": "#2563eb", "default": False},
]


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "shared", "templates")
    static_dir = os.path.join(base_dir, "shared", "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )
    app.config.from_object(Config)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    # Attach WebSockets via flask-sock
    sock = Sock(app)
    register_socket_routes(sock)

    # Attach middleware controllers & error handlers
    attach_security_middleware(app)
    register_error_handlers(app)

    # Register blueprints
    app.register_blueprint(streaming_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(signaling_bp)

    @app.after_request
    def set_security_and_cache_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self)"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "media-src 'self' blob: mediastream:;"
        )
        return response

    @app.route("/")
    def index():
        return render_template("index.html")

    # Redirect /studio to / so current tabs load clean 1-on-1 call immediately
    @app.route("/studio")
    def studio():
        return redirect("/")

    @app.route("/api/themes")
    def api_themes():
        return jsonify({"default": "electric-blue", "themes": THEMES})

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "NotFound", "code": 404, "message": "Requested endpoint does not exist"}), 404
        return redirect("/")

    @app.route("/api/status")
    def api_status():
        stats = signaling_hub.get_diagnostics()
        return jsonify({
            "platform": Config.PLATFORM_NAME,
            "engine": "Python/Flask",
            "status": "ONLINE",
            "active_banned_ips": len(security_controller.banned_ips),
            "allowed_regions_count": len(Config.ALLOWED_REGIONS),
            "signaling": stats,
            "uptime_seconds": int(time.time() - app.start_time)
        })

    app.start_time = time.time()
    return app

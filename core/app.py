import time
from flask import Flask, render_template, jsonify
from core.config import Config
from features.security.middleware import attach_security_middleware, security_controller
from features.security.error_handlers import register_error_handlers
from features.security.geofence import enforce_regional_lock
from features.streaming.routes import streaming_bp
from features.chat.routes import chat_bp

def create_app():
    app = Flask(
        __name__,
        template_folder="../shared/templates",
        static_folder="../shared/static"
    )
    app.config.from_object(Config)

    # Attach middleware controllers & error handlers
    attach_security_middleware(app)
    register_error_handlers(app)

    # Register feature blueprints
    app.register_blueprint(streaming_bp)
    app.register_blueprint(chat_bp)

    @app.route("/")
    @enforce_regional_lock
    def index():
        return render_template("index.html")

    @app.route("/studio")
    @enforce_regional_lock
    def studio():
        return render_template("studio.html")

    @app.route("/api/status")
    def api_status():
        return jsonify({
            "platform": Config.PLATFORM_NAME,
            "status": "ONLINE",
            "active_banned_ips": len(security_controller.banned_ips),
            "allowed_regions_count": len(Config.ALLOWED_REGIONS),
            "uptime_seconds": int(time.time() - app.start_time)
        })

    app.start_time = time.time()
    return app

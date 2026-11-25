import time
from flask import request, jsonify, render_template
from features.security.vpn_detector import SecurityController
from features.security.geofence import resolve_country
from core.config import Config

security_controller = SecurityController(
    ban_duration=Config.BAN_DURATION_SECONDS,
    rate_limit=Config.RATE_LIMIT_MAX,
    rate_window=Config.RATE_LIMIT_WINDOW
)


def attach_security_middleware(app):
    @app.before_request
    def validate_request():
        # Always allow shared static assets (CSS/JS/icons) cleanly
        if request.path.startswith("/static/"):
            return None

        # Reject oversized payloads early
        if request.content_length and request.content_length > Config.MAX_CONTENT_BYTES:
            return jsonify({
                "error": "PayloadTooLarge",
                "code": 413,
                "max_bytes": Config.MAX_CONTENT_BYTES
            }), 413

        # Determine real client IP through Cloudflare Tunnel
        client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For") or request.remote_addr or "127.0.0.1"
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        # 1. Check if IP is currently under temporary ban
        banned, record = security_controller.is_banned(client_ip)
        if banned:
            remaining = max(1, int(record["expires"] - time.time()))
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "TemporaryBan",
                    "reason": record["reason"],
                    "remaining_seconds": remaining
                }), 403
            return render_template(
                "errors/error.html",
                code=403,
                title="Access Temporarily Suspended",
                message=f"{record['reason']}. Cooldown remaining: {remaining} seconds."
            ), 403

        # 2. Rate limiting & flood control
        if not security_controller.evaluate_rate_limit(client_ip, request.path):
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "RateLimitExceeded",
                    "message": "Excessive request rate. Cooldown active."
                }), 429
            return render_template(
                "errors/error.html",
                code=429,
                title="Rate Limit Exceeded",
                message="Too many requests detected. Temporary cooldown active."
            ), 429

        # 3. VPN / Proxy detection and temporary ban
        is_vpn, reason = security_controller.scan_vpn_proxy(request, client_ip)
        if is_vpn:
            security_controller.apply_temporary_ban(client_ip, duration=Config.BAN_DURATION_SECONDS, reason=reason)
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "VPNRestricted",
                    "reason": reason,
                    "ban_seconds": Config.BAN_DURATION_SECONDS
                }), 403
            return render_template(
                "errors/error.html",
                code=403,
                title="Connection Restricted",
                message=reason
            ), 403

        # 4. Regional Geofencing
        country = resolve_country()
        if country not in Config.ALLOWED_REGIONS:
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "GeoRestricted",
                    "status": 403,
                    "message": "Access restricted to East Africa, South Africa, and Asia.",
                    "detected_region": country
                }), 403
            return render_template(
                "errors/error.html",
                code=403,
                title="Regional Access Restricted",
                message=f"Service available in supported territories (Detected: {country})."
            ), 403

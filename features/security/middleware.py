import time
from flask import request, jsonify, render_template_string
from features.security.vpn_detector import SecurityController
from features.security.geofence import resolve_country, GEO_BLOCKED_TEMPLATE
from core.config import Config

security_controller = SecurityController(
    ban_duration=Config.BAN_DURATION_SECONDS,
    rate_limit=Config.RATE_LIMIT_MAX,
    rate_window=Config.RATE_LIMIT_WINDOW
)

BAN_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Xin - Temporary Suspension</title>
  <style>
    body { background: #0e0f17; color: #9094a6; font-family: monospace; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { max-width: 480px; background: #141622; border: 1px solid #dc2626; padding: 32px; border-radius: 6px; text-align: center; }
    h2 { color: #ef4444; font-size: 16px; margin: 0 0 12px; text-transform: uppercase; letter-spacing: 1px; }
    p { font-size: 12px; line-height: 1.6; margin: 0 0 14px; }
    .detail { background: #1b1d2c; padding: 12px; border-radius: 4px; font-size: 11px; color: #f87171; text-align: left; margin-bottom: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Access Temporarily Suspended</h2>
    <p>Connection rejected by Xin automated security middleware controller.</p>
    <div class="detail">
      <div>Reason: {{ reason }}</div>
      <div>Client Address: {{ ip }}</div>
      <div>Cooldown Remaining: {{ remaining }} seconds</div>
    </div>
    <p style="font-size: 10px; color: #6b7280;">Proxy, VPN anonymizers, and automated scrapers are restricted on this platform.</p>
  </div>
</body>
</html>"""

def attach_security_middleware(app):
    @app.before_request
    def validate_request():
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
            return render_template_string(BAN_TEMPLATE, reason=record["reason"], ip=client_ip, remaining=remaining), 403

        # 2. Rate limiting & flood control
        if not security_controller.evaluate_rate_limit(client_ip):
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "RateLimitExceeded",
                    "message": "Excessive request rate. Cooldown active."
                }), 429
            return render_template_string(BAN_TEMPLATE, reason="Excessive traffic rate", ip=client_ip, remaining=300), 429

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
            return render_template_string(BAN_TEMPLATE, reason=reason, ip=client_ip, remaining=Config.BAN_DURATION_SECONDS), 403

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
            return render_template_string(GEO_BLOCKED_TEMPLATE, code=country, ip=client_ip), 403

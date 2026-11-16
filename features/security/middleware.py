import time
from flask import request, jsonify, render_template_string
from features.security.vpn_detector import SecurityController
from core.config import Config

security_controller = SecurityController(
    ban_duration=Config.BAN_DURATION_SECONDS,
    rate_limit=Config.RATE_LIMIT_MAX,
    rate_window=Config.RATE_LIMIT_WINDOW
)

BAN_TEMPLATE = """<!DOCTYPE html>
<html>
<head><title>Xin - Temporary Suspension</title><style>body{background:#06070a;color:#9ca3af;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}.card{max-width:460px;background:#0d0f15;border:1px solid #dc2626;padding:28px;border-radius:6px;text-align:center;}h2{color:#ef4444;font-size:16px;margin:0 0 12px;text-transform:uppercase;letter-spacing:1px;}p{font-size:12px;line-height:1.6;margin:0 0 16px;}.detail{background:#161922;padding:12px;border-radius:4px;font-size:11px;color:#f87171;text-align:left;margin-bottom:16px;}</style></head>
<body><div class="card"><h2>Access Temporarily Suspended</h2><p>Connection rejected by Xin automated security filters.</p><div class="detail"><div>Reason: {{ reason }}</div><div>Client IP: {{ ip }}</div><div>Remaining: {{ remaining }}s</div></div><p style="font-size:10px;color:#6b7280;">VPN, Proxy, and Tor exit traffic are restricted on this platform.</p></div></body>
</html>"""

def attach_security_middleware(app):
    @app.before_request
    def validate_request():
        client_ip = request.remote_addr or "127.0.0.1"

        banned, record = security_controller.is_banned(client_ip)
        if banned:
            rem = int(record["expires"] - time.time())
            if request.path.startswith("/api/"):
                return jsonify({"error": "TemporaryBan", "reason": record["reason"], "remaining_seconds": rem}), 403
            return render_template_string(BAN_TEMPLATE, reason=record["reason"], ip=client_ip, remaining=rem), 403

        if not security_controller.evaluate_rate_limit(client_ip):
            if request.path.startswith("/api/"):
                return jsonify({"error": "RateLimitExceeded", "message": "Excessive request rate"}), 429
            return render_template_string(BAN_TEMPLATE, reason="Excessive traffic rate", ip=client_ip, remaining=300), 429

        is_vpn, reason = security_controller.scan_vpn_proxy(request, client_ip)
        if is_vpn:
            security_controller.apply_temporary_ban(client_ip, duration=900, reason=reason)
            if request.path.startswith("/api/"):
                return jsonify({"error": "VPNRestricted", "reason": reason, "ban_seconds": 900}), 403
            return render_template_string(BAN_TEMPLATE, reason=reason, ip=client_ip, remaining=900), 403

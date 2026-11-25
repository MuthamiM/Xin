from functools import wraps
from flask import request, jsonify, render_template
from core.config import Config

LOCAL_SUBNETS = {"127.0.0.1", "localhost", "::1"}


def _is_private_or_loopback(ip: str) -> bool:
    if not ip:
        return True
    if ip in LOCAL_SUBNETS or ip.startswith("192.168.") or ip.startswith("10."):
        return True
    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return True
    return False


def resolve_country():
    # Trusted CDN/edge headers only (never accept client query overrides)
    cf_country = request.headers.get("CF-IPCountry")
    if cf_country:
        code = cf_country.strip().upper()[:8]
        if code and code != "XX":
            return code

    viewer = request.headers.get("CloudFront-Viewer-Country") or request.headers.get("X-Country-Code")
    if viewer:
        return viewer.strip().upper()[:8]

    client_ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "127.0.0.1"
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    if _is_private_or_loopback(client_ip):
        return "KE"

    return "UNKNOWN"


def enforce_regional_lock(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        code = resolve_country()
        if code not in Config.ALLOWED_REGIONS:
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "GeoRestricted",
                    "status": 403,
                    "message": "Access restricted to East Africa, South Africa, and Asia.",
                    "detected_region": code
                }), 403
            return render_template(
                "errors/error.html",
                code=403,
                title="Regional Access Restricted",
                message=f"Access restricted to allowed territories (Detected: {code})."
            ), 403
        return f(*args, **kwargs)
    return decorated

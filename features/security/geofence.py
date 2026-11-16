from functools import wraps
from flask import request, jsonify, render_template_string
from core.config import Config

LOCAL_SUBNETS = {"127.0.0.1", "localhost"}

def resolve_country():
    cf_country = request.headers.get("CF-IPCountry")
    if cf_country:
        return cf_country.upper()

    viewer = request.headers.get("CloudFront-Viewer-Country") or request.headers.get("X-Country-Code")
    if viewer:
        return viewer.upper()

    test_geo = request.args.get("geo")
    if test_geo and test_geo.upper() in Config.ALLOWED_REGIONS:
        return test_geo.upper()

    client_ip = request.remote_addr or "127.0.0.1"
    if client_ip.startswith("192.168.") or client_ip.startswith("10.") or client_ip in LOCAL_SUBNETS:
        return "KE"  # Local network test default (East Africa Hub)

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
                    "message": "Access is restricted to East Africa, South Africa, and Asia.",
                    "detected_region": code
                }), 403
            return render_template_string("""<!DOCTYPE html>
<html>
<head><title>Xin - Regional Restriction</title><style>body{background:#06070a;color:#9ca3af;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}.card{max-width:440px;background:#0d0f15;border:1px solid #374151;padding:28px;border-radius:6px;text-align:center;}h2{color:#ef4444;font-size:16px;margin:0 0 12px;text-transform:uppercase;letter-spacing:1px;}</style></head>
<body><div class="card"><h2>Regional Restriction Active</h2><p>Xin is accessible exclusively within East Africa, South Africa, and Asian jurisdictions.</p><p style="color:#ef4444;margin-top:16px;">Detected Region: {{ code }} ({{ ip }})</p></div></body>
</html>""", code=code, ip=request.remote_addr), 403
        return f(*args, **kwargs)
    return decorated

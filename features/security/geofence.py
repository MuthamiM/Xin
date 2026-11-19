from functools import wraps
from flask import request, jsonify, render_template_string
from core.config import Config

LOCAL_SUBNETS = {"127.0.0.1", "localhost", "::1"}

def resolve_country():
    cf_country = request.headers.get("CF-IPCountry")
    if cf_country:
        return cf_country.strip().upper()

    viewer = request.headers.get("CloudFront-Viewer-Country") or request.headers.get("X-Country-Code")
    if viewer:
        return viewer.strip().upper()

    test_geo = request.args.get("geo")
    if test_geo:
        return test_geo.strip().upper()

    client_ip = request.remote_addr or "127.0.0.1"
    if (client_ip.startswith("192.168.") or 
        client_ip.startswith("10.") or 
        client_ip.startswith("172.") or 
        client_ip in LOCAL_SUBNETS):
        return "KE"  # Default to East Africa hub (Kenya) for local intranet network tests

    return "UNKNOWN"

GEO_BLOCKED_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Xin - Regional Restriction</title>
  <style>
    body { background: #0e0f17; color: #9094a6; font-family: -apple-system, BlinkMacSystemFont, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { max-width: 480px; background: #141622; border: 1px solid #ff4757; padding: 32px; border-radius: 8px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
    h2 { color: #ff4757; font-size: 18px; margin: 0 0 12px; text-transform: uppercase; letter-spacing: 1px; font-weight: 800; }
    p { font-size: 13px; line-height: 1.6; margin: 0 0 16px; }
    .info { background: #1b1d2c; padding: 14px; border-radius: 4px; font-size: 12px; color: #ff6b81; text-align: left; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Regional Access Restriction Active</h2>
    <p>Xin video streaming platform is accessible exclusively within East Africa, South Africa, and Asian territories.</p>
    <div class="info">
      <div>Detected Jurisdiction: {{ code }}</div>
      <div>Client Address: {{ ip }}</div>
      <div>Status: HTTP 403 Forbidden</div>
    </div>
  </div>
</body>
</html>"""

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
            return render_template_string(GEO_BLOCKED_TEMPLATE, code=code, ip=request.remote_addr), 403
        return f(*args, **kwargs)
    return decorated

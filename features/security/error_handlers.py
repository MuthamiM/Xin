from flask import jsonify, render_template_string, request

ERROR_TEMPLATE = """<!DOCTYPE html>
<html>
<head><title>Xin - Error {{ code }}</title><style>body{background:#06070a;color:#9ca3af;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}.card{max-width:440px;background:#0d0f15;border:1px solid #374151;padding:28px;border-radius:6px;text-align:center;}h2{color:#f87171;font-size:16px;margin:0 0 12px;text-transform:uppercase;letter-spacing:1px;}p{font-size:12px;line-height:1.6;margin:0 0 16px;}a{color:#60a5fa;text-decoration:none;font-size:11px;}</style></head>
<body><div class="card"><h2>HTTP {{ code }} - {{ title }}</h2><p>{{ message }}</p><a href="/">Back to Xin Home</a></div></body>
</html>"""

def register_error_handlers(app):
    @app.errorhandler(400)
    def err_400(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "BadRequest", "code": 400, "message": "Malformed request parameters"}), 400
        return render_template_string(ERROR_TEMPLATE, code=400, title="Bad Request", message="Invalid payload or parameters."), 400

    @app.errorhandler(403)
    def err_403(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Forbidden", "code": 403, "message": "Access restricted by firewall rules"}), 403
        return render_template_string(ERROR_TEMPLATE, code=403, title="Forbidden", message="Access denied by security controller."), 403

    @app.errorhandler(404)
    def err_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "NotFound", "code": 404, "message": "Requested endpoint does not exist"}), 404
        return render_template_string(ERROR_TEMPLATE, code=404, title="Not Found", message="Resource endpoint does not exist."), 404

    @app.errorhandler(429)
    def err_429(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "RateLimitExceeded", "code": 429, "message": "Rate limit threshold reached"}), 429
        return render_template_string(ERROR_TEMPLATE, code=429, title="Too Many Requests", message="Traffic rate threshold reached. Cooldown required."), 429

    @app.errorhandler(500)
    def err_500(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "InternalError", "code": 500, "message": "Server processing exception"}), 500
        return render_template_string(ERROR_TEMPLATE, code=500, title="Internal Server Error", message="An unexpected processing exception occurred."), 500

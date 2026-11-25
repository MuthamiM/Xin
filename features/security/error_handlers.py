from flask import jsonify, render_template, request


def register_error_handlers(app):
    @app.errorhandler(400)
    def err_400(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "BadRequest", "code": 400, "message": "Malformed request parameters"}), 400
        return render_template("errors/error.html", code=400, title="Bad Request", message="Invalid payload or parameters."), 400

    @app.errorhandler(403)
    def err_403(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Forbidden", "code": 403, "message": "Access restricted by firewall rules"}), 403
        return render_template("errors/error.html", code=403, title="Forbidden", message="Access denied by security controller."), 403

    @app.errorhandler(404)
    def err_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "NotFound", "code": 404, "message": "Requested endpoint does not exist"}), 404
        return render_template("errors/error.html", code=404, title="Not Found", message="Resource endpoint does not exist."), 404

    @app.errorhandler(413)
    def err_413(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "PayloadTooLarge", "code": 413, "message": "Payload exceeds maximum allowed limit"}), 413
        return render_template("errors/error.html", code=413, title="Payload Too Large", message="Submitted request exceeds maximum allowed size."), 413

    @app.errorhandler(429)
    def err_429(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "RateLimitExceeded", "code": 429, "message": "Rate limit threshold reached"}), 429
        return render_template("errors/error.html", code=429, title="Too Many Requests", message="Traffic rate threshold reached. Cooldown required."), 429

    @app.errorhandler(500)
    def err_500(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "InternalError", "code": 500, "message": "Server processing exception"}), 500
        return render_template("errors/error.html", code=500, title="Internal Server Error", message="An unexpected processing exception occurred."), 500

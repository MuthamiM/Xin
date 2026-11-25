//! Shared Assets, Templates, and Theme Catalog Controller
//! Enforces canonical path bounds to prevent path traversal vulnerabilities.

use actix_web::{web, HttpRequest, HttpResponse};
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

use crate::config::{XinConfig, AVAILABLE_THEMES};
use crate::error::XinError;

pub async fn serve_index(config: web::Data<Arc<XinConfig>>) -> Result<HttpResponse, XinError> {
    let index_path = config.shared_dir.join("templates").join("index.html");
    let body = fs::read_to_string(&index_path)
        .map_err(|e| XinError::Internal(format!("Unable to load index template: {}", e)))?;

    Ok(HttpResponse::Ok()
        .content_type("text/html; charset=utf-8")
        .body(body))
}

pub async fn redirect_studio() -> HttpResponse {
    HttpResponse::Found()
        .insert_header(("Location", "/"))
        .finish()
}

pub async fn serve_themes() -> HttpResponse {
    HttpResponse::Ok().json(serde_json::json!({
        "default": "electric-blue",
        "themes": AVAILABLE_THEMES
    }))
}

pub async fn serve_static(
    req: HttpRequest,
    path: web::Path<String>,
    config: web::Data<Arc<XinConfig>>,
) -> Result<HttpResponse, XinError> {
    let rel = path.into_inner();
    if rel.contains("..") || rel.contains('\0') {
        return Err(XinError::Forbidden("Invalid asset path".to_string()));
    }

    let static_root = fs::canonicalize(config.shared_dir.join("static"))
        .map_err(|_| XinError::NotFound("Static asset root missing".to_string()))?;

    let candidate: PathBuf = static_root.join(rel.trim_start_matches('/'));
    let canonical = fs::canonicalize(&candidate)
        .map_err(|_| XinError::NotFound(format!("Asset not found: {}", req.path())))?;

    if !canonical.starts_with(&static_root) || !canonical.is_file() {
        return Err(XinError::Forbidden("Access denied to asset path".to_string()));
    }

    let bytes = fs::read(&canonical)
        .map_err(|_| XinError::Internal("Failed to read static asset".to_string()))?;

    let content_type = match canonical.extension().and_then(|e| e.to_str()) {
        Some("css") => "text/css; charset=utf-8",
        Some("js") => "application/javascript; charset=utf-8",
        Some("json") => "application/json; charset=utf-8",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("ico") => "image/x-icon",
        _ => "application/octet-stream",
    };

    Ok(HttpResponse::Ok().content_type(content_type).body(bytes))
}

pub async fn handle_not_found(req: HttpRequest) -> Result<HttpResponse, XinError> {
    if req.path().starts_with("/api/") {
        return Err(XinError::NotFound(format!(
            "Endpoint {} does not exist",
            req.path()
        )));
    }
    Ok(HttpResponse::Found()
        .insert_header(("Location", "/"))
        .finish())
}

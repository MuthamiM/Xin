//! Xin Typed Rust Error Handling
//! Zero-panic error taxonomy mapping cleanly to JSON API payloads and themed HTML error views.

use actix_web::{http::StatusCode, HttpResponse, ResponseError};
use std::fs;
use std::path::Path;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum XinError {
    #[error("Malformed request parameters: {0}")]
    BadRequest(String),

    #[error("Access restricted by security policy: {0}")]
    Forbidden(String),

    #[error("Access temporarily suspended: {reason}")]
    TemporaryBan { reason: String, remaining_secs: u64 },

    #[error("Service restricted in detected region: {region}")]
    GeoRestricted { region: String },

    #[error("Requested resource does not exist: {0}")]
    NotFound(String),

    #[error("Payload exceeds maximum allowed limit of {max_bytes} bytes")]
    PayloadTooLarge { max_bytes: usize },

    #[error("Excessive request rate; cooldown active")]
    RateLimitExceeded,

    #[error("Internal processing failure: {0}")]
    Internal(String),
}

impl XinError {
    pub fn code_str(&self) -> &'static str {
        match self {
            XinError::BadRequest(_) => "BadRequest",
            XinError::Forbidden(_) => "Forbidden",
            XinError::TemporaryBan { .. } => "TemporaryBan",
            XinError::GeoRestricted { .. } => "GeoRestricted",
            XinError::NotFound(_) => "NotFound",
            XinError::PayloadTooLarge { .. } => "PayloadTooLarge",
            XinError::RateLimitExceeded => "RateLimitExceeded",
            XinError::Internal(_) => "InternalError",
        }
    }

    pub fn title_str(&self) -> &'static str {
        match self {
            XinError::BadRequest(_) => "Bad Request",
            XinError::Forbidden(_) => "Forbidden",
            XinError::TemporaryBan { .. } => "Access Temporarily Suspended",
            XinError::GeoRestricted { .. } => "Regional Access Restricted",
            XinError::NotFound(_) => "Not Found",
            XinError::PayloadTooLarge { .. } => "Payload Too Large",
            XinError::RateLimitExceeded => "Too Many Requests",
            XinError::Internal(_) => "Internal Server Error",
        }
    }

    pub fn http_status(&self) -> StatusCode {
        match self {
            XinError::BadRequest(_) => StatusCode::BAD_REQUEST,
            XinError::Forbidden(_)
            | XinError::TemporaryBan { .. }
            | XinError::GeoRestricted { .. } => StatusCode::FORBIDDEN,
            XinError::NotFound(_) => StatusCode::NOT_FOUND,
            XinError::PayloadTooLarge { .. } => StatusCode::PAYLOAD_TOO_LARGE,
            XinError::RateLimitExceeded => StatusCode::TOO_MANY_REQUESTS,
            XinError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    /// Build a content-negotiated response (structured JSON for API routes, themed HTML otherwise).
    pub fn into_http_response(&self, is_api: bool, shared_dir: Option<&Path>) -> HttpResponse {
        let status = self.http_status();
        if is_api {
            let mut payload = serde_json::json!({
                "error": self.code_str(),
                "code": status.as_u16(),
                "message": self.to_string(),
            });
            if let XinError::TemporaryBan { remaining_secs, .. } = self {
                if let Some(obj) = payload.as_object_mut() {
                    obj.insert("remaining_seconds".to_string(), serde_json::json!(remaining_secs));
                }
            }
            if let XinError::GeoRestricted { region } = self {
                if let Some(obj) = payload.as_object_mut() {
                    obj.insert("detected_region".to_string(), serde_json::json!(region));
                }
            }
            return HttpResponse::build(status).json(payload);
        }

        let html = render_error_html(status.as_u16(), self.title_str(), &self.to_string(), shared_dir);
        HttpResponse::build(status)
            .content_type("text/html; charset=utf-8")
            .body(html)
    }
}

impl ResponseError for XinError {
    fn status_code(&self) -> StatusCode {
        self.http_status()
    }

    fn error_response(&self) -> HttpResponse {
        self.into_http_response(true, None)
    }
}

pub fn html_escape(input: &str) -> String {
    let mut escaped = String::with_capacity(input.len());
    for ch in input.chars() {
        match ch {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            '"' => escaped.push_str("&quot;"),
            '\'' => escaped.push_str("&#x27;"),
            _ => escaped.push(ch),
        }
    }
    escaped
}

fn render_error_html(code: u16, title: &str, message: &str, shared_dir: Option<&Path>) -> String {
    let safe_title = html_escape(title);
    let safe_msg = html_escape(message);
    let safe_code = code.to_string();

    if let Some(root) = shared_dir {
        let tpl_path = root.join("templates").join("errors").join("error.html");
        if let Ok(raw) = fs::read_to_string(tpl_path) {
            return raw
                .replace("{{ code }}", &safe_code)
                .replace("{{ title }}", &safe_title)
                .replace("{{ message }}", &safe_msg);
        }
    }

    format!(
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><title>Xin - {title}</title>\
         <link rel=\"stylesheet\" href=\"/static/css/themes.css\"></head>\
         <body style=\"background:#090b10;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh\">\
         <div style=\"max-width:440px;background:#111520;border:1px solid #2563eb;padding:28px;border-radius:12px;text-align:center\">\
         <h2>HTTP {code} - {title}</h2><p>{msg}</p><a href=\"/\" style=\"color:#3b82f6\">Return to Xin</a></div></body></html>",
        code = safe_code,
        title = safe_title,
        msg = safe_msg
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn error_codes_and_escaping() {
        let err = XinError::BadRequest("<script>alert(1)</script>".to_string());
        assert_eq!(err.http_status(), StatusCode::BAD_REQUEST);
        assert_eq!(err.code_str(), "BadRequest");

        let html = render_error_html(400, "Bad <Title>", "<script>xss()</script>", None);
        assert!(!html.contains("<script>"));
        assert!(html.contains("&lt;script&gt;xss()&lt;/script&gt;"));
    }

    #[test]
    fn rate_limit_and_geo_statuses() {
        assert_eq!(XinError::RateLimitExceeded.http_status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(XinError::GeoRestricted { region: "XX".into() }.http_status(), StatusCode::FORBIDDEN);
        assert_eq!(XinError::PayloadTooLarge { max_bytes: 65536 }.http_status(), StatusCode::PAYLOAD_TOO_LARGE);
    }
}

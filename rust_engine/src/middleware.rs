//! Xin Security & Headers Middleware Controllers
//! Enforces regional geofencing (without query overrides), calibrated NAT-safe flood control,
//! malicious user-agent blocking, payload size enforcement, and strict response security headers.

use actix_web::{
    body::EitherBody,
    dev::{Service, ServiceRequest, ServiceResponse, Transform},
    http::header::{HeaderName, HeaderValue},
    Error,
};
use dashmap::DashMap;
use std::future::{ready, Future, Ready};
use std::pin::Pin;
use std::sync::{Arc, LazyLock};
use std::time::Instant;

use crate::config::XinConfig;
use crate::error::XinError;

static RATE_LIMITER: LazyLock<DashMap<String, Vec<Instant>>> = LazyLock::new(DashMap::new);
static BANNED_IPS: LazyLock<DashMap<String, (Instant, String)>> = LazyLock::new(DashMap::new);

const SUSPICIOUS_AGENTS: &[&str] = &[
    "wget", "python-requests", "scrapy", "nikto", "masscan", "sqlmap",
    "nmap", "gobuster", "dirbuster", "hydra", "burpsuite",
];

#[derive(Clone)]
pub struct SecurityMiddleware {
    pub config: Arc<XinConfig>,
}

impl<S, B> Transform<S, ServiceRequest> for SecurityMiddleware
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
    B: 'static,
{
    type Response = ServiceResponse<EitherBody<B>>;
    type Error = Error;
    type InitError = ();
    type Transform = SecurityMiddlewareService<S>;
    type Future = Ready<Result<Self::Transform, Self::InitError>>;

    fn new_transform(&self, service: S) -> Self::Future {
        ready(Ok(SecurityMiddlewareService {
            service,
            config: self.config.clone(),
        }))
    }
}

pub struct SecurityMiddlewareService<S> {
    service: S,
    config: Arc<XinConfig>,
}

impl<S, B> Service<ServiceRequest> for SecurityMiddlewareService<S>
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error> + 'static,
    B: 'static,
{
    type Response = ServiceResponse<EitherBody<B>>;
    type Error = Error;
    type Future = Pin<Box<dyn Future<Output = Result<Self::Response, Self::Error>>>>;

    fn poll_ready(
        &self,
        ctx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.service.poll_ready(ctx)
    }

    fn call(&self, req: ServiceRequest) -> Self::Future {
        let path = req.path().to_string();
        let is_api = path.starts_with("/api/");
        let is_static = path.starts_with("/static/");
        let config = self.config.clone();

        if !is_static {
            // 1. Enforce max payload bytes before reading body
            if let Some(len) = req.headers().get("content-length") {
                if let Ok(size) = len.to_str().unwrap_or("0").parse::<usize>() {
                    if size > config.max_payload_bytes {
                        let res = XinError::PayloadTooLarge {
                            max_bytes: config.max_payload_bytes,
                        }
                        .into_http_response(is_api, Some(&config.shared_dir));
                        return Box::pin(async move {
                            Ok(req.into_response(res).map_into_right_body())
                        });
                    }
                }
            }

            let client_ip = extract_client_ip(&req);
            let local_ip = is_private_or_loopback(&client_ip);

            // 2. Active temporary ban check (private/loopback never locked out)
            if !local_ip {
                if let Some(entry) = BANNED_IPS.get(&client_ip) {
                    let (banned_at, reason) = entry.value();
                    let elapsed = banned_at.elapsed().as_secs();
                    if elapsed < config.ban_duration_secs {
                        let remaining_secs = config.ban_duration_secs - elapsed;
                        let res = XinError::TemporaryBan {
                            reason: reason.clone(),
                            remaining_secs,
                        }
                        .into_http_response(is_api, Some(&config.shared_dir));
                        return Box::pin(async move {
                            Ok(req.into_response(res).map_into_right_body())
                        });
                    }
                    drop(entry);
                    BANNED_IPS.remove(&client_ip);
                }
            }

            // 3. Automated scanner User-Agent guard
            let ua = req
                .headers()
                .get("user-agent")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_lowercase();

            if !local_ip {
                for pattern in SUSPICIOUS_AGENTS {
                    if ua.contains(pattern) {
                        let reason = format!("Automated crawler signature ({})", pattern);
                        BANNED_IPS.insert(client_ip.clone(), (Instant::now(), reason.clone()));
                        let res = XinError::Forbidden(reason)
                            .into_http_response(is_api, Some(&config.shared_dir));
                        return Box::pin(async move {
                            Ok(req.into_response(res).map_into_right_body())
                        });
                    }
                }
            }

            // 4. Calibrated flood control (allows dual-device polling behind NAT)
            let now = Instant::now();
            let limit = if path.starts_with("/api/signaling/") {
                config.rate_limit_max * 2
            } else {
                config.rate_limit_max
            };

            let mut over_limit = false;
            {
                let mut records = RATE_LIMITER.entry(client_ip.clone()).or_default();
                records.retain(|t| now.duration_since(*t).as_secs() < config.rate_limit_window_secs);
                records.push(now);
                if records.len() > limit {
                    over_limit = true;
                }
            }

            if RATE_LIMITER.len() > 4096 {
                let win = config.rate_limit_window_secs;
                RATE_LIMITER.retain(|_, v| {
                    v.last()
                        .map(|t| now.duration_since(*t).as_secs() <= win)
                        .unwrap_or(false)
                });
            }

            if over_limit && !local_ip {
                BANNED_IPS.insert(
                    client_ip.clone(),
                    (Instant::now(), "Rate limit threshold exceeded".to_string()),
                );
                let res = XinError::RateLimitExceeded
                    .into_http_response(is_api, Some(&config.shared_dir));
                return Box::pin(async move {
                    Ok(req.into_response(res).map_into_right_body())
                });
            }

            // 5. Regional geofencing (headers / private subnet only; zero query-param bypass)
            let country = resolve_country(&req, &client_ip);
            if !config.allowed_regions.contains(&country) {
                let res = XinError::GeoRestricted { region: country }
                    .into_http_response(is_api, Some(&config.shared_dir));
                return Box::pin(async move {
                    Ok(req.into_response(res).map_into_right_body())
                });
            }
        }

        let fut = self.service.call(req);
        Box::pin(async move {
            let mut res = fut.await?;
            apply_security_headers(&mut res);
            Ok(res.map_into_left_body())
        })
    }
}

fn apply_security_headers<B>(res: &mut ServiceResponse<B>) {
    let headers = res.headers_mut();
    let pairs = [
        ("cache-control", "no-store, no-cache, must-revalidate, max-age=0"),
        ("pragma", "no-cache"),
        ("expires", "0"),
        ("x-content-type-options", "nosniff"),
        ("x-frame-options", "DENY"),
        ("referrer-policy", "no-referrer"),
        ("permissions-policy", "camera=(self), microphone=(self)"),
        (
            "content-security-policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' ws: wss:; media-src 'self' blob: mediastream:;",
        ),
    ];

    for (name, val) in pairs {
        if let (Ok(hn), Ok(hv)) = (
            HeaderName::from_bytes(name.as_bytes()),
            HeaderValue::from_str(val),
        ) {
            headers.insert(hn, hv);
        }
    }
}

pub fn extract_client_ip(req: &ServiceRequest) -> String {
    if let Some(cf_ip) = req.headers().get("cf-connecting-ip") {
        if let Ok(ip) = cf_ip.to_str() {
            let trimmed = ip.split(',').next().unwrap_or(ip).trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
    }
    if let Some(xff) = req.headers().get("x-forwarded-for") {
        if let Ok(ip) = xff.to_str() {
            let trimmed = ip.split(',').next().unwrap_or(ip).trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
    }
    req.peer_addr()
        .map(|addr| addr.ip().to_string())
        .unwrap_or_else(|| "127.0.0.1".to_string())
}

pub fn is_private_or_loopback(ip: &str) -> bool {
    if ip == "127.0.0.1"
        || ip == "localhost"
        || ip == "::1"
        || ip.starts_with("192.168.")
        || ip.starts_with("10.")
    {
        return true;
    }
    if let Some(rest) = ip.strip_prefix("172.") {
        if let Some(second_octet) = rest.split('.').next() {
            if let Ok(n) = second_octet.parse::<u8>() {
                return (16..=31).contains(&n);
            }
        }
    }
    false
}

fn resolve_country(req: &ServiceRequest, client_ip: &str) -> String {
    for header in ["cf-ipcountry", "cloudfront-viewer-country", "x-country-code"] {
        if let Some(val) = req.headers().get(header) {
            if let Ok(raw) = val.to_str() {
                let code: String = raw.trim().to_uppercase().chars().take(8).collect();
                if !code.is_empty() && code != "XX" {
                    return code;
                }
            }
        }
    }
    if is_private_or_loopback(client_ip) {
        return "KE".to_string();
    }
    "UNKNOWN".to_string()
}

pub fn banned_ip_count() -> usize {
    BANNED_IPS.len()
}

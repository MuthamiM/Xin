//! Xin WebSocket & REST Signaling Controller with Typed Rust Error Handling.

use actix_web::{web, HttpRequest, HttpResponse};
use actix_ws::Message;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use uuid::Uuid;

use crate::config::XinConfig;
use crate::error::XinError;
use crate::matchmaker::MatchmakerState;
use crate::middleware::banned_ip_count;
use crate::types::{is_allowed_event, sanitize_id, sanitize_text, validate_user_id, OutgoingMessage};

fn parse_json_bytes(bytes: &[u8]) -> Result<serde_json::Value, XinError> {
    serde_json::from_slice::<serde_json::Value>(bytes)
        .map_err(|_| XinError::BadRequest("Invalid JSON request body".to_string()))
}

pub async fn ws_signal(
    req: HttpRequest,
    stream: web::Payload,
    state: web::Data<Arc<MatchmakerState>>,
) -> Result<HttpResponse, XinError> {
    let (response, mut session, mut msg_stream) = actix_ws::handle(&req, stream)
        .map_err(|e| XinError::BadRequest(format!("WebSocket upgrade failed: {}", e)))?;

    let state = state.into_inner();
    let ws_id = Uuid::new_v4();

    actix_rt::spawn(async move {
        let (tx, mut rx) = mpsc::unbounded_channel::<serde_json::Value>();
        let mut user_id: Option<String> = None;

        let mut out_session = session.clone();
        let outbound = actix_rt::spawn(async move {
            while let Some(msg_val) = rx.recv().await {
                if let Ok(txt) = serde_json::to_string(&msg_val) {
                    if out_session.text(txt).await.is_err() {
                        break;
                    }
                }
            }
        });

        while let Some(Ok(msg)) = msg_stream.recv().await {
            match msg {
                Message::Text(text) => {
                    let payload: serde_json::Value = match serde_json::from_str(&text) {
                        Ok(v) => v,
                        Err(_) => continue,
                    };

                    let msg_type = payload
                        .get("type")
                        .or_else(|| payload.get("action"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("");

                    if user_id.is_none() {
                        match validate_user_id(payload.get("user_id").and_then(|v| v.as_str()), "user_id") {
                            Ok(uid) => {
                                state.register(&uid, Some(ws_id), Some(tx.clone()));
                                user_id = Some(uid.clone());

                                let reg = serde_json::json!({
                                    "type": "registered",
                                    "user_id": uid,
                                    "message": "WebRTC signaling socket connected."
                                });
                                let _ = session.text(reg.to_string()).await;

                                if msg_type == "join" || payload.get("action").and_then(|v| v.as_str()) == Some("join") {
                                    state.find_match(&uid);
                                }
                            }
                            Err(_) => {
                                let _ = session.close(None).await;
                                break;
                            }
                        }
                        continue;
                    }

                    let Some(ref uid) = user_id else { continue };
                    state.touch(uid);

                    match msg_type {
                        "join" | "next" => {
                            state.find_match(uid);
                        }
                        "leave" => {
                            state.remove_user(uid, true);
                        }
                        "ping" => {
                            let pong = state.heartbeat(uid);
                            let _ = session.text(pong.to_string()).await;
                        }
                        "signal" => {
                            let target = payload.get("target_id").and_then(|v| v.as_str()).map(sanitize_id).unwrap_or_default();
                            if let Some(data) = payload.get("data") {
                                if let Some(resolved) = state.resolve_target(uid, &target) {
                                    state.send_to_user(&resolved, OutgoingMessage::signal(uid, data.clone()));
                                }
                            }
                        }
                        "chat" => {
                            let target = payload.get("target_id").and_then(|v| v.as_str()).map(sanitize_id).unwrap_or_default();
                            let user_name = sanitize_text(
                                payload.get("user").and_then(|v| v.as_str()).unwrap_or("Stranger"),
                                48,
                            );
                            let txt = sanitize_text(
                                payload.get("text").and_then(|v| v.as_str()).unwrap_or(""),
                                2000,
                            );
                            if !txt.is_empty() {
                                if let Some(resolved) = state.resolve_target(uid, &target) {
                                    state.send_to_user(&resolved, OutgoingMessage::chat(uid, &user_name, &txt));
                                }
                            }
                        }
                        evt if is_allowed_event(evt) => {
                            let target = payload.get("target_id").and_then(|v| v.as_str()).map(sanitize_id).unwrap_or_default();
                            if let Some(resolved) = state.resolve_target(uid, &target) {
                                state.send_to_user(&resolved, OutgoingMessage::event(evt, uid));
                            }
                        }
                        _ => {}
                    }
                }
                Message::Ping(bytes) => {
                    let _ = session.pong(&bytes).await;
                }
                Message::Close(_) => break,
                _ => {}
            }
        }

        if let Some(ref uid) = user_id {
            state.detach_ws(uid, ws_id);
        }
        outbound.abort();
    });

    Ok(response)
}

pub async fn api_join(
    state: web::Data<Arc<MatchmakerState>>,
    body: web::Bytes,
) -> Result<HttpResponse, XinError> {
    let payload = parse_json_bytes(&body)?;
    let uid = validate_user_id(payload.get("user_id").and_then(|v| v.as_str()), "user_id")?;
    state.register(&uid, None, None);
    let result = state.find_match(&uid);
    Ok(HttpResponse::Ok().json(result))
}

pub async fn api_poll(
    state: web::Data<Arc<MatchmakerState>>,
    query: web::Query<HashMap<String, String>>,
) -> Result<HttpResponse, XinError> {
    let uid = validate_user_id(query.get("user_id").map(|s| s.as_str()), "user_id")?;
    state.register(&uid, None, None);
    let msgs = state.poll_messages(&uid);
    Ok(HttpResponse::Ok().json(serde_json::json!({ "messages": msgs })))
}

pub async fn api_signal(
    state: web::Data<Arc<MatchmakerState>>,
    body: web::Bytes,
) -> Result<HttpResponse, XinError> {
    let payload = parse_json_bytes(&body)?;
    let sender = validate_user_id(payload.get("sender_id").and_then(|v| v.as_str()), "sender_id")?;
    let target = payload.get("target_id").and_then(|v| v.as_str()).map(sanitize_id).unwrap_or_default();
    let data = payload
        .get("data")
        .ok_or_else(|| XinError::BadRequest("Missing signal data".to_string()))?;

    state.touch(&sender);
    let delivered = if let Some(resolved) = state.resolve_target(&sender, &target) {
        state.send_to_user(&resolved, OutgoingMessage::signal(&sender, data.clone()));
        true
    } else {
        false
    };
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "status": if delivered { "delivered" } else { "not_routed" }
    })))
}

pub async fn api_event(
    state: web::Data<Arc<MatchmakerState>>,
    body: web::Bytes,
) -> Result<HttpResponse, XinError> {
    let payload = parse_json_bytes(&body)?;
    let sender = validate_user_id(payload.get("sender_id").and_then(|v| v.as_str()), "sender_id")?;
    let target = payload.get("target_id").and_then(|v| v.as_str()).map(sanitize_id).unwrap_or_default();
    let event_type = payload
        .get("type")
        .and_then(|v| v.as_str())
        .ok_or_else(|| XinError::BadRequest("Missing event type".to_string()))?;

    if !is_allowed_event(event_type) {
        return Err(XinError::BadRequest(format!("Unsupported event type: {}", event_type)));
    }

    state.touch(&sender);
    let delivered = if let Some(resolved) = state.resolve_target(&sender, &target) {
        state.send_to_user(&resolved, OutgoingMessage::event(event_type, &sender));
        true
    } else {
        false
    };
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "status": if delivered { "delivered" } else { "not_routed" }
    })))
}

pub async fn api_chat(
    state: web::Data<Arc<MatchmakerState>>,
    body: web::Bytes,
) -> Result<HttpResponse, XinError> {
    let payload = parse_json_bytes(&body)?;
    let sender = validate_user_id(payload.get("sender_id").and_then(|v| v.as_str()), "sender_id")?;
    let target = payload.get("target_id").and_then(|v| v.as_str()).map(sanitize_id).unwrap_or_default();
    let user_name = sanitize_text(
        payload.get("user").and_then(|v| v.as_str()).unwrap_or("Stranger"),
        48,
    );
    let text = sanitize_text(
        payload.get("text").and_then(|v| v.as_str()).unwrap_or(""),
        2000,
    );
    if text.is_empty() {
        return Err(XinError::BadRequest("Empty chat text payload".to_string()));
    }

    state.touch(&sender);
    let delivered = if let Some(resolved) = state.resolve_target(&sender, &target) {
        state.send_to_user(&resolved, OutgoingMessage::chat(&sender, &user_name, &text));
        true
    } else {
        false
    };
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "status": if delivered { "delivered" } else { "not_routed" }
    })))
}

pub async fn api_next(
    state: web::Data<Arc<MatchmakerState>>,
    body: web::Bytes,
) -> Result<HttpResponse, XinError> {
    let payload = parse_json_bytes(&body)?;
    let uid = validate_user_id(payload.get("user_id").and_then(|v| v.as_str()), "user_id")?;
    state.register(&uid, None, None);
    let result = state.find_match(&uid);
    Ok(HttpResponse::Ok().json(result))
}

pub async fn api_leave(
    state: web::Data<Arc<MatchmakerState>>,
    body: web::Bytes,
) -> Result<HttpResponse, XinError> {
    // Accepts both navigator.sendBeacon (text/plain) and application/json cleanly
    let payload = parse_json_bytes(&body)?;
    let uid = validate_user_id(payload.get("user_id").and_then(|v| v.as_str()), "user_id")?;
    state.remove_user(&uid, true);
    Ok(HttpResponse::Ok().json(serde_json::json!({ "status": "disconnected" })))
}

pub async fn api_status(
    state: web::Data<Arc<MatchmakerState>>,
    config: web::Data<Arc<XinConfig>>,
    start_time: web::Data<std::time::Instant>,
) -> HttpResponse {
    HttpResponse::Ok().json(serde_json::json!({
        "platform": config.platform_name,
        "engine": "Rust/Actix-Web",
        "status": "ONLINE",
        "active_banned_ips": banned_ip_count(),
        "allowed_regions_count": config.allowed_regions.len(),
        "signaling": state.diagnostics(),
        "uptime_seconds": start_time.elapsed().as_secs()
    }))
}

pub async fn api_stats(state: web::Data<Arc<MatchmakerState>>) -> HttpResponse {
    HttpResponse::Ok().json(state.diagnostics())
}

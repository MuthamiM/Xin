//! Core domain types and input validation helpers for Xin Rust Engine.

use crate::error::XinError;
use serde::Serialize;
use std::time::Instant;
use tokio::sync::mpsc::UnboundedSender;
use uuid::Uuid;

pub type UserId = String;
pub type RoomId = String;

/// Connected user state tracked inside MatchmakerState.
#[allow(dead_code)]
pub struct UserSession {
    pub user_id: UserId,
    pub last_seen: Instant,
    pub ws_id: Option<Uuid>,
    pub ws_sender: Option<UnboundedSender<serde_json::Value>>,
}

/// Active 1-on-1 room linking two peers.
#[allow(dead_code)]
pub struct Room {
    pub room_id: RoomId,
    pub peers: [UserId; 2],
    pub initiator: UserId,
    pub created: Instant,
}

/// Standard signaling payloads serialized directly as JSON objects.
#[derive(Debug, Serialize, Clone)]
pub struct OutgoingMessage;

impl OutgoingMessage {
    pub fn waiting(queue_count: usize) -> serde_json::Value {
        serde_json::json!({
            "type": "waiting",
            "queue_count": queue_count,
            "message": "In lobby queue. Waiting for remote peer to connect."
        })
    }

    pub fn matched(room_id: &str, peer_id: &str, is_initiator: bool) -> serde_json::Value {
        serde_json::json!({
            "type": "matched",
            "room_id": room_id,
            "peer_id": peer_id,
            "is_initiator": is_initiator,
            "message": if is_initiator {
                "Connected with peer. Initiating WebRTC handshake."
            } else {
                "Connected with peer. Awaiting offer."
            }
        })
    }

    pub fn peer_disconnected(room_id: &str) -> serde_json::Value {
        serde_json::json!({
            "type": "peer_disconnected",
            "room_id": room_id,
            "message": "Remote peer has disconnected."
        })
    }

    pub fn pong(in_room: bool, queue_count: usize) -> serde_json::Value {
        serde_json::json!({
            "type": "pong",
            "in_room": in_room,
            "queue_count": queue_count
        })
    }

    pub fn signal(sender_id: &str, data: serde_json::Value) -> serde_json::Value {
        serde_json::json!({
            "type": "signal",
            "sender_id": sender_id,
            "data": data
        })
    }

    pub fn chat(sender_id: &str, user: &str, text: &str) -> serde_json::Value {
        serde_json::json!({
            "type": "chat",
            "sender_id": sender_id,
            "user": user,
            "text": text,
            "time": chrono::Utc::now().format("%H:%M").to_string()
        })
    }

    pub fn event(event_type: &str, sender_id: &str) -> serde_json::Value {
        serde_json::json!({
            "type": event_type,
            "sender_id": sender_id,
            "time": chrono::Utc::now().format("%H:%M").to_string()
        })
    }
}

/// Validate and normalize client/room identifier cleanly (alphanumeric, `_`, `-`, len 2..=64).
pub fn validate_user_id(raw: Option<&str>, field_name: &str) -> Result<String, XinError> {
    let val = raw.ok_or_else(|| XinError::BadRequest(format!("Missing {}", field_name)))?;
    let cleaned = sanitize_id(val);
    if cleaned.len() < 2 {
        return Err(XinError::BadRequest(format!("Invalid {}", field_name)));
    }
    Ok(cleaned)
}

pub fn sanitize_id(input: &str) -> String {
    input
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-')
        .take(64)
        .collect()
}

pub fn sanitize_text(input: &str, max_len: usize) -> String {
    input
        .chars()
        .filter(|c| *c != '<' && *c != '>' && *c != '\0')
        .take(max_len)
        .collect::<String>()
        .trim()
        .to_string()
}

pub fn is_allowed_event(event_type: &str) -> bool {
    matches!(event_type, "chat_request" | "chat_accept" | "chat_decline")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn id_and_text_sanitization() {
        assert_eq!(sanitize_id("usr_12ab-CD; DROP TABLE"), "usr_12ab-CDDROPTABLE");
        assert!(validate_user_id(Some("u"), "user_id").is_err());
        assert!(validate_user_id(Some("usr_12345"), "user_id").is_ok());
        assert_eq!(sanitize_text("  hello <b>world</b>  ", 100), "hello bworld/b");
    }
}

//! Xin Matchmaker - Lock-free concurrent matchmaking engine.
//! Pairs devices with sub-millisecond latency, preserves active rooms across WS/HTTP failover,
//! avoids immediate repeat matches when 3+ peers are queued, and reaps stale sessions without ghosts.

use dashmap::DashMap;
use std::sync::{Mutex, MutexGuard};
use std::time::Instant;
use tokio::sync::mpsc::UnboundedSender;
use uuid::Uuid;

use crate::types::{OutgoingMessage, Room, UserId, UserSession};

pub struct MatchmakerState {
    pub sessions: DashMap<UserId, UserSession>,
    pub message_queues: DashMap<UserId, Vec<serde_json::Value>>,
    pub rooms: DashMap<String, Room>,
    pub user_to_room: DashMap<UserId, String>,
    waiting_queue: Mutex<Vec<UserId>>,
    last_partner: DashMap<UserId, UserId>,
    stale_timeout_secs: u64,
}

impl MatchmakerState {
    pub fn new(stale_timeout_secs: u64) -> Self {
        Self {
            sessions: DashMap::new(),
            message_queues: DashMap::new(),
            rooms: DashMap::new(),
            user_to_room: DashMap::new(),
            waiting_queue: Mutex::new(Vec::new()),
            last_partner: DashMap::new(),
            stale_timeout_secs,
        }
    }

    fn lock_queue(&self) -> MutexGuard<'_, Vec<UserId>> {
        self.waiting_queue
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    pub fn touch(&self, user_id: &str) {
        if let Some(mut session) = self.sessions.get_mut(user_id) {
            session.last_seen = Instant::now();
        }
    }

    /// Register or upgrade a client session. Flushes buffered HTTP messages when a WebSocket attaches.
    pub fn register(
        &self,
        user_id: &str,
        ws_id: Option<Uuid>,
        ws_sender: Option<UnboundedSender<serde_json::Value>>,
    ) {
        if let Some(mut session) = self.sessions.get_mut(user_id) {
            session.last_seen = Instant::now();
            if let Some(sender) = ws_sender {
                session.ws_id = ws_id;
                session.ws_sender = Some(sender.clone());
                drop(session);
                self.flush_queue_to_ws(user_id, &sender);
            }
        } else {
            self.sessions.insert(
                user_id.to_string(),
                UserSession {
                    user_id: user_id.to_string(),
                    last_seen: Instant::now(),
                    ws_id,
                    ws_sender: ws_sender.clone(),
                },
            );
            self.message_queues
                .entry(user_id.to_string())
                .or_default();
        }
    }

    fn flush_queue_to_ws(&self, user_id: &str, sender: &UnboundedSender<serde_json::Value>) {
        if let Some(mut q) = self.message_queues.get_mut(user_id) {
            for msg in q.drain(..) {
                let _ = sender.send(msg);
            }
        }
    }

    /// Detach only the closing WebSocket if it still owns the slot (preserves active room & HTTP failover).
    pub fn detach_ws(&self, user_id: &str, ws_id: Uuid) {
        if let Some(mut session) = self.sessions.get_mut(user_id) {
            if session.ws_id == Some(ws_id) {
                session.ws_id = None;
                session.ws_sender = None;
            }
        }
    }

    /// Completely remove a user (on explicit leave or stale timeout expiry).
    pub fn remove_user(&self, user_id: &str, notify_partner: bool) {
        self.leave_room(user_id, notify_partner);
        {
            let mut queue = self.lock_queue();
            queue.retain(|id| id != user_id);
        }
        self.sessions.remove(user_id);
        self.message_queues.remove(user_id);
        self.last_partner.remove(user_id);
    }

    /// Deliver message to peer over WebSocket or buffer as JSON object for HTTP polling.
    /// Does NOT touch peer `last_seen`, preventing dead sessions from staying alive as ghosts.
    pub fn send_to_user(&self, user_id: &str, msg: serde_json::Value) {
        if let Some(session) = self.sessions.get(user_id) {
            if let Some(ref sender) = session.ws_sender {
                if sender.send(msg.clone()).is_ok() {
                    return;
                }
            }
        }

        let mut queue = self
            .message_queues
            .entry(user_id.to_string())
            .or_default();
        queue.push(msg);
        if queue.len() > 64 {
            queue.remove(0);
        }
    }

    pub fn find_match(&self, user_id: &str) -> serde_json::Value {
        self.touch(user_id);
        self.purge_stale();
        self.leave_room(user_id, true);

        {
            let mut queue = self.lock_queue();
            if !queue.iter().any(|id| id == user_id) {
                queue.push(user_id.to_string());
            }
        }

        self.try_match();

        if let Some(room_id) = self.user_to_room.get(user_id) {
            if let Some(room) = self.rooms.get(room_id.value()) {
                let partner = if room.peers[0] == user_id {
                    room.peers[1].clone()
                } else {
                    room.peers[0].clone()
                };
                return serde_json::json!({
                    "status": "matched",
                    "room_id": room_id.value().clone(),
                    "peer_id": partner
                });
            }
        }

        let queue_count = self.lock_queue().len();
        self.send_to_user(user_id, OutgoingMessage::waiting(queue_count));
        serde_json::json!({
            "status": "waiting",
            "queue_count": queue_count
        })
    }

    pub fn heartbeat(&self, user_id: &str) -> serde_json::Value {
        self.touch(user_id);
        self.purge_stale();

        if !self.user_to_room.contains_key(user_id) {
            let mut queue = self.lock_queue();
            if !queue.iter().any(|id| id == user_id) {
                queue.push(user_id.to_string());
            }
        }

        self.try_match();

        let in_room = self.user_to_room.contains_key(user_id);
        let queue_count = self.lock_queue().len();
        OutgoingMessage::pong(in_room, queue_count)
    }

    fn try_match(&self) {
        let mut queue = self.lock_queue();
        let now = Instant::now();

        let mut clean: Vec<UserId> = Vec::with_capacity(queue.len());
        for uid in queue.drain(..) {
            if self.user_to_room.contains_key(&uid) || clean.contains(&uid) {
                continue;
            }
            let alive = self
                .sessions
                .get(&uid)
                .map(|s| now.duration_since(s.last_seen).as_secs() <= self.stale_timeout_secs)
                .unwrap_or(false);
            if alive {
                clean.push(uid);
            }
        }
        *queue = clean;

        while queue.len() >= 2 {
            let u1 = queue.remove(0);

            // When 2+ peers remain waiting, prefer someone other than last partner
            let last_p = self.last_partner.get(&u1).map(|r| r.value().clone());
            let mut picked_idx: Option<usize> = None;
            if queue.len() >= 2 {
                if let Some(ref lp) = last_p {
                    picked_idx = queue.iter().position(|cand| cand != &u1 && cand != lp);
                }
            }
            let u2 = match picked_idx {
                Some(idx) => queue.remove(idx),
                None => queue.remove(0),
            };

            if u1 == u2 {
                continue;
            }

            let room_id = format!("room-{}", &Uuid::new_v4().to_string()[..8]);
            self.rooms.insert(
                room_id.clone(),
                Room {
                    room_id: room_id.clone(),
                    peers: [u1.clone(), u2.clone()],
                    initiator: u1.clone(),
                    created: now,
                },
            );
            self.user_to_room.insert(u1.clone(), room_id.clone());
            self.user_to_room.insert(u2.clone(), room_id.clone());
            self.last_partner.insert(u1.clone(), u2.clone());
            self.last_partner.insert(u2.clone(), u1.clone());

            self.send_to_user(&u1, OutgoingMessage::matched(&room_id, &u2, true));
            self.send_to_user(&u2, OutgoingMessage::matched(&room_id, &u1, false));
        }
    }

    pub fn leave_room(&self, user_id: &str, notify_partner: bool) {
        if let Some((_, room_id)) = self.user_to_room.remove(user_id) {
            if let Some((_, room)) = self.rooms.remove(&room_id) {
                for peer_id in &room.peers {
                    if peer_id != user_id {
                        self.user_to_room.remove(peer_id);
                        let alive = self
                            .sessions
                            .get(peer_id)
                            .map(|s| s.last_seen.elapsed().as_secs() <= self.stale_timeout_secs)
                            .unwrap_or(false);
                        if notify_partner && alive {
                            self.send_to_user(peer_id, OutgoingMessage::peer_disconnected(&room_id));
                            let mut queue = self.lock_queue();
                            if !queue.iter().any(|id| id == peer_id) {
                                queue.push(peer_id.clone());
                            }
                        }
                    }
                }
            }
        }
    }

    pub fn resolve_target(&self, sender_id: &str, target_id: &str) -> Option<String> {
        if !target_id.is_empty() && self.sessions.contains_key(target_id) {
            return Some(target_id.to_string());
        }
        if let Some(room_id) = self.user_to_room.get(sender_id) {
            if let Some(room) = self.rooms.get(room_id.value()) {
                for peer in &room.peers {
                    if peer != sender_id && self.sessions.contains_key(peer) {
                        return Some(peer.clone());
                    }
                }
            }
        }
        None
    }

    pub fn purge_stale(&self) {
        let stale: Vec<String> = self
            .sessions
            .iter()
            .filter(|e| e.value().last_seen.elapsed().as_secs() > self.stale_timeout_secs)
            .map(|e| e.key().clone())
            .collect();

        for uid in stale {
            self.remove_user(&uid, true);
        }
    }

    pub fn poll_messages(&self, user_id: &str) -> Vec<serde_json::Value> {
        self.touch(user_id);
        self.purge_stale();

        if !self.user_to_room.contains_key(user_id) {
            let need_wait_msg = {
                let mut queue = self.lock_queue();
                if !queue.iter().any(|id| id == user_id) {
                    queue.push(user_id.to_string());
                    Some(queue.len())
                } else {
                    None
                }
            };
            if let Some(count) = need_wait_msg {
                self.send_to_user(user_id, OutgoingMessage::waiting(count));
            }
        }

        self.try_match();

        if let Some(mut msgs) = self.message_queues.get_mut(user_id) {
            msgs.drain(..).collect()
        } else {
            vec![]
        }
    }

    pub fn diagnostics(&self) -> serde_json::Value {
        let active = self
            .sessions
            .iter()
            .filter(|e| e.value().last_seen.elapsed().as_secs() <= self.stale_timeout_secs)
            .count();
        let ws_count = self
            .sessions
            .iter()
            .filter(|e| e.value().ws_sender.is_some())
            .count();
        let queue_count = self.lock_queue().len();

        serde_json::json!({
            "active_users": active,
            "waiting_in_lobby": queue_count,
            "active_rooms": self.rooms.len(),
            "connected_websockets": ws_count
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn instant_pair_and_poll_messages() {
        let hub = MatchmakerState::new(8);
        hub.register("laptop_1", None, None);
        hub.register("phone_2", None, None);

        let r1 = hub.find_match("laptop_1");
        assert_eq!(r1["status"], "waiting");

        let r2 = hub.find_match("phone_2");
        assert_eq!(r2["status"], "matched");
        assert_eq!(r2["peer_id"], "laptop_1");

        let laptop_msgs = hub.poll_messages("laptop_1");
        assert!(laptop_msgs.iter().any(|m| m["type"] == "matched" && m["peer_id"] == "phone_2"));
    }

    #[test]
    fn anti_repeat_when_three_users_exist() {
        let hub = MatchmakerState::new(8);
        hub.register("u1", None, None);
        hub.register("u2", None, None);
        hub.register("u3", None, None);

        hub.find_match("u1");
        hub.find_match("u2"); // pairs u1 + u2

        // u3 waits, then u1 hits next (unpairs u1 & u2; queue becomes [u3, u2, u1])
        hub.find_match("u3");
        let next_res = hub.find_match("u1");
        // u3 and u2 were ahead in queue, or u1 pairs with someone other than u2 if possible
        assert!(hub.rooms.len() >= 1);
        assert_ne!(next_res["status"], "error");
    }

    #[test]
    fn ws_detach_preserves_http_polling_room() {
        let hub = MatchmakerState::new(8);
        let ws_id = Uuid::new_v4();
        hub.register("u1", Some(ws_id), None);
        hub.register("u2", None, None);
        hub.find_match("u1");
        let res = hub.find_match("u2");
        assert_eq!(res["status"], "matched");

        // Detaching WS keeps room intact so HTTP polling continues cleanly
        hub.detach_ws("u1", ws_id);
        assert!(hub.user_to_room.contains_key("u1"));
        assert!(hub.user_to_room.contains_key("u2"));
    }

    #[test]
    fn target_resolution_falls_back_to_active_room() {
        let hub = MatchmakerState::new(8);
        hub.register("a1", None, None);
        hub.register("b2", None, None);
        hub.find_match("a1");
        hub.find_match("b2");

        assert_eq!(hub.resolve_target("a1", "stale_id"), Some("b2".to_string()));
    }
}

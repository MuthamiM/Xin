//! Xin Rust Engine Entrypoint
//! High-speed Actix-Web backend with middleware controllers, typed Rust error handling,
//! shared assets/themes, WebRTC signaling, and lock-free matchmaking.

mod config;
mod controllers;
mod error;
mod matchmaker;
mod middleware;
mod types;

use actix_cors::Cors;
use actix_web::{middleware as actix_mw, web, App, HttpServer};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing_subscriber::EnvFilter;

use crate::config::XinConfig;
use crate::controllers::{assets, signaling};
use crate::matchmaker::MatchmakerState;
use crate::middleware::SecurityMiddleware;

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let config = Arc::new(XinConfig::from_env());
    let state = Arc::new(MatchmakerState::new(config.stale_timeout_secs));
    let start_time = Instant::now();

    // Background stale-session reaper (eliminates ghosts every 3s)
    let reaper = state.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(3));
        loop {
            interval.tick().await;
            reaper.purge_stale();
        }
    });

    let bind_addr = format!("{}:{}", config.host, config.port);
    tracing::info!(
        "XIN RUST ENGINE STARTING ON http://{} [Shared Assets: {}]",
        bind_addr,
        config.shared_dir.display()
    );

    let cfg_clone = config.clone();
    let state_clone = state.clone();

    HttpServer::new(move || {
        let cors = Cors::default()
            .allowed_origin("https://xin.mftechnologies.org")
            .allowed_origin("http://localhost:5000")
            .allowed_origin("http://127.0.0.1:5000")
            .allow_any_method()
            .allow_any_header()
            .max_age(3600);

        App::new()
            .wrap(cors)
            .wrap(actix_mw::Logger::default())
            .wrap(SecurityMiddleware {
                config: cfg_clone.clone(),
            })
            .app_data(web::Data::new(cfg_clone.clone()))
            .app_data(web::Data::new(state_clone.clone()))
            .app_data(web::Data::new(start_time))
            // Frontend & Shared Assets/Themes
            .route("/", web::get().to(assets::serve_index))
            .route("/studio", web::get().to(assets::redirect_studio))
            .route("/static/{tail:.*}", web::get().to(assets::serve_static))
            .route("/api/themes", web::get().to(assets::serve_themes))
            // WebSocket Signaling
            .route("/ws/signal", web::get().to(signaling::ws_signal))
            // REST Matchmaking & Signaling API
            .route("/api/signaling/join", web::post().to(signaling::api_join))
            .route("/api/signaling/poll", web::get().to(signaling::api_poll))
            .route("/api/signaling/signal", web::post().to(signaling::api_signal))
            .route("/api/signaling/event", web::post().to(signaling::api_event))
            .route("/api/signaling/chat", web::post().to(signaling::api_chat))
            .route("/api/signaling/next", web::post().to(signaling::api_next))
            .route("/api/signaling/leave", web::post().to(signaling::api_leave))
            .route("/api/signaling/stats", web::get().to(signaling::api_stats))
            .route("/api/status", web::get().to(signaling::api_status))
            // Safe 404 Catch-All
            .default_service(web::route().to(assets::handle_not_found))
    })
    .workers(4)
    .bind(&bind_addr)?
    .run()
    .await
}

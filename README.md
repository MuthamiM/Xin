# Xin - 1-on-1 Live Video Platform

Real-time WebRTC audio and video streaming platform for instant peer-to-peer calls.
Built with a dual **Rust (Actix-Web)** + **Python (Flask)** architecture with typed error handling, middleware controllers, shared themes/assets, security hardening, and sub-millisecond matchmaking.

## Architecture

```
Xin/
  core/                    Python Flask app factory and config
  features/
    signaling/             WebRTC signaling hub and routes (Python)
    security/              Middleware, VPN/agent guard, geofence, error handlers
    chat/                  REST chat service
    streaming/             MJPEG streaming engine
  shared/
    templates/
      index.html           1-on-1 WebRTC video/audio & message-request client
      errors/error.html    Shared themed HTML error view
    static/
      css/themes.css       Shared theme CSS variables (Electric Blue default)
      js/xin_shared.js     Shared theme switcher & client-side sanitization
  rust_engine/             High-performance Rust server (Actix-Web + Tokio)
    src/
      main.rs              HTTP/WebSocket server, CORS, reaper task
      config.rs            Runtime configuration, theme catalog, region allowlist
      error.rs             Typed XinError enum (thiserror + IntoResponse + HTML escaping)
      types.rs             Validating ID/text sanitizers & signaling message builders
      matchmaker.rs        Lock-free concurrent matchmaking (DashMap + anti-repeat FIFO)
      middleware.rs        Security headers, flood guard, agent blocker, geofencing
      controllers/
        assets.rs          Path-traversal-safe static asset & template controller
        signaling.rs       WebSocket /ws/signal & REST API handlers
  deploy/                  Docker, Cloudflare Tunnel, nginx configs
  test_xin_webrtc.py       Automated Python test suite
  run.py                   Python server entrypoint
```

## Features

- Real WebRTC `getUserMedia` video and audio across phone and desktop browsers
- Pre-allocated `sendrecv` transceivers, ICE candidate buffering, and glare-free renegotiation
- Lock-free concurrent matchmaking (`DashMap`) with automatic stale-session reaping and anti-repeat pairing
- Two-screen layout: fullscreen caller view + expandable top-right local preview (`YOU` / `STRANGER`)
- 4-button floating dock (`NEXT`, `MIC ON`, `CAM ON`, `CHAT`) with Electric Blue active states
- Message request workflow supporting accept/decline in both the top banner and chat drawer
- Shared static assets, theme catalog (`/api/themes`), and themed HTML/JSON error responses
- Security hardening: CSP, `X-Frame-Options: DENY`, `nosniff`, payload caps (64 KB), NAT-safe rate limiting, scanner UA blocking, and trusted-header geofencing

## Running

### Rust Server (Recommended, port 5000)
```bash
cd rust_engine
cargo test
cargo build --release
./target/release/xin-engine
```

### Python Fallback Server (port 5000)
```bash
pip install -r requirements.txt
python test_xin_webrtc.py
python run.py
```

### Cloudflare Tunnel
```bash
cloudflared tunnel run --url http://127.0.0.1:5000 xin-tunnel
```

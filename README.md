# Xin - 1-on-1 Real-Time Streaming Platform
Omegle-style video platform with feature-first architecture, geofencing, VPN detection, and subsea cable routing between East Africa, South Africa, and Asia.

## Features
- Omegle-style split-screen: Stranger remote stream (phone camera / RTSP / WebRTC) + local laptop webcam.
- Zero emojis across all UI, templates, logs, and controllers.
- Security Middleware:
  - Automated VPN / proxy detection with temporary 15-minute IP bans.
  - Regional geofencing strictly allowing East Africa, South Africa, and Asia.
  - Rate limiting & flood protection (80 req/min).
  - Custom error handling for HTTP 400, 403, 404, 429, 500.
- Scalable to 1,000 concurrent streams via MediaMTX + NGINX microcaching.

## Project Structure (Feature-First)
```
Xin/
├── core/
│   ├── config.py
│   └── app.py
├── features/
│   ├── security/
│   │   ├── middleware.py
│   │   ├── vpn_detector.py
│   │   ├── geofence.py
│   │   └── error_handlers.py
│   ├── streaming/
│   │   ├── engine.py
│   │   └── routes.py
│   ├── chat/
│   │   ├── service.py
│   │   └── routes.py
│   └── studio/
├── shared/
│   ├── templates/
│   │   ├── index.html
│   │   └── studio.html
│   └── static/
├── deploy/
│   ├── docker-compose.yml
│   ├── mediamtx.yml
│   ├── nginx_edge.conf
│   ├── Dockerfile
│   └── SCALING_ARCHITECTURE.md
├── run.py
├── requirements.txt
└── README.md
```

## Quick Start
```bash
python run.py
```
Platform runs at http://localhost:5000.

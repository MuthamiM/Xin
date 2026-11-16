# Xin - High-Throughput Streaming Scaling Architecture
Target: 1,000 Concurrent Live Streams | Zero-Lag WebRTC/LL-HLS | EA, SA & Asia

## 1. Network & Subsea Cable Routing
Xin routes live streams across the Indian Ocean subsea network between East Africa (Mombasa/Nairobi hub), South Africa (Cape Town/Johannesburg hub), and Asia (Singapore, Mumbai, Tokyo, Dubai hubs):
- Subsea cables utilized: PEACE Cable, SEA-ME-WE 5, 2Africa, EASSy, SEACOM.
- Latency between Kenya (Mombasa) and India/Singapore: 32ms - 48ms.
- South Africa to Asia direct: 95ms - 110ms.

## 2. Bandwidth Calculus (1,000 Streams)
- **Ingress Bandwidth:**
  - 1,000 streams * 2.5 Mbps (1080p30 H.264 / Opus) = 2.5 Gbps sustained ingress.
- **Egress Bandwidth (Viewer Fan-Out):**
  - Peer-to-peer 1-on-1 mesh: 2.5 Gbps total egress.
  - Broadcast model (100 viewers per stream): 100,000 viewers * 1.5 Mbps = 150 Gbps egress.
  - Handled via MediaMTX edge relays + NGINX RAM microcaching (500ms segments).

## 3. Security Controllers & Geofencing
- **Geofence Policy:** Strictly whitelisted ISO codes:
  - East Africa: KE, TZ, UG, RW, ET, BI, SO, DJ.
  - South Africa: ZA, NA, BW.
  - Asia: IN, SG, MY, ID, TH, VN, PH, JP, KR, HK, TW, CN, PK, BD, LK, AE, SA, QA, OM.
  - All other regions receive HTTP 403 Forbidden.
- **VPN / Proxy Detection:**
  - Inspects HTTP headers (Via, X-Forwarded-For depth, CF-Threat-Score, Tor/crawler User-Agents).
  - Automatically issues a 15-minute temporary IP ban.
- **Flood Control:**
  - Rate limited to 80 requests per minute with automated 5-minute cooldown.
- **Error Handling:**
  - Full middleware interception for HTTP 400, 403, 404, 429, and 500.

## 4. Deployment on Ubuntu
```bash
git clone https://github.com/MuthamiM/Xin.git
cd Xin
pip install -r requirements.txt
python run.py

# Or launch complete 1000-stream cluster via Docker:
cd deploy
docker-compose up -d
```

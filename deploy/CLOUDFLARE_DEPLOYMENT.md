# Hosting Xin on Cloudflare
High-Throughput 1-on-1 Streaming Mesh across East Africa, South Africa, and Asia

## Architecture Overview
When hosting Xin behind Cloudflare:
1. Users connect to Cloudflare Edge (Anycast IP network).
2. Cloudflare automatically handles SSL/TLS termination, DDoS mitigation, and edge caching.
3. Cloudflare injects the user's geographic headers:
   - `CF-IPCountry`: Real ISO country code of visitor.
   - `CF-Connecting-IP`: Visitor client IP address.
   - `CF-Threat-Score`: Anonymizer / bot threat score (0-100).
4. Xin security middleware reads these headers in `features/security/middleware.py`:
   - Validates if country is in the whitelist (East Africa, South Africa, Asia).
   - Blocks all other regions (US, Europe, etc.) with HTTP 403.
   - Scans proxy/VPN threat scores and applies temporary 15-minute IP bans if triggered.

---

## Method 1: Instant Quick Tunnel (No Cloudflare Account Needed)
You can launch an instant public HTTPS tunnel directly from the command line:

### On Windows
```powershell
& "C:\Users\cantroll\.gemini\antigravity\scratch\bin\cloudflared.exe" tunnel --protocol http2 --url http://127.0.0.1:5000
```

### On Ubuntu
```bash
cloudflared tunnel --protocol http2 --url http://127.0.0.1:5000
```
This prints an instant public URL such as `https://<random-id>.trycloudflare.com` with free Cloudflare SSL.

---

## Method 2: Production Named Tunnel with Custom Domain
For a permanent domain (e.g. `xin.yourdomain.com`):

### 1. Authenticate with Cloudflare
```bash
cloudflared tunnel login
```

### 2. Create the Named Tunnel
```bash
cloudflared tunnel create xin-cluster
```
This generates a tunnel UUID and credentials JSON file in `~/.cloudflared/<tunnel-id>.json`.

### 3. Configure DNS Record in Cloudflare
```bash
cloudflared tunnel route dns xin-cluster xin.yourdomain.com
```

### 4. Deploy config.yml
Copy `deploy/cloudflared.yml` to `~/.cloudflared/config.yml` and replace `YOUR_TUNNEL_UUID_HERE` with your tunnel ID.

### 5. Run the Tunnel Service
```bash
cloudflared tunnel run xin-cluster
```

---

## Method 3: Complete Docker Compose Deployment (Ubuntu)
Run the entire platform including MediaMTX, NGINX, Redis, Xin Core, and Cloudflare Tunnel:
```bash
cd Xin/deploy
docker compose up -d
```
All containers start with automatic recovery and health checks.

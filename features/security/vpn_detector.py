import time

SUSPICIOUS_AGENTS = [
    "wget", "python-requests", "scrapy", "nikto", "masscan", "sqlmap"
]

class SecurityController:
    def __init__(self, ban_duration=900, rate_limit=80, rate_window=60):
        self.banned_ips = {}       # ip -> { "expires": timestamp, "reason": str }
        self.request_records = {}   # ip -> [timestamps]
        self.ban_duration = ban_duration
        self.rate_limit = rate_limit
        self.rate_window = rate_window

    def is_banned(self, ip):
        now = time.time()
        if ip in self.banned_ips:
            data = self.banned_ips[ip]
            if now < data["expires"]:
                return True, data
            else:
                del self.banned_ips[ip]
        return False, None

    def apply_temporary_ban(self, ip, duration=None, reason="Security policy violation"):
        dur = duration or self.ban_duration
        expires = time.time() + dur
        self.banned_ips[ip] = {
            "expires": expires,
            "reason": reason,
            "duration": dur
        }
        print(f"[SECURITY] Temporary ban applied to IP {ip} for {dur}s. Reason: {reason}")

    def evaluate_rate_limit(self, ip):
        now = time.time()
        if ip not in self.request_records:
            self.request_records[ip] = []
        self.request_records[ip] = [t for t in self.request_records[ip] if now - t < self.rate_window]
        self.request_records[ip].append(now)

        if len(self.request_records[ip]) > self.rate_limit:
            self.apply_temporary_ban(ip, duration=300, reason="Rate limit threshold exceeded (Flood protection)")
            return False
        return True

    def scan_vpn_proxy(self, request, ip):
        if ip in {"127.0.0.1", "localhost"} or ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
            return False, ""

        # Cloudflare Tunnel passes legitimate edge traffic
        cf_ray = request.headers.get("CF-Ray")
        if not cf_ray:
            via = request.headers.get("Via")
            if via:
                return True, "Proxy header (Via) signature identified"

            fwd = request.headers.get("X-Forwarded-For")
            if fwd and len(fwd.split(",")) > 2:
                return True, "Multi-hop proxy chain identified"

        threat = request.headers.get("CF-Threat-Score")
        if threat:
            try:
                if int(threat) > 30:
                    return True, "Elevated network threat score"
            except ValueError:
                pass

        ua = (request.headers.get("User-Agent") or "").lower()
        for pattern in SUSPICIOUS_AGENTS:
            if pattern in ua:
                return True, f"Automated crawler agent signature ({pattern})"

        return False, ""

import threading
import time

SUSPICIOUS_AGENTS = [
    "wget", "python-requests", "scrapy", "nikto", "masscan", "sqlmap",
    "nmap", "gobuster", "dirbuster", "hydra", "burpsuite"
]


class SecurityController:
    def __init__(self, ban_duration=900, rate_limit=600, rate_window=60):
        self.lock = threading.Lock()
        self.banned_ips = {}       # ip -> { "expires": timestamp, "reason": str }
        self.request_records = {}  # ip -> [timestamps]
        self.ban_duration = ban_duration
        self.rate_limit = rate_limit
        self.rate_window = rate_window

    def _is_local(self, ip: str) -> bool:
        if ip in {"127.0.0.1", "localhost", "::1"} or ip.startswith("192.168.") or ip.startswith("10."):
            return True
        if ip.startswith("172."):
            parts = ip.split(".")
            if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                return True
        return False

    def is_banned(self, ip):
        now = time.time()
        with self.lock:
            if ip in self.banned_ips:
                data = self.banned_ips[ip]
                if now < data["expires"]:
                    return True, dict(data)
                del self.banned_ips[ip]
        return False, None

    def apply_temporary_ban(self, ip, duration=None, reason="Security policy violation"):
        if self._is_local(ip):
            return
        dur = duration or self.ban_duration
        expires = time.time() + dur
        with self.lock:
            self.banned_ips[ip] = {
                "expires": expires,
                "reason": reason,
                "duration": dur
            }
        print(f"[SECURITY] Temporary ban applied to IP {ip} for {dur}s. Reason: {reason}")

    def evaluate_rate_limit(self, ip, path=""):
        now = time.time()
        # High-frequency WebRTC polling & static assets get higher burst limit
        limit = self.rate_limit * 2 if path.startswith(("/api/signaling/", "/static/")) else self.rate_limit

        with self.lock:
            records = self.request_records.get(ip, [])
            records = [t for t in records if now - t < self.rate_window]
            records.append(now)
            self.request_records[ip] = records

            # Prune old keys occasionally to keep memory bounded
            if len(self.request_records) > 2048:
                stale = [k for k, v in self.request_records.items() if not v or (now - v[-1]) > self.rate_window]
                for k in stale:
                    del self.request_records[k]

            over_limit = len(records) > limit

        if over_limit:
            self.apply_temporary_ban(ip, duration=300, reason="Rate limit threshold exceeded (Flood protection)")
            return False
        return True

    def scan_vpn_proxy(self, request, ip):
        if self._is_local(ip):
            return False, ""

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

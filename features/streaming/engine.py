import ssl
import urllib.request
import threading
import time
import os
import cv2
import numpy as np
from core.config import Config

class StreamEngine:
    def __init__(self):
        self.source_mode = "phone"
        self.filter_mode = "none"
        self.lock = threading.Lock()
        self.current_frame = None
        self.running = True
        self.fps = 30
        self.start_time = time.time()

        self.stream_url = Config.PHONE_STREAM_URL
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def set_source(self, src):
        with self.lock:
            self.source_mode = src

    def set_filter(self, flt):
        with self.lock:
            self.filter_mode = flt

    def _apply_fx(self, frame):
        flt = self.filter_mode
        if flt == "cyberpunk":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            neon = np.zeros_like(frame)
            neon[:, :, 0] = edges
            neon[:, :, 1] = edges
            shifted = cv2.applyColorMap(gray, cv2.COLORMAP_TWILIGHT_SHIFTED)
            return cv2.addWeighted(shifted, 0.7, neon, 0.9, 0)
        elif flt == "cartoon":
            color = cv2.bilateralFilter(frame, 7, 50, 50)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.medianBlur(gray, 5)
            edges = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 2)
            return cv2.bitwise_and(color, color, mask=edges)
        elif flt == "thermal":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return cv2.applyColorMap(gray, cv2.COLORMAP_JET)
        elif flt == "glitch":
            g = frame.copy()
            h, w = g.shape[:2]
            shift = 10
            g[:, :-shift, 2] = frame[:, shift:, 2]
            for _ in range(2):
                y = np.random.randint(0, h - 20)
                sh = np.random.randint(5, 15)
                g[y:y+sh] = np.roll(g[y:y+sh], np.random.randint(-10, 10), axis=1)
            return g
        return frame

    def _render_synthetic(self, t):
        f = np.zeros((720, 1280, 3), dtype=np.uint8)
        for y in range(720):
            f[y, :, 0] = int(20 + 20 * (y / 720))
            f[y, :, 1] = int(12 + 16 * (y / 720))
            f[y, :, 2] = int(8 + 12 * (y / 720))

        cx = int(640 + 180 * np.cos(t * 1.5))
        cy = int(360 + 100 * np.sin(t * 1.5))
        cv2.circle(f, (cx, cy), 80, (0, 200, 255), -1)
        cv2.circle(f, (1280 - cx, 720 - cy), 50, (220, 0, 160), -1)

        for x in range(0, 1280, 80):
            cv2.line(f, (x, 0), (x, 720), (35, 45, 60), 1)
        for y in range(0, 720, 80):
            cv2.line(f, (0, y), (1280, y), (35, 45, 60), 1)

        cv2.putText(f, "XIN // DIRECT SIGNAL", (40, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2)
        cv2.putText(f, f"TIME: {time.strftime('%H:%M:%S UTC')}", (40, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 190, 220), 1)
        return f

    def _worker(self):
        t0 = time.time()
        while self.running:
            if self.source_mode == "phone":
                try:
                    req = urllib.request.Request(self.stream_url, headers={'User-Agent': 'Mozilla/5.0'})
                    stream = urllib.request.urlopen(req, context=self.ctx, timeout=3)
                    buf = b""
                    while self.running and self.source_mode == "phone":
                        chunk = stream.read(8192)
                        if not chunk:
                            break
                        buf += chunk
                        a = buf.find(b'\xff\xd8')
                        b = buf.find(b'\xff\xd9')
                        if a != -1 and b != -1 and b > a:
                            jpg = buf[a:b+2]
                            buf = buf[b+2:]
                            f = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if f is not None:
                                out = self._apply_fx(f)
                                with self.lock:
                                    self.current_frame = out
                    stream.close()
                except Exception:
                    raw = self._render_synthetic(time.time() - t0)
                    cv2.putText(raw, "SIGNAL RECONNECTING...", (420, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 240), 2)
                    out = self._apply_fx(raw)
                    with self.lock:
                        self.current_frame = out
                    time.sleep(1.0)
            else:
                raw = self._render_synthetic(time.time() - t0)
                out = self._apply_fx(raw)
                with self.lock:
                    self.current_frame = out
                time.sleep(0.025)

    def get_jpeg(self):
        with self.lock:
            if self.current_frame is None:
                return None
            ret, buf = cv2.imencode('.jpg', self.current_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                return buf.tobytes()
            return None

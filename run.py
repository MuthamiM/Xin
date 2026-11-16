#!/usr/bin/env python3
"""
Xin Platform Entrypoint
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.app import create_app
from core.config import Config

app = create_app()

if __name__ == "__main__":
    print("==================================================================")
    print("XIN PRODUCTION RUNTIME [FEATURE-FIRST ARCHITECTURE]")
    print(f"Server Port:    http://{Config.HOST}:{Config.PORT}")
    print("Local Access:   http://localhost:5000")
    print("Security:       Middleware active [GeoIP, VPN Guard, Flood Control]")
    print("Allowed:        East Africa, South Africa, Asia")
    print("==================================================================")
    app.run(host=Config.HOST, port=Config.PORT, debug=False, threaded=True)

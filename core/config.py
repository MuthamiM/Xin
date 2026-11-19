import os

class Config:
    PLATFORM_NAME = "Xin"
    PORT = int(os.environ.get("PORT", 5000))
    HOST = "0.0.0.0"
    
    # Phone camera stream
    PHONE_STREAM_URL = os.environ.get("PHONE_STREAM_URL", "https://192.168.1.201:4444/video/mjpeg")
    
    # Security & Banning
    VPN_DETECTION_ENABLED = True
    BAN_DURATION_SECONDS = 900  # 15 minutes
    RATE_LIMIT_MAX = 80         # requests per minute
    RATE_LIMIT_WINDOW = 60      # seconds
    
    # Regional Access Whitelist (ISO country codes)
    ALLOWED_REGIONS = {
        # East Africa
        "KE": "Kenya",
        "TZ": "Tanzania",
        "UG": "Uganda",
        "RW": "Rwanda",
        "ET": "Ethiopia",
        "BI": "Burundi",
        "SO": "Somalia",
        "DJ": "Djibouti",
        # South Africa
        "ZA": "South Africa",
        "NA": "Namibia",
        "BW": "Botswana",
        # Asia
        "IN": "India",
        "SG": "Singapore",
        "MY": "Malaysia",
        "ID": "Indonesia",
        "TH": "Thailand",
        "VN": "Vietnam",
        "PH": "Philippines",
        "JP": "Japan",
        "KR": "South Korea",
        "HK": "Hong Kong",
        "TW": "Taiwan",
        "CN": "China",
        "PK": "Pakistan",
        "BD": "Bangladesh",
        "LK": "Sri Lanka",
        "AE": "United Arab Emirates",
        "SA": "Saudi Arabia",
        "QA": "Qatar",
        "OM": "Oman",
        # Cloudflare Edge & Origin Development Egress
        "US": "United States",
    }

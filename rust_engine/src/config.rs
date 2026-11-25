//! Xin Configuration - Runtime settings, regional geofencing allowlist, and shared themes.

use serde::Serialize;
use std::collections::HashSet;
use std::env;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize)]
pub struct ThemeSpec {
    pub id: &'static str,
    pub name: &'static str,
    pub accent: &'static str,
    pub default: bool,
}

pub const AVAILABLE_THEMES: &[ThemeSpec] = &[
    ThemeSpec {
        id: "electric-blue",
        name: "Electric Blue",
        accent: "#2563eb",
        default: true,
    },
    ThemeSpec {
        id: "cobalt-deep",
        name: "Cobalt Deep",
        accent: "#1d4ed8",
        default: false,
    },
    ThemeSpec {
        id: "obsidian-steel",
        name: "Obsidian Steel",
        accent: "#2563eb",
        default: false,
    },
];

#[derive(Debug, Clone)]
pub struct XinConfig {
    pub platform_name: &'static str,
    pub host: String,
    pub port: u16,
    pub rate_limit_max: usize,
    pub rate_limit_window_secs: u64,
    pub ban_duration_secs: u64,
    pub max_payload_bytes: usize,
    pub stale_timeout_secs: u64,
    pub allowed_regions: HashSet<String>,
    pub shared_dir: PathBuf,
}

impl XinConfig {
    pub fn from_env() -> Self {
        let host = env::var("XIN_HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
        let port = env::var("XIN_PORT")
            .or_else(|_| env::var("PORT"))
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(5000);

        let regions = [
            // East Africa
            "KE", "TZ", "UG", "RW", "ET", "BI", "SO", "DJ",
            // South Africa
            "ZA", "NA", "BW",
            // Asia
            "IN", "SG", "MY", "ID", "TH", "VN", "PH", "JP", "KR", "HK", "TW", "CN", "PK", "BD", "LK", "AE", "SA", "QA", "OM",
            // Cloudflare Tunnel edge egress
            "US",
        ];
        let allowed_regions = regions.iter().map(|s| (*s).to_string()).collect();

        // Resolve shared asset/template directory cleanly whether launched from workspace root or rust_engine/
        let shared_dir = if PathBuf::from("shared/templates/index.html").exists() {
            PathBuf::from("shared")
        } else if PathBuf::from("../shared/templates/index.html").exists() {
            PathBuf::from("../shared")
        } else {
            PathBuf::from("C:/Users/cantroll/.gemini/antigravity/scratch/Xin/shared")
        };

        Self {
            platform_name: "Xin",
            host,
            port,
            rate_limit_max: 600,
            rate_limit_window_secs: 60,
            ban_duration_secs: 300,
            max_payload_bytes: 65_536,
            stale_timeout_secs: 8,
            allowed_regions,
            shared_dir,
        }
    }
}

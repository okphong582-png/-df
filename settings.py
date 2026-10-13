"""Shared local/environment settings. Never commit config.json or .env."""
import json
import os
from pathlib import Path


def load_config():
    path = Path(__file__).with_name("config.json")
    config = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    for name in ("bot_token", "admin_id", "firebase_url", "link4m_token",
                 "public_proxy_host", "public_proxy_port", "web_port", "web_host",
                 "auth_mode", "proxy_access_mode", "proxy_http2"):
        if name.upper() in os.environ:
            config[name] = os.environ[name.upper()]
    return config

import json
import os
import sys
import time
import random
import string
from urllib.parse import quote
import requests
from settings import load_config

# Fix console encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

cfg = load_config()
FIREBASE_URL = cfg.get("firebase_url", "").rstrip("/")
LINK4M_TOKEN = cfg.get("link4m_token", "").strip()

def fb_put(path, data):
    try:
        r = requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=8)
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[!] Firebase PUT error: {e}")
        return False

def generate_single_key(prefix="MIZZE", link4m_token=None):
    if not link4m_token:
        link4m_token = LINK4M_TOKEN

    chars = string.ascii_uppercase + string.digits
    rand1 = "".join(random.choices(chars, k=4))
    rand2 = "".join(random.choices(chars, k=4))
    key_code = f"{prefix}-{rand1}-{rand2}"

    # 1. Tạo nội dung Markdown trên Rentry
    content = f"""# 🎮 {prefix} FREE FIRE VIP KEY
Mã Key của bạn: `{key_code}`

---
📌 **Hướng dẫn kích hoạt:**
1. Quay lại Telegram Bot: `@ProxyMizzeGetkey_bot`
2. Bấm nút **[🔑 Xác Thực Key]**
3. Gửi mã `{key_code}` vào chat để nhận quyền chơi **24 Giờ**!
"""

    # 2. Tạo paste trên Rentry.co
    s = requests.Session()
    s.get("https://rentry.co", timeout=10)
    csrf = s.cookies.get("csrftoken")
    res_rentry = s.post(
        "https://rentry.co/api/new",
        data={"csrfmiddlewaretoken": csrf, "text": content},
        headers={"Referer": "https://rentry.co"},
        timeout=10
    )
    if res_rentry.status_code != 200:
        raise Exception(f"Rentry HTTP {res_rentry.status_code}")
    data_rentry = res_rentry.json()
    if data_rentry.get("status") != "200":
        raise Exception(f"Rentry API error: {data_rentry}")
    rentry_url = data_rentry.get("url")

    # 3. Rút gọn qua Link4m API
    api_url = f"https://link4m.co/api-shorten/v2?api={link4m_token}&url={quote(rentry_url)}"
    res_l4m = requests.get(api_url, timeout=12)
    if res_l4m.status_code != 200:
        raise Exception(f"Link4m HTTP {res_l4m.status_code}")
    data_l4m = res_l4m.json()
    if data_l4m.get("status") != "success":
        raise Exception(f"Link4m error: {data_l4m.get('message', 'Không rõ')}")
    short_url = data_l4m.get("shortenedUrl")

    # 4. Lưu lên Firebase Realtime Database
    safe_k = key_code.replace(".", "_")
    record = {
        "key": key_code,
        "link": short_url,
        "rentry": rentry_url,
        "createdAt": int(time.time() * 1000),
        "durationHours": 24
    }
    fb_put(f"keys/{safe_k}", record)

    return record

def bulk_generate(count=5, prefix="MIZZE", link4m_token=None):
    print(f"[*] Bắt đầu tạo tự động {count} Key (Prefix: {prefix})...")
    created = []
    for i in range(1, count + 1):
        try:
            print(f"[{i}/{count}] Đang tạo Rentry & Link4m...", end=" ", flush=True)
            res = generate_single_key(prefix=prefix, link4m_token=link4m_token)
            created.append(res)
            print(f"OK -> Key: {res['key']} | Link: {res['link']}")
        except Exception as e:
            print(f"LỖI: {e}")
        time.sleep(0.5)

    print(f"\n[OK] Đã hoàn thành tạo {len(created)}/{count} Key lên Firebase!")
    return created

if __name__ == "__main__":
    count = 5
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            pass
    prefix = sys.argv[2] if len(sys.argv) > 2 else "MIZZE"
    bulk_generate(count=count, prefix=prefix)

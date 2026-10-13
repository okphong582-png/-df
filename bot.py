import json
import os
import sys
import time
from datetime import datetime
import threading
import ipaddress
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import requests
import telebot
from telebot import types
from settings import load_config

# Fix console encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

cfg = load_config()
BOT_TOKEN = cfg.get("bot_token", "").strip()
ADMIN_ID = str(cfg.get("admin_id", "")).strip()
FIREBASE_URL = cfg.get("firebase_url", "").rstrip("/")
WEB_PORT = int(cfg.get("web_port", 8088))
WEB_HOST = cfg.get("web_host", "127.0.0.1")
PUBLIC_PROXY_HOST = cfg.get("public_proxy_host", "127.0.0.1")
PUBLIC_PROXY_PORT = int(cfg.get("public_proxy_port", 1297))
PUBLIC_PROXY_URL = f"http://{PUBLIC_PROXY_HOST}:{PUBLIC_PROXY_PORT}"

# Firebase helper functions (REST API)
def fb_get(path):
    try:
        r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=6)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def fb_put(path, data):
    try:
        r = requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=6)
        return r.status_code in (200, 204)
    except Exception:
        return False

def fb_delete(path):
    try:
        r = requests.delete(f"{FIREBASE_URL}/{path}.json", timeout=6)
        return r.status_code in (200, 204)
    except Exception:
        return False

def ip_to_key(ip):
    return str(ip).replace(".", "_").replace(":", "_")

def key_to_ip(safe_ip):
    return str(safe_ip).replace("_", ".")

LINK4M_TOKEN = cfg.get("link4m_token", "").strip()

try:
    from generate_keys import generate_single_key, bulk_generate
except Exception:
    pass

# Mini Web Server dự phòng bắt IP và cung cấp API tạo key cho Admin
class IPTrackingHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Endpoint tạo key hàng loạt (Rentry + Link4m) cho Admin Web
        if parsed.path == "/api/bulk_create":
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

            count = min(int(params.get("count", ["5"])[0]), 50)
            prefix = params.get("prefix", ["MIZZE"])[0]
            token = params.get("token", [LINK4M_TOKEN])[0]

            created = []
            for _ in range(count):
                try:
                    res = generate_single_key(prefix=prefix, link4m_token=token)
                    created.append(res)
                except Exception as e:
                    created.append({"error": str(e)})

            self.wfile.write(json.dumps({"status": "success", "keys": created}).encode("utf-8"))
            return

        client_ip = (
            self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or self.headers.get("CF-Connecting-IP", "")
            or self.headers.get("X-Real-IP", "")
            or self.client_address[0]
        )

        user_id = params.get("uid", [""])[0]
        redirect_url = params.get("to", [""])[0]

        if user_id and client_ip and client_ip != "127.0.0.1":
            fb_put(f"pending_ips/{user_id}", {
                "ip": client_ip,
                "timestamp": int(time.time() * 1000)
            })

        if redirect_url:
            self.send_response(302)
            self.send_header("Location", redirect_url)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Xác nhận IP</title></head>
<body style="font-family:sans-serif;text-align:center;padding:40px;background:#090d16;color:#fff;">
    <h2>🌐 Đã ghi nhận IP mạng của bạn:</h2>
    <h1 style="color:#38bdf8;">{client_ip}</h1>
    <p>Bây giờ bạn hãy quay lại Telegram Bot và bấm <b>Xác thực Key</b> để kích hoạt!</p>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

def run_ip_server():
    try:
        server = HTTPServer((WEB_HOST, WEB_PORT), IPTrackingHandler)
        server.serve_forever()
    except Exception:
        pass

bot = telebot.TeleBot(BOT_TOKEN if BOT_TOKEN else "123456:dummy")

# Lưu trữ message_id của bảng menu duy nhất cho mỗi user
user_menu_msg = {}
waiting_for_key = {}

def get_user_status(uid):
    detected_ip = None
    is_active = False
    time_left_str = "Chưa kích hoạt"
    active_ip = None

    now_ms = int(time.time() * 1000)
    auth_ips = fb_get("authorized_ips") or {}
    for k, item in auth_ips.items():
        if str(item.get("userId", "")) == str(uid):
            exp_ms = item.get("expiresAt", 0)
            diff = exp_ms - now_ms
            if diff > 0:
                is_active = True
                active_ip = item.get("ip", key_to_ip(k))
                h = int(diff // (3600 * 1000))
                m = int((diff % (3600 * 1000)) // (60 * 1000))
                time_left_str = f"🟢 Đang hoạt động (Còn: {h}h {m}p)"
                break
            else:
                time_left_str = "🔴 Đã hết hạn 24H"

    pending = fb_get(f"pending_ips/{uid}")
    if pending and pending.get("ip"):
        detected_ip = pending.get("ip")
    elif active_ip:
        detected_ip = active_ip

    return detected_ip, is_active, time_left_str

def build_main_menu(uid, name):
    detected_ip, is_active, status_str = get_user_status(uid)
    ip_display = f"<code>{detected_ip}</code> ✅" if detected_ip else "<i>(Chưa nhận diện - Bấm lấy key để tự lấy)</i>"

    text = (
        "╔══════════════════════════════════════╗\n"
        "       ⚡ <b>FREE FIRE VIP PROXY SYSTEM</b> ⚡\n"
        "╚══════════════════════════════════════╝\n\n"
        f"👤 <b>Người dùng:</b> {name} <code>({uid})</code>\n"
        f"🌐 <b>IP Mạng:</b> {ip_display}\n"
        f"📊 <b>Trạng thái:</b> {status_str}\n"
        f"🛡️ <b>Server Proxy:</b> <code>159.223.110.159:1297</code>\n\n"
        "────────────────────────────────────────\n"
        "📌 <b>Hướng dẫn sử dụng:</b>\n"
        "1. Bấm <b>🔗 Lấy Link Get Key</b> để lấy link vượt mã.\n"
        "   <i>(Hệ thống sẽ TỰ ĐỘNG nhận diện IP mạng của bạn)</i>\n"
        "2. Vượt xong bấm <b>🔑 Xác Thực Key</b> để mở quyền <b>24H</b>.\n"
        "────────────────────────────────────────"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    track_ip_link = f"{PUBLIC_PROXY_URL}/get_ip?uid={uid}"

    markup.add(
        types.InlineKeyboardButton("🔗 Lấy Link Get Key", callback_data="get_key"),
        types.InlineKeyboardButton("🔑 Xác Thực Key", callback_data="prompt_key"),
        types.InlineKeyboardButton("🌐 Tự Động Lấy IP Mạng", url=track_ip_link),
        types.InlineKeyboardButton("🔄 Làm Mới Menu", callback_data="refresh_menu")
    )

    if str(uid) == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("👑 Bảng Quản Trị Admin", callback_data="admin_menu"))

    return text, markup

def safe_edit_menu(chat_id, text, markup):
    msg_id = user_menu_msg.get(chat_id)
    if msg_id:
        try:
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        except Exception:
            pass

    # Nếu không edit được (tin nhắn cũ bị xóa hoặc chưa có), gửi tin mới
    sent = bot.send_message(
        chat_id,
        text,
        reply_markup=markup,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    user_menu_msg[chat_id] = sent.message_id

@bot.message_handler(commands=["start", "menu"])
def cmd_start(msg):
    chat_id = msg.chat.id
    uid = str(msg.from_user.id)
    name = msg.from_user.first_name or "Bạn"

    # Xóa tin nhắn lệnh /start của user để chat luôn sạch
    try:
        bot.delete_message(chat_id, msg.message_id)
    except Exception:
        pass

    # Xóa tin nhắn menu cũ nếu có
    old_id = user_menu_msg.get(chat_id)
    if old_id:
        try:
            bot.delete_message(chat_id, old_id)
        except Exception:
            pass

    waiting_for_key[uid] = False
    text, markup = build_main_menu(uid, name)
    sent = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    user_menu_msg[chat_id] = sent.message_id

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    uid = str(call.from_user.id)
    name = call.from_user.first_name or "Bạn"
    data = call.data

    user_menu_msg[chat_id] = call.message.message_id

    if data == "main_menu":
        waiting_for_key[uid] = False
        text, markup = build_main_menu(uid, name)
        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id)

    elif data == "refresh_menu":
        waiting_for_key[uid] = False
        text, markup = build_main_menu(uid, name)
        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id, "✅ Đã làm mới trạng thái!", show_alert=False)

    elif data == "get_key":
        waiting_for_key[uid] = False
        keys_data = fb_get("keys") or {}
        if not keys_data:
            text = (
                "╔══════════════════════════════════════╗\n"
                "          ⚠️ <b>THÔNG BÁO KHO KEY</b>\n"
                "╚══════════════════════════════════════╝\n\n"
                "Kho hiện tại chưa có Key nào khả dụng.\n"
                "Vui lòng liên hệ Admin để tạo thêm Key nhé!"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Quay Lại Menu", callback_data="main_menu"))
            safe_edit_menu(chat_id, text, markup)
            bot.answer_callback_query(call.id)
            return

        key_list = list(keys_data.keys())
        first_key = key_list[0]
        item = keys_data[first_key]
        link = item.get("link", "")

        encoded_to = quote(link, safe="")
        track_link = f"{PUBLIC_PROXY_URL}/get_ip?uid={uid}&to={encoded_to}" if link.startswith("http") else link

        text = (
            "╔══════════════════════════════════════╗\n"
            "         🎁 <b>LINK GET KEY CỦA BẠN</b>\n"
            "╚══════════════════════════════════════╝\n\n"
            f"🔗 <b>Link nhiệm vụ:</b>\n"
            f"<a href='{track_link}'>{link}</a>\n\n"
            "💡 <b>LƯU Ý:</b>\n"
            "• Hãy bấm nút <b>🚀 Mở Link Vượt Key</b> bên dưới.\n"
            "• Trình duyệt sẽ <b>TỰ ĐỘNG BẮT IP MẠNG</b> của bạn ngay lập tức.\n"
            "• Nhận được mã Key xong, quay lại đây bấm <b>🔑 Xác Thực Key</b>!"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🚀 Mở Link Vượt Key (Tự Lấy IP)", url=track_link),
            types.InlineKeyboardButton("🔑 Xác Thực Key Ngay", callback_data="prompt_key"),
            types.InlineKeyboardButton("🔙 Quay Lại Menu Chính", callback_data="main_menu")
        )
        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id)

    elif data == "prompt_key":
        waiting_for_key[uid] = True
        detected_ip, _, _ = get_user_status(uid)
        ip_info = f"<code>{detected_ip}</code> ✅" if detected_ip else "⚠️ <i>Chưa nhận diện được</i>"

        text = (
            "╔══════════════════════════════════════╗\n"
            "            🔑 <b>XÁC THỰC MÃ KEY</b>\n"
            "╚══════════════════════════════════════╝\n\n"
            f"🌐 <b>IP mạng hiện tại:</b> {ip_info}\n\n"
            "👉 <b>Vui lòng gửi mã Key vào ô chat bên dưới:</b>\n"
            "<i>(Ví dụ: FF-ABCD-1234)</i>\n\n"
            "💡 <i>Sau khi gửi, hệ thống sẽ kích hoạt 24H cho IP mạng của bạn và xóa mã Key.</i>"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        if not detected_ip:
            markup.add(types.InlineKeyboardButton("🌐 Bấm Để Nhận Diện IP Trước", url=f"{PUBLIC_PROXY_URL}/get_ip?uid={uid}"))
        markup.add(types.InlineKeyboardButton("🔙 Hủy & Về Menu Chính", callback_data="main_menu"))

        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id)

    elif data == "admin_menu":
        if uid != ADMIN_ID:
            bot.answer_callback_query(call.id, "⛔ Bạn không có quyền Admin!", show_alert=True)
            return

        keys = fb_get("keys") or {}
        ips = fb_get("authorized_ips") or {}

        text = (
            "╔══════════════════════════════════════╗\n"
            "        👑 <b>BẢNG QUẢN TRỊ ADMIN</b>\n"
            "╚══════════════════════════════════════╝\n\n"
            f"📋 <b>Số Key khả dụng:</b> {len(keys)}\n"
            f"🌐 <b>IP đang chơi (24H):</b> {len(ips)}\n\n"
            "💡 <i>Bạn cũng có thể mở file <b>admin.html</b> trên máy tính để quản trị giao diện trực quan!</i>"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚡ Tạo 5 Key (Rentry + Link4m)", callback_data="admin_bulk_5"),
            types.InlineKeyboardButton("⚡ Tạo 10 Key (Rentry + Link4m)", callback_data="admin_bulk_10"),
            types.InlineKeyboardButton("📋 Xem Danh Sách Key", callback_data="admin_list_keys"),
            types.InlineKeyboardButton("🌐 Xem Danh Sách IP Active", callback_data="admin_list_ips"),
            types.InlineKeyboardButton("🔙 Về Menu Người Dùng", callback_data="main_menu")
        )
        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id)

    elif data in ("admin_bulk_5", "admin_bulk_10"):
        if uid != ADMIN_ID:
            return
        bot.answer_callback_query(call.id, "⏳ Đang tạo Key qua Rentry & Link4m... Vui lòng chờ vài giây!", show_alert=False)
        count = 5 if data == "admin_bulk_5" else 10

        created = bulk_generate(count=count, prefix="MIZZE", link4m_token=LINK4M_TOKEN)

        lines = [f"🎉 <b>ĐÃ TẠO THÀNH CÔNG {len(created)} KEY MỚI!</b>\n"]
        for it in created:
            lines.append(f"• Key: <code>{it['key']}</code>\n  🔗 Link4m: {it['link']}")

        text = "\n".join(lines)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Quay Lại Menu Admin", callback_data="admin_menu"))
        safe_edit_menu(chat_id, text, markup)

    elif data == "admin_list_keys":
        if uid != ADMIN_ID:
            return
        keys = fb_get("keys") or {}
        lines = ["📋 <b>DANH SÁCH KEY KHẢ DỤNG:</b>\n"]
        if not keys:
            lines.append("<i>Chưa có key nào.</i>")
        else:
            for k, it in list(keys.items())[:15]:
                lines.append(f"• <code>{it.get('key', k)}</code>")

        text = "\n".join(lines)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Quay Lại Menu Admin", callback_data="admin_menu"))
        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id)

    elif data == "admin_list_ips":
        if uid != ADMIN_ID:
            return
        ips = fb_get("authorized_ips") or {}
        now_ms = int(time.time() * 1000)
        lines = ["🌐 <b>DANH SÁCH IP ĐANG ĐƯỢC CẤP QUYỀN:</b>\n"]
        if not ips:
            lines.append("<i>Chưa có IP nào active.</i>")
        else:
            for k, it in list(ips.items())[:15]:
                ip_val = it.get("ip", key_to_ip(k))
                diff = it.get("expiresAt", 0) - now_ms
                if diff > 0:
                    h = int(diff // (3600 * 1000))
                    m = int((diff % (3600 * 1000)) // (60 * 1000))
                    lines.append(f"• <code>{ip_val}</code> (Còn: <b>{h}h {m}p</b>)")
                else:
                    lines.append(f"• <code>{ip_val}</code> (<i>Đã hết hạn</i>)")

        text = "\n".join(lines)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Quay Lại Menu Admin", callback_data="admin_menu"))
        safe_edit_menu(chat_id, text, markup)
        bot.answer_callback_query(call.id)

# Xử lý khi user gửi tin nhắn văn bản (mã Key)
@bot.message_handler(func=lambda m: True)
def handle_text_messages(msg):
    chat_id = msg.chat.id
    uid = str(msg.from_user.id)
    text = (msg.text or "").strip()

    # Xóa ngay tin nhắn của người dùng để cuộc hội thoại luôn sạch sẽ
    try:
        bot.delete_message(chat_id, msg.message_id)
    except Exception:
        pass

    if not waiting_for_key.get(uid):
        # Nếu chưa bấm xác thực key, chỉ refresh lại menu chính
        main_text, markup = build_main_menu(uid, msg.from_user.first_name or "Bạn")
        safe_edit_menu(chat_id, main_text, markup)
        return

    # Tách key và IP nếu người dùng gửi kèm IP
    manual_ip = None
    key_input = text
    if "ip:" in text.lower():
        parts = text.lower().split("ip:")
        key_input = parts[0].strip()
        manual_ip = parts[1].strip()
    elif " " in text and ("." in text.split(" ")[-1]):
        parts = text.split(" ")
        key_input = parts[0].strip()
        manual_ip = parts[-1].strip()

    # Kiểm tra Key trong Firebase
    keys_data = fb_get("keys") or {}
    matched_id = None
    for k_id, item in keys_data.items():
        saved_key = item.get("key", k_id)
        if saved_key.strip().upper() == key_input.upper():
            matched_id = k_id
            break

    if not matched_id:
        error_text = (
            "╔══════════════════════════════════════╗\n"
            "         ❌ <b>XÁC THỰC THẤT BẠI</b>\n"
            "╚══════════════════════════════════════╝\n\n"
            f"Mã Key: <code>{key_input}</code>\n"
            "<b>Key không hợp lệ hoặc đã có người sử dụng!</b>\n\n"
            "👉 Vui lòng bấm <b>Lấy Link Get Key</b> để vượt key mới."
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🔗 Lấy Link Get Key Mới", callback_data="get_key"),
            types.InlineKeyboardButton("🔑 Thử Nhập Lại Mã Khác", callback_data="prompt_key"),
            types.InlineKeyboardButton("🔙 Quay Lại Menu Chính", callback_data="main_menu")
        )
        safe_edit_menu(chat_id, error_text, markup)
        return

    # Xác định IP mạng
    target_ip = manual_ip
    if not target_ip:
        pending = fb_get(f"pending_ips/{uid}")
        if pending and pending.get("ip"):
            target_ip = pending.get("ip")

    if not target_ip:
        no_ip_text = (
            "╔══════════════════════════════════════╗\n"
            "          ⚠️ <b>CHƯA CÓ IP MẠNG</b>\n"
            "╚══════════════════════════════════════╝\n\n"
            f"Key <code>{key_input}</code> hợp lệ, nhưng hệ thống <b>chưa nhận diện được IP</b> mạng của bạn!\n\n"
            "👉 Hãy bấm nút bên dưới để hệ thống nhận diện IP mạng của bạn, sau đó gửi lại Key nhé!"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 Bấm Vào Đây Để Lấy IP Tự Động", url=f"{PUBLIC_PROXY_URL}/get_ip?uid={uid}"),
            types.InlineKeyboardButton("🔑 Gửi Lại Mã Key", callback_data="prompt_key"),
            types.InlineKeyboardButton("🔙 Quay Lại Menu Chính", callback_data="main_menu")
        )
        safe_edit_menu(chat_id, no_ip_text, markup)
        return

    try:
        target_ip = str(ipaddress.ip_address(target_ip))
    except ValueError:
        bot.send_message(chat_id, "IP không hợp lệ. Hãy nhận diện lại IP hoặc gửi key kèm IP đúng.")
        return

    # Kích hoạt 24 Giờ cho IP
    now_ms = int(time.time() * 1000)
    expires_ms = now_ms + (24 * 3600 * 1000)
    expire_dt = datetime.fromtimestamp(expires_ms / 1000).strftime("%H:%M %d/%m/%Y")

    safe_ip = ip_to_key(target_ip)
    auth_data = {
        "ip": target_ip,
        "userId": uid,
        "username": msg.from_user.username or msg.from_user.first_name or "",
        "keyUsed": key_input,
        "activatedAt": now_ms,
        "expiresAt": expires_ms
    }

    # 1. Lưu IP vào Firebase
    if not fb_put(f"authorized_ips/{safe_ip}", auth_data):
        bot.send_message(chat_id, "Không lưu được quyền IP lên Firebase. Key chưa bị xóa; hãy thử lại.")
        return

    # 2. XÓA MÃ KEY NGAY LẬP TỨC để không bị dùng lại
    deleted = fb_delete(f"keys/{matched_id}")
    waiting_for_key[uid] = False

    success_text = (
        "╔══════════════════════════════════════╗\n"
        "        🎉 <b>XÁC THỰC THÀNH CÔNG!</b>\n"
        "╚══════════════════════════════════════╝\n\n"
        f"🌐 <b>IP được cấp quyền:</b> <code>{target_ip}</code>\n"
        f"⏳ <b>Thời hạn chơi:</b> 24 Giờ\n"
        f"⏰ <b>Hết hạn vào lúc:</b> <code>{expire_dt}</code>\n\n"
        + ("✅ <b>Đã xóa mã Key khỏi hệ thống.</b>\n" if deleted else "⚠️ Chưa xóa được key; hãy báo admin.\n")
        + f"👉 Proxy: <code>{PUBLIC_PROXY_HOST}:{PUBLIC_PROXY_PORT}</code>. Chờ khoảng 5–8 giây để cập nhật quyền."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Quay Lại Menu Chính", callback_data="main_menu"))
    safe_edit_menu(chat_id, success_text, markup)

if __name__ == "__main__":
    if not BOT_TOKEN or "DIEN_BOT_TOKEN" in BOT_TOKEN or not FIREBASE_URL or not ADMIN_ID:
        raise SystemExit("Thieu BOT_TOKEN, ADMIN_ID hoac FIREBASE_URL; xem .env.example")
    threading.Thread(target=run_ip_server, daemon=True).start()
    # Old inline-button callbacks expire while the PC is offline. Do not replay
    # queued clicks or old key-generation requests after restarting the bot.
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
    raise SystemExit("Bot polling da dung; khoi dong lai dich vu")

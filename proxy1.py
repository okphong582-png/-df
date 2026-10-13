"""
mitmproxy addon — MITM CDN Free Fire.
Chỉ thay codepatch. fileinfo lấy bản live từ CDN rồi sửa 1 dòng.
Không đụng / không serve avatar/assetindexer.

  mitmdump --listen-host 0.0.0.0 --listen-port 1297 ^
    --set block_global=false --ssl-insecure ^
    --set connection_strategy=lazy ^
    --set upstream_cert=false ^
    -s proxy1.py

Cùng thư mục:
  fileinfo                   (fallback; sẽ được cập nhật từ CDN)
  assembly-csharp-patch      (UnityFS, ưu tiên)
  assembly-csharp-patch.gz   (nếu đã gzip)
  aim.gz                     (fallback)
"""

from __future__ import annotations

import base64
import asyncio
import gzip
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import ssl
import tempfile
import time
import threading
import urllib.error
import urllib.request
from typing import Optional, Tuple
from urllib.parse import urlparse
from settings import load_config

from mitmproxy import ctx, http
from mitmproxy.addonmanager import Loader

CONFIG = load_config()
FIREBASE_RTDB_URL = CONFIG.get("firebase_url", "").rstrip("/")

BASE = os.path.dirname(os.path.abspath(__file__))
FILEINFO_PATH = os.path.join(BASE, "fileinfo")
PATCH_CANDIDATES = (
    os.path.join(BASE, "assembly-csharp-patch.gz"),
    os.path.join(BASE, "assembly-csharp-patch"),
    os.path.join(BASE, "aim.gz"),
)
BAK_PATH = FILEINFO_PATH + ".bak"

LINE_RE = re.compile(
    r"^[^\r\n]*codepatch/assembly-csharp-patch[^\r\n]*$",
    re.MULTILINE | re.IGNORECASE,
)
PATCH_KEY = "codepatch/assembly-csharp-patch"
GZIP_MAGIC = b"\x1f\x8b"
UNITYFS_MAGIC = b"UnityFS"
MAX_AIM = 32 * 1024 * 1024
MAX_FI = 8 * 1024 * 1024
MAX_FAILOVER = 64 * 1024 * 1024

INTERCEPT_RE = re.compile(
    r"(^|\.)(freefiremobile\.com|purplevioleto\.com|ppmainecoonghj\.com)$",
    re.IGNORECASE,
)
ALLOW_HOSTS = [
    r"(^|\.)freefiremobile\.com(:\d+)?$",
    r"(^|\.)purplevioleto\.com(:\d+)?$",
    r"(^|\.)ppmainecoonghj\.com(:\d+)?$",
]
ALT_CDN = (
    "core-aw.freefiremobile.com",
    "core-bs.freefiremobile.com",
    "core-gmc.freefiremobile.com",
    "dl.gmc.freefiremobile.com",
)
COPY_HDRS = (
    "user-agent",
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "cookie",
    "x-unity-version",
    "x-requested-with",
)
BLOCK_MSG = "Cút khỏi server ch có quyền truy cập"


def log(level: str, msg: str) -> None:
    try:
        getattr(ctx.log, level)(msg)
    except Exception:
        pass


def sha1_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha1(data).digest()).decode("ascii")


def atomic_write(path: str, data: bytes) -> None:
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".fi.", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def path_only(flow: http.HTTPFlow) -> str:
    p = flow.request.path or ""
    return p.split("?", 1)[0]


def host_of(flow: http.HTTPFlow) -> str:
    return (flow.request.host or flow.request.pretty_host or "").lower()


def sni_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace").lower()
    return str(value).lower()


def should_intercept(host: str) -> bool:
    host = (host or "").split(":")[0].strip(".").lower()
    if not host:
        return False
    return INTERCEPT_RE.search(host) is not None


def is_ff(host: str) -> bool:
    return should_intercept(host)


def is_main_fileinfo(path: str) -> bool:
    low = path.lower()
    if "fileinfo" not in low:
        return False
    if "optional" in low:
        return False
    return "/abhotupdates/" in low


def is_aim(path: str) -> bool:
    """Local replace: codepatch only."""
    low = path.lower()
    if "fileinfo" in low:
        return False
    if "assetindexer" in low or "/avatar/" in low:
        return False
    return "assembly-csharp-patch" in low or "codepatch" in low


def is_avatar(path: str) -> bool:
    low = path.lower()
    return "assetindexer" in low or "/avatar/" in low


def is_noise_error(msg: str) -> bool:
    low = (msg or "").lower()
    return any(
        token in low
        for token in (
            "11003",
            "getaddrinfo",
            "1225",
            "refused the network connection",
            "tls handshake failed",
            "cannot agree on a tls version",
            "does not trust the proxy",
        )
    )


class FFHotUpdateAddon:
    def __init__(self) -> None:
        self.fi: Optional[bytes] = None
        self.aim: Optional[bytes] = None
        self.ready = False
        self.fi_mtime = -1.0
        self.aim_mtime = -1.0
        self.patch_path = ""
        self.next_stat = 0.0
        self.waiting_aim = False
        self.n_fi = 0
        self.n_aim = 0
        self.n_pass = 0
        self.n_dns = 0
        self.n_refuse = 0
        self.n_fail = 0
        self._ssl = ssl._create_unverified_context()
        self.auth_cache = {}
        self.auth_cache_time = 0.0
        self._auth_stop = threading.Event()
        self._auth_thread = None
        self._connection_credentials = {}

    def _auth_worker(self) -> None:
        while not self._auth_stop.wait(2):
            self._refresh_auth_cache()

    def _refresh_auth_cache(self) -> None:
        if not FIREBASE_RTDB_URL:
            log("error", "Chua cau hinh FIREBASE_URL / firebase_url")
            return
        try:
            req = urllib.request.Request(
                f"{FIREBASE_RTDB_URL}/authorized_ips.json",
                headers={"User-Agent": "FFProxy/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.auth_cache = data if isinstance(data, dict) else {}
                    self.auth_cache_time = time.monotonic()
        except Exception as exc:
            log("warn", f"Khong cap nhat duoc quyen IP: {type(exc).__name__}")

    def _is_private_or_tunnel(self, ip: str) -> bool:
        if not ip:
            return True
        if ip in ("127.0.0.1", "localhost", "::1"):
            return True
        if ip.startswith("192.168.") or ip.startswith("10."):
            return True
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                if 16 <= second <= 31:
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _connection_key(conn):
        return str(getattr(conn, "id", id(conn)))

    def _capture_credentials(self, flow):
        key = self._connection_key(flow.client_conn)
        header = flow.request.headers.pop("Proxy-Authorization", None)
        if header is not None:
            self._connection_credentials.pop(key, None)
            try:
                scheme, encoded = header.split(None, 1)
                if scheme.lower() != "basic":
                    return None
                username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
                if not re.fullmatch(r"\d{1,20}", username) or not 1 <= len(password) <= 256:
                    return None
                self._connection_credentials[key] = (username, password)
            except (ValueError, UnicodeError):
                return None
        return self._connection_credentials.get(key)

    def client_disconnected(self, client):
        self._connection_credentials.pop(self._connection_key(client), None)

    def check_ip_authorized(self, flow: http.HTTPFlow) -> Tuple[bool, str]:
        credentials = self._capture_credentials(flow)
        now_ms = int(time.time() * 1000)
        # Only the TCP peer is trusted. HTTP forwarding headers are client-controlled.
        client_ip = flow.client_conn.address[0] if flow.client_conn and flow.client_conn.address else ""
        try:
            parsed_ip = ipaddress.ip_address(client_ip)
            check_ip = str(parsed_ip.ipv4_mapped or parsed_ip) if parsed_ip.version == 6 else str(parsed_ip)
        except ValueError:
            return False, "Khong xac dinh duoc IP ket noi"
        # Refresh happens in one background worker, never in the request hook.
        if time.monotonic() - self.auth_cache_time > 6:
            return False, "Du lieu cap quyen chua san sang / mat ket noi Firebase"
        cache = self.auth_cache
        if CONFIG.get("auth_mode") in ("tunnel_credentials", "tunnel_compat") and parsed_ip.is_loopback:
            if not credentials:
                return False, "Thieu tai khoan proxy rieng; lay cau hinh Potatso trong bot"
            username, password = credentials
            digest = hashlib.sha256(password.encode()).hexdigest()
            for item in cache.values():
                if not isinstance(item, dict) or str(item.get("userId", "")) != username:
                    continue
                expiry, token_hash = item.get("expiresAt", 0), item.get("proxyTokenHash", "")
                if (isinstance(expiry, (int, float)) and expiry > now_ms
                        and isinstance(token_hash, str) and hmac.compare_digest(token_hash, digest)):
                    return True, "Tai khoan proxy rieng con quyen"
            return False, "Tai khoan proxy sai, het han hoac da bi thu hoi"
        safe_ip = check_ip.replace(".", "_").replace(":", "_")
        if safe_ip in cache:
            item = cache[safe_ip]
            if not isinstance(item, dict):
                return False, "Du lieu quyen IP khong hop le"
            expires_at = item.get("expiresAt", 0)
            if isinstance(expires_at, (int, float)) and expires_at > now_ms:
                return True, "IP hop le (con han)"
            else:
                return False, "IP da het han 24H"

        if self._is_private_or_tunnel(check_ip):
            return False, "Tunnel/LAN khong truyen IP goc; can ket noi truc tiep toi VPS hoac cap quyen dung IP peer"
        return False, f"IP {check_ip} chua xac thuc qua Bot Telegram"

    def _save_pending_ip(self, uid: str, ip: str) -> bool:
        try:
            data = json.dumps({"ip": ip, "timestamp": int(time.time() * 1000)}).encode("utf-8")
            req = urllib.request.Request(
                f"{FIREBASE_RTDB_URL}/pending_ips/{uid}.json",
                data=data,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception as e:
            log("warn", f"Loi luu pending_ip: {e}")
            return False

    def load(self, loader: Loader) -> None:
        loader.add_option("proxy_replace", bool, True, "Serve local codepatch; patch live fileinfo")

    def configure(self, updated) -> None:  # noqa: ARG002
        self._apply_runtime_options()

    def running(self) -> None:
        self._apply_runtime_options()
        self._refresh_auth_cache()
        self._auth_thread = threading.Thread(target=self._auth_worker, daemon=True)
        self._auth_thread.start()
        self.sync(force=True)
        log(
            "info",
            f"READY fi={len(self.fi or b'')} patch={len(self.aim or b'')} "
            f"src={os.path.basename(self.patch_path) or '?'} "
            f"ok={self.ready} intercept=FF-CDN-only codepatch-only",
        )
        if not self.ready:
            log("error", "THIẾU assembly-csharp-patch — không thể Thay codepatch")

    def done(self) -> None:
        self._auth_stop.set()
        if self._auth_thread:
            self._auth_thread.join(timeout=4)
        log(
            "info",
            f"stats fileinfo={self.n_fi} codepatch={self.n_aim} failover={self.n_fail} "
            f"passthrough={self.n_pass} dns={self.n_dns} refuse={self.n_refuse}",
        )
        if self.n_fi and not self.n_aim:
            log(
                "error",
                "Có fileinfo nhưng KHÔNG có GET assembly-csharp-patch. "
                "Xóa cache hot-update trên máy rồi mở lại game.",
            )

    def tls_clienthello(self, data) -> None:
        sni = ""
        try:
            hello = getattr(data, "client_hello", None)
            sni = sni_str(getattr(hello, "sni", None) if hello is not None else None)
        except Exception:
            sni = ""
        if not sni:
            try:
                server = getattr(getattr(data, "context", None), "server", None)
                sni = sni_str(getattr(server, "address", None) and server.address[0])
            except Exception:
                sni = ""
        if should_intercept(sni):
            return
        try:
            data.ignore_connection = True
            self.n_pass += 1
        except Exception:
            pass

    def error(self, flow: http.HTTPFlow) -> None:
        msg = ""
        try:
            msg = str(getattr(flow.error, "msg", flow.error) or "")
        except Exception:
            msg = ""
        host = host_of(flow)
        if "11003" in msg or "getaddrinfo" in msg.lower():
            self.n_dns += 1
            if should_intercept(host):
                log("error", f"DNS FAIL CDN {host}: {msg}")
            else:
                log("info", f"bỏ DNS fail (không phải FF) {host or '?'}")
            return
        if "1225" in msg or "refused" in msg.lower():
            self.n_refuse += 1
            if should_intercept(host):
                log("error", f"REFUSE CDN {host}: {msg}")
            else:
                log("info", f"bỏ refuse (không phải FF) {host or '?'}")
            return
        if is_noise_error(msg) and not should_intercept(host):
            return
        log("warn", f"flow error {host}: {msg}")

    def http_connect(self, flow: http.HTTPFlow) -> None:
        self._capture_credentials(flow)
        # Original PC mode checks game requests after TLS negotiation, allowing
        # browsers, Telegram and iOS connectivity checks to work normally.
        if CONFIG.get("proxy_access_mode") == "game_only":
            return
        authorized, reason = self.check_ip_authorized(flow)
        if not authorized:
            log("warn", f"[CHAN CONNECT] {reason}")
            flow.response = http.Response.make(403, BLOCK_MSG.encode("utf-8"),
                                               {"Content-Type": "text/plain; charset=utf-8"})

    async def request(self, flow: http.HTTPFlow) -> None:
        self._capture_credentials(flow)
        self._strip_bearer(flow)

        host = host_of(flow)
        path = path_only(flow)
        low = path.lower()

        local_hosts = {"localhost", "127.0.0.1", "::1", str(CONFIG.get("public_proxy_host", ""))}
        if host in local_hosts and path in ("/", "/status", "/healthz"):
            authorized, reason = self.check_ip_authorized(flow)
            if path == "/healthz":
                flow.response = http.Response.make(200, b"ok", {"Content-Type": "text/plain"})
            else:
                message = "IP da duoc cap quyen" if authorized else BLOCK_MSG
                page = ("<!doctype html><meta charset='utf-8'><title>Trang thai proxy</title>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        "<body style='font:18px system-ui;padding:24px'><h1>" + html.escape(message) +
                        "</h1><p>" + html.escape(reason) + "</p>"
                        "<p>Game tu hien thong bao loi cua game; trang nay hien ly do tu proxy.</p>")
                flow.response = http.Response.make(200, page.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})
            return

        # Direct VPS connection preserves the caller's address; do not trust spoofed headers.
        if host in local_hosts and path == "/get_ip":
            uid = flow.request.query.get("uid", "")
            to_url = flow.request.query.get("to", "")
            client_ip = flow.client_conn.address[0] if flow.client_conn and flow.client_conn.address else ""
            if not re.fullmatch(r"\d{1,20}", uid):
                flow.response = http.Response.make(400, b"Invalid Telegram uid")
                return
            try:
                parsed_ip = ipaddress.ip_address(client_ip)
                if parsed_ip.version == 6 and parsed_ip.ipv4_mapped:
                    parsed_ip = parsed_ip.ipv4_mapped
                client_ip = str(parsed_ip)
            except ValueError:
                flow.response = http.Response.make(400, b"Invalid peer IP")
                return
            if not parsed_ip.is_loopback:
                saved = await asyncio.to_thread(self._save_pending_ip, uid, client_ip)
                if not saved:
                    flow.response = http.Response.make(503, "Không ghi được IP vào Firebase. Hãy thử lại.".encode("utf-8"),
                                                       {"Content-Type": "text/plain; charset=utf-8"})
                    return
            if parsed_ip.is_loopback:
                if CONFIG.get("auth_mode") in ("tunnel_credentials", "tunnel_compat"):
                    firebase_pending = f"{FIREBASE_RTDB_URL}/pending_ips/{uid}.json"
                    script = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<p id="message">Đang nhận diện IP mạng...</p><script>
const pending = PENDING_URL;
const target = REDIRECT_URL;
fetch('https://api.ipify.org?format=json').then(r => {
  if (!r.ok) throw new Error('Không nhận diện được IP');
  return r.json();
}).then(d => fetch(pending, {
  method: 'PUT', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ip: d.ip, timestamp: Date.now()})
})).then(r => {
  if (!r.ok) throw new Error('Không lưu được IP');
  document.getElementById('message').textContent = 'Đã nhận diện IP. Quay lại Telegram để xác thực key.';
  if (target) window.location.href = target;
}).catch(e => { document.getElementById('message').textContent = e.message + '. Hãy thử lại.'; });
</script>"""
                    safe_target = to_url if urlparse(to_url).scheme in ("http", "https") else ""
                    script = script.replace("PENDING_URL", json.dumps(firebase_pending).replace("<", "\\u003c"))
                    script = script.replace("REDIRECT_URL", json.dumps(safe_target).replace("<", "\\u003c"))
                    flow.response = http.Response.make(200, script.encode("utf-8"),
                        {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})
                    return
                page = "Tunnel lam mat IP goc. Ket noi truc tiep toi VPS de xac thuc dung IP."
            else:
                page = "Da ghi nhan IP: " + html.escape(client_ip) + ". Quay lai Telegram de xac thuc key."
            if not parsed_ip.is_loopback and urlparse(to_url).scheme in ("http", "https"):
                flow.response = http.Response.make(302, b"", {"Location": to_url, "Cache-Control": "no-store"})
                return
            flow.response = http.Response.make(
                200,
                ("<!doctype html><meta charset='utf-8'><p>" + page + "</p>").encode("utf-8"),
                {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}
            )
            return

        protected_game = is_ff(host) and (is_main_fileinfo(path) or is_aim(path)
                                          or "login" in host or "login" in low or "ping" in low)
        if CONFIG.get("proxy_access_mode") == "game_only" and not protected_game:
            self._replace(flow, "request")
            return

        # VPS strict mode checks all traffic; PC compatibility checks game only.
        is_auth, reason = self.check_ip_authorized(flow)
        if not is_auth:
            flow.metadata["access_denied"] = True
            log("warn", f"[CHAN] {BLOCK_MSG} ({reason}) -> {host}{path}")
            if "login" in host or "login" in low or "ping" in low:
                flow.response = http.Response.make(
                    403,
                    json.dumps({
                        "status": 403,
                        "msg": BLOCK_MSG,
                        "error": BLOCK_MSG,
                        "message": BLOCK_MSG
                    }, ensure_ascii=False).encode("utf-8"),
                    {"Content-Type": "application/json; charset=utf-8"}
                )
            else:
                flow.response = http.Response.make(
                    403,
                    BLOCK_MSG.encode("utf-8"),
                    {"Content-Type": "text/plain; charset=utf-8"}
                )
            return

        self._replace(flow, "request")

    async def response(self, flow: http.HTTPFlow) -> None:
        if flow.response is None or flow.metadata.get("access_denied"):
            return
        path = path_only(flow)
        host = host_of(flow)

        if not is_ff(host):
            return

        if is_avatar(path):
            return

        if is_ff(host) and (is_main_fileinfo(path) or is_aim(path)):
            is_auth, reason = self.check_ip_authorized(flow)
            if not is_auth:
                flow.response = http.Response.make(
                    403,
                    BLOCK_MSG.encode("utf-8"),
                    {"Content-Type": "text/plain; charset=utf-8"}
                )
                return

        if is_aim(path) and self.aim:
            if flow.response.content != self.aim:
                self._serve(flow, self.aim, "application/octet-stream", "Thay codepatch")
                self.n_aim += 1
                self.waiting_aim = False
            return

        if is_main_fileinfo(path):
            self._serve_fileinfo_from_live(flow)
            return

        await asyncio.to_thread(self._failover_cdn, flow)

    def _serve_fileinfo_from_live(self, flow: http.HTTPFlow) -> None:
        if not self.sync():
            log("error", "local chưa ready, bỏ fileinfo live")
            return

        resp = flow.response
        body = (resp.content if resp is not None else None) or b""
        code = resp.status_code if resp is not None else 0

        src = "cdn"
        raw_text = ""
        if code == 200 and body and len(body) <= MAX_FI:
            if body[:2] == GZIP_MAGIC:
                try:
                    body = gzip.decompress(body)
                except OSError as e:
                    log("warn", f"fileinfo CDN gzip fail: {e}")
                    body = b""
            if body:
                raw_text = body.decode("utf-8", errors="replace")
        if not raw_text:
            log("warn", f"fileinfo CDN {code} {len(body)}B — fallback local")
            if not self.fi:
                log("error", "không có fileinfo local để fallback")
                return
            raw_text = self.fi.decode("utf-8", errors="replace")
            src = "local"

        patched = self._patch_fileinfo_text(raw_text)
        if patched is None:
            log("error", f"fileinfo {src} không có đúng 1 dòng {PATCH_KEY}")
            if src != "local" and self.fi:
                self._serve(flow, self.fi, "application/octet-stream", "Thay fileinfo (local fallback)")
                self.n_fi += 1
                self.waiting_aim = True
            return

        encoded = patched.encode("utf-8")
        if encoded != self.fi:
            try:
                if self.fi and not os.path.isfile(BAK_PATH):
                    atomic_write(BAK_PATH, self.fi)
                atomic_write(FILEINFO_PATH, encoded)
            except OSError as e:
                log("warn", f"không ghi fileinfo local: {e}")
            self.fi = encoded
            try:
                self.fi_mtime = os.path.getmtime(FILEINFO_PATH)
            except OSError:
                pass

        if resp is None or resp.content != encoded:
            self._serve(flow, encoded, "application/octet-stream", f"Thay fileinfo ({src}+codepatch)")
        self.n_fi += 1
        self.waiting_aim = True
        log("info", ">>> chờ PATCH: GET assembly-csharp-patch")

    def _failover_cdn(self, flow: http.HTTPFlow) -> None:
        if flow.response is None:
            return
        host = host_of(flow)
        path = path_only(flow)
        if not is_ff(host) or "/abhotupdates/" not in path.lower():
            return
        if is_aim(path) or is_main_fileinfo(path) or is_avatar(path):
            return
        code = flow.response.status_code
        if code not in (401, 403, 404, 410, 502, 503):
            return

        body = flow.response.content or b""
        preview = body[:160].decode("utf-8", errors="replace").replace("\n", " ")
        log("warn", f"bundle {code} từ {host} ({len(body)}B) {preview}")
        seen = {host}
        headers = {}
        for key in COPY_HDRS:
            val = flow.request.headers.get(key)
            if val:
                headers[key] = val
        raw_path = flow.request.path or path
        for alt in ALT_CDN:
            if alt in seen:
                continue
            seen.add(alt)
            url = f"https://{alt}{raw_path}"
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, context=self._ssl, timeout=4) as resp:
                    data = resp.read(MAX_FAILOVER + 1)
                    status = getattr(resp, "status", 200)
                    ctype = resp.headers.get("Content-Type") or "application/octet-stream"
            except urllib.error.HTTPError as e:
                log("warn", f"failover {alt} → HTTP {e.code}")
                continue
            except Exception as e:
                log("warn", f"failover {alt} fail: {type(e).__name__}: {e}")
                continue
            if status != 200 or not data or len(data) > MAX_FAILOVER:
                continue
            self._serve(flow, data, ctype, f"Failover bundle ← {alt}")
            self.n_fail += 1
            return

    def _apply_runtime_options(self) -> None:
        pairs = (
            ("connection_strategy", "lazy"),
            ("ssl_insecure", True),
            ("upstream_cert", False),
            ("http2", str(CONFIG.get("proxy_http2", "true")).lower() not in ("false", "0")),
        )
        for k, v in pairs:
            try:
                if getattr(ctx.options, k) != v:
                    setattr(ctx.options, k, v)
            except Exception:
                pass
        try:
            cur = list(ctx.options.allow_hosts or [])
            new = list(dict.fromkeys(cur + ALLOW_HOSTS))
            if new != cur:
                ctx.options.allow_hosts = new
        except Exception:
            pass
        try:
            if ctx.options.allow_hosts and ctx.options.ignore_hosts:
                ctx.options.ignore_hosts = []
        except Exception:
            pass

    @staticmethod
    def _strip_bearer(flow: http.HTTPFlow) -> None:
        try:
            h = flow.request.headers
            val = h.get("authorization")
            if val is not None:
                stripped = val.strip()
                if stripped.lower() == "bearer" or not stripped:
                    del h["authorization"]
                elif val != stripped:
                    h["authorization"] = stripped
        except Exception:
            pass

    def _replace(self, flow: http.HTTPFlow, where: str) -> None:
        try:
            on = bool(ctx.options.proxy_replace)
        except Exception:
            on = True
        if not on:
            return

        host = host_of(flow)
        if not is_ff(host):
            return

        path = path_only(flow)
        low = path.lower()
        if "/abhotupdates/" in low:
            log("info", f"cdn {where} {host}{path}")

        # fileinfo: để CDN trả bản đủ, chỉ sửa codepatch ở response.
        # avatar: không đụng.
        if not is_aim(path):
            return

        if not self.sync():
            log("error", f"local chưa ready, bỏ {path}")
            return

        if not self.aim or self.aim[:2] != GZIP_MAGIC:
            log("error", "codepatch local không phải gzip — không serve")
            return
        self._serve(flow, self.aim, "application/octet-stream", "Thay codepatch")
        self.n_aim += 1
        self.waiting_aim = False

    def _codepatch_line(self, gz: Optional[bytes] = None) -> Optional[str]:
        blob = self.aim if gz is None else gz
        if not blob or blob[:2] != GZIP_MAGIC:
            return None
        try:
            raw = gzip.decompress(blob)
        except OSError:
            return None
        return (
            f"{PATCH_KEY},{sha1_b64(raw)},{len(raw)},0,"
            f"{sha1_b64(blob)},{len(blob)},True,0"
        )

    def _dump_codepatch_candidates(self, text: str, tag: str) -> None:
        hits = 0
        for i, ln in enumerate(text.splitlines()):
            low = ln.lower()
            if "codepatch" in low or "assembly-csharp" in low or "assetindexer" in low:
                log("warn", f"{tag} L{i + 1}: {ln.strip()[:240]}")
                hits += 1
                if hits >= 8:
                    break
        if not hits:
            log("warn", f"{tag}: không thấy dòng codepatch/assembly-csharp/assetindexer")

    def _patch_fileinfo_text(self, text: str) -> Optional[str]:
        line = self._codepatch_line()
        if not line:
            return None
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
        found = list(LINE_RE.finditer(text))
        if len(found) != 1:
            log("warn", f"fileinfo cần đúng 1 dòng {PATCH_KEY}, gặp {len(found)}")
            self._dump_codepatch_candidates(text, "fileinfo")
            return None
        old = found[0].group(0).strip()
        if old == line:
            return text
        return LINE_RE.sub(line, text, count=1)

    @staticmethod
    def _serve(flow: http.HTTPFlow, body: bytes, ctype: str, tag: str) -> None:
        flow.response = http.Response.make(
            200,
            body,
            {
                "Content-Type": ctype,
                "Content-Length": str(len(body)),
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
        log("info", f"[OK] {tag} {len(body)}B")

    @staticmethod
    def _resolve_patch() -> str:
        for path in PATCH_CANDIDATES:
            if os.path.isfile(path) and os.path.getsize(path) > 20:
                return path
        return ""

    @staticmethod
    def _as_gzip(blob: bytes, src_path: str) -> Tuple[Optional[bytes], str]:
        if blob[:2] == GZIP_MAGIC:
            return blob, src_path
        if blob[:7] == UNITYFS_MAGIC or blob[:8] == b"UnityRaw":
            gz_path = os.path.join(BASE, "assembly-csharp-patch.gz")
            packed = gzip.compress(blob, compresslevel=9, mtime=0)
            try:
                if (
                    not os.path.isfile(gz_path)
                    or os.path.getsize(gz_path) != len(packed)
                ):
                    atomic_write(gz_path, packed)
            except OSError as e:
                log("warn", f"không ghi {gz_path}: {e}")
            return packed, src_path
        return None, src_path

    def sync(self, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and self.ready and now < self.next_stat:
            return True
        self.next_stat = now + 2.0

        patch_path = self._resolve_patch()
        if not patch_path:
            self.ready = False
            return False
        try:
            am = os.path.getmtime(patch_path)
            fm = os.path.getmtime(FILEINFO_PATH) if os.path.isfile(FILEINFO_PATH) else -1.0
        except OSError:
            self.ready = False
            return False

        if (
            not force
            and self.ready
            and self.aim is not None
            and am == self.aim_mtime
            and fm == self.fi_mtime
            and self.patch_path == patch_path
        ):
            return True

        try:
            if os.path.getsize(patch_path) > MAX_AIM:
                log("error", "file quá lớn")
                self.ready = False
                return False
            with open(patch_path, "rb") as f:
                blob = f.read()
            gz, _hint = self._as_gzip(blob, patch_path)
            if gz is None:
                log("error", "codepatch không đọc được (cần UnityFS hoặc gzip)")
                self.ready = False
                return False
        except OSError as e:
            log("error", f"đọc file fail: {e}")
            self.ready = False
            return False

        if len(gz) < 20 or gz[:2] != GZIP_MAGIC:
            log("error", "codepatch gzip invalid")
            self.ready = False
            return False
        try:
            raw = gzip.decompress(gz)
        except OSError as e:
            log("error", f"decompress codepatch fail: {e}")
            self.ready = False
            return False

        fi = b""
        if os.path.isfile(FILEINFO_PATH):
            try:
                if os.path.getsize(FILEINFO_PATH) > MAX_FI:
                    log("error", "fileinfo quá lớn")
                else:
                    with open(FILEINFO_PATH, "rb") as f:
                        fi = f.read()
            except OSError as e:
                log("warn", f"đọc fileinfo fail: {e}")

        raw_hash = sha1_b64(raw)
        gz_hash = sha1_b64(gz)
        log("info", f"codepatch Hash={raw_hash} ZipHash={gz_hash} raw={len(raw)} gz={len(gz)}")
        self.aim = gz

        # Chỉ patch dòng codepatch nếu local fileinfo có sẵn. Không đụng avatar.
        if fi:
            text = fi.decode("utf-8", errors="replace")
            patched = self._patch_fileinfo_text(text)
            if patched is not None:
                encoded = patched.encode("utf-8")
                if encoded != fi:
                    try:
                        if not os.path.isfile(BAK_PATH):
                            atomic_write(BAK_PATH, fi)
                        atomic_write(FILEINFO_PATH, encoded)
                    except OSError as e:
                        log("warn", f"ghi fileinfo fail: {e}")
                    else:
                        fi = encoded
                        log("info", f"fileinfo local patched {PATCH_KEY}")
            else:
                log("warn", f"fileinfo local không có đúng 1 dòng {PATCH_KEY} — chờ bản CDN")
        else:
            log("info", "chưa có fileinfo local — sẽ lấy từ CDN rồi chỉ sửa codepatch")

        self.fi = fi or None
        self.aim = gz
        self.patch_path = patch_path
        self.aim_mtime = am
        try:
            self.fi_mtime = os.path.getmtime(FILEINFO_PATH) if os.path.isfile(FILEINFO_PATH) else -1.0
        except OSError:
            self.fi_mtime = -1.0
        self.ready = True
        kind = "UnityFS" if raw[:7] == UNITYFS_MAGIC else "raw"
        log(
            "info",
            f"sync ok src={os.path.basename(patch_path)} {kind} "
            f"raw={len(raw)} gz={len(gz)} fi={len(self.fi or b'')}",
        )
        return True


addons = [FFHotUpdateAddon()]

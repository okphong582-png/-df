"""Exercise the actual addon lifecycle and async hooks over a local socket."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import ssl
import shutil
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@pytest.mark.parametrize("mode", ["strict", "pc_compat"])
def test_mitmdump_startup_status_and_real_403(tmp_path, mode):
    class Firebase(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({}).encode())

        def log_message(self, *args):
            pass

    fake = ThreadingHTTPServer(("127.0.0.1", 0), Firebase)
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = os.environ.copy()
    env["FIREBASE_URL"] = f"http://127.0.0.1:{fake.server_port}"
    env["PUBLIC_PROXY_HOST"] = "127.0.0.1"
    if mode == "pc_compat":
        env.update(AUTH_MODE="tunnel_compat", PROXY_ACCESS_MODE="game_only", PROXY_HTTP2="false")
    else:
        env.update(AUTH_MODE="direct", PROXY_ACCESS_MODE="strict")
    engine = shutil.which("mitmdump") if mode == "pc_compat" else None
    command = [engine] if engine else [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()"]
    command += ["--listen-host", "127.0.0.1", "--listen-port", str(port),
               "--set", f"confdir={tmp_path / 'ca'}", "-s", "proxy1.py"]
    log_path = tmp_path / "proxy.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            session = requests.Session()
            session.trust_env = False
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError(log_path.read_text(encoding="utf-8"))
                try:
                    if session.get(base + "/healthz", timeout=0.3).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Proxy failed to start")
            status = session.get(base + "/status", timeout=3)
            assert "Cút khỏi server ch có quyền truy cập" in status.text
            denied = session.post("http://loginbp.ppmainecoonghj.com/MajorLogin",
                                  proxies={"http": base}, timeout=3)
            assert denied.status_code == 403
            assert denied.json()["message"] == "Cút khỏi server ch có quyền truy cập"
            if mode == "pc_compat":
                internet = session.get(f"http://127.0.0.1:{fake.server_port}/internet-check",
                                       proxies={"http": base}, timeout=3)
                assert internet.status_code == 200
                # Test a real HTTPS CONNECT to an unrelated, local TLS origin
                # with no active game grant: connectivity must remain available.
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
                now = datetime.datetime.now(datetime.timezone.utc)
                cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                        .public_key(key.public_key()).serial_number(x509.random_serial_number())
                        .not_valid_before(now - datetime.timedelta(minutes=1))
                        .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
                cert_path, key_path = tmp_path / "origin.pem", tmp_path / "origin.key"
                cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
                key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
                tls_origin = ThreadingHTTPServer(("127.0.0.1", 0), Firebase)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(cert_path, key_path)
                tls_origin.socket = context.wrap_socket(tls_origin.socket, server_side=True)
                threading.Thread(target=tls_origin.serve_forever, daemon=True).start()
                try:
                    with pytest.warns(requests.packages.urllib3.exceptions.InsecureRequestWarning):
                        internet = session.get(f"https://127.0.0.1:{tls_origin.server_port}/internet-check",
                                               proxies={"https": base}, verify=False, timeout=5)
                    assert internet.status_code == 200
                finally:
                    tls_origin.shutdown()
                    tls_origin.server_close()
        finally:
            process.terminate()
            process.wait(timeout=10)
            fake.shutdown()
            fake.server_close()
    output = log_path.read_text(encoding="utf-8", errors="replace")
    assert "Addon error" not in output
    assert "error in script" not in output.lower()

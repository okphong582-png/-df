"""Exercise the actual addon lifecycle and async hooks over a local socket."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


def test_mitmdump_startup_status_and_real_403(tmp_path):
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
    command = [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()",
               "--listen-host", "127.0.0.1", "--listen-port", str(port),
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
        finally:
            process.terminate()
            process.wait(timeout=10)
            fake.shutdown()
            fake.server_close()
    output = log_path.read_text(encoding="utf-8", errors="replace")
    assert "Addon error" not in output
    assert "error in script" not in output.lower()

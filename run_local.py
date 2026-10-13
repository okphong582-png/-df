"""PC launcher: visible MITM + Bore windows, optional bot, scoped restarts."""
import argparse
import os
import shutil
import socket
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys
import time
from pathlib import Path
from settings import load_config

BASE = Path(__file__).resolve().parent


def build_commands(direct=False, proxy_only=False):
    config = load_config()
    port = int(config.get("public_proxy_port", 1297))
    engine = shutil.which("mitmdump")
    proxy = [engine] if engine else [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()"]
    proxy += ["--listen-host", "0.0.0.0", "--listen-port", str(port),
              "--set", "block_global=false", "--ssl-insecure",
              "--set", "connection_strategy=lazy", "--set", "upstream_cert=false",
              "--set", "flow_detail=0", "--set", "termlog_verbosity=error",
              "-s", "proxy1.py"]
    commands = {
        "proxy": proxy,
    }
    if not direct:
        bore = BASE / "bore.exe"
        if not bore.is_file():
            raise SystemExit("Thieu bore.exe trong thu muc. Chua the tao tunnel public.")
        # Avoid IPv6/localhost ambiguity: MITM listens on IPv4, so forward to
        # 127.0.0.1 explicitly. Keep the public server on its resolved IPv4 too.
        server_ip = socket.gethostbyname("bore.pub")
        commands["bore"] = [str(bore), "local", str(port), "--local-host", "127.0.0.1",
                            "--to", server_ip, "-p", str(port)]
    if not proxy_only:
        commands["bot"] = [sys.executable, "bot.py"]
    return commands


def child_environment(direct=False):
    env = os.environ.copy()
    if not direct:
        env.update(AUTH_MODE="tunnel_compat", PROXY_ACCESS_MODE="game_only", PROXY_HTTP2="false")
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(PYTHONUNBUFFERED="1", RUST_LOG="warn", NO_COLOR="1")
    return env


def worker(name, command, env):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW({"proxy": "MITMDump Server", "bore": "Bore Public Tunnel", "bot": "Telegram Bot"}[name])
    child = None
    (BASE / "logs").mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(BASE / "logs" / f"{name}.log", maxBytes=2 * 1024 * 1024,
                                  backupCount=2, encoding="utf-8")
    logger.addHandler(handler)
    try:
        while True:
            print(f"[{name}] Starting; Ctrl+C stops this service.", flush=True)
            child = subprocess.Popen(command, cwd=BASE, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            last_print = {}
            for line in child.stdout:
                logger.info(line.rstrip())
                # Repeated dropped socket errors must not flood the console.
                signature = "socket-drop" if "10053" in line else line.strip()
                now = time.monotonic()
                if now - last_print.get(signature, -100) >= 30:
                    print(line, end="", flush=True)
                    last_print[signature] = now
            code = child.wait()
            print(f"[{name}] Exited ({code}); retry in 5 seconds.", flush=True)
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
        handler.close()
        logger.removeHandler(handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-only", action="store_true")
    parser.add_argument("--direct", action="store_true", help="No Bore; exact-IP VPS/LAN mode")
    parser.add_argument("--show-windows", action="store_true")
    parser.add_argument("--worker", choices=("proxy", "bore", "bot"))
    args = parser.parse_args()
    commands = build_commands(args.direct, args.proxy_only)
    env = child_environment(args.direct)
    if args.worker:
        worker(args.worker, commands[args.worker], env)
        return
    port = int(load_config().get("public_proxy_port", 1297))
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(f"Cong {port} dang duoc su dung. Chi mo mot launcher; dung ban proxy cu truoc.")
    children = {}
    try:
        for name in commands:
            command = [sys.executable, str(BASE / "run_local.py"), "--worker", name]
            if args.direct:
                command.append("--direct")
            if args.proxy_only:
                command.append("--proxy-only")
            flags = subprocess.CREATE_NEW_CONSOLE if args.show_windows and os.name == "nt" else 0
            children[name] = subprocess.Popen(command, cwd=BASE, env=env, creationflags=flags)
        print("MITM va Bore da duoc goi. Xem log trong tung cua so de biet da ket noi hay chua.", flush=True)
        print("Bore phai bao listening/connected thi IP public moi dung duoc. Ctrl+C de dung.", flush=True)
        while all(child.poll() is None for child in children.values()):
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping this launcher's services...", flush=True)
    finally:
        for child in children.values():
            if child.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    child.send_signal(__import__("signal").SIGINT)
        for child in children.values():
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()

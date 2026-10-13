"""Supervise only our own child processes; Ctrl+C stops them cleanly."""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    commands = {
        "proxy": [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()",
                  "--listen-host", "0.0.0.0", "--listen-port", "1297",
                  "--set", "block_global=false", "--set", "connection_strategy=lazy", "-s", "proxy1.py"],
        "bot": [sys.executable, "bot.py"],
    }
    children = {}
    try:
        while True:
            for name, command in commands.items():
                child = children.get(name)
                if child is None or child.poll() is not None:
                    print(f"Starting {name} (restart if exited)", flush=True)
                    children[name] = subprocess.Popen(command, cwd=BASE)
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopping proxy and bot...", flush=True)
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()

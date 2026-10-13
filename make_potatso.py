"""Export a standard HTTP proxy URI, QR and selective Wi-Fi PAC file."""
import argparse
import base64
import ipaddress
import json
from pathlib import Path
from urllib.parse import quote
from proxy_accounts import proxy_uri


def export(host, port, output, name="FF Proxy", username=None, password=None):
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    try:
        parsed = ipaddress.ip_address(host)
        uri_host = f"[{host}]" if parsed.version == 6 else host
    except ValueError:
        if not host or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in host):
            raise ValueError("Invalid IP/domain")
        uri_host = host
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    uri = f"http://{uri_host}:{port}#{quote(name)}"
    if username is not None or password is not None:
        if not username or not password:
            raise ValueError("Both username and password are required")
        uri = proxy_uri(host, port, username, password)
    (output / "potatso-uri.txt").write_text(uri + "\n", encoding="utf-8")
    # Subscription transports use a base64 list of URIs.
    (output / "potatso-subscription.txt").write_text(base64.b64encode(uri.encode()).decode() + "\n", encoding="ascii")
    pac = '''function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  var domains = ["freefiremobile.com", "purplevioleto.com", "ppmainecoonghj.com"];
  for (var i = 0; i < domains.length; i++) {
    if (host === domains[i] || dnsDomainIs(host, "." + domains[i])) return PROXY_VALUE;
  }
  return "DIRECT";
}
'''.replace("PROXY_VALUE", json.dumps(f"PROXY {uri_host}:{port}"))
    if username is None:
        # PAC has no standard way to carry per-user HTTP Basic credentials.
        (output / "game-only.pac").write_text(pac, encoding="utf-8")
    try:
        import qrcode
        qrcode.make(uri).save(output / "potatso-qr.png")
    except ImportError:
        print("Install qrcode[pil] for QR export")
    print(f"Exported configuration for {host}:{port} to {output}")
    return uri


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=1297)
    parser.add_argument("--output")
    parser.add_argument("--username", help="Telegram user ID; password is prompted privately")
    args = parser.parse_args()
    password = __import__("getpass").getpass("Proxy password: ") if args.username else None
    output = args.output or ("dist/potatso" if args.username else "client")
    export(args.host, args.port, output, username=args.username, password=password)

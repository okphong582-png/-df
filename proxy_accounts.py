"""Per-user proxy secrets. Only their hashes are stored with active grants."""
import hashlib
import secrets
from urllib.parse import quote


def new_secret():
    secret = secrets.token_urlsafe(32)
    return secret, hashlib.sha256(secret.encode("utf-8")).hexdigest()


def proxy_uri(host, port, username, password):
    address = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{quote(str(username), safe='')}:{quote(password, safe='')}@{address}:{int(port)}#FFProxy"

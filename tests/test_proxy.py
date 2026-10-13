import asyncio
import base64
import gzip
import time
from types import SimpleNamespace
from unittest.mock import patch

from mitmproxy import http
import proxy1
from make_potatso import export
from settings import load_config


def flow(ip="203.0.113.10", url="https://loginbp.ppmainecoonghj.com/MajorLogin"):
    return SimpleNamespace(client_conn=SimpleNamespace(address=(ip, 1234)),
                           request=http.Request.make("POST", url), response=None, metadata={})


def addon():
    instance = proxy1.FFHotUpdateAddon()
    instance.auth_cache_time = time.monotonic()
    instance.auth_cache = {"203_0_113_10": {"expiresAt": (time.time() + 3600) * 1000}}
    return instance


def test_request_does_not_fetch_firebase():
    instance = addon()
    with patch.object(instance, "_refresh_auth_cache", side_effect=AssertionError("network on request")):
        for _ in range(100):
            assert instance.check_ip_authorized(flow())[0]
            assert not instance.check_ip_authorized(flow("203.0.113.11"))[0]


def test_no_tunnel_or_subnet_or_forward_header_bypass():
    instance = addon()
    for ip in ("127.0.0.1", "10.1.2.3", "203.0.113.11"):
        request = flow(ip)
        request.request.headers["X-Forwarded-For"] = "203.0.113.10"
        assert not instance.check_ip_authorized(request)[0]


def test_expired_and_stale_grants_denied():
    instance = addon()
    instance.auth_cache["203_0_113_10"]["expiresAt"] = 1
    assert not instance.check_ip_authorized(flow())[0]
    instance = addon()
    instance.auth_cache_time -= 16
    assert not instance.check_ip_authorized(flow())[0]


def test_login_denial_preserved_after_response():
    instance = addon()
    request = flow("203.0.113.11")
    asyncio.run(instance.request(request))
    assert request.response.status_code == 403
    assert request.response.json()["message"] == proxy1.BLOCK_MSG
    asyncio.run(instance.response(request))
    assert request.response.json()["message"] == proxy1.BLOCK_MSG


def test_no_open_connect_or_http_proxy():
    instance = addon()
    request = flow("203.0.113.11", "https://example.org/")
    instance.http_connect(request)
    assert request.response.status_code == 403
    request = flow("203.0.113.11", "http://example.org/")
    asyncio.run(instance.request(request))
    assert request.response.status_code == 403


def test_host_boundary_and_non_game_passthrough():
    assert proxy1.is_ff("core-gmc.freefiremobile.com")
    assert not proxy1.is_ff("evilfreefiremobile.com")
    assert not proxy1.is_ff("freefiremobile.com.attacker.example")
    instance = addon()
    request = flow(url="https://example.org/codepatch/assembly-csharp-patch")
    request.response = http.Response.make(200, b"unchanged")
    asyncio.run(instance.response(request))
    assert request.response.content == b"unchanged"


def test_status_and_health_without_grant():
    instance = addon()
    request = flow("203.0.113.11", "http://127.0.0.1:1297/status")
    asyncio.run(instance.request(request))
    assert proxy1.BLOCK_MSG in request.response.text
    request = flow(url="http://127.0.0.1:1297/healthz")
    asyncio.run(instance.request(request))
    assert request.response.text == "ok"


def test_ip_capture_uses_peer_and_rejects_injected_uid():
    instance = addon()
    request = flow(url="http://127.0.0.1:1297/get_ip?uid=12345")
    request.request.headers["X-Forwarded-For"] = "198.51.100.1"
    with patch.object(instance, "_save_pending_ip") as save:
        asyncio.run(instance.request(request))
        save.assert_called_once_with("12345", "203.0.113.10")
    request = flow(url="http://127.0.0.1:1297/get_ip?uid=bad%22%3Cscript%3E")
    asyncio.run(instance.request(request))
    assert request.response.status_code == 400


def test_patch_gzip_integrity():
    instance = addon()
    assert instance.sync(force=True)
    assert gzip.decompress(instance.aim).startswith(b"UnityFS")
    assert instance._patch_fileinfo_text(instance.fi.decode()).count(proxy1.PATCH_KEY) == 1


def test_potatso_export(tmp_path):
    uri = export("203.0.113.10", 1297, tmp_path)
    assert uri.startswith("http://203.0.113.10:1297#")
    assert base64.b64decode((tmp_path / "potatso-subscription.txt").read_text()).decode() == uri
    assert 'return "DIRECT"' in (tmp_path / "game-only.pac").read_text()


def test_environment_overrides_local_config(monkeypatch):
    monkeypatch.setenv("PUBLIC_PROXY_HOST", "203.0.113.12")
    assert load_config()["public_proxy_host"] == "203.0.113.12"

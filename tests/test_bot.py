from types import SimpleNamespace
from unittest.mock import patch
import time
import hashlib

import bot as app


def message():
    return SimpleNamespace(chat=SimpleNamespace(id=123), message_id=1,
                           from_user=SimpleNamespace(id=123, username="test", first_name="Test"),
                           text="TEST-KEY 203.0.113.10")


def test_failed_grant_never_consumes_key_or_reports_success():
    app.waiting_for_key["123"] = True
    with patch.object(app, "fb_get", return_value={"record": {"key": "TEST-KEY"}}), \
         patch.object(app, "fb_put", return_value=False), \
         patch.object(app, "fb_delete") as delete, \
         patch.object(app.bot, "delete_message"), \
         patch.object(app.bot, "send_message") as send, \
         patch.object(app, "safe_edit_menu") as edit:
        app.handle_text_messages(message())
        delete.assert_not_called()
        edit.assert_not_called()
        assert "chưa bị xóa" in send.call_args.args[1]
        assert app.waiting_for_key["123"]


def test_successful_grant_uses_configured_endpoint():
    app.waiting_for_key["123"] = True
    with patch.object(app, "fb_get", return_value={"record": {"key": "TEST-KEY"}}), \
         patch.object(app, "fb_put", return_value=True) as put, \
         patch.object(app, "fb_delete", return_value=True), \
         patch.object(app.bot, "delete_message"), \
         patch.object(app, "safe_edit_menu") as edit:
        app.handle_text_messages(message())
        assert put.call_args.args[0] == "authorized_ips/203_0_113_10"
        assert len(put.call_args.args[1]["proxyTokenHash"]) == 64
        assert "Username:" in edit.call_args.args[1]
        assert f"{app.PUBLIC_PROXY_HOST}:{app.PUBLIC_PROXY_PORT}" in edit.call_args.args[1]
        assert not app.waiting_for_key["123"]


def test_issue_credentials_requires_active_owner_and_conditional_write():
    row = {"userId": "123", "expiresAt": (time.time() + 3600) * 1000}
    response = SimpleNamespace(status_code=200, headers={"ETag": '"version-1"'}, json=lambda: dict(row))
    with patch.object(app, "fb_get", return_value={"row": row}), \
         patch.object(app.requests, "get", return_value=response), \
         patch.object(app.requests, "put", return_value=SimpleNamespace(status_code=200)) as put:
        secret = app.issue_proxy_credentials("123")
        assert secret
        assert put.call_args.kwargs["headers"]["If-Match"] == '"version-1"'
        assert put.call_args.kwargs["json"]["proxyTokenHash"] == hashlib.sha256(secret.encode()).hexdigest()
    with patch.object(app, "fb_get", return_value={"row": row}), patch.object(app.requests, "get") as get:
        assert app.issue_proxy_credentials("456") is None
        get.assert_not_called()


def test_concurrent_revoke_never_recreates_grant():
    row = {"userId": "123", "expiresAt": (time.time() + 3600) * 1000}
    response = SimpleNamespace(status_code=200, headers={"ETag": '"version-1"'}, json=lambda: dict(row))
    with patch.object(app, "fb_get", return_value={"row": row}), \
         patch.object(app.requests, "get", return_value=response), \
         patch.object(app.requests, "put", return_value=SimpleNamespace(status_code=412)) as put:
        assert app.issue_proxy_credentials("123") is None
        assert put.call_count == 1
    revoked = SimpleNamespace(status_code=200, headers={"ETag": '"deleted"'}, json=lambda: None)
    with patch.object(app, "fb_get", return_value={"row": row}), \
         patch.object(app.requests, "get", return_value=revoked), \
         patch.object(app.requests, "put") as put:
        assert app.issue_proxy_credentials("123") is None
        put.assert_not_called()

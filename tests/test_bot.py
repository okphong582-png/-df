from types import SimpleNamespace
from unittest.mock import patch

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
        assert f"{app.PUBLIC_PROXY_HOST}:{app.PUBLIC_PROXY_PORT}" in edit.call_args.args[1]
        assert not app.waiting_for_key["123"]

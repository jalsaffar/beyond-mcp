from unittest.mock import MagicMock, patch

import pytest

from beyond_mcp.config import BeyondConfig
from beyond_mcp.talk import PangoTalkClient


def _client(**kwargs) -> PangoTalkClient:
    return PangoTalkClient(BeyondConfig(host="127.0.0.1", **kwargs))


def test_send_drains_banner_enables_echo_then_frames_command():
    sock = MagicMock()
    sock.recv.side_effect = [b"Welcome to BEYOND!\r\n", b"OK\r\n", b"OK\r\n"]
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    with patch("beyond_mcp.talk.socket.create_connection", return_value=sock) as cc:
        result = _client().send("EnableLaserOutput")
    cc.assert_called_once_with(("127.0.0.1", 16063), timeout=3.0)
    assert [c.args[0] for c in sock.sendall.call_args_list] == [
        b"Echo 1\r\n", b"EnableLaserOutput\r\n"]
    assert result["acknowledged"] is True
    assert result["rejected"] is False
    assert result["port"] == 16063


def test_send_reports_error_reply():
    sock = MagicMock()
    sock.recv.side_effect = [
        b"Welcome to BEYOND!\r\n", b"OK\r\n",
        b"ERROR Line: 1, Error: Unknown command: nosuchcommand\r\n"]
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    with patch("beyond_mcp.talk.socket.create_connection", return_value=sock):
        result = _client().send("NoSuchCommand")
    assert result["rejected"] is True
    assert result["acknowledged"] is False
    assert "Unknown command" in result["reply"]


def test_send_rejects_multiline_command():
    with pytest.raises(ValueError, match="One command per call"):
        _client().send("EnableLaserOutput\r\nBlackout")


def test_send_rejects_empty_command():
    with pytest.raises(ValueError, match="must not be empty"):
        _client().send("   ")


def test_send_respects_allowed_hosts():
    config = BeyondConfig(host="10.9.9.9")
    with pytest.raises(ValueError, match="not in BEYOND_ALLOWED_HOSTS"):
        PangoTalkClient(config).send("EnableLaserOutput")


def test_talk_port_env_override(monkeypatch):
    from beyond_mcp.config import load_config
    monkeypatch.setenv("BEYOND_TALK_PORT", "26063")
    assert load_config().talk_port == 26063


def test_default_ports_match_beyond_defaults():
    config = BeyondConfig()
    assert config.osc_port == 8000
    assert config.talk_port == 16063


def test_probe_unreachable_includes_hint():
    with patch("beyond_mcp.talk.socket.create_connection", side_effect=OSError("refused")):
        result = _client().probe()
    assert result["reachable"] is False
    assert "Enable the PangoTalk TCP server" in result["hint"]

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from beyond_mcp.config import BeyondConfig, load_config
from beyond_mcp.http_api import BeyondHttpClient, BeyondHttpError


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _client(**kwargs) -> BeyondHttpClient:
    return BeyondHttpClient(BeyondConfig(host="127.0.0.1", **kwargs))


def _serve(*bodies):
    replies = [_Reply(b if isinstance(b, bytes) else json.dumps(b).encode()) for b in bodies]
    return patch("beyond_mcp.http_api._opener.open", side_effect=replies)


def test_default_http_port_and_env_override(monkeypatch):
    assert BeyondConfig().http_port == 8088
    monkeypatch.setenv("BEYOND_HTTP_PORT", "9099")
    assert load_config().http_port == 9099


def test_page_cues_skips_empty_and_gives_both_numberings():
    body = {"info": {"pageName": "Static 1"}, "cue": [
        {"name": "A", "comment": "", "empty": False},
        {"name": "", "comment": "", "empty": True},
        {"name": "C", "comment": "x", "empty": False}]}
    with _serve(body) as opened:
        result = _client().page_cues(4)
    assert opened.call_args.args[0] == "http://127.0.0.1:8088/apiv1/ws/page?index=4"
    assert result["script_page"] == 5
    assert [(c["cue"], c["script_cue"], c["name"]) for c in result["cues"]] == [(0, 1, "A"), (2, 3, "C")]


def test_pages_add_script_numbers():
    body = {"grid": {"pageCount": 1}, "categoryName": ["STATIC"],
            "allPages": [{"name": "Static 1", "category": "STATIC", "page": 0}]}
    with _serve(body):
        result = _client().pages()
    assert result["pages"] == [{"page": 0, "script_page": 1, "name": "Static 1", "category": "STATIC"}]


def test_control_characters_inside_names_parse():
    with _serve(b'{"cue":[{"name":"LINE\x01ONE","empty":false}],"info":{}}'):
        assert _client().page_cues(0)["cues"][0]["name"] == "LINE\x01ONE"


def test_cue_strips_fx_slots():
    with _serve({"caption": "SHEET", "fX1": -1, "fX1Action": 100, "brightness": 90}):
        assert _client().cue(0, 0) == {"caption": "SHEET", "brightness": 90}


def test_zones_are_trimmed_unless_geometry_asked():
    body = {"count": 1, "items": [{"name": "B5", "projectorIndex": 23, "uGC": {"sizeX": 50}, "hue": 0}]}
    with _serve(body):
        plain = _client().zones()
    with _serve(body):
        full = _client().zones(include_geometry=True)
    assert "hue" not in plain["zones"][0] and "geometry" not in plain["zones"][0]
    assert plain["zones"][0]["projector_index"] == 23
    assert full["zones"][0]["geometry"] == {"sizeX": 50}


def test_master_merges_bpm():
    with _serve({"bPM": 128.0, "tcInEnabled": 1}, {"brightness": 100}) as opened:
        result = _client().master()
    assert result == {"live_control": {"brightness": 100}, "bpm": 128.0, "timecode_in_enabled": 1}
    assert opened.call_count == 2


@pytest.mark.parametrize("path", [
    "/apiv1/playlist/play", "/apiv1/playlist/stop", "/apiv1/playlist/next",
    "/apiv1/ps/cmd/EnableLaserOutput", "/apiv1/ps/execscript"])
def test_routes_that_act_are_refused_before_any_request(path):
    with patch("beyond_mcp.http_api._opener.open") as opened:
        with pytest.raises(ValueError, match="read-only list"):
            _client()._get(path)
    opened.assert_not_called()


def test_negative_numbers_rejected():
    with pytest.raises(ValueError):
        _client().page_cues(-1)
    with pytest.raises(ValueError):
        _client().cue(0, -1)


def test_respects_allowed_hosts():
    with patch("beyond_mcp.http_api._opener.open") as opened:
        with pytest.raises(ValueError, match="not in BEYOND_ALLOWED_HOSTS"):
            BeyondHttpClient(BeyondConfig(host="10.9.9.9")).pages()
    opened.assert_not_called()


def test_ipv6_host_is_bracketed():
    assert BeyondHttpClient(BeyondConfig(host="::1")).base_url == "http://[::1]:8088"


def test_probe_reports_absent_server_with_hint():
    with patch("beyond_mcp.http_api._opener.open", side_effect=urllib.error.URLError("refused")):
        result = _client().probe()
    assert result["reachable"] is False
    assert "Ultimate" in result["hint"]


def test_probe_reports_grid():
    with _serve({"grid": {"pageCount": 122, "colCount": 8, "rowCount": 5}, "allPages": []}):
        result = _client().probe()
    assert result["reachable"] is True
    assert (result["page_count"], result["grid_columns"], result["grid_rows"]) == (122, 8, 5)


def test_http_error_carries_status():
    error = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error":"nope"}'))
    with patch("beyond_mcp.http_api._opener.open", side_effect=error):
        with pytest.raises(BeyondHttpError, match="400"):
            _client().pages()

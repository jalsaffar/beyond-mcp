"""The read-only workspace reader: BEYOND.ini keys, exported page names, file listings — against a temp BEYOND folder."""
from pathlib import Path

from beyond_mcp import workspace

INI = "[Main]\nLastWorkspaceFileName2=C:\\x\\WORKSPACES\\SHOWSPACE.BeyondWorkspace\nTalkServerActive=1\nUdpTalkPort=16062\n"


def _home(tmp_path: Path) -> Path:
    (tmp_path / "BEYOND.ini").write_text(INI, encoding="utf-8")
    pages = tmp_path / "PAGES" / "SHOWSPACE"
    pages.mkdir(parents=True)
    for n, name in ((1, "STATIC"), (7, "HOT CUES"), (38, "SACRED LASERS")):
        (pages / f"Page_{n:03d}_{name}.BeyondPage").write_bytes(b"PANGOLINxPage01")
    (pages / "odd.BeyondPage").write_bytes(b"x")
    z = tmp_path / "PROJECTION ZONES"
    z.mkdir()
    (z / "2025 CIRCLE.bzones").write_bytes(b"PANGOLINLxZl001")
    return tmp_path


def test_read_ini_picks_the_operator_keys(tmp_path):
    info = workspace.read_ini(_home(tmp_path))
    assert info["LastWorkspaceFileName2"].endswith("SHOWSPACE.BeyondWorkspace")
    assert info["TalkServerActive"] == "1" and info["UdpTalkPort"] == "16062"
    assert workspace.workspace_stem(tmp_path) == "SHOWSPACE"


def test_read_ini_missing_is_empty(tmp_path):
    assert workspace.read_ini(tmp_path) == {}
    assert workspace.pages(tmp_path)["count"] == 0


def test_pages_come_from_export_file_names(tmp_path):
    out = workspace.pages(_home(tmp_path))
    assert out["workspace"] == "SHOWSPACE" and out["count"] == 4
    by = {r["page"]: r["name"] for r in out["pages"]}
    assert by[1] == "STATIC" and by[7] == "HOT CUES" and by[38] == "SACRED LASERS" and by[None] == "odd"


def test_files_lists_a_kind_and_rejects_unknown(tmp_path):
    out = workspace.files("zones", _home(tmp_path))
    assert out["count"] == 1 and out["files"][0]["name"] == "2025 CIRCLE"
    try:
        workspace.files("nonsense", tmp_path)
    except ValueError as ex:
        assert "kind must be" in str(ex)
    else:
        raise AssertionError("unknown kind accepted")


def test_tools_registered():
    from beyond_mcp.server import mcp as server_mcp

    names = set(server_mcp._tool_manager._tools)
    assert {"workspace_info", "workspace_pages", "workspace_files"} <= names

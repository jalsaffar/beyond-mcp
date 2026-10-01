"""Read-only view of the BEYOND installation folder (Dropbox/BEYOND555 by default): which workspace is loaded, the
Talk-server settings, and the exported page / zone / projector / show files by name.

BEYOND's own files (.BeyondWorkspace, .BeyondPage, .bzones, .BSHW ...) are proprietary containers ("PANGOLIN…" header,
"PFCh01" chunks) that are compressed — cue and zone NAMES inside them are not recoverable offline. What IS readable:
the workspace path and network settings in BEYOND.ini, and the page NUMBERS + NAMES that BEYOND writes into the file
names when pages are exported (PAGES/<workspace>/Page_NNN_<name>.BeyondPage). Nothing here touches the network or writes.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

_KINDS = {
    "pages": ("PAGES", "*.BeyondPage"),
    "zones": ("PROJECTION ZONES", "*.bzones"),
    "projectors": ("PROJECTOR SETTINGS", "*.BeyondProjector"),
    "shows": ("SHOWS", "*.BSHW"),
    "showlists": ("SHOWLISTS", "*.BeyondSL"),
    "workspaces": ("WORKSPACES", "*.BeyondWorkspace"),
    "quicktargets": ("QUICK TARGETS", "*.bbml"),
}


def beyond_home() -> Path:
    return Path(os.getenv("BEYOND_HOME", str(Path.home() / "Dropbox" / "BEYOND555")))


def read_ini(home: Path | None = None) -> dict:
    """The few BEYOND.ini keys an operator cares about (workspace, Talk server, ports). Missing file -> {}."""
    home = home or beyond_home()
    ini = home / "BEYOND.ini"
    if not ini.exists():
        return {}
    txt = ini.read_text(encoding="utf-8", errors="ignore")
    keys = ("LastWorkspaceFileName2", "TalkServerActive", "TalkClientActive", "UdpTalkPort", "TcpTalkPort",
            "TalkServerAdapter", "TcpTalkServerPassword", "PortIn", "OscEnabled")
    out: dict = {"ini": str(ini), "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(ini.stat().st_mtime))}
    for k in keys:
        m = re.search(r"^%s=(.*)$" % re.escape(k), txt, re.M)
        if m:
            out[k] = m.group(1).strip()
    return out


def workspace_stem(home: Path | None = None) -> str | None:
    ws = read_ini(home).get("LastWorkspaceFileName2")
    return Path(ws).stem if ws else None


def pages(home: Path | None = None, workspace: str | None = None) -> dict:
    """Page numbers + names from the exported page files of the loaded (or given) workspace."""
    home = home or beyond_home()
    stem = workspace or workspace_stem(home)
    folder = home / "PAGES" / stem if stem else None
    rows = []
    if folder and folder.exists():
        for f in sorted(folder.glob("*.BeyondPage")):
            m = re.match(r"Page_(\d+)_(.*)\.BeyondPage$", f.name)
            rows.append({"page": int(m.group(1)) if m else None, "name": m.group(2) if m else f.stem,
                         "exported": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)), "bytes": f.stat().st_size})
    return {"workspace": stem, "folder": str(folder) if folder else None, "count": len(rows), "pages": rows,
            "note": "names come from the export file names; cue names inside BEYOND's files are not readable offline"}


def files(kind: str, home: Path | None = None) -> dict:
    """List one kind of BEYOND file: pages | zones | projectors | shows | showlists | workspaces | quicktargets."""
    home = home or beyond_home()
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {sorted(_KINDS)}")
    sub, pattern = _KINDS[kind]
    folder = home / sub
    rows = []
    if folder.exists():
        for f in sorted(folder.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
            rows.append({"name": f.stem, "path": str(f.relative_to(home)), "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)), "bytes": f.stat().st_size})
    return {"kind": kind, "folder": str(folder), "count": len(rows), "files": rows}

"""Read-only client for BEYOND's HTTP server (BEYOND Ultimate 5.8 and later).

The HTTP server is the only BEYOND channel that reports state as data: page
and cue names, Live Control values, zones, playlist position. It ships off
(Settings > HTTP Server settings) and exists only in Ultimate, so callers must
treat "not reachable" as a normal answer and keep OSC / PangoTalk as the
working path.

This module stays read-only on purpose. BEYOND has no authentication here, and
some of its GET routes act (`/apiv1/playlist/play`, `/apiv1/ps/cmd/...`), so
every request is checked against `_READ_PATHS`. Commands that change laser
state belong on PangoTalk behind the safety flags.

Numbering: this API counts pages and cues from 0, PangoScript counts from 1.
Results carry both so a caller can build `StartCue page,cue` without guessing.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import BeyondConfig

_READ_PATHS = frozenset({
    "/apiv1/ws/info2",
    "/apiv1/ws/page",
    "/apiv1/psobject",
    "/apiv1/lc/master",
    "/apiv1/playlist/state",
    "/apiv1/playlist/list",
})

_HINT = (
    "BEYOND's HTTP server did not answer. It needs BEYOND Ultimate 5.8 or later "
    "on this PC, with Settings > HTTP Server settings > Enable HTTP Server on. "
    "The Ultimate account license runs on one PC at a time. OSC and PangoTalk "
    "are unaffected."
)

_FX_KEY = re.compile(r"^fX\d")

# Proxies from the environment must never see show-control traffic.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BeyondHttpError(RuntimeError):
    """The HTTP server was unreachable or answered with a failure."""


@dataclass
class BeyondHttpClient:
    config: BeyondConfig
    timeout: float = 3.0

    @property
    def base_url(self) -> str:
        host = self.config.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.config.http_port}"

    def _get(self, path: str, **params: Any) -> Any:
        self.config.check_host_allowed()
        if path not in _READ_PATHS:
            raise ValueError(f"{path} is not on the read-only list for this client.")
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with _opener.open(url, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise BeyondHttpError(f"BEYOND answered {exc.code} for {path}: {detail}") from None
        except OSError as exc:
            raise BeyondHttpError(f"{_HINT} ({exc})") from None
        # BEYOND's JSON can carry raw control characters inside cue names.
        return json.loads(body.decode("utf-8", errors="replace"), strict=False)

    def probe(self) -> dict[str, Any]:
        """Read-only reachability check. Never raises for an absent server."""
        self.config.check_host_allowed()
        start = time.monotonic()
        result: dict[str, Any] = {"host": self.config.host, "port": self.config.http_port}
        try:
            grid = self._get("/apiv1/ws/info2").get("grid", {})
        except (BeyondHttpError, ValueError) as exc:
            result.update(reachable=False, hint=str(exc))
        else:
            result.update(reachable=True, page_count=grid.get("pageCount"),
                          grid_columns=grid.get("colCount"), grid_rows=grid.get("rowCount"))
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
        return result

    def pages(self) -> dict[str, Any]:
        """Every page with its name and category, plus the grid shape."""
        info = self._get("/apiv1/ws/info2")
        pages = [{"page": p.get("page"), "script_page": p.get("page", 0) + 1,
                  "name": p.get("name"), "category": p.get("category")}
                 for p in info.get("allPages", [])]
        return {"grid": info.get("grid", {}), "categories": info.get("categoryName", []),
                "pages": pages}

    def page_cues(self, page: int) -> dict[str, Any]:
        """Cue names on one page (0-based). Empty slots are left out."""
        if page < 0:
            raise ValueError("page counts from 0 on the HTTP API.")
        data = self._get("/apiv1/ws/page", index=page)
        cues = [{"cue": i, "script_cue": i + 1, "name": c.get("name"), "comment": c.get("comment", "")}
                for i, c in enumerate(data.get("cue", [])) if not c.get("empty")]
        return {"page": page, "script_page": page + 1, "info": data.get("info", {}), "cues": cues}

    def cue(self, page: int, cue: int) -> dict[str, Any]:
        """One cue's Live Control values. BEYOND does not say whether it is playing."""
        if page < 0 or cue < 0:
            raise ValueError("page and cue count from 0 on the HTTP API.")
        data = self._get("/apiv1/psobject", name=f"cue.{page}.{cue}")
        return {key: value for key, value in data.items() if not _FX_KEY.match(key)}

    def master(self) -> dict[str, Any]:
        """Master Live Control plus the BPM. Laser output state is not reported."""
        state = self._get("/apiv1/psobject", name="master")
        return {"live_control": self._get("/apiv1/lc/master"), "bpm": state.get("bPM"),
                "timecode_in_enabled": state.get("tcInEnabled")}

    def zones(self, include_geometry: bool = False) -> dict[str, Any]:
        """Zone list trimmed from BEYOND's ~480 KB reply. projector_index is 1-based."""
        data = self._get("/apiv1/psobject", name="zone")
        zones = []
        for index, item in enumerate(data.get("items", [])):
            zone = {"index": index, "name": item.get("name"), "projector_index": item.get("projectorIndex"),
                    "active": item.get("active"), "muted": item.get("muted"), "blocked": item.get("blockZone"),
                    "visible": item.get("visible"), "projector_connected": item.get("projectorConnected")}
            if include_geometry:
                zone["geometry"] = item.get("uGC")
            zones.append(zone)
        return {"count": data.get("count", len(zones)), "zones": zones}

    def playlist(self) -> dict[str, Any]:
        """Playback position and the show list. Starts nothing."""
        shows = [{"track": i, "name": s.get("name"), "duration_ms": s.get("infoDurationMS"),
                  "file_missing": s.get("showFileNotFound"), "timecode": s.get("enableTC"),
                  "timecode_start_ms": s.get("tcStart")}
                 for i, s in enumerate(self._get("/apiv1/playlist/list").get("show", []))]
        return {"state": self._get("/apiv1/playlist/state"), "shows": shows}

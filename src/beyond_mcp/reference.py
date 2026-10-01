"""Searchable local index of the BEYOND help file (PangoScript / OSC reference).

BEYOND ships its authoritative command reference inside BEYOND_Help.chm. This
module decompiles that CHM once into a per-user cache (via Windows' hh.exe)
and greps the resulting HTML, so tools can look up exact PangoScript and OSC
command syntax offline. The cache lives outside the repo on purpose — the
help content is Pangolin's copyrighted material and must not be committed.
"""
from __future__ import annotations

import html
import os
import re
import subprocess
from pathlib import Path

DEFAULT_CHM = Path(os.environ.get(
    "BEYOND_HELP_CHM", Path.home() / "Dropbox" / "BEYOND555" / "BEYOND_Help.chm"))
CACHE_DIR = Path(os.environ.get(
    "BEYOND_HELP_CACHE", Path.home() / ".beyond-mcp" / "help-cache"))

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _ensure_cache() -> Path | str:
    if any(CACHE_DIR.glob("**/*.htm*")):
        return CACHE_DIR
    if not DEFAULT_CHM.exists():
        return (f"help file not found at {DEFAULT_CHM} — set BEYOND_HELP_CHM to the "
                f"BEYOND_Help.chm path")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["hh.exe", "-decompile", str(CACHE_DIR), str(DEFAULT_CHM)],
                       timeout=300, check=False)
    except FileNotFoundError:
        return "hh.exe not available — cannot decompile the CHM on this system"
    except subprocess.TimeoutExpired:
        return "CHM decompile timed out"
    if not any(CACHE_DIR.glob("**/*.htm*")):
        return "decompile produced no HTML — CHM may be locked or corrupt"
    return CACHE_DIR


def search(query: str, limit: int = 20, context_chars: int = 240) -> dict:
    """Case-insensitive search across the decompiled help; returns matching
    passages with their topic file so exact command syntax can be quoted."""
    cache = _ensure_cache()
    if isinstance(cache, str):
        return {"error": cache}
    needle = query.lower()
    hits = []
    for f in sorted(cache.glob("**/*.htm*")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        plain = html.unescape(_TAG_RE.sub(" ", text))
        plain = _WS_RE.sub(" ", plain)
        low = plain.lower()
        pos = 0
        while True:
            i = low.find(needle, pos)
            if i == -1:
                break
            snippet = plain[max(0, i - context_chars // 2): i + context_chars]
            hits.append({"topic": f.stem, "snippet": snippet.strip()})
            pos = i + len(needle)
            if len(hits) >= limit * 3:
                break
        if len(hits) >= limit * 3:
            break
    seen, out = set(), []
    for h in hits:
        key = (h["topic"], h["snippet"][:80])
        if key not in seen:
            seen.add(key)
            out.append(h)
        if len(out) >= limit:
            break
    return {"query": query, "matches": len(out), "results": out,
            "cache": str(cache)}

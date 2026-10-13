# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

MCP server for Pangolin BEYOND laser software — show control, cue management, zone configuration,
and live parameter control over **OSC**. Apache-2.0, forked to `jalsaffar/beyond-mcp` (origin) from `drohi-r/beyond-mcp` (upstream).

See `../CLAUDE.md` for the shared MCP conventions and `AGENTS.md` for the short rule list.

## Commands

```bash
uv sync
uv run python -m pytest -v
uv run python -m pytest tests/test_server.py -v -k cue    # subset
uv run python -m beyond_mcp.server
```

## Architecture

Three layers, deliberately thin:

- **`config.py`** — `BeyondConfig` frozen dataclass + `load_config()`.
- **`client.py`** (165 lines) — `BeyondClient` plus standalone OSC encoders
  (`build_osc_message`, `build_osc_bundle`). This is the only place that talks OSC UDP.
- **`talk.py`** — `PangoTalkClient`, the PangoTalk TCP channel (port 16063): one PangoScript
  command per call, CRLF framed, OK/ERROR acknowledgement when BEYOND's Echo is on. The only
  transport with confirmation; BEYOND ships it disabled (enable once in Settings > Network).
- **`reference.py`** — decompiles `BEYOND_Help.chm` into `~/.beyond-mcp/help-cache` (hh.exe, first
  use only) and greps it: the authoritative PangoScript/OSC syntax lookup. The cache stays out of
  the repo deliberately — Pangolin's copyrighted help content must never be committed.
- **`~/.beyond-mcp/pangoscript-reference.md`** (user-local, not in the repo) — a distilled, original
  wording reference of all 493 PangoScript commands across 22 domains plus language basics
  (variables, labels/goto, triggers, ObjectTree, the `/b/` OSC gateway, OSC lines inside scripts),
  live verified against 5.5.0.2061 on 2026-09-03. Read it before composing `pango_talk` commands;
  `pango_reference` is the raw lookup when a command isn't in it.
- **`server.py`** (~1350 lines) — the MCP tool surface, one banner-commented section per domain
  (cues, zones, projectors, master parameters, beat/BPM, PangoTalk/reference, etc.). Tools are
  thin wrappers over `client.send_osc`; keep protocol logic out of the tool bodies.

OSC is **fire-and-forget UDP** — a send gets no reply confirming BEYOND acted. Do not write an OSC
tool whose contract implies a confirmed result. Feedback does exist, but only through separate
channels (verified on this rig 2026-10-13, BEYOND 5.5.0.2061):

- **BEYOND's outgoing OSC**, once enabled (Settings > OSC: Enable outgoing communication,
  Destination IP 127.0.0.1, Outgoing port 8001 on this rig; never 8000, BEYOND's own input).
  BEYOND then emits feedback for `/beyond/zonesetup/*` and the `/b/` gateway: sending
  `/beyond/zonesetup/zone N` makes it send all 23 geometry values of that zone. Anything else is
  sent only when a script asks (`OscOut`, `OscOutTTS`, `RegisterOscFeedback`).
- **PangoTalk** (`pango_talk`, TCP 16063, when the Talk server is enabled): `Echo 1` gives `OK` /
  `ERROR` lines, but a property ASSIGNMENT returns nothing when accepted (silence = accepted, an
  ERROR line within milliseconds = rejected). To confirm a write, read it back:
  `OscOut "/addr", Zone.0.UGC.SizeX` answers OK and sends the value to the outgoing OSC port (BEYOND
  pads four zero bytes after the float, so parse by offset). `DisplayPopup <expr>` is a harmless
  name probe. Send one line at a time and wait for its reply: a line arriving while the previous
  one runs can be refused as "Unknown function, undeclared or not initialized variable".
- **Zone geometry names** (Zone.N.UGC.*): SizeX/Y, PositionX/Y, RotationZ, LinearityX/Y,
  SymmetryX/Y, KeystoneX/Y, PincussionX/Y (two s), BowX/Y, ShearX/Y. They hold the same numbers as
  the OSC zonesetup values, Position Y's sign included; only the Projection Zones dialog shows Y
  flipped. Zone.N.SizeX / PositionX without UGC are the Live Control content values, not geometry.

Port reality on this rig (verified 2026-09-03 against BEYOND.ini + netstat): BEYOND's OSC input
default is **8000** ([OSC] PortIn), and its OSC server ships **disabled** (EnableIn=0) — the old
12000 default reached nothing, ever. PangoTalk is TCP 16063 / UDP 16062, also shipped disabled.

### Safety profiles — the distinctive part of this codebase

`BEYOND_SAFETY_PROFILE` selects one of three profiles, which set defaults for two independent
flags:

| Profile | `read_only` | `confirm_destructive` |
|---|---|---|
| `lab` (default) | off | off |
| `show-safe` | off | **on** |
| `read-only` | **on** | **on** |

`BEYOND_READ_ONLY` and `BEYOND_CONFIRM_DESTRUCTIVE` override the profile's defaults individually.
Any new tool that changes laser state must respect both flags — a tool that bypasses them defeats
the entire mechanism, and in this domain that means firing lasers during a `read-only` session.

An invalid profile name raises at load rather than falling back to `lab`. Preserve that.

## Config

| Env var | Default |
|---|---|
| `BEYOND_HOST` | `127.0.0.1` |
| `BEYOND_OSC_PORT` | `8000` (BEYOND's own [OSC] PortIn default) |
| `BEYOND_TALK_PORT` | `16063` (PangoTalk TCP) |
| `BEYOND_ALLOWED_HOSTS` | `127.0.0.1,localhost,::1` |
| `BEYOND_SAFETY_PROFILE` | `lab` |
| `BEYOND_HELP_CHM` | `~/Dropbox/BEYOND555/BEYOND_Help.chm` |
| `BEYOND_HELP_CACHE` | `~/.beyond-mcp/help-cache` |

## Docs and skills

`docs/` holds `live-validation.md` (what has actually been tested against real hardware),
`operator-workflows.md`, and `mcp-config-examples.md`. `.claude/skills/` provides `cue-programming`,
`show-prep`, and `zone-alignment`, which load automatically when working in this directory.

OSC addresses come from Pangolin's documentation and vary by BEYOND version — validate against the
installed version before claiming an address works.

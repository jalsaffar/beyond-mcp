# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

MCP server for Pangolin BEYOND laser software — show control, cue management, zone configuration,
and live parameter control over **OSC**. Apache-2.0, published as `drohi-r/beyond-mcp`.

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
  (`build_osc_message`, `build_osc_bundle`). This is the only place that talks UDP.
- **`server.py`** (~1300 lines) — the MCP tool surface, one banner-commented section per domain
  (cues, zones, projectors, master parameters, beat/BPM, etc.). Tools are thin wrappers over
  `client.send_osc`; keep protocol logic out of the tool bodies.

OSC is **fire-and-forget UDP** — there is no reply confirming BEYOND acted. `health_check()` is the
only feedback channel. Do not write a tool whose contract implies a confirmed result.

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
| `BEYOND_OSC_PORT` | `12000` |
| `BEYOND_ALLOWED_HOSTS` | `127.0.0.1,localhost,::1` |
| `BEYOND_SAFETY_PROFILE` | `lab` |

## Docs and skills

`docs/` holds `live-validation.md` (what has actually been tested against real hardware),
`operator-workflows.md`, and `mcp-config-examples.md`. `.claude/skills/` provides `cue-programming`,
`show-prep`, and `zone-alignment`, which load automatically when working in this directory.

OSC addresses come from Pangolin's documentation and vary by BEYOND version — validate against the
installed version before claiming an address works.

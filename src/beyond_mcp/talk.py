"""PangoTalk TCP client — BEYOND's request/response PangoScript channel.

Unlike OSC (fire-and-forget UDP), the PangoTalk TCP server ([NET] section of
BEYOND.ini, default port 16063) accepts raw PangoScript text terminated by
CRLF and can acknowledge with OK/ERROR lines, making it the only BEYOND
transport with confirmation. The server ships disabled; it must be switched
on once inside BEYOND (Settings > Network) before these calls connect.
"""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Any

from .config import BeyondConfig

_RECV_IDLE_S = 0.8


@dataclass
class PangoTalkClient:
    config: BeyondConfig
    timeout: float = 3.0

    def send(self, command: str, *, expect_reply: bool = True) -> dict[str, Any]:
        """Send one PangoScript command line and collect whatever reply arrives.

        Reply contents depend on BEYOND's Echo mode; with echo off a valid
        command may produce no bytes at all — that is not an error.
        """
        self.config.check_host_allowed()
        command = command.strip()
        if not command:
            raise ValueError("PangoScript command must not be empty.")
        if "\n" in command or "\r" in command:
            raise ValueError("One command per call — newlines are the protocol framing.")

        start = time.monotonic()
        with socket.create_connection(
                (self.config.host, self.config.talk_port), timeout=self.timeout) as sock:
            self._drain(sock)                      # "Welcome to BEYOND!" banner
            sock.sendall(b"Echo 1\r\n")            # turn on OK/ERROR acknowledgements
            self._drain(sock)                      # the Echo command's own OK
            sock.sendall(command.encode("utf-8") + b"\r\n")
            reply = b""
            if expect_reply:
                sock.settimeout(_RECV_IDLE_S)
                while True:
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    reply += chunk
                    if reply.endswith(b"\r\n"):
                        break
        text = reply.decode("utf-8", errors="replace").strip()
        return {
            "command": command,
            "reply": text,
            "acknowledged": text.startswith("OK"),
            "rejected": text.startswith("ERROR"),
            "host": self.config.host,
            "port": self.config.talk_port,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
        }

    @staticmethod
    def _drain(sock: socket.socket, window: float = 0.5) -> bytes:
        """Read whatever the server has queued (banner, echo acks) until idle."""
        sock.settimeout(window)
        out = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            out += chunk
            if out.endswith(b"\r\n"):
                break
        return out

    def probe(self) -> dict[str, Any]:
        """Read-only reachability check of the PangoTalk TCP server."""
        self.config.check_host_allowed()
        start = time.monotonic()
        try:
            with socket.create_connection(
                    (self.config.host, self.config.talk_port), timeout=self.timeout):
                pass
            return {"reachable": True, "host": self.config.host,
                    "port": self.config.talk_port,
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 1)}
        except OSError as exc:
            return {"reachable": False, "host": self.config.host,
                    "port": self.config.talk_port, "error": str(exc),
                    "hint": "Enable the PangoTalk TCP server in BEYOND: "
                            "Settings > Network > enable Talk server (TCP). "
                            "It ships disabled; nothing connects until it is on.",
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 1)}

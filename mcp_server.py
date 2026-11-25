#!/usr/bin/env python3
"""Lantern Farm MCP server.

Default transport is stdio (JSON-RPC with Content-Length framing, as used
by Claude Desktop, Cursor, and other MCP clients). Pass --http to also
serve the streamable HTTP transport, bound only to 127.0.0.1. The HTTP
bearer token is read from mcp.env in this folder (see mcp.env.example)
and is never printed or logged.

Tools share the same engine and save as the CLI and the web page, and
the same turn and energy rules.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from describe import describe_state
from engine import (
    do_action,
    energy_cost,
    known_players,
    load_crops,
    load_rules,
    max_energy,
    parse_player,
    session,
    weather_forecast,
)
from hey_notify import maybe_notify_after_end_turn
from config import display_name, players_public, title

ENV_PATH = ROOT / "mcp.env"
HTTP_HOST = "127.0.0.1"
HTTP_PORT_DEFAULT = 8791
PROTOCOL_VERSION = "2025-03-26"

# Optional state path, used by tests. The live server leaves this None.
_STATE_PATH: Path | None = None


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def load_http_settings() -> tuple[str, int]:
    """Return (token, port). Token may be empty if HTTP should stay off."""
    env = {}
    if ENV_PATH.is_file():
        env = _parse_env_file(ENV_PATH)
    token = (
        env.get("LANTERN_FARM_MCP_TOKEN")
        or env.get("MCP_TOKEN")
        or os.environ.get("LANTERN_FARM_MCP_TOKEN")
        or ""
    ).strip()
    raw_port = env.get("LANTERN_FARM_MCP_PORT") or os.environ.get("LANTERN_FARM_MCP_PORT") or str(HTTP_PORT_DEFAULT)
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = HTTP_PORT_DEFAULT
    return token, port


def ensure_http_token() -> str:
    """Read the bearer token, or write a new mcp.env if the file is missing.

    The token itself is never printed.
    """
    token, _port = load_http_settings()
    if token:
        return token
    if ENV_PATH.is_file():
        return ""
    token = secrets.token_urlsafe(32)
    ENV_PATH.write_text(
        "# Generated for the optional HTTP transport. Never commit this file.\n"
        f"LANTERN_FARM_MCP_TOKEN={token}\n"
        f"LANTERN_FARM_MCP_PORT={HTTP_PORT_DEFAULT}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError:
        pass
    sys.stderr.write(
        f"Wrote a new bearer token to {ENV_PATH.name} (the token itself is not printed).\n"
    )
    return token


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def farm_look(player: str, path: Path | None = None) -> str:
    key, err = parse_player(player)
    if err or not key:
        return err or "Say which player is looking."
    with session(write=False, path=path or _STATE_PATH) as (state, crops):
        return describe_state(state, crops, viewer=key)


def farm_do(player: str, command: str, path: Path | None = None) -> tuple[bool, str]:
    key, err = parse_player(player)
    if err or not key:
        return False, err or "Say which player is acting."
    dest = path or _STATE_PATH
    from engine import STATE_PATH
    with session(write=True, path=dest) as (state, crops):
        ok, message = do_action(state, crops, command, player=key)
        # Never ping from a test or alternate save — only the live farm.
        if ok:
            maybe_notify_after_end_turn(key, state, ok, state_path=dest)
        return ok, message


def farm_end_turn(player: str, note: str | None = None, path: Path | None = None) -> tuple[bool, str]:
    text = (note or "").strip()
    command = f"end turn: {text}" if text else "end turn"
    return farm_do(player, command, path=path)


def farm_rules() -> str:
    rules = load_rules()
    crops = load_crops()
    catalog = []
    for kind, info in (crops.get("crops") or {}).items():
        catalog.append(
            {
                "kind": kind,
                "grow_days": int(info.get("grow_days", 0)),
                "seed_price": int(info.get("seed_price", 0)),
                "sell_price": int(info.get("sell_price", 0)),
                "seasons": list(info.get("seasons") or []),
                "eat_energy": info.get("eat_energy", info.get("raw_energy")),
            }
        )
    payload = {
        "title": title(),
        "players": players_public(),
        "max_energy": max_energy(rules),
        "action_energy": {
            "till": energy_cost("till", rules),
            "plant": energy_cost("plant", rules),
            "water": energy_cost("water", rules),
            "harvest": energy_cost("harvest", rules),
            "buy": energy_cost("buy", rules),
            "sell": energy_cost("sell", rules),
            "pluck": energy_cost("pluck", rules),
            "move": energy_cost("move", rules),
            "eat": energy_cost("eat", rules),
            "end_turn": energy_cost("end_turn", rules),
        },
        "snacks_per_turn": int(rules.get("snacks_per_turn") or 2),
        "pass_out_energy": int(rules.get("pass_out_energy") or 50),
        "weeds": rules.get("weeds") or {},
        "crops": catalog,
        "notes": [
            "The same engine and state.json as the CLI and web page.",
            "You can only act on your own turn.",
            "You can only till, plant, water, harvest, or pluck the tile you are standing on.",
            "Move with `move up/down/left/right`, `move to <row> <col>`, or `go cabin`. Each step costs 10 energy, diagonals included.",
            "Ending your turn in the cabin is sleep (full energy tomorrow). Ending it elsewhere is passing out (half energy, where you fell).",
            "Eat a harvested crop with `eat <crop>` (free, up to 2 snacks a turn). Eating spends the crop instead of selling it.",
            "The day advances when every player has ended their turn.",
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"



def farm_forecast(player: str | None = None, path: Path | None = None) -> str:
    """Next 7 days, the same forecast shown in look. Player is optional."""
    dest = path or _STATE_PATH
    from describe import forecast_lines
    from engine import load_crops, session as _session
    with _session(write=False, path=dest) as (state, crops):
        # Optional player only so turn context is not required to peek at the sky.
        lines = forecast_lines(state, crops)
        if not lines:
            return "No forecast is available."
        return "\n".join(lines) + "\n"

TOOL_SPECS = [
    {
        "name": "farm_look",
        "description": (
            "Describe the farm for a player: day, weather, gold, whose turn, "
            "energy, where each player is standing, inventory, every tile, a 7-day forecast, "
            "legal actions, and the recent log. Same text as `python3 cli.py look`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "player": {
                    "type": "string",
                    "description": "Player id (one of: " + ", ".join(known_players()) + ")",
                }
            },
            "required": ["player"],
            "additionalProperties": False,
        },
    },
    {
        "name": "farm_do",
        "description": (
            "Run one farm command as a player: move, go cabin, till, plant, "
            "water, harvest, pluck, eat, buy, sell, or end turn. You can only "
            "work the tile you are standing on. Same commands and energy costs "
            "as the CLI. Refused if it is not that player's turn."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "Player id acting"},
                "command": {
                    "type": "string",
                    "description": 'A command such as "water 1 1" or "plant 2 2 kabocha"',
                },
            },
            "required": ["player", "command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "farm_end_turn",
        "description": (
            "End the named player's turn, optionally leaving a short note "
            "(up to 280 characters) for the other player."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "Player id ending the turn"},
                "note": {
                    "type": "string",
                    "description": "Optional note for the other player",
                },
            },
            "required": ["player"],
            "additionalProperties": False,
        },
    },
    {
        "name": "farm_forecast",
        "description": (
            "The 7-day weather forecast for the farm, as of today. "
            "It is not always accurate, and it can change as days approach. "
            "The same text appears in farm_look."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "Optional player id"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "farm_rules",
        "description": "Return energy costs, movement and sleep rules, snack caps, crop prices (including raw eat energy), and the configured players.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def call_tool(name: str, arguments: dict | None) -> tuple[str, bool]:
    args = arguments or {}
    try:
        if name == "farm_look":
            return farm_look(str(args.get("player") or "")), False
        if name == "farm_do":
            ok, message = farm_do(str(args.get("player") or ""), str(args.get("command") or ""))
            return message, not ok
        if name == "farm_end_turn":
            note = args.get("note")
            ok, message = farm_end_turn(
                str(args.get("player") or ""),
                None if note is None else str(note),
            )
            return message, not ok
        if name == "farm_forecast":
            return farm_forecast(args.get("player")), False
        if name == "farm_rules":
            return farm_rules(), False
    except Exception:
        # Never include exception text; it might mention paths or env values.
        return "The farm tool failed.", True
    return f"Unknown tool: {name}", True


# ---------------------------------------------------------------------------
# JSON-RPC / MCP
# ---------------------------------------------------------------------------

def handle_rpc(message: dict) -> dict | None:
    """Handle one JSON-RPC message. Returns a response, or None for notifications."""
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    mid = message.get("id", None)
    method = message.get("method")
    params = message.get("params") or {}
    is_notification = "id" not in message

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "lantern-farm", "version": "0.2.0"},
            "instructions": (
                f"{title()} MCP. Use farm_look to see the farm, farm_do to act, "
                "farm_end_turn to hand off, and farm_rules for costs and crops. "
                "The same save and turn rules as the CLI and web page."
            ),
        }
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method in {"notifications/initialized", "initialized", "notifications/cancelled"}:
        return None

    if method == "ping":
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": mid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOL_SPECS}}

    if method == "tools/call":
        name = str((params or {}).get("name") or "")
        arguments = (params or {}).get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        text, is_error = call_tool(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": bool(is_error),
            },
        }

    if is_notification:
        return None
    return {
        "jsonrpc": "2.0",
        "id": mid,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _write_stdio(message: dict | list) -> None:
    """MCP stdio is newline-delimited JSON: one message per line, no headers."""
    raw = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(raw + b"\n")
    sys.stdout.buffer.flush()


def _read_stdio() -> dict | list | None:
    """Read one MCP stdio message. Prefer newline-delimited JSON; fall back to Content-Length."""
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    stripped = line.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        try:
            return json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    # Fallback: LSP-style Content-Length framing.
    headers: dict[str, str] = {}
    while True:
        if line in (b"\n", b"\r\n"):
            break
        try:
            text = line.decode("ascii", errors="replace")
        except Exception:
            return None
        if ":" in text:
            key, val = text.split(":", 1)
            headers[key.strip().lower()] = val.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    try:
        length = int(headers.get("content-length") or "0")
    except ValueError:
        return None
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def serve_stdio() -> int:
    sys.stderr.write("Lantern Farm MCP listening on stdio\n")
    sys.stderr.flush()
    while True:
        message = _read_stdio()
        if message is None:
            return 0
        if isinstance(message, list):
            replies = [handle_rpc(item) for item in message]
            batch = [r for r in replies if r is not None]
            if batch:
                _write_stdio(batch)
            continue
        reply = handle_rpc(message)
        if reply is not None:
            _write_stdio(reply)


# ---------------------------------------------------------------------------
# Streamable HTTP (127.0.0.1 only)
# ---------------------------------------------------------------------------

def _tokens_match(given: str, expected: str) -> bool:
    if not expected or not given:
        return False
    left = hashlib.sha256(given.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


class MCPHTTPHandler(BaseHTTPRequestHandler):
    server_version = "LanternFarmMCP/0.2"
    token = ""

    def log_message(self, fmt: str, *args) -> None:
        # Never log headers or bodies; they may contain the bearer token.
        try:
            path = url_path_only(self.path)
        except Exception:
            path = "/"
        sys.stderr.write("%s %s %s\n" % (self.address_string(), self.command, path))

    def _unauthorized(self) -> None:
        body = b'{"error":"unauthorized"}\n'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization") or ""
        if not header.lower().startswith("bearer "):
            return False
        given = header[7:].strip()
        return _tokens_match(given, self.token)

    def _send_json(self, code: int, payload) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def _send_sse(self, payload: dict | list) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        body = f"event: message\ndata: {data}\n\n".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._unauthorized()
            return
        path = url_path_only(self.path)
        if path in {"/", "/mcp", "/sse"}:
            # Streamable HTTP: GET may open an SSE stream. We have nothing
            # pending, so close after a short comment.
            body = b": lantern-farm mcp\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._unauthorized()
            return
        path = url_path_only(self.path)
        if path not in {"/", "/mcp", "/message"}:
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            message = json.loads(raw.decode("utf-8") or "null")
        except json.JSONDecodeError:
            self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        accept = (self.headers.get("Accept") or "").lower()
        want_sse = "text/event-stream" in accept
        if isinstance(message, list):
            replies = [handle_rpc(item) for item in message]
            payload = [r for r in replies if r is not None]
        else:
            payload = handle_rpc(message)
        if payload is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if want_sse:
            self._send_sse(payload)
        else:
            self._send_json(200, payload)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()


def url_path_only(path: str) -> str:
    return path.split("?", 1)[0]


def serve_http(token: str, port: int) -> None:
    if not token:
        sys.stderr.write("HTTP transport disabled: no bearer token in mcp.env\n")
        return
    handler = MCPHTTPHandler
    handler.token = token
    server = ThreadingHTTPServer((HTTP_HOST, port), handler)
    sys.stderr.write(f"Lantern Farm MCP HTTP on http://{HTTP_HOST}:{port}/mcp\n")
    sys.stderr.flush()
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lantern Farm MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve streamable HTTP on 127.0.0.1 (in addition to stdio if --stdio-too, otherwise instead of stdio)",
    )
    parser.add_argument(
        "--stdio-too",
        action="store_true",
        help="With --http, also keep the stdio transport on this process",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port (default 8791, or LANTERN_FARM_MCP_PORT in mcp.env)",
    )
    args = parser.parse_args(argv)

    if args.http:
        token = ensure_http_token()
        if not token:
            sys.stderr.write("HTTP transport disabled: mcp.env has no LANTERN_FARM_MCP_TOKEN\n")
            return 2
        _, env_port = load_http_settings()
        port = args.port or env_port or HTTP_PORT_DEFAULT
        if args.stdio_too:
            thread = threading.Thread(target=serve_http, args=(token, port), daemon=True)
            thread.start()
            return serve_stdio()
        serve_http(token, port)
        return 0

    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())

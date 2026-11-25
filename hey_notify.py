"""Optional turn notification, configured in config.local.json.

When notify is set (for example a Hey webhook), a ping is sent on a
configured handoff. Credentials are read from the env file named in
config, never from the repo. Never print or log the URL, the auth
value, or exception text (it may contain the URL). Fails gracefully if
notify is unset, the env file is missing, or the request fails.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from config import display_name, notify_config

def notify_disabled() -> bool:
    val = (os.environ.get("LANTERN_FARM_NO_NOTIFY") or "").strip().lower()
    return val in {"1", "true", "yes", "on"}


# The real farm save, computed from this file so a test redirect of
# engine.STATE_PATH cannot make a temp file look live.
_LIVE_STATE_PATH = Path(__file__).resolve().parent / "state.json"


def is_live_save(state_path: Path | None) -> bool:
    """True only when this is the farm's real state.json (or the implicit live path)."""
    if state_path is None:
        return True
    try:
        return Path(state_path).resolve() == _LIVE_STATE_PATH.resolve()
    except OSError:
        return False




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


def _env_path(cfg: dict) -> Path:
    raw = str(cfg.get("env_file") or "").strip()
    if not raw:
        return Path()
    return Path(raw).expanduser()


def turn_ping_message(day: int, note: str | None = None) -> str:
    """Notification body from the configured templates."""
    cfg = notify_config() or {}
    message = str(cfg.get("message") or "🌱 Lantern Farm: your turn (Day {day})")
    try:
        message = message.format(day=int(day))
    except (KeyError, IndexError, ValueError):
        message = f"🌱 Lantern Farm: your turn (Day {int(day)})"
    if note:
        from_id = str(cfg.get("from") or "")
        line = str(cfg.get("note_line") or "{from_name}: {note}")
        try:
            line = line.format(from_name=display_name(from_id) if from_id else "Note", note=str(note), from_id=from_id)
        except (KeyError, IndexError, ValueError):
            line = f"{display_name(from_id) if from_id else 'Note'}: {note}"
        message = message + "\n" + line
    return message


def send_turn_ping(day: int, note: str | None = None) -> bool:
    """POST the turn ping. Return True if the ping was sent."""
    if notify_disabled():
        return False
    cfg = notify_config()
    if not cfg:
        return False
    path = _env_path(cfg)
    if not path.is_file():
        sys.stderr.write("Turn notify skipped: config file not found\n")
        return False
    env = _parse_env_file(path)
    url_key = str(cfg.get("url_key") or "WEBHOOK_URL")
    auth_key = str(cfg.get("auth_key") or "WEBHOOK_AUTH")
    url = env.get(url_key) or ""
    auth = (env.get(auth_key) or "").strip()
    if auth.lower().startswith("authorization:"):
        auth = auth.split(":", 1)[1].strip()
    if not url or not auth:
        sys.stderr.write("Turn notify skipped: URL or auth missing\n")
        return False
    payload = json.dumps(
        {"message": turn_ping_message(day, note), "screenshot": None}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": auth,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            # Read and discard the body; do not log it.
            response.read()
            if 200 <= int(response.status) < 300:
                sys.stderr.write("Turn notify sent\n")
                return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        sys.stderr.write("Turn notify failed\n")
        return False
    sys.stderr.write("Turn notify failed\n")
    return False




def maybe_notify_after_end_turn(
    player: str | None,
    state: dict,
    ok: bool,
    state_path: Path | None = None,
) -> None:
    """If the configured player just handed the turn to the other, send a ping.

    Never fires when LANTERN_FARM_NO_NOTIFY is set, or when state_path points
    at anything other than the live state.json.
    """
    if not ok:
        return
    if notify_disabled() or not is_live_save(state_path):
        return
    cfg = notify_config()
    if not cfg:
        return
    from_id = str(cfg.get("from") or "").strip().lower()
    to_id = str(cfg.get("to") or "").strip().lower()
    if not from_id or not to_id:
        return
    if (player or "").strip().lower() != from_id:
        return
    if (state.get("current_player") or "").strip().lower() != to_id:
        return
    note = None
    last = state.get("last_note") or {}
    if isinstance(last, dict) and (last.get("from") or "").strip().lower() == from_id:
        text = (last.get("text") or "").strip()
        if text:
            note = text
    send_turn_ping(int(state.get("day", 0)), note=note)

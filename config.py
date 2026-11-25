"""Farm configuration.

config.example.json is the committed generic baseline. If config.local.json
is present, it is deep-merged on top (player names, theme, flavor, notify).
Never commit or print the local file's secrets; notify credentials live in a
separate env file referenced by path only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLE_PATH = ROOT / "config.example.json"
LOCAL_PATH = ROOT / "config.local.json"

_cache: dict | None = None


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(force: bool = False) -> dict:
    global _cache
    if _cache is not None and not force:
        return _cache
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    if LOCAL_PATH.is_file():
        data = _deep_merge(data, json.loads(LOCAL_PATH.read_text(encoding="utf-8")))
    _cache = data
    return data


def players() -> list[dict]:
    found = load_config().get("players") or []
    out = []
    for item in found:
        if isinstance(item, dict) and item.get("id"):
            rec = dict(item)
            rec["id"] = str(rec["id"]).strip().lower()
            rec["name"] = str(rec.get("name") or rec["id"]).strip()
            out.append(rec)
        elif isinstance(item, str) and item.strip():
            key = item.strip().lower()
            out.append({"id": key, "name": key.capitalize()})
    return out or [
        {"id": "player1", "name": "Player 1"},
        {"id": "player2", "name": "Player 2"},
    ]


def player_ids() -> tuple[str, ...]:
    return tuple(p["id"] for p in players())


def player_record(player: str | None) -> dict | None:
    key = (player or "").strip().lower()
    if not key:
        return None
    for rec in players():
        if rec["id"] == key:
            return rec
    return None


def display_name(player: str | None) -> str:
    rec = player_record(player)
    if rec and rec.get("name"):
        return str(rec["name"])
    if player and str(player).strip():
        return str(player).strip().capitalize()
    return "Someone"


def starting_player() -> str:
    ids = player_ids()
    wanted = str(load_config().get("starting_player") or "").strip().lower()
    if wanted in ids:
        return wanted
    return ids[0]


def default_web_player() -> str:
    ids = player_ids()
    wanted = str((load_config().get("defaults") or {}).get("web_player") or "").strip().lower()
    if wanted in ids:
        return wanted
    return starting_player()


def default_cli_player() -> str:
    ids = player_ids()
    wanted = str((load_config().get("defaults") or {}).get("cli_player") or "").strip().lower()
    if wanted in ids:
        return wanted
    if len(ids) > 1:
        return ids[1]
    return ids[0]


def other_player_id(player: str | None) -> str:
    ids = player_ids()
    key = (player or "").strip().lower()
    if key in ids and len(ids) > 1:
        return ids[(ids.index(key) + 1) % len(ids)]
    for item in ids:
        if item != key:
            return item
    return ids[-1]


def flavor(key: str, **fmt) -> str:
    text = str((load_config().get("flavor") or {}).get(key) or "")
    if fmt and text:
        try:
            text = text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def title() -> str:
    return str(load_config().get("title") or "Lantern Farm")


def place() -> str:
    return str(load_config().get("place") or "the farm")


def theme_css_vars() -> dict[str, str]:
    raw = (load_config().get("theme") or {}).get("css_vars") or {}
    return {str(k): str(v) for k, v in raw.items()}


def notify_config() -> dict | None:
    raw = load_config().get("notify")
    if isinstance(raw, dict) and raw:
        return raw
    return None


def players_public() -> list[dict]:
    """Id, display name, and avatar color only — nothing from notify or tokens."""
    out = []
    for p in players():
        rec = {"id": p["id"], "name": p["name"]}
        color = str(p.get("color") or p.get("avatar_color") or "").strip()
        if color:
            rec["color"] = color
        out.append(rec)
    return out

"""Per-player Autopass: take a break, and the farm ends idle turns for you.

Settings live on the player slot in the farm state — never next to notify
tokens or other credentials. The same rules work for any two people, not
just a particular pair of players.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

DEFAULT_ENABLED = False
DEFAULT_MAX_TURNS = 3
DEFAULT_TIMEOUT_MINUTES = 30
MIN_TURNS = 1
MAX_TURNS = 30
MIN_TIMEOUT_MINUTES = 1
MAX_TIMEOUT_MINUTES = 24 * 60

TURN_STARTED_AT = "turn_started_at"
AUTOPASS_KEY = "autopass"
AWAY_NOTE_KEY = "away_note"
MAX_AWAY_NOTE = 280


def _aware(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now().astimezone()
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.now().astimezone().tzinfo or timezone.utc)
    return value


def _parse_iso(raw) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _aware(stamp)


def _clamp_int(raw, default: int, lo: int, hi: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))



def normalize_away_note(raw) -> str:
    """Plain free text: trimmed, length-capped, never an unexpected structure."""
    if raw is None:
        return ""
    text = " ".join(str(raw).split())
    if len(text) > MAX_AWAY_NOTE:
        text = text[:MAX_AWAY_NOTE].rstrip()
    return text


def away_note_of(state: dict, player: str | None) -> str:
    from engine import normalize_player, player_slot

    name = normalize_player(player)
    if not name:
        return ""
    slot = player_slot(state, name)
    return normalize_away_note(slot.get(AWAY_NOTE_KEY))


def set_away_note(state: dict, player: str | None, raw) -> str:
    from engine import normalize_player, player_slot

    name = normalize_player(player)
    if not name:
        return ""
    note = normalize_away_note(raw)
    slot = player_slot(state, name)
    if note:
        slot[AWAY_NOTE_KEY] = note
    else:
        slot.pop(AWAY_NOTE_KEY, None)
    return note


def autopass_log_line(state: dict, player: str | None) -> str:
    """Visible log line when a turn is ended by Autopass."""
    from engine import display_name

    line = f"{display_name(player)}'s turn autopassed (on a break)"
    note = away_note_of(state, player)
    if note:
        line += f": {note}"
    return line


def default_autopass() -> dict:
    return {
        "enabled": DEFAULT_ENABLED,
        "max_turns": DEFAULT_MAX_TURNS,
        "timeout_minutes": DEFAULT_TIMEOUT_MINUTES,
        "turns_used": 0,
        "away_log": [],
        "away_pending": False,
    }


def normalize_autopass(raw) -> dict:
    """Return a clean autopass dict. Never copies unknown keys (no tokens)."""
    base = default_autopass()
    if not isinstance(raw, dict):
        return base
    base["enabled"] = bool(raw.get("enabled"))
    base["max_turns"] = _clamp_int(raw.get("max_turns"), DEFAULT_MAX_TURNS, MIN_TURNS, MAX_TURNS)
    base["timeout_minutes"] = _clamp_int(
        raw.get("timeout_minutes"), DEFAULT_TIMEOUT_MINUTES, MIN_TIMEOUT_MINUTES, MAX_TIMEOUT_MINUTES
    )
    base["turns_used"] = _clamp_int(raw.get("turns_used"), 0, 0, MAX_TURNS)
    log = raw.get("away_log") or []
    clean = []
    if isinstance(log, list):
        for item in log:
            if isinstance(item, str) and item.strip():
                clean.append(item.strip())
            elif isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    clean.append(text)
    base["away_log"] = clean
    base["away_pending"] = bool(raw.get("away_pending"))
    return base


def autopass_of(state: dict, player: str | None) -> dict:
    from engine import normalize_player, player_slot

    name = normalize_player(player)
    if not name:
        return default_autopass()
    slot = player_slot(state, name)
    raw = slot.get(AUTOPASS_KEY)
    cfg = normalize_autopass(raw)
    # Keep the live dict in place so callers can mutate it even if another
    # helper also calls autopass_of (normalize always returns a fresh copy).
    if isinstance(raw, dict):
        raw.clear()
        raw.update(cfg)
        slot[AUTOPASS_KEY] = raw
        return raw
    slot[AUTOPASS_KEY] = cfg
    return cfg


def set_autopass_settings(
    state: dict,
    player: str | None,
    *,
    enabled: bool | None = None,
    max_turns: int | None = None,
    timeout_minutes: int | None = None,
) -> dict:
    """Update a player's autopass settings. Turning it off ends a break."""
    cfg = autopass_of(state, player)
    if max_turns is not None:
        cfg["max_turns"] = _clamp_int(max_turns, cfg["max_turns"], MIN_TURNS, MAX_TURNS)
    if timeout_minutes is not None:
        cfg["timeout_minutes"] = _clamp_int(
            timeout_minutes, cfg["timeout_minutes"], MIN_TIMEOUT_MINUTES, MAX_TIMEOUT_MINUTES
        )
    if enabled is not None:
        was = bool(cfg["enabled"])
        cfg["enabled"] = bool(enabled)
        if cfg["enabled"] and not was:
            # A new break starts a fresh count. Keep any unshown summary.
            cfg["turns_used"] = 0
        if (not cfg["enabled"]) and was:
            if cfg["away_log"]:
                cfg["away_pending"] = True
    return cfg


def mark_turn_started(state: dict, now: datetime | None = None) -> None:
    """Stamp when the current player's turn began."""
    state[TURN_STARTED_AT] = _aware(now).isoformat(timespec="seconds")


def turn_started_at(state: dict) -> datetime | None:
    return _parse_iso(state.get(TURN_STARTED_AT))


def _summary_from_cfg(cfg: dict) -> str:
    lines = list(cfg.get("away_log") or [])
    if not lines:
        return ""
    return f"While you were away: {' '.join(lines)}"


def format_away_summary(state: dict, player: str | None) -> str:
    """Short 'while you were away' text, or an empty string."""
    return _summary_from_cfg(autopass_of(state, player))


def acknowledge_away_summary(state: dict, player: str | None) -> None:
    cfg = autopass_of(state, player)
    cfg["away_pending"] = False
    cfg["away_log"] = []


def player_is_back(state: dict, player: str | None) -> str:
    """Any action by this player ends a break and counts as being back.

    Returns the summary to show, if any, and leaves it pending until
    acknowledged so the web view can display it.
    """
    cfg = autopass_of(state, player)
    had_break = bool(cfg["enabled"] or cfg["turns_used"] or cfg["away_log"])
    if not had_break:
        return ""
    summary = _summary_from_cfg(cfg)
    cfg["enabled"] = False
    cfg["turns_used"] = 0
    if cfg["away_log"]:
        cfg["away_pending"] = True
    return summary


def autopass_due(state: dict, now: datetime | None = None, rules: dict | None = None) -> bool:
    """True when the current player's idle turn should be ended for them."""
    from engine import normalize_player

    current = normalize_player(state.get("current_player"))
    if not current:
        return False
    cfg = autopass_of(state, current)
    if not cfg["enabled"]:
        return False
    if int(cfg["turns_used"]) >= int(cfg["max_turns"]):
        return False
    started = turn_started_at(state)
    if started is None:
        return False
    timeout = timedelta(minutes=int(cfg["timeout_minutes"]))
    return _aware(now) - started >= timeout


def _weather_word(state: dict) -> str:
    weather = str(state.get("weather") or "sun").strip().lower()
    return {
        "sun": "sunny",
        "cloud": "overcast",
        "rain": "rainy",
        "snow": "snowy",
        "storm": "stormy",
    }.get(weather, weather or "clear")


def _away_line(state: dict, previous_day: int, day_advanced: bool) -> str:
    from config import display_name

    day = int(state.get("day") or 0)
    weather = _weather_word(state)
    if day_advanced:
        return f"Day {previous_day} ended. Day {day} dawns, {weather}."
    nxt = display_name(state.get("current_player"))
    return f"Day {day} — your turn ended; it is {nxt}'s turn."


def maybe_apply_autopass(
    state: dict,
    crops: dict,
    rules: dict | None = None,
    now: datetime | None = None,
) -> tuple[bool, str, str | None]:
    """If the current player's turn has timed out, vote end-day for them.

    No other action is taken on their behalf. Returns
    ``(applied, message, ended_for_player)``.
    """
    from engine import end_turn, normalize_player, load_rules

    rules = rules or load_rules()
    now = _aware(now)
    current = normalize_player(state.get("current_player"))
    if not current or not autopass_due(state, now=now, rules=rules):
        return False, "", None
    previous_day = int(state.get("day") or 0)
    ok, msg = end_turn(state, crops, current, rules, via="autopass")
    if not ok:
        return False, msg, None
    # Re-fetch after end_turn: a new day replaces player slots with copies.
    cfg = autopass_of(state, current)
    cfg["turns_used"] = int(cfg["turns_used"]) + 1
    day_advanced = int(state.get("day") or 0) != previous_day
    line = _away_line(state, previous_day, day_advanced)
    if cfg["turns_used"] >= cfg["max_turns"]:
        line = f"{line} Autopass reached its maximum of {cfg['max_turns']} turns."
    cfg["away_log"].append(line)
    cfg["away_pending"] = True
    mark_turn_started(state, now=now)
    return True, msg, current


def public_autopass(state: dict, player: str | None) -> dict:
    """Settings for the web UI: only the documented fields, never credentials."""
    cfg = autopass_of(state, player)
    return {
        "enabled": bool(cfg["enabled"]),
        "max_turns": int(cfg["max_turns"]),
        "timeout_minutes": int(cfg["timeout_minutes"]),
        "turns_used": int(cfg["turns_used"]),
        "away_pending": bool(cfg["away_pending"]),
        "defaults": {
            "enabled": DEFAULT_ENABLED,
            "max_turns": DEFAULT_MAX_TURNS,
            "timeout_minutes": DEFAULT_TIMEOUT_MINUTES,
        },
    }

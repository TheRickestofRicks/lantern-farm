"""Lantern Farm — deterministic rules and JSON state.

The JSON state is the single source of truth. Both the text view and the
image view derive what they show from it; they never invent tile state.
"""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CROPS_PATH = ROOT / "crops.json"
RULES_PATH = ROOT / "rules.json"
STATE_PATH = ROOT / "state.json"
LOCK_PATH = ROOT / ".state.lock"

SEASONS = ["spring", "summer", "autumn", "winter"]
ROWS = 3
COLS = 3
CABIN_ROW = 1  # 1-indexed, top-right
CABIN_COL = 3
MAX_LOG = 50
NOTE_MAX = 280
RECENT_NOTE_COUNT = 15
JOURNAL_ARCHIVE_PATH = ROOT / "local" / "journal-archive.json"
_LEAVES_A_NOTE = re.compile(r"^(.*) leaves a note:\s*(.*)$", re.DOTALL)
SEASON_ALIASES = {
    "spring": "spring",
    "summer": "summer",
    "autumn": "autumn",
    "fall": "autumn",
    "winter": "winter",
}

POSITION_NAMES = {
    (1, 1): "top-left",
    (1, 2): "top-center",
    (1, 3): "top-right",
    (2, 1): "mid-left",
    (2, 2): "center",
    (2, 3): "mid-right",
    (3, 1): "bottom-left",
    (3, 2): "bottom-center",
    (3, 3): "bottom-right",
}



def load_crops() -> dict:
    return json.loads(CROPS_PATH.read_text(encoding="utf-8"))


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def known_players() -> tuple[str, ...]:
    from config import player_ids
    return player_ids()


# Back-compat alias; prefer known_players() so a local config overlay is honoured.
KNOWN_PLAYERS = None  # replaced below with a live view


class _LivePlayers:
    def __iter__(self):
        return iter(known_players())

    def __contains__(self, item):
        return item in known_players()

    def __len__(self):
        return len(known_players())

    def __getitem__(self, index):
        return known_players()[index]


KNOWN_PLAYERS = _LivePlayers()


def display_name(player: str | None) -> str:
    from config import display_name as _display_name
    return _display_name(player)


def normalize_player(player: str | None) -> str | None:
    if player is None:
        return None
    key = str(player).strip().lower()
    if not key:
        return None
    if key not in known_players():
        return None
    return key


def parse_player(player: str | None) -> tuple[str | None, str | None]:
    key = normalize_player(player)
    if key:
        return key, None
    ids = " and ".join(known_players()) or "configured in config.local.json"
    return None, f"Players are {ids}. Try --player {known_players()[-1] if known_players() else 'player1'}"


def max_energy(rules: dict | None = None) -> int:
    rules = rules or load_rules()
    return int(rules.get("max_energy", 100))


def energy_cost(action_verb: str, rules: dict | None = None) -> int:
    rules = rules or load_rules()
    costs = rules.get("action_energy") or {}
    verb = (action_verb or "").strip().lower()
    if verb in {"end", "end_turn", "end-turn", "endturn"}:
        verb = "end_turn"
    if verb in costs:
        return int(costs[verb])
    return 0


def step_energy(rules: dict | None = None) -> int:
    """Energy charged for any one step, including a diagonal."""
    rules = rules or load_rules()
    costs = rules.get("action_energy") or {}
    if "move" in costs:
        return int(costs["move"])
    return int(rules.get("move_energy", 5))


def snacks_per_turn(rules: dict | None = None) -> int:
    rules = rules or load_rules()
    return int(rules.get("snacks_per_turn", 2))


def pass_out_energy(rules: dict | None = None) -> int:
    rules = rules or load_rules()
    return int(rules.get("pass_out_energy", 50))


def eat_energy_for(crops: dict | None, kind: str) -> int | None:
    """Energy restored by eating a harvested crop raw, or None if it is not edible."""
    info = crop_info(crops or load_crops(), kind)
    if not info:
        return None
    raw = info.get("eat_energy", info.get("raw_energy"))
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None


def in_bounds(row: int, col: int) -> bool:
    return 1 <= int(row) <= ROWS and 1 <= int(col) <= COLS


def is_cabin_at(row: int, col: int) -> bool:
    return int(row) == CABIN_ROW and int(col) == CABIN_COL


def plot_number(row: int, col: int) -> int:
    return (int(row) - 1) * COLS + int(col)


def describe_place(row: int, col: int) -> str:
    """Bare place name, for phrases like 'walks to X'."""
    if is_cabin_at(row, col):
        return "the cabin"
    return position_name(row, col)


def describe_where(row: int, col: int) -> str:
    """Prepositional location, for phrases like 'is X' or 'already X'."""
    if is_cabin_at(row, col):
        return "in the cabin"
    return f"at {position_name(row, col)}"


def steps_phrase(count: int) -> str:
    n = int(count)
    return "1 step" if n == 1 else f"{n} steps"


def player_where(state: dict, player: str) -> tuple[int, int]:
    slot = player_slot(state, player)
    try:
        row = int(slot.get("row") or 0)
        col = int(slot.get("col") or 0)
    except (TypeError, ValueError):
        row, col = 0, 0
    if not in_bounds(row, col):
        return CABIN_ROW, CABIN_COL
    return row, col


def set_player_where(state: dict, player: str, row: int, col: int) -> None:
    slot = player_slot(state, player)
    slot["row"] = int(row)
    slot["col"] = int(col)


def is_player_in_cabin(state: dict, player: str) -> bool:
    row, col = player_where(state, player)
    return is_cabin_at(row, col)


def players_at(state: dict, row: int, col: int) -> list[str]:
    found = []
    for name in known_players():
        here = player_where(state, name)
        if here == (int(row), int(col)):
            found.append(name)
    return found


def path_steps(src: tuple[int, int], dst: tuple[int, int]) -> list[tuple[int, int]]:
    """Shortest path on the grid, 8-direction steps (Chebyshev)."""
    row, col = src
    goal_r, goal_c = dst
    steps: list[tuple[int, int]] = []
    while (row, col) != (goal_r, goal_c):
        dr = 0 if row == goal_r else (1 if goal_r > row else -1)
        dc = 0 if col == goal_c else (1 if goal_c > col else -1)
        row, col = row + dr, col + dc
        steps.append((row, col))
    return steps


def path_cost(src: tuple[int, int], dst: tuple[int, int], rules: dict | None = None) -> int:
    return step_energy(rules) * len(path_steps(src, dst))


def sleep_outlook(state: dict, player: str, rules: dict | None = None) -> str:
    """Warning shown before ending a turn, and in the look/UI."""
    rules = rules or load_rules()
    cap = max_energy(rules)
    faint = pass_out_energy(rules)
    if is_player_in_cabin(state, player):
        return f"You'll sleep in the cabin — {cap} energy tomorrow"
    return f"You'll pass out in the field — {faint} energy tomorrow"


def player_slot(state: dict, player: str) -> dict:
    from inventory import empty_pack, normalize_pack

    players = state.setdefault("players", {})
    slot = players.setdefault(player, {})
    slot.setdefault("energy", 0)
    slot.setdefault("ended_turn", False)
    slot.setdefault("row", CABIN_ROW)
    slot.setdefault("col", CABIN_COL)
    slot.setdefault("snacks_eaten", 0)
    if "pack" not in slot:
        slot["pack"] = empty_pack()
    else:
        slot["pack"] = normalize_pack(slot.get("pack"))
    return slot


def who(player: str | None, you_verb: str, they_verb: str) -> str:
    """'You till', or the configured display name plus the verb."""
    if not player:
        return f"You {you_verb}"
    return f"{display_name(player)} {they_verb}"


def sanitize_note(note: str | None, limit: int = NOTE_MAX) -> str:
    """Collapse whitespace, strip controls, cap at 280 characters. Empty means no note."""
    if not note:
        return ""
    text = str(note).replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(text.split())
    text = "".join(ch for ch in text if ch >= " ")
    text = text.strip()
    if len(text) > limit:
        text = text[:limit].rstrip()
    return text


def parse_end_turn_command(command: str) -> tuple[bool, str]:
    """True if this is an end-turn command, plus the optional note (possibly empty)."""
    raw = (command or "").strip()
    lower = raw.lower()
    for prefix in ("end turn:", "end-turn:", "end_turn:", "endturn:"):
        if lower.startswith(prefix):
            return True, raw[len(prefix):].strip()
    if lower in {"end turn", "end-turn", "end_turn", "endturn"}:
        return True, ""
    for prefix in ("end turn ", "end-turn ", "end_turn ", "endturn "):
        if lower.startswith(prefix):
            return True, raw[len(prefix):].strip()
    return False, ""


def days_per_season(crops: dict | None) -> int:
    if not crops:
        return 15
    return int(crops.get("days_per_season", 15))


def days_per_year(crops: dict | None = None) -> int:
    return days_per_season(crops) * len(SEASONS)


def year_for_day(day: int, crops: dict | None = None) -> int:
    """1-indexed year. Day 1 is year 1, spring."""
    span = days_per_year(crops)
    return ((int(day) - 1) // span) + 1


def normalize_season(name: str | None) -> str | None:
    """Canonical season id, or None if the name is not a season. 'fall' means autumn."""
    if name is None:
        return None
    key = str(name).strip().lower()
    if not key:
        return None
    return SEASON_ALIASES.get(key)


def empty_journal(year: int = 1) -> dict:
    return {
        "year": int(year),
        "seasons": {season: [] for season in SEASONS},
    }


def _note_key(entry: dict | None) -> tuple:
    if not isinstance(entry, dict):
        return (0, "", 0, "", "")
    return (
        int(entry.get("year") or 0),
        str(entry.get("season") or ""),
        int(entry.get("day") or 0),
        str(entry.get("from") or ""),
        str(entry.get("text") or ""),
    )


def _journal_entry(day: int, player: str, text: str, crops: dict | None = None) -> dict | None:
    text = sanitize_note(text)
    player = normalize_player(player) or (str(player).strip().lower() if player else "")
    if not text or not player:
        return None
    day = int(day)
    return {
        "day": day,
        "year": year_for_day(day, crops),
        "season": season_for_day(day, crops),
        "from": player,
        "text": text,
    }


def _player_name_map() -> dict[str, str]:
    """Map display names and ids (lowercased) to player ids. Built at call time."""
    mapping: dict[str, str] = {}
    for pid in known_players():
        mapping[pid.lower()] = pid
        mapping[display_name(pid).strip().lower()] = pid
    return mapping


def journal_archive_path() -> Path:
    return Path(JOURNAL_ARCHIVE_PATH)


def _load_archive(path: Path | None = None) -> dict:
    dest = path or journal_archive_path()
    if not dest.is_file():
        return {"years": {}}
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"years": {}}
    if not isinstance(data, dict):
        return {"years": {}}
    years = data.get("years")
    if not isinstance(years, dict):
        data["years"] = {}
    return data


def _save_archive(data: dict, path: Path | None = None) -> bool:
    dest = path or journal_archive_path()
    try:
        dest.parent.mkdir(mode=0o700, exist_ok=True)
    except OSError:
        pass
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(dest)
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        return True
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


def _merge_season_lists(existing: list, incoming: list) -> list:
    out = []
    seen = set()
    for entry in list(existing or []) + list(incoming or []):
        if not isinstance(entry, dict):
            continue
        key = _note_key(entry)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    out.sort(key=lambda e: (int(e.get("day") or 0),))
    return out


def _append_entries_to_archive(entries: list[dict], path: Path | None = None) -> bool:
    """Merge entries into the archive file, grouped by year and season. Deduped."""
    by_year: dict[int, dict[str, list]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("text") or not entry.get("from"):
            continue
        year = int(entry.get("year") or 0)
        season = normalize_season(entry.get("season")) or season_for_day(int(entry.get("day") or 1))
        if year < 1:
            continue
        by_year.setdefault(year, {s: [] for s in SEASONS})
        if season in by_year[year]:
            by_year[year][season].append(entry)
    if not by_year:
        return True
    data = _load_archive(path)
    years = data.setdefault("years", {})
    for year, seasons in by_year.items():
        slot = years.get(str(year))
        if not isinstance(slot, dict):
            slot = {s: [] for s in SEASONS}
        for season in SEASONS:
            slot[season] = _merge_season_lists(slot.get(season) or [], seasons.get(season) or [])
        years[str(year)] = slot
    return _save_archive(data, path)


def archive_journal_if_needed(state: dict, crops: dict | None = None, path: Path | None = None) -> bool:
    """If the farm has moved into a new year, file last year's journal and start a fresh one."""
    crops = crops or load_crops()
    journal = state.get("journal")
    current = year_for_day(int(state.get("day") or 1), crops)
    state["year"] = current
    if not isinstance(journal, dict):
        state["journal"] = empty_journal(current)
        return True
    old_year = int(journal.get("year") or 0)
    if old_year >= current:
        if old_year != current and not any(
            (journal.get("seasons") or {}).get(s) for s in SEASONS
        ):
            state["journal"] = empty_journal(current)
            return True
        return False
    seasons = journal.get("seasons") or {}
    outgoing = []
    for season in SEASONS:
        for entry in seasons.get(season) or []:
            if isinstance(entry, dict):
                outgoing.append(entry)
    if outgoing:
        if not _append_entries_to_archive(outgoing, path):
            return False
    state["journal"] = empty_journal(current)
    return True


def ensure_journal(state: dict, crops: dict | None = None) -> dict:
    """Return the current-year journal, creating an empty one if needed."""
    crops = crops or load_crops()
    current = year_for_day(int(state.get("day") or 1), crops)
    journal = state.get("journal")
    if not isinstance(journal, dict):
        journal = empty_journal(current)
        state["journal"] = journal
    journal.setdefault("year", current)
    seasons = journal.setdefault("seasons", {})
    if not isinstance(seasons, dict):
        journal["seasons"] = {s: [] for s in SEASONS}
        seasons = journal["seasons"]
    for season in SEASONS:
        if not isinstance(seasons.get(season), list):
            seasons[season] = []
    # Drop unknown season keys from the live journal (fall is stored as autumn).
    return journal


def record_journal_note(
    state: dict,
    player: str,
    text: str,
    day: int | None = None,
    crops: dict | None = None,
) -> bool:
    """Append a sanitized end-turn note to the current year's journal. Deduped. Returns True if added."""
    crops = crops or load_crops()
    entry = _journal_entry(int(day or state.get("day") or 1), player, text, crops)
    if not entry:
        return False
    current = year_for_day(int(state.get("day") or 1), crops)
    if entry["year"] < current:
        return _append_entries_to_archive([entry])
    if entry["year"] > current:
        # A note from a future year should not land in this year's book.
        return False
    ensure_journal(state, crops)
    if int(state["journal"].get("year") or 0) != current:
        if not archive_journal_if_needed(state, crops):
            return False
    bucket = state["journal"]["seasons"].setdefault(entry["season"], [])
    if any(_note_key(existing) == _note_key(entry) for existing in bucket):
        return False
    bucket.append(entry)
    return True


def _notes_from_legacy(state: dict, crops: dict | None = None) -> list[dict]:
    """Recover end-turn notes already stored in last_note or the game log."""
    crops = crops or load_crops()
    found: list[dict] = []
    seen: set[tuple] = set()
    names = _player_name_map()

    def _add(player, text, day) -> None:
        entry = _journal_entry(day, player, text, crops)
        if not entry:
            return
        key = _note_key(entry)
        if key in seen:
            return
        seen.add(key)
        found.append(entry)

    for item in state.get("log") or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("text") or "")
        match = _LEAVES_A_NOTE.match(raw)
        if not match:
            continue
        body = match.group(2)
        player = item.get("player") or names.get(match.group(1).strip().lower())
        if not player:
            continue
        day = item.get("day") or state.get("day") or 1
        _add(player, body, day)

    note = state.get("last_note")
    if isinstance(note, dict):
        _add(note.get("from"), note.get("text"), note.get("day") or state.get("day") or 1)
    return found


def rebucket_journal(state: dict, crops: dict | None = None) -> None:
    """Recompute each entry's year/season from its day and group it under the right tab."""
    crops = crops or load_crops()
    journal = state.get("journal")
    if not isinstance(journal, dict):
        return
    current = int(journal.get("year") or year_for_day(int(state.get("day") or 1), crops))
    pooled: list[dict] = []
    leftover: list[dict] = []
    for _season, entries in list((journal.get("seasons") or {}).items()):
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            try:
                day = int(entry.get("day") or 0)
            except (TypeError, ValueError):
                continue
            if day < 1:
                continue
            entry["day"] = day
            entry["year"] = year_for_day(day, crops)
            entry["season"] = season_for_day(day, crops)
            if entry["year"] == current:
                pooled.append(entry)
            else:
                leftover.append(entry)
    seasons = {s: [] for s in SEASONS}
    seen = set()
    for entry in pooled:
        key = _note_key(entry)
        if key in seen:
            continue
        seen.add(key)
        seasons[entry["season"]].append(entry)
    for season in SEASONS:
        seasons[season].sort(key=lambda e: (int(e.get("day") or 0),))
    journal["seasons"] = seasons
    journal["year"] = current
    if leftover:
        _append_entries_to_archive(leftover)


def migrate_journal(state: dict, crops: dict | None = None) -> bool:
    """Ensure a current-year journal exists and import any notes already in the save."""
    crops = crops or load_crops()
    before = json.dumps(
        {"year": state.get("year"), "journal": state.get("journal")},
        sort_keys=True,
        ensure_ascii=False,
    )
    current = year_for_day(int(state.get("day") or 1), crops)
    if state.get("year") != current:
        state["year"] = current
    ensure_journal(state, crops)
    archive_journal_if_needed(state, crops)
    imported = _notes_from_legacy(state, crops)
    for entry in imported:
        record_journal_note(
            state,
            entry["from"],
            entry["text"],
            day=entry["day"],
            crops=crops,
        )
    rebucket_journal(state, crops)
    after = json.dumps(
        {"year": state.get("year"), "journal": state.get("journal")},
        sort_keys=True,
        ensure_ascii=False,
    )
    return before != after


def all_journal_entries(state: dict, year: int | None = None) -> list[dict]:
    """Current-year notes, chronological (spring through winter, then by day). Deduped."""
    crops = load_crops()
    ensure_journal(state, crops)
    journal = state["journal"]
    want = int(year or journal.get("year") or year_for_day(int(state.get("day") or 1), crops))
    entries: list[dict] = []
    seen: set[tuple] = set()
    for season in SEASONS:
        for entry in journal.get("seasons", {}).get(season) or []:
            if not isinstance(entry, dict):
                continue
            if int(entry.get("year") or want) != want:
                continue
            key = _note_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    entries.sort(key=lambda e: (int(e.get("day") or 0),))
    return entries


def recent_notes(state: dict, limit: int = RECENT_NOTE_COUNT) -> list[dict]:
    """The last `limit` notes in the current year, most recent first. Deduped."""
    entries = all_journal_entries(state)
    out: list[dict] = []
    seen: set[tuple] = set()
    for entry in reversed(entries):
        key = _note_key(entry)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
        if len(out) >= int(limit):
            break
    return out


def season_journal_entries(state: dict, season: str | None = None) -> tuple[int, dict[str, list[dict]]]:
    """Current-year notes grouped by season. Optional season filters to one canonical season."""
    crops = load_crops()
    ensure_journal(state, crops)
    journal = state["journal"]
    year = int(journal.get("year") or year_for_day(int(state.get("day") or 1), crops))
    wanted = normalize_season(season) if season else None
    grouped = {s: [] for s in SEASONS}
    seen: set[tuple] = set()
    for name in SEASONS:
        if wanted and name != wanted:
            continue
        for entry in journal.get("seasons", {}).get(name) or []:
            if not isinstance(entry, dict):
                continue
            key = _note_key(entry)
            if key in seen:
                continue
            seen.add(key)
            grouped[name].append(entry)
        grouped[name].sort(key=lambda e: (int(e.get("day") or 0),))
    if wanted:
        return year, {wanted: grouped[wanted]}
    return year, grouped


def wither_after(crops: dict) -> int:
    return int(crops.get("wither_after_dry_days", 2))


def season_for_day(day: int, crops: dict | None = None) -> str:
    n = days_per_season(crops)
    return SEASONS[((int(day) - 1) // n) % len(SEASONS)]


def day_in_season(day: int, crops: dict | None = None) -> int:
    n = days_per_season(crops)
    return ((int(day) - 1) % n) + 1


WEATHER_KINDS = ("sun", "cloud", "rain", "storm", "snow")
WET_WEATHER = frozenset({"rain", "storm", "snow"})
DRY_WEATHER = frozenset({"sun", "cloud"})


def weather_rules(rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    raw = rules.get("weather") or {}
    seasons = dict(raw.get("seasons") or {})
    wet = raw.get("wet") or list(WET_WEATHER)
    forecast = dict(raw.get("forecast") or {})
    return {"seasons": seasons, "wet": list(wet), "forecast": forecast}


def weather_mix(seed: int, day: int, salt: int = 0) -> int:
    """Stable mix of the farm's weather seed, a day, and a salt. No RNG."""
    n = (
        (int(seed) * 747796405)
        ^ (int(day) * 73856093)
        ^ (int(salt) * 1664525)
        ^ 0x9E3779B9
    ) & 0xFFFFFFFF
    n = ((n ^ (n >> 16)) * 0x7FEB352D) & 0xFFFFFFFF
    n = ((n ^ (n >> 15)) * 0x846CA68B) & 0xFFFFFFFF
    return n ^ (n >> 16)


def season_weather_weights(season: str, rules: dict | None = None) -> dict[str, int]:
    cfg = weather_rules(rules)
    raw = cfg["seasons"].get(season) or cfg["seasons"].get("spring") or {}
    out: dict[str, int] = {}
    for kind in WEATHER_KINDS:
        try:
            weight = int(raw.get(kind, 0))
        except (TypeError, ValueError):
            weight = 0
        if weight > 0:
            out[kind] = weight
    return out or {"sun": 1}


def _pick_weighted(weights: dict[str, int], roll: int) -> str:
    items = list(weights.items())
    total = sum(w for _k, w in items)
    if total <= 0:
        return "sun"
    r = int(roll) % total
    acc = 0
    for kind, weight in items:
        acc += weight
        if r < acc:
            return kind
    return items[-1][0]


def weather_for_day(
    day: int,
    crops: dict | None = None,
    rules: dict | None = None,
    seed: int | None = None,
    state: dict | None = None,
) -> str:
    """Deterministic weather from the farm seed and the day number. No RNG is used."""
    if seed is None and state is not None:
        raw = state.get("weather_seed")
        if raw is not None and raw != "":
            seed = int(raw)
    if seed is None:
        seed = 0
    rules = rules or load_rules()
    season = season_for_day(day, crops)
    weights = season_weather_weights(season, rules)
    return _pick_weighted(weights, weather_mix(int(seed), int(day), salt=1))


def find_weather_seed(
    required: dict[int, str],
    rules: dict | None = None,
    crops: dict | None = None,
    start: int = 0,
    limit: int = 2_000_000,
) -> int:
    """First seed in [start, start+limit) that produces the required day→weather map."""
    rules = rules or load_rules()
    want = {int(d): str(w) for d, w in required.items()}
    for seed in range(int(start), int(start) + int(limit)):
        if all(weather_for_day(day, crops, rules, seed=seed) == kind for day, kind in want.items()):
            return seed
    # Extremely unlikely with the default tables; keep a defined fallback.
    return int(start)


def ensure_weather_seed(state: dict, rules: dict | None = None, crops: dict | None = None) -> bool:
    """Add weather_seed if missing, without changing today's already-set weather."""
    rules = rules or load_rules()
    crops = crops or load_crops()
    if state.get("weather_seed") is not None and str(state.get("weather_seed")) != "":
        try:
            state["weather_seed"] = int(state["weather_seed"])
        except (TypeError, ValueError):
            state["weather_seed"] = 0
            return True
        return False
    day = int(state.get("day") or 1)
    current = str(state.get("weather") or "sun")
    if current not in WEATHER_KINDS:
        current = "sun"
    state["weather_seed"] = find_weather_seed({day: current}, rules, crops)
    return True


def forecast_length(rules: dict | None = None) -> int:
    cfg = weather_rules(rules).get("forecast") or {}
    try:
        n = int(cfg.get("days", 7))
    except (TypeError, ValueError):
        n = 7
    return max(1, n)


def forecast_accuracy(lead: int, rules: dict | None = None) -> float:
    """Chance the forecast made today is right for a day `lead` days ahead."""
    cfg = weather_rules(rules).get("forecast") or {}
    try:
        near = float(cfg.get("near", 0.90))
        far = float(cfg.get("far", 0.50))
    except (TypeError, ValueError):
        near, far = 0.90, 0.50
    n = forecast_length(rules)
    lead = int(lead)
    if lead <= 1:
        return near
    if lead >= n:
        return far
    return near + (far - near) * (lead - 1) / (n - 1)


def forecast_weather(
    target_day: int,
    made_on: int,
    seed: int,
    crops: dict | None = None,
    rules: dict | None = None,
) -> str:
    """Predicted weather for target_day, as forecast on made_on (deterministic)."""
    rules = rules or load_rules()
    actual = weather_for_day(target_day, crops, rules, seed=seed)
    lead = int(target_day) - int(made_on)
    if lead <= 0:
        return actual
    acc = forecast_accuracy(lead, rules)
    # Compare in 1/10000ths so this stays integer and stable.
    threshold = int(round(acc * 10000))
    roll = weather_mix(int(seed), int(made_on), salt=int(target_day) * 0x27d4eb2d) % 10000
    if roll < threshold:
        return actual
    season = season_for_day(target_day, crops)
    weights = dict(season_weather_weights(season, rules))
    weights.pop(actual, None)
    if not weights:
        return actual
    return _pick_weighted(weights, weather_mix(int(seed), int(made_on), salt=int(target_day) * 0x165667B1))


def weather_forecast(state: dict, crops: dict | None = None, rules: dict | None = None, days: int | None = None) -> list[dict]:
    """Next-N-day forecast, re-derived from the seed and the day it is made."""
    rules = rules or load_rules()
    crops = crops or load_crops()
    ensure_weather_seed(state, rules, crops)
    seed = int(state["weather_seed"])
    made_on = int(state.get("day") or 1)
    n = int(days) if days is not None else forecast_length(rules)
    out = []
    for lead in range(1, n + 1):
        target = made_on + lead
        predicted = forecast_weather(target, made_on, seed, crops, rules)
        out.append(
            {
                "day": target,
                "lead": lead,
                "season": season_for_day(target, crops),
                "weather": predicted,
            }
        )
    return out


def is_wet_weather(weather: str) -> bool:
    return weather in WET_WEATHER


def crop_info(crops: dict, kind: str) -> dict | None:
    return crops.get("crops", {}).get(kind)


def normalize_kind(kind: str) -> str:
    k = (kind or "").strip().lower().replace(" ", "_")
    for suffix in ("_seedling", "_seed"):
        if k.endswith(suffix):
            k = k[: -len(suffix)]
            break
    aliases = {
        "everbearing_strawberry": "everbearing",
        "everbearingstrawberry": "everbearing",
    }
    return aliases.get(k, k)


def crop_name(kind: str, info: dict | None = None) -> str:
    if info and info.get("name"):
        return str(info["name"])
    return kind


def crop_name_plural(kind: str, info: dict | None = None, count: int = 1) -> str:
    if count == 1:
        return crop_name(kind, info)
    if info and info.get("name_plural"):
        return str(info["name_plural"])
    name = crop_name(kind, info)
    if name.endswith("s"):
        return name
    return name + "s"


def stock_word(info: dict | None = None) -> str:
    word = str((info or {}).get("stock") or "seed").strip().lower()
    return word or "seed"


def stock_key(kind: str, info: dict | None = None) -> str:
    return f"{kind}_{stock_word(info)}"


def stock_noun(info: dict | None = None, count: int = 1) -> str:
    word = stock_word(info)
    if count == 1:
        return word
    if word.endswith("s"):
        return word
    return word + "s"


def shop_name(kind: str, info: dict | None = None) -> str:
    if info and info.get("shop_name"):
        return str(info["shop_name"])
    return f"{crop_name(kind, info)} {stock_word(info)}"


def initial_stage(info: dict | None = None) -> str:
    if not info:
        return "seed"
    stages = info.get("stages") or []
    if stages:
        first = sorted(stages, key=lambda s: int(s.get("at") or 0))[0]
        return str(first.get("id") or "seed")
    return "seed"


def a_or_an(word: str) -> str:
    text = (word or "").strip()
    if not text:
        return "a"
    return "an" if text[0].lower() in "aeiou" else "a"


def stage_for(days_grown: int, info: dict, crop: dict | None = None) -> str:
    if crop and regrow_days(info) > 0 and int(crop.get("harvests") or 0) > 0:
        needed = regrow_days(info)
        if days_grown >= needed:
            return "mature"
        if days_grown <= 0:
            return "regrowing"
        return "growing"
    stages = sorted(info["stages"], key=lambda s: int(s["at"]))
    current = stages[0]["id"]
    for stage in stages:
        if days_grown >= int(stage["at"]):
            current = stage["id"]
    return current


def stage_label(info: dict, stage_id: str) -> str:
    if stage_id == "regrowing":
        return "regrowing"
    if stage_id == "dormant":
        return "dormant"
    for stage in info.get("stages", []):
        if stage["id"] == stage_id:
            return stage.get("label", stage_id)
    return stage_id


def grow_days(info: dict) -> int:
    return int(info["grow_days"])


def regrow_days(info: dict) -> int:
    return int(info.get("regrow_days") or 0)


def crop_in_shop(info: dict) -> bool:
    if not info:
        return False
    return info.get("available", True) is not False


def crop_shop_seasons(info: dict | None) -> list:
    if not info:
        return []
    return list(info.get("shop_seasons") or info.get("seasons") or [])


def crop_in_season(info: dict, season: str | None) -> bool:
    """Whether the shop sells this crop in the given season."""
    if not info:
        return False
    if not season:
        return True
    return season in crop_shop_seasons(info)


def crop_for_sale(info: dict, season: str | None = None) -> bool:
    return crop_in_shop(info) and crop_in_season(info, season)


def shop_kinds(crops: dict, season: str | None = None) -> list[str]:
    return [
        kind
        for kind, info in (crops.get("crops") or {}).items()
        if crop_for_sale(info, season)
    ]


def fertilizer_shop_items(season: str | None = None, rules: dict | None = None) -> list[str]:
    from inventory import FERTILIZERS, FERTILIZER_SHOP_SEASONS
    if season and season not in FERTILIZER_SHOP_SEASONS:
        return []
    return list(FERTILIZERS.keys())


def shop_listing(crops: dict, season: str | None = None, rules: dict | None = None) -> list[str]:
    return shop_kinds(crops, season) + fertilizer_shop_items(season, rules)


def is_perennial(info: dict | None) -> bool:
    if not info:
        return False
    return bool(info.get("perennial")) or int(info.get("lifespan_seasons") or 0) > 0


def lifespan_seasons(info: dict | None) -> int:
    return int((info or {}).get("lifespan_seasons") or 0)


def season_index(day: int, crops: dict | None = None) -> int:
    n = days_per_season(crops)
    return (max(1, int(day)) - 1) // n


def crop_season_age(crop: dict, day: int, crops: dict | None = None) -> int:
    planted = int(crop.get("planted_day") or day)
    return season_index(day, crops) - season_index(planted, crops) + 1


def crop_is_dormant(crop: dict | None, info: dict | None, season: str | None) -> bool:
    if not crop or not info or crop.get("stage") == "withered":
        return False
    if crop.get("stage") == "dormant":
        return True
    if is_perennial(info) and season not in (info.get("seasons") or []):
        return True
    return False


def in_fruiting_window(state: dict, info: dict, crops: dict | None = None) -> bool:
    season = state.get("season")
    fruiting = info.get("fruiting_seasons") or info.get("seasons") or []
    if season not in fruiting:
        return False
    day_no = day_in_season(int(state["day"]), crops)
    # Only apply an early-season cutoff when the crop defines one.
    if season == "summer" and info.get("fruiting_early_summer_days"):
        return day_no <= int(info.get("fruiting_early_summer_days"))
    if season == "autumn" and info.get("fruiting_early_autumn_days"):
        return day_no <= int(info.get("fruiting_early_autumn_days"))
    return True


def crop_can_fruit(crop: dict, info: dict, state: dict, crops: dict | None = None) -> bool:
    if not is_perennial(info):
        return True
    if info.get("fruiting_after_dormancy", True) and not crop.get("overwintered"):
        return False
    return in_fruiting_window(state, info, crops)


def runner_chance_pct(info: dict) -> int:
    ch = (info or {}).get("runner_chance")
    if not ch:
        return 0
    return int(round(float(ch) * 100))


def runner_roll(day: int, row: int, col: int, seed: int, chance_pct: int) -> bool:
    """Deterministic 0–99 roll; True if the runner takes root this day."""
    if chance_pct <= 0:
        return False
    n = weed_hash(int(day), int(row), int(col), salt=int(seed) ^ 4242)
    return (n % 100) < int(chance_pct)


def crop_cycle_days(info: dict, crop: dict | None = None) -> int:
    if crop and regrow_days(info) > 0 and int(crop.get("harvests") or 0) > 0:
        return regrow_days(info)
    return grow_days(info)


def ensure_inventory_keys(state: dict, crops: dict | None = None) -> bool:
    """Install packs and the cabin chest, then refresh the totals view."""
    from inventory import migrate_inventory, sync_inventory_view

    changed = migrate_inventory(state, crops or load_crops(), load_rules())
    sync_inventory_view(state)
    return changed


def position_name(row: int, col: int) -> str:
    common = POSITION_NAMES.get((row, col), "plot")
    return f"{common}, row {row} col {col}"


def parse_row_col(row, col) -> tuple[int | None, int | None, str | None]:
    try:
        r = int(row)
        c = int(col)
    except (TypeError, ValueError):
        return None, None, "Use row and column numbers from 1 to 3, like: water 2 1"
    if not (1 <= r <= ROWS and 1 <= c <= COLS):
        return None, None, "Row and column must each be 1, 2, or 3."
    return r, c, None


def get_tile(state: dict, row: int, col: int) -> dict:
    return state["tiles"][row - 1][col - 1]


def iter_tiles(state: dict):
    for r in range(1, ROWS + 1):
        for c in range(1, COLS + 1):
            yield r, c, get_tile(state, r, c)


def log_append(state: dict, text: str, player: str | None = None) -> None:
    entry = {"day": int(state["day"]), "text": text}
    if player:
        entry["player"] = player
    state.setdefault("log", []).append(entry)
    if len(state["log"]) > MAX_LOG:
        state["log"] = state["log"][-MAX_LOG:]


def fresh_state(crops: dict | None = None, weather_seed: int | None = None, rules: dict | None = None) -> dict:
    crops = crops or load_crops()
    rules = rules or load_rules()
    inventory = {key: int(val) for key, val in crops.get("starting_inventory", {}).items()}
    for kind, info in (crops.get("crops") or {}).items():
        inventory.setdefault(stock_key(kind, info), 0)
        inventory.setdefault(kind, 0)
    tiles = []
    for r in range(1, ROWS + 1):
        row = []
        for c in range(1, COLS + 1):
            if r == CABIN_ROW and c == CABIN_COL:
                row.append(
                    {
                        "type": "cabin",
                        "tilled": False,
                        "watered": False,
                        "crop": None,
                        "weed": None,
                        "weedy": False,
                        "weedy_ticks": 0,
                    }
                )
            else:
                row.append(
                    {
                        "type": "soil",
                        "tilled": False,
                        "watered": False,
                        "crop": None,
                        "weed": None,
                        "weedy": False,
                        "weedy_ticks": 0,
                    }
                )
        tiles.append(row)
    day = 1
    if weather_seed is None:
        weather_seed = find_weather_seed({1: "sun"}, rules, crops)
    weather_seed = int(weather_seed)
    weather = weather_for_day(day, crops, rules, seed=weather_seed)
    state = {
        "day": day,
        "season": season_for_day(day, crops),
        "days_per_season": days_per_season(crops),
        "weather": weather,
        "weather_seed": weather_seed,
        "gold": int(crops.get("starting_gold", 80)),
        "inventory": inventory,
        "tiles": tiles,
        "log": [
            {
                "day": 1,
                "text": __flavor_intro(),
            }
        ],
        "last_note": None,
        "year": 1,
        "journal": empty_journal(1),
    }
    apply_new_day_turns(state, rules)
    from inventory import migrate_inventory
    migrate_inventory(state, crops, rules)
    if is_wet_weather(weather):
        dawn_water(state, rules)
        log_append(state, weather_arrive_message(weather))
    return state



def till_hold_days(rules: dict | None = None) -> int:
    """Days an empty tilled bed stays open without water before it reverts."""
    rules = rules or load_rules()
    try:
        n = int(rules.get("till_hold_days") or 5)
    except (TypeError, ValueError):
        n = 5
    return max(1, n)


def tile_is_living_plant(tile: dict) -> bool:
    crop = tile.get("crop")
    return bool(crop and crop.get("stage") not in (None, "withered"))


def reset_till_hold(tile: dict, rules: dict | None = None) -> None:
    if tile.get("type") == "cabin":
        tile.pop("untilled_in", None)
        return
    tile["untilled_in"] = till_hold_days(rules)


def clear_till_hold(tile: dict) -> None:
    tile.pop("untilled_in", None)


def till_hold_left(tile: dict, rules: dict | None = None) -> int | None:
    """Days left before an empty tilled bed reverts, or None if it does not apply."""
    if tile.get("type") == "cabin" or not tile.get("tilled"):
        return None
    if tile_is_living_plant(tile):
        return None
    raw = tile.get("untilled_in")
    if raw is None:
        return till_hold_days(rules)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return till_hold_days(rules)


def till_hold_phrase(tile: dict, rules: dict | None = None) -> str:
    left = till_hold_left(tile, rules)
    if left is None:
        return ""
    if left <= 0:
        return " It will go untilled at nightfall if it stays empty."
    day_word = "day" if left == 1 else "days"
    return f" {left} {day_word} left until it reverts if left unwatered."


def tick_till_hold(state: dict, tile: dict, row: int, col: int, notes: list, rules: dict | None = None) -> None:
    """Evening tick for an empty (or withered) tilled bed. Watering resets; five dry days revert."""
    if tile.get("type") != "soil" or not tile.get("tilled"):
        tile.pop("untilled_in", None)
        return
    if tile_is_living_plant(tile):
        tile.pop("untilled_in", None)
        return
    hold = till_hold_days(rules)
    if tile.get("watered"):
        tile["untilled_in"] = hold
        return
    left = till_hold_left(tile, rules)
    if left is None:
        left = hold
    left -= 1
    if left <= 0:
        tile["tilled"] = False
        tile.pop("untilled_in", None)
        notes.append(f"The soil at {position_name(row, col)} has gone untilled after sitting empty.")
    else:
        tile["untilled_in"] = left


def dawn_water(state: dict, rules: dict | None = None) -> None:
    for _r, _c, tile in iter_tiles(state):
        if tile["type"] == "soil":
            tile["watered"] = True
            if tile.get("tilled") and not tile_is_living_plant(tile):
                reset_till_hold(tile, rules)


def __flavor_intro() -> str:
    from config import flavor
    return flavor("intro_log") or "A small farm. The cabin lantern in the top-right is already lit."


def weather_arrive_message(weather: str) -> str:
    from config import flavor
    if weather == "rain":
        return flavor("rain") or "Rain falls over the farm. Every plot is watered."
    if weather == "storm":
        return flavor("storm") or "A storm rolls over the farm. Every plot is watered."
    if weather == "snow":
        return flavor("snow") or "Snow settles on the farm. The soil is wet beneath it."
    if weather == "cloud":
        return flavor("cloud") or "The sky is overcast. The soil stays as you left it."
    return flavor("clear") or "A clear day dawns over the farm."


def save_state(state: dict, path: Path | None = None) -> None:
    dest = path or STATE_PATH
    tmp = dest.with_suffix(".json.tmp")
    text = json.dumps(state, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dest)


def load_state(crops: dict | None = None, path: Path | None = None) -> dict:
    src = path or STATE_PATH
    if not src.exists():
        state = fresh_state(crops)
        save_state(state, src)
        return state
    state = json.loads(src.read_text(encoding="utf-8"))
    if migrate_state(state, load_rules()):
        save_state(state, src)
    return state


@contextmanager
def session(write: bool = True, crops: dict | None = None, path: "Path | None" = None):
    """Lock, load, optionally save state.json. Safe for CLI and web together."""
    crops = crops or load_crops()
    dest = path or STATE_PATH
    lock_path = LOCK_PATH if dest == STATE_PATH else Path(str(dest) + ".lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            state = load_state(crops, dest)
            yield state, crops
            if write:
                save_state(state, dest)
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def reset_state(crops: dict | None = None) -> dict:
    crops = crops or load_crops()
    state = fresh_state(crops)
    save_state(state)
    return state


def apply_new_day_turns(state: dict, rules: dict | None = None) -> None:
    """Start a day from last night's positions: cabin sleep is full energy, passing out is half."""
    from config import starting_player as config_starting_player
    rules = rules or load_rules()
    cap = max_energy(rules)
    faint = pass_out_energy(rules)
    starter = normalize_player(config_starting_player()) or normalize_player(rules.get("starting_player"))
    names = list(known_players()) or [p for p in (rules.get("players") or [])]
    existing = state.get("players") or {}
    slots = {}
    for name in names:
        key = normalize_player(name) or (str(name).strip().lower() if name else None)
        if not key:
            continue
        prev = existing.get(key) or {}
        try:
            row = int(prev.get("row") or 0)
            col = int(prev.get("col") or 0)
        except (TypeError, ValueError):
            row, col = 0, 0
        if not in_bounds(row, col):
            row, col = CABIN_ROW, CABIN_COL
        slept = is_cabin_at(row, col)
        from inventory import empty_pack, normalize_pack

        slots[key] = {
            "energy": cap if slept else faint,
            "ended_turn": False,
            "row": CABIN_ROW if slept else row,
            "col": CABIN_COL if slept else col,
            "snacks_eaten": 0,
            "pack": normalize_pack(prev.get("pack")) if prev.get("pack") is not None else empty_pack(),
        }
    for key in known_players():
        if key not in slots:
            from inventory import empty_pack

            slots[key] = {
                "energy": cap,
                "ended_turn": False,
                "row": CABIN_ROW,
                "col": CABIN_COL,
                "snacks_eaten": 0,
                "pack": empty_pack(),
            }
    state["players"] = slots
    fallback = next(iter(slots), "player1")
    state["current_player"] = starter if starter in slots else fallback


def migrate_tile_fields(state: dict) -> bool:
    """Add weed fields to older tiles without touching the rest of the save."""
    changed = False
    for _r, _c, tile in iter_tiles(state):
        if "weed" not in tile:
            tile["weed"] = None
            changed = True
        if "weedy" not in tile:
            tile["weedy"] = False
            changed = True
        if "weedy_ticks" not in tile:
            tile["weedy_ticks"] = 0
            changed = True
        if tile.get("type") == "soil" and tile.get("tilled"):
            if tile_is_living_plant(tile):
                if "untilled_in" in tile:
                    tile.pop("untilled_in", None)
                    changed = True
            elif "untilled_in" not in tile:
                reset_till_hold(tile)
                changed = True
        elif "untilled_in" in tile and not tile.get("tilled"):
            tile.pop("untilled_in", None)
            changed = True
    return changed



LEGACY_DAYS_PER_SEASON = 14
LEGACY_GROW_DAYS = {"kabocha": 7, "turnip": 4, "carrot": 5, "strawberry": 5}


def remap_calendar_day(day, old_n: int, new_n: int):
    """Map a day from one season length to another, keeping season and day-in-season."""
    try:
        day = int(day)
    except (TypeError, ValueError):
        return day
    if day < 1 or old_n == new_n or old_n <= 0 or new_n <= 0:
        return day
    idx = (day - 1) // old_n
    into = (day - 1) % old_n + 1
    into = min(into, new_n)
    return idx * new_n + into


def migrate_calendar(state: dict, crops: dict | None = None) -> bool:
    """Remap day numbers when days_per_season changes. Idempotent. Never kills living plants."""
    crops = crops or load_crops()
    new_n = days_per_season(crops)
    raw = state.get("days_per_season")
    if raw is None:
        old_n = LEGACY_DAYS_PER_SEASON
    else:
        old_n = int(raw)
    if old_n == new_n:
        if state.get("days_per_season") != new_n:
            state["days_per_season"] = new_n
            return True
        return False
    state["day"] = remap_calendar_day(state.get("day") or 1, old_n, new_n)
    state["season"] = season_for_day(int(state["day"]), crops)
    note = state.get("last_note")
    if isinstance(note, dict) and "day" in note:
        note["day"] = remap_calendar_day(note["day"], old_n, new_n)
    for entry in state.get("log") or []:
        if isinstance(entry, dict) and "day" in entry:
            entry["day"] = remap_calendar_day(entry["day"], old_n, new_n)
    journal = state.get("journal")
    if isinstance(journal, dict):
        for _season, entries in list((journal.get("seasons") or {}).items()):
            for entry in entries or []:
                if isinstance(entry, dict) and "day" in entry:
                    entry["day"] = remap_calendar_day(entry["day"], old_n, new_n)
        rebucket_journal(state, crops)
    for r, c, tile in iter_tiles(state):
        weed = tile.get("weed")
        if isinstance(weed, dict) and "appeared_day" in weed:
            weed["appeared_day"] = remap_calendar_day(weed["appeared_day"], old_n, new_n)
        crop = tile.get("crop")
        if not crop:
            continue
        if "planted_day" in crop:
            crop["planted_day"] = remap_calendar_day(crop["planted_day"], old_n, new_n)
        if crop.get("stage") == "withered":
            continue
        kind = crop.get("kind")
        info = crop_info(crops, kind) or {}
        old_g = int(LEGACY_GROW_DAYS.get(kind, grow_days(info) if info else 0) or 0)
        new_g = grow_days(info) if info else old_g
        if old_g and new_g:
            remaining = max(0, old_g - int(crop.get("days_grown") or 0))
            crop["days_grown"] = max(0, new_g - remaining)
            if crop["days_grown"] >= new_g:
                crop["days_grown"] = new_g
                crop["stage"] = "mature"
            elif info:
                crop["stage"] = stage_for(crop["days_grown"], info, crop)
    state["days_per_season"] = new_n
    # Keep today's weather; only the day number and season label were remapped.
    return True



def migrate_state(state: dict, rules: dict | None = None) -> bool:
    """Add turn/energy/weed fields to older saves. Returns True if the state changed."""
    rules = rules or load_rules()
    changed = migrate_tile_fields(state)
    if ensure_inventory_keys(state):
        changed = True
    if migrate_crop_vitals(state):
        changed = True
    if migrate_calendar(state, load_crops()):
        changed = True
    if "last_note" not in state:
        state["last_note"] = None
        changed = True
    if migrate_journal(state, load_crops()):
        changed = True
    if ensure_weather_seed(state, rules, None):
        changed = True
    if state.get("players") and state.get("current_player"):
        # Fill any missing slots without resetting mid-turn energy.
        for key in KNOWN_PLAYERS:
            if key not in state["players"]:
                state["players"][key] = {
                    "energy": max_energy(rules),
                    "ended_turn": False,
                    "row": CABIN_ROW,
                    "col": CABIN_COL,
                    "snacks_eaten": 0,
                }
                changed = True
            else:
                slot = state["players"][key]
                slot.setdefault("energy", max_energy(rules))
                slot.setdefault("ended_turn", False)
                # Missing positions go to the cabin. Never change mid-turn energy.
                if "row" not in slot or "col" not in slot:
                    slot["row"] = CABIN_ROW
                    slot["col"] = CABIN_COL
                    changed = True
                slot.setdefault("row", CABIN_ROW)
                slot.setdefault("col", CABIN_COL)
                if "snacks_eaten" not in slot:
                    slot["snacks_eaten"] = 0
                    changed = True
        return changed
    apply_new_day_turns(state, rules)
    return True


def other_player(player: str, rules: dict | None = None) -> str:
    from config import other_player_id
    rules = rules or load_rules()
    players = [normalize_player(p) for p in (list(known_players()) or rules.get("players") or [])]
    players = [p for p in players if p]
    if player in players:
        return players[(players.index(player) + 1) % len(players)]
    return other_player_id(player)


def _apply_end_note(state: dict, player: str, note: str | None) -> str:
    """Store or clear the last note. Returns the sanitized note, if any."""
    text = sanitize_note(note)
    incoming = state.get("last_note") or None
    # A note from the other player lasts until this player ends their turn.
    if incoming and incoming.get("from") and incoming.get("from") != player and not text:
        state["last_note"] = None
    if text:
        state["last_note"] = {
            "from": player,
            "text": text,
            "day": int(state["day"]),
        }
        record_journal_note(state, player, text, day=int(state["day"]))
        log_append(
            state,
            f"{display_name(player)} leaves a note: {text}",
            player,
        )
    return text


def end_turn(
    state: dict,
    crops: dict,
    player: str,
    rules: dict | None = None,
    note: str | None = None,
) -> tuple[bool, str]:
    rules = rules or load_rules()
    player, err = parse_player(player)
    if err:
        return False, err
    current = normalize_player(state.get("current_player"))
    if current != player:
        return False, f"It's {display_name(current)}'s turn right now."
    note_text = _apply_end_note(state, player, note)
    player_slot(state, player)["ended_turn"] = True
    everyone_done = all(
        bool(player_slot(state, name).get("ended_turn"))
        for name in (normalize_player(p) for p in (rules.get("players") or KNOWN_PLAYERS))
        if name
    )
    night_notes = []
    for name in known_players():
        where = describe_where(*player_where(state, name))
        if is_player_in_cabin(state, name):
            night_notes.append(
                f"{display_name(name)} slept in the cabin and wakes with {max_energy(rules)} energy."
            )
        else:
            night_notes.append(
                f"{display_name(name)} passed out {where} and wakes with {pass_out_energy(rules)} energy."
            )
    outlook = sleep_outlook(state, player, rules)
    here = describe_where(*player_where(state, player))
    if everyone_done:
        _ok, day_msg = advance_day(state, crops, rules)
        apply_new_day_turns(state, rules)
        nxt = state["current_player"]
        cap = max_energy(rules)
        night = " ".join(night_notes)
        header = (
            f"{display_name(player)} ends the turn {here}. {outlook}. "
            f"The day turns. {day_msg} {night} "
            f"It is {display_name(nxt)}'s turn, {player_slot(state, nxt)['energy']}/{cap} energy."
        )
        log_append(
            state,
            f"{display_name(player)} ends the turn {here}. A new day begins. {night} "
            f"It is {display_name(nxt)}'s turn.",
            player,
        )
        return True, header
    nxt = other_player(player, rules)
    state["current_player"] = nxt
    # Same-day handoff keeps the other player's energy for this day.
    # (Passing out or sleeping is resolved when the day actually turns.)
    cap = max_energy(rules)
    msg = (
        f"{display_name(player)} ends the turn {here}. {outlook}. "
        f"It is {display_name(nxt)}'s turn, {player_slot(state, nxt)['energy']}/{cap} energy."
    )
    log_append(state, msg, player)
    return True, msg


# --- actions -----------------------------------------------------------------

def till(state: dict, crops: dict, row, col, player: str | None = None) -> tuple[bool, str]:
    r, c, err = parse_row_col(row, col)
    if err:
        return False, err
    tile = get_tile(state, r, c)
    here = position_name(r, c)
    if tile["type"] == "cabin":
        return False, f"That's the cabin ({here}). You can't till the porch."
    crop = tile.get("crop")
    if crop and crop.get("stage") != "withered":
        info = crop_info(crops, crop.get("kind")) or {}
        if crop_is_dormant(crop, info, state.get("season")):
            return False, (
                f"A dormant {crop['kind']} is still living at {here}. "
                "You can't till the bed while it rests."
            )
        return False, f"A {crop['kind']} is growing at {here}. Harvest or wait before tilling."
    cleared = ""
    if crop and crop.get("stage") == "withered":
        tile["crop"] = None
        cleared = f" {who(player, 'clear', 'clears')} the withered plant."
    if tile.get("tilled") and not cleared:
        return False, f"{here[0].upper() + here[1:]} is already tilled."
    if player:
        from inventory import pack_has, TOOL_HOE, sync_inventory_view, item_name
        if not pack_has(state, player, TOOL_HOE):
            return False, (
                f"{display_name(player)} needs a hoe in their pack to till. "
                "Take one from the cabin chest."
            )
    tile["tilled"] = True
    reset_till_hold(tile)
    msg = f"{who(player, 'till', 'tills')} the soil at {here}.{cleared}"
    log_append(state, msg, player)
    return True, msg


def plant(state: dict, crops: dict, row, col, kind, player: str | None = None) -> tuple[bool, str]:
    r, c, err = parse_row_col(row, col)
    if err:
        return False, err
    kind = normalize_kind(str(kind))
    info = crop_info(crops, kind)
    if not info:
        known = ", ".join(crops.get("crops", {}))
        return False, f"Unknown crop {kind!r}. The shop sells: {known}."
    tile = get_tile(state, r, c)
    here = position_name(r, c)
    if tile["type"] == "cabin":
        return False, f"That's the cabin ({here}). You can't plant there."
    if not tile.get("tilled"):
        return False, f"{here[0].upper() + here[1:]} isn't tilled yet. Till it first."
    crop = tile.get("crop")
    if crop and crop.get("stage") == "withered":
        return False, f"A withered plant is still at {here}. Till or harvest to clear it first."
    if crop:
        return False, f"Something is already growing at {here}."
    if state["season"] not in info["seasons"]:
        when = ", ".join(info["seasons"])
        name = crop_name(kind, info)
        return False, f"{name[0].upper() + name[1:]} only grows in {when}. It is {state['season']}."
    seed_key = stock_key(kind, info)
    name = crop_name(kind, info)
    noun = stock_noun(info, 1)
    nouns = stock_noun(info, 2)
    from inventory import pack_has, take_available, sync_inventory_view
    have = int(state["inventory"].get(seed_key, 0) or 0)
    if player and not pack_has(state, player, seed_key):
        return False, (
            f"No {name} {nouns} in the pack. Take some from the cabin chest, "
            "or buy them at the shop."
        )
    if not player and have < 1:
        return False, f"You have no {name} {nouns}. Buy some at the shop."
    taken = take_available(state, seed_key, 1, player, pack_only=bool(player))
    if taken < 1:
        return False, f"You have no {name} {nouns}. Buy some at the shop."
    tile["crop"] = {
        "kind": kind,
        "planted_day": int(state["day"]),
        "days_grown": 0,
        "stage": initial_stage(info),
        "dry_days": 0,
        "growth": 0,
        "health": 100,
    }
    clear_till_hold(tile)
    msg = f"{who(player, 'plant', 'plants')} {a_or_an(name)} {name} {noun} at {here}."
    log_append(state, msg, player)
    return True, msg


def water(state: dict, crops: dict, row, col, player: str | None = None) -> tuple[bool, str]:
    r, c, err = parse_row_col(row, col)
    if err:
        return False, err
    tile = get_tile(state, r, c)
    here = position_name(r, c)
    if tile["type"] == "cabin":
        return False, f"That's the cabin ({here}). The porch doesn't need watering."
    crop = tile.get("crop")
    info = crop_info(crops, crop["kind"]) if crop and crop.get("kind") else {}
    if crop and crop_is_dormant(crop, info, state.get("season")):
        return False, f"The {crop['kind']} at {here} is dormant and doesn't need water."
    if tile.get("watered"):
        return False, f"{here[0].upper() + here[1:]} is already watered today."
    if player:
        from inventory import pack_has, TOOL_CAN
        if not pack_has(state, player, TOOL_CAN):
            return False, (
                f"{display_name(player)} needs a watering can in their pack. "
                "Take one from the cabin chest."
            )
    tile["watered"] = True
    if not tile_is_living_plant(tile):
        reset_till_hold(tile)
    if crop and crop.get("stage") != "withered":
        msg = f"{who(player, 'water', 'waters')} the {crop['kind']} at {here}."
    else:
        msg = f"{who(player, 'water', 'waters')} the soil at {here}."
    log_append(state, msg, player)
    return True, msg



# Hidden growth / health and whole-item yields (see docs/granular-growth.md).
MIN_HARVEST_GROWTH = {
    "strawberry": 70,
    "everbearing": 70,
    "kabocha": 60,
    "turnip": 70,
    "carrot": 75,
}
YIELD_RANGE = {
    "strawberry": (1, 3),
    "everbearing": (1, 3),
    "kabocha": (1, 2),
    "turnip": (1, 2),
    "carrot": (1, 2),
}


def min_harvest_growth(kind: str) -> int:
    return int(MIN_HARVEST_GROWTH.get(kind, 70))


def yield_range_for(kind: str) -> tuple[int, int]:
    lo, hi = YIELD_RANGE.get(kind, (1, 2))
    return max(1, int(lo)), max(1, int(hi))


def crop_can_be_harvested(crop: dict, info: dict | None, state: dict, crops: dict | None = None) -> bool:
    if not crop or crop.get("stage") in {None, "withered"}:
        return False
    if crop_is_dormant(crop, info, state.get("season")) and crop.get("stage") != "mature":
        return False
    if info and is_perennial(info) and not crop_can_fruit(crop, info, state, crops):
        return False
    ensure_crop_vitals(crop, info)
    growth = int(crop.get("growth") or 0)
    return growth >= min_harvest_growth(crop.get("kind") or "")


def _quality(growth: int, health: int, bonus: float = 0.0) -> float:
    q = (max(0, min(100, growth)) / 100.0) * (max(0, min(100, health)) / 100.0)
    return max(0.0, min(1.0, q + bonus))


def yield_roll(
    kind: str,
    growth: int,
    health: int,
    day: int,
    row: int,
    col: int,
    harvest_index: int = 0,
    bonus: float = 0.0,
) -> int:
    """Deterministic weighted roll. Always at least 1 if called for a legal harvest."""
    lo, hi = yield_range_for(kind)
    if hi <= lo:
        return lo
    q = _quality(growth, health, bonus)
    r = weed_hash(int(day), int(row), int(col), salt=7000 + int(harvest_index)) % 100
    if hi == 3:
        p3 = 5 + 75 * (q ** 1.5)
        p2 = p3 + (20 + 40 * q)
        if r < p3:
            return 3
        if r < min(100, p2):
            return 2
        return 1
    # 1–2 range
    p2 = 15 + 70 * q
    return 2 if r < p2 else 1


def fertilizer_on_tile(tile: dict | None, state: dict, crops: dict | None = None) -> dict | None:
    """Return the bag on this plot if it still counts for the current season."""
    fert = tile.get("fertilizer") if isinstance(tile, dict) else None
    if not isinstance(fert, dict) or not fert.get("kind"):
        return None
    season = state.get("season")
    year = year_for_day(int(state.get("day") or 1), crops)
    if fert.get("season") == season and int(fert.get("year") or 0) == int(year):
        return fert
    return None


def fertilizer_phrase(tile: dict | None, state: dict, crops: dict | None = None) -> str:
    fert = fertilizer_on_tile(tile, state, crops)
    if not fert:
        return ""
    kind = fert.get("kind")
    if kind == "general":
        return " The soil is fertilized (general)."
    if kind == "yield":
        return " The soil is fed with yield-boost fertilizer."
    if kind == "growth":
        return " The soil is fed with growth-boost fertilizer."
    return " The soil is fertilized."


def clear_expired_fertilizer(state: dict, crops: dict | None = None) -> None:
    for _r, _c, tile in iter_tiles(state):
        fert = tile.get("fertilizer")
        if not fert:
            continue
        if not fertilizer_on_tile(tile, state, crops):
            tile["fertilizer"] = None


def fertilizer_bonus(tile: dict) -> float:
    fert = tile.get("fertilizer") if isinstance(tile, dict) else None
    if not isinstance(fert, dict):
        return 0.0
    kind = fert.get("kind")
    if kind == "yield":
        return 0.25
    if kind == "general":
        return 0.10
    return 0.0


def growth_step_for(info: dict, crop: dict, weedy: bool = False, tile: dict | None = None) -> float:
    cycle = crop_cycle_days(info, crop) or 1
    step = 100.0 / cycle
    if weedy:
        step *= 0.5
    fert = (tile or {}).get("fertilizer") if tile else None
    if isinstance(fert, dict) and fert.get("kind") == "growth":
        step *= 1.5
    return step


def ensure_crop_vitals(crop: dict, info: dict | None = None, *, establishing: bool = False) -> None:
    if crop.get("health") is None:
        crop["health"] = 100
    growth = crop.get("growth")
    grown = int(crop.get("days_grown") or 0)
    # Mature plants (including test fixtures and pre-vitals saves) are fully grown.
    # A days_grown fixture with growth still 0 (or missing) is inferred from the cycle.
    missing = growth is None or (
        float(growth or 0) == 0
        and grown > 0
        and crop.get("stage") not in {None, "seed", "withered"}
        and not establishing
    )
    if missing or (crop.get("stage") == "mature" and float(growth or 0) < 100):
        if establishing and growth is None:
            crop["growth"] = 0
        elif crop.get("stage") == "mature":
            crop["growth"] = 100
        else:
            cycle = crop_cycle_days(info, crop) if info else 0
            crop["growth"] = min(100.0, (100.0 * grown / cycle) if cycle else 0)
    g = float(crop.get("growth") or 0)
    crop["growth"] = 100 if g >= 99.99 else max(0.0, min(100.0, g))
    crop["health"] = int(crop.get("health") or 100)


def migrate_crop_vitals(state: dict, crops: dict | None = None) -> bool:
    """Fill hidden growth/health on living plants. Idempotent."""
    crops = crops or load_crops()
    changed = False
    for r, c, tile in iter_tiles(state):
        crop = tile.get("crop")
        if not crop or crop.get("stage") == "withered":
            continue
        info = crop_info(crops, crop.get("kind"))
        before = (crop.get("growth"), crop.get("health"))
        establishing = bool(
            info
            and is_perennial(info)
            and not crop_can_fruit(crop, info, state, crops)
        )
        ensure_crop_vitals(crop, info, establishing=establishing)
        if (crop.get("growth"), crop.get("health")) != before:
            changed = True
    return changed


def crop_hint(crop: dict, tile: dict, state: dict, info: dict | None = None) -> str:
    """Gentle look-text hints. Never print growth or health numbers."""
    if not crop:
        return ""
    stage = crop.get("stage")
    if stage == "withered":
        return ""
    if stage == "dormant" or (info and crop_is_dormant(crop, info, state.get("season")) and stage != "mature"):
        return ""
    growth = int(crop.get("growth") if crop.get("growth") is not None else (100 if stage == "mature" else 0))
    health = int(crop.get("health") if crop.get("health") is not None else 100)
    watered = bool(tile.get("watered"))
    weedy = bool(tile.get("weedy"))
    dry = int(crop.get("dry_days") or 0)
    bits = []
    kind = crop.get("kind") or ""
    if growth < 25 and stage not in {"mature"}:
        bits.append("just getting started")
    if not watered and dry >= 2:
        bits.append("is drying out")
    elif not watered:
        bits.append("looks a little thirsty")
    if weedy:
        bits.append("is a little crowded by weeds")
    can_pick = growth >= min_harvest_growth(kind)
    if can_pick and growth >= 100:
        bits.append("looks ready to pick")
    elif can_pick:
        bits.append("could be picked, though it might still put on more")
    if health <= 35:
        bits.append("is struggling")
    elif health >= 85 and watered and not weedy and not can_pick:
        bits.append("is thriving")
    elif 40 <= health < 75 and not any("struggling" in b or "thirsty" in b or "drying" in b for b in bits):
        bits.append("is getting along")
    # Keep to one or two hints.
    # Prefer the most useful: pick window, thirst/weeds, then health.
    unique = []
    for b in bits:
        if b not in unique:
            unique.append(b)
    unique = unique[:2]
    if not unique:
        return ""
    if len(unique) == 1:
        phrase = unique[0]
        if phrase.startswith("is ") or phrase.startswith("looks ") or phrase.startswith("could "):
            return f" It {phrase}."
        return f" It is {phrase}."
    a, b = unique[0], unique[1]
    def form(p):
        if p.startswith("is "):
            return p
        if p.startswith("looks ") or p.startswith("could "):
            return p
        return "is " + p
    return f" It {form(a)} and {form(b)}."


def maybe_wither(crop: dict, tile: dict, info: dict | None, state: dict, here: str, notes: list) -> bool:
    """Rare wither: health 0, long drought at low health, or three off-season evenings."""
    health = int(crop.get("health") or 0)
    dry = int(crop.get("dry_days") or 0)
    off = int(crop.get("off_season_days") or 0)
    kind = crop.get("kind")
    if health <= 0 or (dry >= 6 and health <= 20) or (off >= 3 and not is_perennial(info)):
        crop["stage"] = "withered"
        if off >= 3 and not is_perennial(info):
            notes.append(f"The {kind} at {here} withered in the {state.get('season')} air.")
        elif dry >= 6:
            notes.append(f"The {kind} at {here} withered after a long drought.")
        else:
            notes.append(f"The {kind} at {here} withered.")
        return True
    return False


def harvest(state: dict, crops: dict, row, col, player: str | None = None) -> tuple[bool, str]:
    r, c, err = parse_row_col(row, col)
    if err:
        return False, err
    tile = get_tile(state, r, c)
    here = position_name(r, c)
    if tile["type"] == "cabin":
        return False, f"That's the cabin ({here}). Nothing to harvest there."
    crop = tile.get("crop")
    if not crop:
        return False, f"Nothing is planted at {here}."
    if crop.get("stage") == "withered":
        tile["crop"] = None
        if tile.get("tilled"):
            reset_till_hold(tile)
        msg = f"{who(player, 'clear', 'clears')} the withered plant at {here}."
        log_append(state, msg, player)
        return True, msg
    kind_peek = crop.get("kind")
    peek_info = crop_info(crops, kind_peek) if kind_peek else {}
    if (
        crop.get("stage") != "mature"
        and crop_is_dormant(crop, peek_info, state.get("season"))
    ):
        return False, f"The {kind_peek} at {here} is dormant and resting until spring."
    kind = crop["kind"]
    info = crop_info(crops, kind) or {}
    ensure_crop_vitals(crop, info)
    if not crop_can_be_harvested(crop, info, state, crops):
        return (
            False,
            f"The {kind} at {here} is still filling out; it isn't ready to pick yet.",
        )
    from inventory import pack_space_for, store_item, sync_inventory_view, item_name
    growth = int(crop.get("growth") or 0)
    health = int(crop.get("health") or 100)
    harvests = int(crop.get("harvests") or 0)
    yield_n = yield_roll(
        kind, growth, health, int(state.get("day") or 1), r, c, harvests,
        bonus=fertilizer_bonus(tile),
    )
    if player and not pack_space_for(state, player, kind, yield_n):
        return False, (
            f"{display_name(player)}'s pack is full. "
            "Drop something at the cabin chest, then come back to harvest."
        )
    leftover = store_item(state, kind, yield_n, player, prefer="pack" if player else "chest")
    if leftover:
        return False, "There is no room for the harvest."
    if regrow_days(info) > 0 or is_perennial(info):
        crop["harvests"] = int(crop.get("harvests") or 0) + 1
        crop["days_grown"] = 0
        crop["growth"] = 0
        crop["days_grown"] = 0
        crop["health"] = max(1, int(crop.get("health") or 100) - 5)
        noun = crop_name_plural(kind, info, yield_n)
        if is_perennial(info) and state.get("season") not in (info.get("seasons") or []):
            crop["stage"] = "dormant"
            msg = (
                f"{who(player, 'harvest', 'harvests')} {yield_n} {noun} at {here}. "
                "It will rest until spring."
            )
        else:
            crop["stage"] = "regrowing"
            again = regrow_days(info) or grow_days(info)
            msg = (
                f"{who(player, 'harvest', 'harvests')} {yield_n} {noun} at {here}. "
                f"It will fruit again in {again} watered day(s) if it is still in season."
            )
        log_append(state, msg, player)
        return True, msg
    tile["crop"] = None
    # The bed stays tilled; today's water remains. Till-hold starts (or resets if watered).
    reset_till_hold(tile)
    noun = crop_name_plural(kind, info, yield_n)
    msg = f"{who(player, 'harvest', 'harvests')} {yield_n} {noun} at {here}."
    log_append(state, msg, player)
    return True, msg


def _parse_count(n) -> tuple[int | None, str | None]:
    try:
        count = int(n)
    except (TypeError, ValueError):
        return None, "How many? Use a whole number, like: buy kabocha 2"
    if count < 1:
        return None, "Choose a count of at least 1."
    return count, None


def fertilize(
    state: dict,
    crops: dict,
    row,
    col,
    kind=None,
    player: str | None = None,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Feed a soil plot. One bag per plot per season; the bag must be in the pack."""
    from inventory import (
        FERTILIZERS,
        fertilizer_item_for_kind,
        fertilizer_info,
        pack_has,
        pack_of,
        take_available,
        item_name,
        is_fertilizer,
    )
    r, c, err = parse_row_col(row, col)
    if err:
        return False, err
    tile = get_tile(state, r, c)
    if tile["type"] != "soil":
        return False, f"You can only fertilize soil. {position_name(r, c)} is {tile['type']}."
    existing = fertilizer_on_tile(tile, state, crops)
    if existing:
        return False, (
            f"The plot at {position_name(r, c)} is already fertilized this "
            f"{state.get('season') or 'season'}."
        )
    item = fertilizer_item_for_kind(kind) if kind else None
    if kind and not item:
        return False, (
            "Unknown fertilizer. Use general, yield, or growth "
            "(or the bag's full name)."
        )
    if not item:
        # Pick the bag in the pack (or chest when no player, for tests).
        found = []
        if player:
            for slot in pack_of(state, player, rules):
                if slot and is_fertilizer(slot.get("item")) and slot["item"] not in found:
                    found.append(slot["item"])
        else:
            from inventory import chest_of
            for slot in chest_of(state, rules):
                if slot and is_fertilizer(slot.get("item")) and slot["item"] not in found:
                    found.append(slot["item"])
        if not found:
            return False, "You need a bag of fertilizer in your pack."
        if len(found) > 1:
            names = ", ".join(FERTILIZERS[i]["name"] for i in found)
            return False, f"Which bag? You are carrying {names}. Try: fertilize general."
        item = found[0]
    if player and not pack_has(state, player, item, 1, rules):
        return False, f"You need {item_name(item, 1, crops, rules)} in your pack."
    taken = take_available(state, item, 1, player, pack_only=bool(player), rules=rules)
    if taken < 1:
        return False, f"You need {item_name(item, 1, crops, rules)} in your pack."
    info = fertilizer_info(item, rules) or FERTILIZERS[item]
    bag_kind = info["kind"]
    tile["fertilizer"] = {
        "kind": bag_kind,
        "season": state.get("season"),
        "year": year_for_day(int(state.get("day") or 1), crops),
    }
    crop = tile.get("crop")
    if bag_kind == "general" and crop and crop.get("stage") not in {None, "withered"}:
        ensure_crop_vitals(crop, crop_info(crops, crop.get("kind")))
        crop["health"] = min(100, int(crop.get("health") or 100) + 10)
    here = position_name(r, c)
    if bag_kind == "general":
        fed = "general fertilizer"
    elif bag_kind == "yield":
        fed = "yield-boost fertilizer"
    else:
        fed = "growth-boost fertilizer"
    msg = f"{who(player, 'fertilize', 'fertilizes')} the plot at {here} with {fed}."
    log_append(state, msg, player)
    return True, msg


def buy(state: dict, crops: dict, kind, n, player: str | None = None) -> tuple[bool, str]:
    from inventory import (
        store_item,
        pack_space_for,
        item_name as inv_item_name,
        fertilizer_item_for_kind,
        fertilizer_info,
        FERTILIZERS,
        FERTILIZER_SHOP_SEASONS,
        is_fertilizer,
    )
    raw_kind = kind
    fert_item = fertilizer_item_for_kind(str(kind))
    if fert_item:
        season = state.get("season") or "this season"
        if season not in FERTILIZER_SHOP_SEASONS:
            known = ", ".join(shop_listing(crops, season)) or "nothing right now"
            return False, (
                f"The shop isn't selling fertilizer this {season}. It sells: {known}."
            )
        count, err = _parse_count(n)
        if err:
            return False, err
        info = fertilizer_info(fert_item) or FERTILIZERS[fert_item]
        price = int(info["price"]) * count
        gold = int(state["gold"])
        label = inv_item_name(fert_item, count, crops)
        if gold < price:
            return (
                False,
                f"Not enough gold. {label} cost {price}G; you have {gold}G.",
            )
        if player and not is_player_in_cabin(state, player):
            return False, "The shop is at the cabin. Walk there to buy."
        state["gold"] = gold - price
        prefer = "pack" if player and pack_space_for(state, player, fert_item, count) else "chest"
        store_item(state, fert_item, count, player, prefer=prefer if player else "chest")
        where = "the pack" if prefer == "pack" and player else "the cabin chest"
        msg = (
            f"{who(player, 'buy', 'buys')} {label} for {price}G "
            f"({where}). "
            f"{display_name(player) if player else 'You'} "
            f"{'has' if player else 'have'} {state['gold']}G left."
        )
        log_append(state, msg, player)
        return True, msg
    kind = normalize_kind(str(kind))
    info = crop_info(crops, kind)
    if not info:
        known = ", ".join(shop_listing(crops, state.get("season"))) or "nothing right now"
        return False, f"Unknown seed {kind!r}. The shop sells: {known}."
    if not crop_in_shop(info):
        known = ", ".join(shop_listing(crops, state.get("season"))) or "nothing right now"
        return False, f"The shop isn't selling {shop_name(kind, info)}s yet. It sells: {known}."
    if not crop_in_season(info, state.get("season")):
        season = state.get("season") or "this season"
        known = ", ".join(shop_listing(crops, season)) or "nothing right now"
        return False, f"The shop isn't selling {shop_name(kind, info)}s this {season}. It sells: {known}."
    count, err = _parse_count(n)
    if err:
        return False, err
    price = int(info["seed_price"]) * count
    gold = int(state["gold"])
    noun = stock_noun(info, count)
    label = f"{crop_name(kind, info)} {noun}"
    if gold < price:
        return (
            False,
            f"Not enough gold. {count} {label} cost {price}G; you have {gold}G.",
        )
    if player and not is_player_in_cabin(state, player):
        return False, "The shop is at the cabin. Walk there to buy."
    state["gold"] = gold - price
    seed_key = stock_key(kind, info)
    from inventory import store_item, pack_space_for, item_name as inv_item_name
    prefer = "pack" if player and pack_space_for(state, player, seed_key, count) else "chest"
    if player and prefer == "pack" and not pack_space_for(state, player, seed_key, count):
        prefer = "chest"
    store_item(state, seed_key, count, player, prefer=prefer if player else "chest")
    where = "the pack" if prefer == "pack" and player else "the cabin chest"
    msg = (
        f"{who(player, 'buy', 'buys')} {count} {label} for {price}G "
        f"({where}). "
        f"{display_name(player) if player else 'You'} "
        f"{'has' if player else 'have'} {state['gold']}G left."
    )
    log_append(state, msg, player)
    return True, msg


def sell(state: dict, crops: dict, kind, n, player: str | None = None, rules: dict | None = None) -> tuple[bool, str]:
    from inventory import (
        item_name,
        item_sell_price,
        normalize_item,
        take_available,
        pack_has,
        item_count,
        sync_inventory_view,
    )
    if player and not is_player_in_cabin(state, player):
        return False, "Sell from the cabin. Carry the goods home first."
    item = normalize_item(str(kind)) or normalize_kind(str(kind))
    price = item_sell_price(item, crops, rules)
    if price is None:
        known = ", ".join(crops.get("crops", {}))
        return False, f"Unknown or unsellable item {kind!r}. You can sell: {known}."
    count, err = _parse_count(n)
    if err:
        return False, err
    have = item_count(state, item, rules)
    if player:
        from inventory import pack_of, chest_of, stack_count
        have = stack_count(pack_of(state, player, rules), item) + stack_count(chest_of(state, rules), item)
    if have < count:
        return False, f"You only have {have} {item_name(item, max(have, 1), crops, rules).split(' ', 1)[-1] if have != 1 else item_name(item, 1, crops, rules)[2:]} to sell."
    taken = take_available(state, item, count, player, pack_only=False, rules=rules)
    if taken < count:
        # refund nothing; take_available is all-or-we already checked
        return False, f"You only have {taken} to sell."
    gold = int(price) * count
    state["gold"] = int(state["gold"]) + gold
    noun = item_name(item, count, crops, rules)
    # item_name already includes the count
    msg = (
        f"{who(player, 'sell', 'sells')} {noun} for {gold}G. "
        f"{display_name(player) if player else 'You'} now "
        f"{'has' if player else 'have'} {state['gold']}G."
    )
    log_append(state, msg, player)
    return True, msg


def weed_rules(rules: dict | None = None) -> dict:
    rules = rules or load_rules()
    data = dict(rules.get("weeds") or {})
    data.setdefault("min_new_per_day", 1)
    data.setdefault("max_new_per_day", 2)
    data.setdefault("eligible", "tilled_or_planted")
    return data


def weed_hash(day: int, row: int, col: int, salt: int = 0) -> int:
    """Stable, seedless mix of day and plot. No RNG state is used."""
    n = (
        (int(day) * 73856093)
        ^ (int(row) * 19349663)
        ^ (int(col) * 83492791)
        ^ (int(salt) * 1664525)
        ^ 0x9E3779B9
    ) & 0xFFFFFFFF
    n = ((n ^ (n >> 16)) * 0x7FEB352D) & 0xFFFFFFFF
    n = ((n ^ (n >> 15)) * 0x846CA68B) & 0xFFFFFFFF
    return n ^ (n >> 16)


def tile_has_weed(tile: dict) -> bool:
    return bool(tile.get("weed")) or bool(tile.get("weedy"))


def plot_eligible_for_weed(tile: dict) -> bool:
    if not tile or tile.get("type") != "soil":
        return False
    if tile_has_weed(tile):
        return False
    crop = tile.get("crop")
    planted = bool(crop and crop.get("kind") and crop.get("stage") != "withered")
    return bool(tile.get("tilled")) or planted


def new_weed_count_for_day(day: int, rules: dict | None = None) -> int:
    cfg = weed_rules(rules)
    lo = int(cfg.get("min_new_per_day", 1))
    hi = int(cfg.get("max_new_per_day", 2))
    if hi < lo:
        lo, hi = hi, lo
    if hi <= 0:
        return 0
    lo = max(0, lo)
    span = hi - lo + 1
    return lo + (weed_hash(day, 0, 0, salt=17) % span)


def sprout_and_age_weeds(state: dict, rules: dict | None = None) -> list[str]:
    """At day turn: age unplucked weeds, then sprout 1–2 new ones deterministically."""
    rules = rules or load_rules()
    notes: list[str] = []
    day = int(state["day"])

    for r, c, tile in iter_tiles(state):
        if tile.get("type") != "soil":
            continue
        weed = tile.get("weed")
        if weed and not tile.get("weedy"):
            appeared = int(weed.get("appeared_day", day))
            if appeared < day:
                tile["weedy"] = True
                tile["weedy_ticks"] = int(tile.get("weedy_ticks") or 0)
                here = position_name(r, c)
                notes.append(
                    f"The plot at {here} has grown weedy; the crop will grow more slowly."
                )

    count = new_weed_count_for_day(day, rules)
    if count <= 0:
        return notes
    eligible = [
        (r, c, tile)
        for r, c, tile in iter_tiles(state)
        if plot_eligible_for_weed(tile)
    ]
    eligible.sort(key=lambda item: (weed_hash(day, item[0], item[1]), item[0], item[1]))
    for r, c, tile in eligible[:count]:
        tile["weed"] = {"appeared_day": day}
        tile.setdefault("weedy", False)
        tile.setdefault("weedy_ticks", 0)
        notes.append(f"A small weed has crept in at {position_name(r, c)}.")
    return notes


def pluck(state: dict, crops: dict, row, col, player: str | None = None) -> tuple[bool, str]:
    r, c, err = parse_row_col(row, col)
    if err:
        return False, err
    tile = get_tile(state, r, c)
    here = position_name(r, c)
    if tile["type"] == "cabin":
        return False, f"That's the cabin ({here}). There are no weeds on the porch."
    if not tile_has_weed(tile):
        return False, f"There's no weed to pluck at {here}."
    tile["weed"] = None
    tile["weedy"] = False
    tile["weedy_ticks"] = 0
    msg = f"{who(player, 'pluck', 'plucks')} the weed at {here}."
    log_append(state, msg, player)
    return True, msg



def _apply_season_to_crop(state: dict, crops: dict, crop: dict, row: int, col: int) -> list[str]:
    """Die, go dormant, wake, or wither when the season changes at dawn."""
    notes: list[str] = []
    info = crop_info(crops, crop.get("kind"))
    if not info:
        return notes
    here = position_name(row, col)
    season = state.get("season")
    day = int(state["day"])
    kind = crop["kind"]
    if is_perennial(info):
        life = lifespan_seasons(info)
        if life and crop_season_age(crop, day, crops) > life:
            crop["stage"] = "withered"
            notes.append(f"The {kind} at {here} lived out its two years.")
            return notes
        growing_seasons = info.get("seasons") or []
        if season not in growing_seasons:
            crop["overwintered"] = True
            if crop.get("stage") != "dormant":
                if crop.get("stage") == "mature":
                    notes.append(
                        f"The {kind} at {here} is going dormant, but a berry is still ready to harvest."
                    )
                else:
                    crop["stage"] = "dormant"
                    notes.append(f"The {kind} at {here} has gone dormant for {season}.")
            return notes
        if crop.get("stage") == "dormant":
            crop["overwintered"] = True
            if crop_can_fruit(crop, info, state, crops) and not crop.get("fruiting_started"):
                crop["days_grown"] = 0
                crop["fruiting_started"] = True
                crop["stage"] = "regrowing"
            else:
                crop["stage"] = stage_for(int(crop.get("days_grown") or 0), info, crop)
                if crop["stage"] == "mature" and not crop_can_fruit(crop, info, state, crops):
                    crop["stage"] = "growing"
            notes.append(f"The {kind} at {here} has woken for {season}.")
        return notes
    if season not in (info.get("seasons") or []):
        crop["off_season_days"] = int(crop.get("off_season_days") or 0) + 1
        crop["health"] = max(0, int(crop.get("health") if crop.get("health") is not None else 100) - 20)
        ensure_crop_vitals(crop, info)
        if maybe_wither(crop, get_tile(state, row, col), info, state, here, notes):
            return notes
        notes.append(f"The {kind} at {here} is unhappy in the {season} air.")
    else:
        crop["off_season_days"] = 0
    return notes


def _apply_runners(state: dict, crops: dict) -> list[str]:
    """Active perennials may send one runner a season into an adjacent tilled empty plot."""
    notes: list[str] = []
    day = int(state["day"])
    season = state.get("season")
    season_i = season_index(day, crops)
    seed = int(state.get("weather_seed") or 0)
    parents = []
    for r, c, tile in iter_tiles(state):
        crop = tile.get("crop")
        if not crop or crop.get("stage") == "withered":
            continue
        info = crop_info(crops, crop.get("kind"))
        if not info or runner_chance_pct(info) <= 0:
            continue
        if crop_is_dormant(crop, info, season):
            continue
        if season not in (info.get("seasons") or []):
            continue
        if int(crop.get("runner_season") if crop.get("runner_season") is not None else -1) == season_i:
            continue
        parents.append((r, c, crop, info))
    for r, c, crop, info in parents:
        if not runner_roll(day, r, c, seed, runner_chance_pct(info)):
            continue
        dest = _pick_runner_plot(state, r, c, day, seed)
        if not dest:
            continue
        rr, cc = dest
        tile = get_tile(state, rr, cc)
        tile["crop"] = {
            "kind": crop["kind"],
            "planted_day": day,
            "days_grown": 0,
            "stage": initial_stage(info),
            "dry_days": 0,
            "growth": 0,
            "health": 100,
        }
        crop["runner_season"] = season_i
        notes.append(
            f"A {crop['kind']} runner took root at {position_name(rr, cc)} "
            f"from the plant at {position_name(r, c)}."
        )
    return notes


def _pick_runner_plot(state: dict, row: int, col: int, day: int, seed: int):
    candidates = []
    for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
        rr, cc = row + dr, col + dc
        if not in_bounds(rr, cc):
            continue
        tile = get_tile(state, rr, cc)
        if tile.get("type") != "soil" or not tile.get("tilled") or tile.get("crop"):
            continue
        candidates.append((rr, cc))
    if not candidates:
        return None
    n = weed_hash(int(day), int(row), int(col), salt=int(seed) ^ 9091)
    return candidates[n % len(candidates)]


def _apply_evening_growth(state: dict, crops: dict, rules: dict | None = None) -> list[str]:
    notes = []
    for r, c, tile in iter_tiles(state):
        if tile["type"] != "soil":
            continue
        crop = tile.get("crop")
        living = bool(crop and crop.get("stage") != "withered")
        if not living:
            tick_till_hold(state, tile, r, c, notes, rules)
            tile["watered"] = False
            continue
        clear_till_hold(tile)
        here = position_name(r, c)
        kind = crop["kind"]
        info = crop_info(crops, kind)
        establishing = bool(info and is_perennial(info) and not crop_can_fruit(crop, info, state, crops))
        ensure_crop_vitals(crop, info, establishing=establishing)
        if crop_is_dormant(crop, info, state.get("season")):
            crop["dry_days"] = 0
            if tile.get("weedy"):
                crop["health"] = max(0, int(crop.get("health") or 100) - 3)
            tile["watered"] = False
            continue
        if tile.get("watered"):
            crop["dry_days"] = 0
            if tile.get("weedy"):
                crop["health"] = max(0, int(crop.get("health") or 100) - 6)
            else:
                crop["health"] = min(100, int(crop.get("health") or 100) + 4)
            # General fertilizer's one-time health bump is applied when the bag is used.
            can_grow = bool(info) and crop.get("stage") != "mature" and not establishing
            if establishing:
                can_grow = False
                if crop.get("stage") not in {"mature", "withered"}:
                    established = int(crop.get("days_established") or 0)
                    if tile.get("weedy"):
                        ticks = int(tile.get("weedy_ticks") or 0)
                        if ticks % 2 == 1:
                            tile["weedy_ticks"] = ticks + 1
                        else:
                            crop["days_established"] = established + 1
                            tile["weedy_ticks"] = ticks + 1
                    else:
                        crop["days_established"] = established + 1
                    leaf_days = min(int(crop.get("days_established") or 0), max(0, grow_days(info) - 1))
                    leaf = stage_for(leaf_days, info, crop)
                    if leaf != "mature":
                        crop["stage"] = leaf
            if can_grow and info:
                step = growth_step_for(info, crop, weedy=bool(tile.get("weedy")), tile=tile)
                if tile.get("weedy"):
                    tile["weedy_ticks"] = int(tile.get("weedy_ticks") or 0) + 1
                grown = min(100.0, float(crop.get("growth") or 0) + float(step))
                crop["growth"] = 100 if grown >= 99.99 else round(grown, 4)
                cycle = crop_cycle_days(info, crop) or 1
                if crop["growth"] >= 100:
                    crop["growth"] = 100
                    crop["days_grown"] = cycle
                    new_stage = "mature"
                else:
                    crop["days_grown"] = min(cycle - 1, max(0, int(round(float(crop["growth"]) / 100.0 * cycle))))
                    new_stage = stage_for(crop["days_grown"], info, crop)
                    if new_stage == "mature":
                        new_stage = "growing"
                if new_stage != crop.get("stage"):
                    crop["stage"] = new_stage
                    if new_stage == "mature":
                        notes.append(f"The {kind} at {here} looks ready to pick.")
                    else:
                        notes.append(
                            f"The {kind} at {here} is now {stage_label(info, new_stage)}."
                        )
                else:
                    crop["stage"] = new_stage
            # Mature crops stay mature when watered. Weeds never kill a crop by themselves.
        else:
            crop["dry_days"] = int(crop.get("dry_days", 0)) + 1
            drain = 12 if tile.get("weedy") else 8
            crop["health"] = max(0, int(crop.get("health") or 100) - drain)
            maybe_wither(crop, tile, info, state, here, notes)
        tile["watered"] = False
    return notes


def advance_day(state: dict, crops: dict, rules: dict | None = None) -> tuple[bool, str]:
    """Apply evening growth and dawn the next day. Used when both players end their turn."""
    rules = rules or load_rules()
    notes = _apply_evening_growth(state, crops, rules)
    state["day"] = int(state["day"]) + 1
    state["season"] = season_for_day(state["day"], crops)
    clear_expired_fertilizer(state, crops)
    archive_journal_if_needed(state, crops)
    ensure_weather_seed(state, rules, crops)
    state["weather"] = weather_for_day(
        state["day"], crops, rules, seed=int(state["weather_seed"])
    )

    for r, c, tile in iter_tiles(state):
        crop = tile.get("crop")
        if not crop or crop.get("stage") == "withered":
            continue
        info = crop_info(crops, crop["kind"])
        notes.extend(_apply_season_to_crop(state, crops, crop, r, c))

    if is_wet_weather(state["weather"]):
        dawn_water(state)
        notes.append(weather_arrive_message(state["weather"]))

    notes.extend(sprout_and_age_weeds(state, rules))
    notes.extend(_apply_runners(state, crops))

    season = state["season"]
    d = state["day"]
    within = day_in_season(d, crops)
    total = days_per_season(crops)
    sky = {
        "sun": "a clear, sunny morning",
        "cloud": "an overcast morning",
        "rain": "a rainy morning",
        "storm": "a stormy morning",
        "snow": "a snowy morning",
    }.get(state["weather"], state["weather"])
    header = f"Day {d} dawns, {season} (day {within} of {total}), {sky}."
    parts = [header] + notes
    msg = " ".join(parts)
    log_append(state, header)
    for note in notes:
        log_append(state, note)
    return True, msg


def sleep(state: dict, crops: dict, rules: dict | None = None) -> tuple[bool, str]:
    """Back-compat alias used by growth tests. Prefer end_turn in play."""
    return advance_day(state, crops, rules)



# --- movement and snacks -----------------------------------------------------

MOVE_DELTA = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}


def _must_stand_here(state: dict, player: str, row: int, col: int) -> str | None:
    here = player_where(state, player)
    if here != (int(row), int(col)):
        return (
            f"{display_name(player)} is {describe_where(*here)}. "
            f"Walk there before you can work that tile."
        )
    return None


def move_one(state: dict, player: str, direction: str, rules: dict | None = None) -> tuple[bool, str]:
    rules = rules or load_rules()
    delta = MOVE_DELTA.get(direction)
    if not delta:
        return False, "Usage: move up, move down, move left, or move right"
    row, col = player_where(state, player)
    dest = (row + delta[0], col + delta[1])
    if not in_bounds(*dest):
        return False, "There's no farm that way."
    cost = step_energy(rules)
    slot = player_slot(state, player)
    energy = int(slot["energy"])
    if cost > energy:
        return (
            False,
            f"Not enough energy. A step costs {cost}; "
            f"{display_name(player)} has {energy} left.",
        )
    set_player_where(state, player, dest[0], dest[1])
    slot["energy"] = energy - cost
    return (
        True,
        f"{display_name(player)} walks {direction} to {describe_place(*dest)} ({cost} energy).",
    )


def move_to(state: dict, player: str, row, col, rules: dict | None = None) -> tuple[bool, str]:
    rules = rules or load_rules()
    dest_r, dest_c, err = parse_row_col(row, col)
    if err:
        return False, err
    src = player_where(state, player)
    dest = (dest_r, dest_c)
    if src == dest:
        return True, f"{display_name(player)} is already {describe_where(*dest)}."
    steps = path_steps(src, dest)
    cost = step_energy(rules) * len(steps)
    slot = player_slot(state, player)
    energy = int(slot["energy"])
    if cost > energy:
        return (
            False,
            f"Not enough energy. Walking to {describe_place(*dest)} is "
            f"{steps_phrase(len(steps))} ({cost} energy); "
            f"{display_name(player)} has {energy} left.",
        )
    set_player_where(state, player, dest_r, dest_c)
    slot["energy"] = energy - cost
    return (
        True,
        f"{display_name(player)} walks to {describe_place(*dest)} "
        f"({steps_phrase(len(steps))}, {cost} energy).",
    )


def go_cabin(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    return move_to(state, player, CABIN_ROW, CABIN_COL, rules)


def do_move_command(
    state: dict,
    player: str,
    verb: str,
    args: list[str],
    rules: dict | None = None,
) -> tuple[bool, str]:
    rules = rules or load_rules()
    tokens = [verb] + list(args)
    # Drop a leading go/move/walk; treat "to" as optional.
    words = [w.lower() for w in tokens]
    if words and words[0] in {"move", "go", "walk"}:
        words = words[1:]
    if words and words[0] == "to":
        words = words[1:]
    if not words:
        return False, "Usage: move up/down/left/right, move to <row> <col>, or go cabin"
    if len(words) == 1 and words[0] in MOVE_DELTA:
        return move_one(state, player, words[0], rules)
    if words and words[0] in {"cabin", "home", "house"}:
        return go_cabin(state, player, rules)
    if len(words) == 2:
        return move_to(state, player, words[0], words[1], rules)
    return False, "Usage: move up/down/left/right, move to <row> <col>, or go cabin"


def eat(state: dict, crops: dict, kind, player: str, rules: dict | None = None) -> tuple[bool, str]:
    """Eat a snack from the pack. Free, capped per turn, restores energy."""
    from inventory import item_eat_energy, normalize_item, pack_has, take_available, item_name

    rules = rules or load_rules()
    raw_kind = (kind or "").strip().lower()
    if raw_kind.endswith("_seed") or raw_kind.endswith(" seed") or raw_kind.endswith("_seedling") or raw_kind.endswith(" seedling"):
        return False, "Seeds aren't a snack. Eat a harvested crop, like: eat carrot"
    item = normalize_item(kind) or normalize_kind(kind)
    restore = item_eat_energy(item, crops, rules)
    if restore is None:
        if crop_info(crops, item):
            return False, f"{item} isn't edible raw."
        return False, f"Unknown snack '{kind}'. Try carrot, turnip, kabocha, or a crafted food."
    kind = item
    if not pack_has(state, player, kind, 1, rules):
        return False, f"No {item_name(kind, 1, crops, rules)[2:]} in the pack."
    slot = player_slot(state, player)
    eaten = int(slot.get("snacks_eaten") or 0)
    cap_snacks = snacks_per_turn(rules)
    if eaten >= cap_snacks:
        return False, f"{display_name(player)} already had {cap_snacks} snacks this turn."
    cap_e = max_energy(rules)
    energy = int(slot["energy"])
    if energy >= cap_e:
        return False, f"{display_name(player)} is already at full energy. Sell it or save it."
    gained = min(restore, cap_e - energy)
    taken = take_available(state, kind, 1, player, pack_only=True, rules=rules)
    if taken < 1:
        return False, f"No {kind} in the pack."
    slot["energy"] = energy + gained
    slot["snacks_eaten"] = eaten + 1
    left = cap_snacks - (eaten + 1)
    snack_bit = "No snacks left this turn." if left <= 0 else f"{left} snack(s) left this turn."
    return (
        True,
        f"{display_name(player)} eats a {kind} and recovers {gained} energy "
        f"({slot['energy']}/{cap_e}). {snack_bit}",
    )


# --- dispatcher --------------------------------------------------------------


def take_item(state: dict, item, n, player: str, rules: dict | None = None, crops: dict | None = None) -> tuple[bool, str]:
    """Move items from the cabin chest into the pack. Must be at the cabin."""
    from inventory import (
        normalize_item,
        parse_item_and_count,
        pack_space_for,
        remove_from_chest,
        add_to_pack,
        item_name,
        chest_of,
        stack_count,
        sync_inventory_view,
    )
    rules = rules or load_rules()
    crops = crops or load_crops()
    if not is_player_in_cabin(state, player):
        return False, "The chest is at the cabin. Walk there to take something."
    if isinstance(item, list):
        item, n, err = parse_item_and_count(item)
        if err:
            return False, err
    else:
        item = normalize_item(str(item)) or str(item).strip().lower()
        count, err = _parse_count(n)
        if err:
            return False, err
        n = count
    if not pack_space_for(state, player, item, n, rules):
        return False, f"{display_name(player)}'s pack has no room for {item_name(item, n, crops, rules)}."
    have = stack_count(chest_of(state, rules), item)
    if have < n:
        return False, f"The chest only has {item_name(item, have, crops, rules)}."
    removed = remove_from_chest(state, item, n, rules)
    leftover = add_to_pack(state, player, item, removed, rules)
    if leftover:
        # Should not happen after the space check; put leftover back.
        from inventory import add_to_chest
        add_to_chest(state, item, leftover, rules)
        removed -= leftover
    sync_inventory_view(state, rules)
    if removed <= 0:
        return False, "Nothing was taken."
    msg = f"{display_name(player)} takes {item_name(item, removed, crops, rules)} from the chest."
    log_append(state, msg, player)
    return True, msg


def drop_item(state: dict, item, n, player: str, rules: dict | None = None, crops: dict | None = None) -> tuple[bool, str]:
    """Move items from the pack into the cabin chest. Must be at the cabin."""
    from inventory import (
        normalize_item,
        parse_item_and_count,
        remove_from_pack,
        add_to_chest,
        item_name,
        pack_has,
        sync_inventory_view,
    )
    rules = rules or load_rules()
    crops = crops or load_crops()
    if not is_player_in_cabin(state, player):
        return False, "The chest is at the cabin. Walk there to drop something."
    if isinstance(item, list):
        item, n, err = parse_item_and_count(item)
        if err:
            return False, err
    else:
        item = normalize_item(str(item)) or str(item).strip().lower()
        count, err = _parse_count(n)
        if err:
            return False, err
        n = count
    if not pack_has(state, player, item, n, rules):
        return False, f"No {item_name(item, n, crops, rules)} in the pack."
    removed = remove_from_pack(state, player, item, n, rules)
    add_to_chest(state, item, removed, rules)
    sync_inventory_view(state, rules)
    msg = f"{display_name(player)} puts {item_name(item, removed, crops, rules)} in the chest."
    log_append(state, msg, player)
    return True, msg


def craft(state: dict, recipe, player: str, rules: dict | None = None, crops: dict | None = None) -> tuple[bool, str]:
    """Cook a recipe at the cabin, using pack first, then the chest."""
    from inventory import (
        recipes,
        normalize_item,
        take_available,
        store_item,
        pack_space_for,
        item_name,
        item_count,
        pack_of,
        chest_of,
        stack_count,
        sync_inventory_view,
    )
    rules = rules or load_rules()
    crops = crops or load_crops()
    if not is_player_in_cabin(state, player):
        return False, "Craft at the cabin kitchen."
    key = normalize_item(str(recipe)) or str(recipe or "").strip().lower().replace(" ", "_")
    recs = recipes(rules)
    rec = recs.get(key)
    if not rec:
        names = ", ".join(recs)
        return False, f"Unknown recipe {recipe!r}. You can craft: {names}."
    # Check ingredients (pack + chest).
    needed = dict(rec.get("ingredients") or {})
    berry_need = int(rec.get("berries") or 0)
    def available(item):
        return stack_count(pack_of(state, player, rules), item) + stack_count(chest_of(state, rules), item)
    for item, n in needed.items():
        item = normalize_item(item) or item
        if available(item) < int(n):
            return False, f"Not enough {item_name(item, int(n), crops, rules)} to craft {rec.get('name') or key}."
    if berry_need:
        berries = available("strawberry") + available("everbearing")
        if berries < berry_need:
            return False, f"Not enough strawberries. {rec.get('name') or key} needs {berry_need}."
    # Consume.
    for item, n in needed.items():
        item = normalize_item(item) or item
        take_available(state, item, int(n), player, pack_only=False, rules=rules)
    if berry_need:
        left = berry_need
        for berry in ("strawberry", "everbearing"):
            if left <= 0:
                break
            got = take_available(state, berry, left, player, pack_only=False, rules=rules)
            left -= got
        if left > 0:
            return False, "Not enough strawberries."
    # Result.
    leftover = store_item(state, key, 1, player, prefer="pack", rules=rules)
    where = "the chest" if leftover or not pack_space_for(state, player, key, 1, rules) else "the pack"
    # store_item with prefer pack already overflowed to chest, leftover is 0 then.
    # Determine where it landed: if pack has it now...
    from inventory import pack_has
    where = "the pack" if pack_has(state, player, key, 1, rules) else "the chest"
    msg = f"{display_name(player)} cooks {item_name(key, 1, crops, rules)} at the cabin ({where})."
    log_append(state, msg, player)
    return True, msg


def is_end_turn_command(command: str) -> bool:
    is_end, _note = parse_end_turn_command(command)
    return is_end


def legal_actions(
    state: dict,
    crops: dict,
    player: str | None = None,
    rules: dict | None = None,
) -> list[str]:
    rules = rules or load_rules()
    migrate_state(state, rules)
    actor = normalize_player(player) or normalize_player(state.get("current_player"))
    current = normalize_player(state.get("current_player"))
    if actor and current and actor != current:
        return []
    energy = int(player_slot(state, actor)["energy"]) if actor else max_energy(rules)
    actions: list[str] = []
    here = player_where(state, actor) if actor else (CABIN_ROW, CABIN_COL)
    step = step_energy(rules)
    for direction, delta in MOVE_DELTA.items():
        dest = (here[0] + delta[0], here[1] + delta[1])
        if in_bounds(*dest) and energy >= step:
            actions.append(f"move {direction}")
    if not is_cabin_at(*here):
        walk = path_cost(here, (CABIN_ROW, CABIN_COL), rules)
        if energy >= walk:
            actions.append("go cabin")
    for r, c, tile in iter_tiles(state):
        if (r, c) == here:
            continue
        walk = path_cost(here, (r, c), rules)
        if energy >= walk:
            actions.append(f"move to {r} {c}")
    r, c = here
    tile = get_tile(state, r, c)
    if tile["type"] != "cabin":
        crop = tile.get("crop")
        withered = bool(crop and crop.get("stage") == "withered")
        if (not crop or withered) and (not tile.get("tilled") or withered):
            if energy >= energy_cost("till", rules):
                from inventory import pack_has, TOOL_HOE
                if not actor or pack_has(state, actor, TOOL_HOE, 1, rules):
                    actions.append(f"till {r} {c}")
        if tile.get("tilled") and not crop:
            if energy >= energy_cost("plant", rules):
                from inventory import pack_has
                for kind, info in crops.get("crops", {}).items():
                    seed_key = stock_key(kind, info)
                    in_pack = pack_has(state, actor, seed_key, 1, rules) if actor else int(state["inventory"].get(seed_key, 0)) > 0
                    if state["season"] in info["seasons"] and in_pack:
                        actions.append(f"plant {r} {c} {kind}")
        if not tile.get("watered"):
            info = crop_info(crops, crop["kind"]) if crop and crop.get("kind") else {}
            dormant = crop_is_dormant(crop, info, state.get("season")) if crop else False
            if (not dormant) and energy >= energy_cost("water", rules):
                from inventory import pack_has, TOOL_CAN
                if not actor or pack_has(state, actor, TOOL_CAN, 1, rules):
                    actions.append(f"water {r} {c}")
        if crop and crop_can_be_harvested(crop, crop_info(crops, crop.get("kind")), state, crops):
            from inventory import pack_space_for
            if not actor or pack_space_for(state, actor, crop.get("kind") or "item", 1, rules):
                actions.append(f"harvest {r} {c}")
        if withered:
            actions.append(f"harvest {r} {c}")
        if tile_has_weed(tile) and energy >= energy_cost("pluck", rules):
            actions.append(f"pluck {r} {c}")
        if energy >= energy_cost("fertilize", rules) and not fertilizer_on_tile(tile, state, crops):
            from inventory import pack_of, chest_of, is_fertilizer
            bags = []
            if actor:
                for slot in pack_of(state, actor, rules):
                    if slot and is_fertilizer(slot.get("item")) and slot["item"] not in bags:
                        bags.append(slot["item"])
            else:
                for slot in chest_of(state, rules):
                    if slot and is_fertilizer(slot.get("item")) and slot["item"] not in bags:
                        bags.append(slot["item"])
            if len(bags) == 1:
                actions.append(f"fertilize {r} {c}")
            else:
                from inventory import FERTILIZERS
                for item in bags:
                    kind = FERTILIZERS[item]["kind"]
                    actions.append(f"fertilize {r} {c} {kind}")
    from inventory import (
        pack_of,
        chest_of,
        recipes,
        item_eat_energy,
        item_sell_price,
        stack_count,
    )
    at_cabin = is_cabin_at(*here)
    if at_cabin:
        for kind, info in crops.get("crops", {}).items():
            if crop_for_sale(info, state.get("season")):
                price = int(info["seed_price"])
                if int(state["gold"]) >= price:
                    actions.append(f"buy {kind} 1")
        from inventory import fertilizer_info
        for item in fertilizer_shop_items(state.get("season"), rules):
            info = fertilizer_info(item, rules)
            if info and int(state["gold"]) >= int(info["price"]):
                actions.append(f"buy {item} 1")
        sellable = {}
        if actor:
            for slot in (pack_of(state, actor, rules) + chest_of(state, rules)):
                if not slot:
                    continue
                item = slot.get("item")
                if item and item_sell_price(item, crops, rules) is not None:
                    sellable[item] = sellable.get(item, 0) + int(slot.get("count") or 0)
        for item, have in sellable.items():
            if have > 0:
                actions.append(f"sell {item} 1")
        for slot in chest_of(state, rules):
            if slot and slot.get("item"):
                actions.append(f"take {slot['item']}")
        if actor:
            for slot in pack_of(state, actor, rules):
                if slot and slot.get("item"):
                    actions.append(f"drop {slot['item']}")
        def _have(item):
            n = 0
            if actor:
                n += stack_count(pack_of(state, actor, rules), item)
            n += stack_count(chest_of(state, rules), item)
            return n
        for rec_id, rec in recipes(rules).items():
            ok_rec = True
            if int(rec.get("berries") or 0):
                if _have("strawberry") + _have("everbearing") < int(rec["berries"]):
                    ok_rec = False
            for item, n in (rec.get("ingredients") or {}).items():
                if _have(item) < int(n):
                    ok_rec = False
                    break
            if ok_rec:
                actions.append(f"craft {rec_id}")
    if actor:
        for slot in pack_of(state, actor, rules):
            if not slot:
                continue
            item = slot.get("item")
            if (
                item
                and item_eat_energy(item, crops, rules) is not None
                and int(player_slot(state, actor).get("snacks_eaten") or 0) < snacks_per_turn(rules)
                and energy < max_energy(rules)
            ):
                actions.append(f"eat {item}")
    actions.append("end turn")
    return actions


def do_action(
    state: dict,
    crops: dict,
    command: str,
    player: str | None = None,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Apply one command to the in-memory state. Does not load or save files."""
    rules = rules or load_rules()
    migrate_state(state, rules)
    raw = (command or "").strip()
    if not raw:
        return False, "Say what to do, like: water 1 2"
    parts = raw.split()
    verb = parts[0].lower()
    args = parts[1:]
    if verb == "look":
        return True, "look"
    if verb == "sleep":
        return (
            False,
            "The day advances when both players have ended their turn. Use: end turn",
        )
    if verb in {"new", "reset"}:
        return False, "To start a new farm, run: python3 cli.py new"

    actor, err = parse_player(player)
    if err or not actor:
        return False, "Say who is acting with --player " + " or --player ".join(known_players()) + "."

    current = normalize_player(state.get("current_player"))
    if current != actor:
        return False, f"It's {display_name(current)}'s turn right now."

    is_end, note = parse_end_turn_command(raw)
    if is_end:
        return end_turn(state, crops, actor, rules, note=note)

    if verb in {"move", "go", "walk"}:
        return do_move_command(state, actor, verb, args, rules)

    if verb == "eat":
        if len(args) != 1:
            return False, "Usage: eat <crop>   example: eat carrot"
        return eat(state, crops, args[0], actor, rules)

    if verb in {"take", "drop", "put", "stow", "craft"}:
        if verb == "craft":
            if not args:
                return False, "Usage: craft <recipe>   example: craft strawberry_jam"
            return craft(state, " ".join(args), actor, rules, crops)
        if verb in {"put", "stow"}:
            verb = "drop"
        if not args:
            return False, f"Usage: {verb} <item> [count]   example: {verb} hoe"
        if verb == "take":
            return take_item(state, args, None, actor, rules, crops)
        return drop_item(state, args, None, actor, rules, crops)

    # Plot work is on the tile you're standing on. Coords are optional,
    # but if given they must be the current tile.
    here = player_where(state, actor)
    fert_kind = None
    if verb == "fertilize":
        # fertilize | fertilize <kind> | fertilize <row> <col> | fertilize <row> <col> <kind>
        if len(args) == 0:
            r, c = here
        elif len(args) == 1:
            r, c = here
            fert_kind = args[0]
        elif len(args) == 2:
            r, c, err = parse_row_col(args[0], args[1])
            if err:
                return False, err
        elif len(args) == 3:
            r, c, err = parse_row_col(args[0], args[1])
            if err:
                return False, err
            fert_kind = args[2]
        else:
            return False, "Usage: fertilize [kind]   or: fertilize <row> <col> [kind]"
        stood = _must_stand_here(state, actor, r, c)
        if stood:
            return False, stood
    plot_verbs = {"till", "plant", "water", "harvest", "pluck"}
    if verb in plot_verbs:
        if verb == "plant":
            if len(args) == 1:
                r, c = here
                kind = args[0]
            elif len(args) == 3:
                r, c, err = parse_row_col(args[0], args[1])
                if err:
                    return False, err
                kind = args[2]
            else:
                return False, "Usage: plant <kind>   or: plant <row> <col> <kind>"
            stood = _must_stand_here(state, actor, r, c)
            if stood:
                return False, stood
        else:
            if len(args) == 0:
                r, c = here
            elif len(args) == 2:
                r, c, err = parse_row_col(args[0], args[1])
                if err:
                    return False, err
            else:
                return False, f"Usage: {verb}   or: {verb} <row> <col>"
            stood = _must_stand_here(state, actor, r, c)
            if stood:
                return False, stood

    cost = energy_cost(verb, rules)
    energy = int(player_slot(state, actor)["energy"])
    if cost > energy:
        return (
            False,
            f"Not enough energy. {verb} costs {cost}; "
            f"{display_name(actor)} has {energy} left.",
        )

    if verb == "till":
        ok, msg = till(state, crops, r, c, actor)
    elif verb == "plant":
        ok, msg = plant(state, crops, r, c, kind, actor)
    elif verb == "water":
        ok, msg = water(state, crops, r, c, actor)
    elif verb == "harvest":
        ok, msg = harvest(state, crops, r, c, actor)
    elif verb == "buy":
        if len(args) != 2:
            return False, "Usage: buy <kind> <count>   example: buy kabocha 2"
        ok, msg = buy(state, crops, args[0], args[1], actor)
    elif verb == "sell":
        if len(args) != 2:
            return False, "Usage: sell <kind> <count>   example: sell kabocha 1"
        ok, msg = sell(state, crops, args[0], args[1], actor)
    elif verb == "pluck":
        ok, msg = pluck(state, crops, r, c, actor)
    elif verb == "fertilize":
        ok, msg = fertilize(state, crops, r, c, fert_kind, actor, rules)
    else:
        return (
            False,
            "Unknown action. Try look, move, go cabin, till, plant, water, harvest, "
            "pluck, fertilize, eat, buy, sell, take, drop, craft, or end turn.",
        )

    if ok and cost:
        player_slot(state, actor)["energy"] = energy - cost
    return ok, msg


def perform(command: str, player: str | None = None) -> tuple[bool, str]:
    """Load state, apply a command, save (except look)."""
    from config import default_cli_player
    if player is None:
        player = default_cli_player()
    verb = (command or "").strip().split()[:1]
    write = not (verb and verb[0].lower() == "look")
    with session(write=write) as (state, crops):
        return do_action(state, crops, command, player=player)

"""Lantern Farm — deterministic rules and JSON state.

The JSON state is the single source of truth. Both the text view and the
image view derive what they show from it; they never invent tile state.
"""

from __future__ import annotations

import fcntl
import json
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
    return int(rules.get("move_energy", 10))


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


def describe_where(row: int, col: int) -> str:
    if is_cabin_at(row, col):
        return "in the cabin"
    return f"at plot {plot_number(row, col)}"


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
    players = state.setdefault("players", {})
    slot = players.setdefault(player, {})
    slot.setdefault("energy", 0)
    slot.setdefault("ended_turn", False)
    slot.setdefault("row", CABIN_ROW)
    slot.setdefault("col", CABIN_COL)
    slot.setdefault("snacks_eaten", 0)
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
        return 14
    return int(crops.get("days_per_season", 14))


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
    k = (kind or "").strip().lower()
    if k.endswith("_seed"):
        k = k[: -len("_seed")]
    return k


def stage_for(days_grown: int, info: dict) -> str:
    stages = sorted(info["stages"], key=lambda s: int(s["at"]))
    current = stages[0]["id"]
    for stage in stages:
        if days_grown >= int(stage["at"]):
            current = stage["id"]
    return current


def stage_label(info: dict, stage_id: str) -> str:
    for stage in info.get("stages", []):
        if stage["id"] == stage_id:
            return stage.get("label", stage_id)
    return stage_id


def grow_days(info: dict) -> int:
    return int(info["grow_days"])


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
    for kind in crops.get("crops", {}):
        inventory.setdefault(f"{kind}_seed", 0)
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
    }
    apply_new_day_turns(state, load_rules())
    if is_wet_weather(weather):
        dawn_water(state)
        log_append(state, weather_arrive_message(weather))
    return state


def dawn_water(state: dict) -> None:
    for _r, _c, tile in iter_tiles(state):
        if tile["type"] == "soil":
            tile["watered"] = True


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
        slots[key] = {
            "energy": cap if slept else faint,
            "ended_turn": False,
            "row": CABIN_ROW if slept else row,
            "col": CABIN_COL if slept else col,
            "snacks_eaten": 0,
        }
    for key in known_players():
        if key not in slots:
            slots[key] = {
                "energy": cap,
                "ended_turn": False,
                "row": CABIN_ROW,
                "col": CABIN_COL,
                "snacks_eaten": 0,
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
    return changed


def migrate_state(state: dict, rules: dict | None = None) -> bool:
    """Add turn/energy/weed fields to older saves. Returns True if the state changed."""
    rules = rules or load_rules()
    changed = migrate_tile_fields(state)
    if "last_note" not in state:
        state["last_note"] = None
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
        return False, f"A {crop['kind']} is growing at {here}. Harvest or wait before tilling."
    cleared = ""
    if crop and crop.get("stage") == "withered":
        tile["crop"] = None
        cleared = f" {who(player, 'clear', 'clears')} the withered plant."
    if tile.get("tilled") and not cleared:
        return False, f"{here[0].upper() + here[1:]} is already tilled."
    tile["tilled"] = True
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
        return False, f"{kind.capitalize()} only grows in {when}. It is {state['season']}."
    seed_key = f"{kind}_seed"
    if int(state["inventory"].get(seed_key, 0)) < 1:
        return False, f"You have no {kind} seeds. Buy some at the shop."
    state["inventory"][seed_key] = int(state["inventory"].get(seed_key, 0)) - 1
    tile["crop"] = {
        "kind": kind,
        "planted_day": int(state["day"]),
        "days_grown": 0,
        "stage": "seed",
        "dry_days": 0,
    }
    msg = f"{who(player, 'plant', 'plants')} a {kind} seed at {here}."
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
    if tile.get("watered"):
        return False, f"{here[0].upper() + here[1:]} is already watered today."
    tile["watered"] = True
    crop = tile.get("crop")
    if crop and crop.get("stage") != "withered":
        msg = f"{who(player, 'water', 'waters')} the {crop['kind']} at {here}."
    else:
        msg = f"{who(player, 'water', 'waters')} the soil at {here}."
    log_append(state, msg, player)
    return True, msg


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
        msg = f"{who(player, 'clear', 'clears')} the withered plant at {here}."
        log_append(state, msg, player)
        return True, msg
    if crop.get("stage") != "mature":
        info = crop_info(crops, crop["kind"]) or {}
        needed = grow_days(info) if info else "?"
        return (
            False,
            f"The {crop['kind']} at {here} is not ready "
            f"(day {crop.get('days_grown', 0)} of {needed}, {crop.get('stage')}).",
        )
    kind = crop["kind"]
    state["inventory"][kind] = int(state["inventory"].get(kind, 0)) + 1
    tile["crop"] = None
    # The bed stays tilled; today's water remains.
    msg = f"{who(player, 'harvest', 'harvests')} a {kind} at {here}."
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


def buy(state: dict, crops: dict, kind, n, player: str | None = None) -> tuple[bool, str]:
    kind = normalize_kind(str(kind))
    info = crop_info(crops, kind)
    if not info:
        known = ", ".join(crops.get("crops", {}))
        return False, f"Unknown seed {kind!r}. The shop sells: {known}."
    count, err = _parse_count(n)
    if err:
        return False, err
    price = int(info["seed_price"]) * count
    gold = int(state["gold"])
    if gold < price:
        return (
            False,
            f"Not enough gold. {count} {kind} seed(s) cost {price}G; you have {gold}G.",
        )
    state["gold"] = gold - price
    seed_key = f"{kind}_seed"
    state["inventory"][seed_key] = int(state["inventory"].get(seed_key, 0)) + count
    noun = "seed" if count == 1 else "seeds"
    msg = (
        f"{who(player, 'buy', 'buys')} {count} {kind} {noun} for {price}G. "
        f"{display_name(player) if player else 'You'} "
        f"{'has' if player else 'have'} {state['gold']}G left."
    )
    log_append(state, msg, player)
    return True, msg


def sell(state: dict, crops: dict, kind, n, player: str | None = None) -> tuple[bool, str]:
    kind = normalize_kind(str(kind))
    info = crop_info(crops, kind)
    if not info:
        known = ", ".join(crops.get("crops", {}))
        return False, f"Unknown crop {kind!r}. You can sell: {known}."
    count, err = _parse_count(n)
    if err:
        return False, err
    have = int(state["inventory"].get(kind, 0))
    if have < count:
        return False, f"You only have {have} {kind}(s) to sell."
    gold = int(info["sell_price"]) * count
    state["inventory"][kind] = have - count
    state["gold"] = int(state["gold"]) + gold
    noun = kind if count == 1 else f"{kind}s"
    msg = (
        f"{who(player, 'sell', 'sells')} {count} {noun} for {gold}G. "
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


def _apply_evening_growth(state: dict, crops: dict, rules: dict | None = None) -> list[str]:
    notes = []
    limit = wither_after(crops)
    for r, c, tile in iter_tiles(state):
        if tile["type"] != "soil":
            continue
        crop = tile.get("crop")
        if not crop or crop.get("stage") == "withered":
            tile["watered"] = False
            continue
        here = position_name(r, c)
        kind = crop["kind"]
        info = crop_info(crops, kind)
        if tile.get("watered"):
            crop["dry_days"] = 0
            if crop.get("stage") != "mature" and info:
                skip_growth = False
                if tile.get("weedy"):
                    ticks = int(tile.get("weedy_ticks") or 0)
                    # Gentle: first watered day after becoming weedy still grows;
                    # the next one is skipped, then they alternate (50%).
                    skip_growth = (ticks % 2 == 1)
                    tile["weedy_ticks"] = ticks + 1
                if skip_growth:
                    notes.append(
                        f"The weedy {kind} at {here} skips a day of growth."
                    )
                else:
                    crop["days_grown"] = int(crop.get("days_grown", 0)) + 1
                    new_stage = stage_for(crop["days_grown"], info)
                    if new_stage != crop.get("stage"):
                        crop["stage"] = new_stage
                        if new_stage == "mature":
                            notes.append(f"The {kind} at {here} is mature and ready to harvest.")
                        else:
                            notes.append(
                                f"The {kind} at {here} is now {stage_label(info, new_stage)} "
                                f"(day {crop['days_grown']} of {grow_days(info)})."
                            )
                    else:
                        crop["stage"] = new_stage
            # Mature crops stay mature when watered. Weeds never kill a crop.
        else:
            crop["dry_days"] = int(crop.get("dry_days", 0)) + 1
            if crop["dry_days"] >= limit:
                crop["stage"] = "withered"
                notes.append(
                    f"The {kind} at {here} withered after {crop['dry_days']} dry day(s)."
                )
        tile["watered"] = False
    return notes


def advance_day(state: dict, crops: dict, rules: dict | None = None) -> tuple[bool, str]:
    """Apply evening growth and dawn the next day. Used when both players end their turn."""
    rules = rules or load_rules()
    notes = _apply_evening_growth(state, crops, rules)
    state["day"] = int(state["day"]) + 1
    state["season"] = season_for_day(state["day"], crops)
    ensure_weather_seed(state, rules, crops)
    state["weather"] = weather_for_day(
        state["day"], crops, rules, seed=int(state["weather_seed"])
    )

    for r, c, tile in iter_tiles(state):
        crop = tile.get("crop")
        if not crop or crop.get("stage") == "withered":
            continue
        info = crop_info(crops, crop["kind"])
        if info and state["season"] not in info["seasons"]:
            crop["stage"] = "withered"
            notes.append(
                f"The {crop['kind']} at {position_name(r, c)} "
                f"withered in the {state['season']} air."
            )

    if is_wet_weather(state["weather"]):
        dawn_water(state)
        notes.append(weather_arrive_message(state["weather"]))

    notes.extend(sprout_and_age_weeds(state, rules))

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
        f"{display_name(player)} walks {direction} to {describe_where(*dest)} ({cost} energy).",
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
            f"Not enough energy. Walking {describe_where(*dest)} is {len(steps)} "
            f"step(s) ({cost} energy); {display_name(player)} has {energy} left.",
        )
    set_player_where(state, player, dest_r, dest_c)
    slot["energy"] = energy - cost
    return (
        True,
        f"{display_name(player)} walks to {describe_where(*dest)} "
        f"({len(steps)} step(s), {cost} energy).",
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
    """Eat a harvested crop from the pack. Free, capped per turn, restores energy."""
    rules = rules or load_rules()
    raw_kind = (kind or "").strip().lower()
    if raw_kind.endswith("_seed") or raw_kind.endswith(" seed"):
        return False, "Seeds aren't a snack. Eat a harvested crop, like: eat carrot"
    kind = normalize_kind(kind)
    restore = eat_energy_for(crops, kind)
    if restore is None:
        if crop_info(crops, kind):
            return False, f"{kind} isn't edible raw."
        return False, f"Unknown crop '{kind}'. Try carrot, turnip, or kabocha."
    have = int(state.setdefault("inventory", {}).get(kind, 0) or 0)
    if have <= 0:
        return False, f"No {kind} in the pack."
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
    state["inventory"][kind] = have - 1
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
                actions.append(f"till {r} {c}")
        if tile.get("tilled") and not crop:
            if energy >= energy_cost("plant", rules):
                for kind, info in crops.get("crops", {}).items():
                    if state["season"] in info["seasons"] and int(
                        state["inventory"].get(f"{kind}_seed", 0)
                    ) > 0:
                        actions.append(f"plant {r} {c} {kind}")
        if not tile.get("watered"):
            if energy >= energy_cost("water", rules):
                actions.append(f"water {r} {c}")
        if crop and crop.get("stage") == "mature":
            actions.append(f"harvest {r} {c}")
        if withered:
            actions.append(f"harvest {r} {c}")
        if tile_has_weed(tile) and energy >= energy_cost("pluck", rules):
            actions.append(f"pluck {r} {c}")
    for kind, info in crops.get("crops", {}).items():
        price = int(info["seed_price"])
        if int(state["gold"]) >= price:
            actions.append(f"buy {kind} 1")
        if int(state["inventory"].get(kind, 0)) > 0:
            actions.append(f"sell {kind} 1")
            if (
                eat_energy_for(crops, kind) is not None
                and int(player_slot(state, actor).get("snacks_eaten") or 0) < snacks_per_turn(rules)
                and energy < max_energy(rules)
            ):
                actions.append(f"eat {kind}")
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

    # Plot work is on the tile you're standing on. Coords are optional,
    # but if given they must be the current tile.
    here = player_where(state, actor)
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
    else:
        return (
            False,
            "Unknown action. Try look, move, go cabin, till, plant, water, harvest, "
            "pluck, eat, buy, sell, or end turn.",
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

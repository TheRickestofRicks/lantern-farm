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

WET_WEATHER = frozenset({"rain", "snow"})


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


def player_slot(state: dict, player: str) -> dict:
    players = state.setdefault("players", {})
    slot = players.setdefault(player, {})
    slot.setdefault("energy", 0)
    slot.setdefault("ended_turn", False)
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


def weather_for_day(day: int, crops: dict | None = None) -> str:
    """Deterministic weather from the day number. No RNG is used."""
    season = season_for_day(day, crops)
    d = day_in_season(day, crops)
    # Days 3, 5, 10, and 14 of every 14-day season are wet.
    wet = d in {3, 5, 10, 14}
    if not wet:
        return "sun"
    return "snow" if season == "winter" else "rain"


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


def fresh_state(crops: dict | None = None) -> dict:
    crops = crops or load_crops()
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
    weather = weather_for_day(day, crops)
    state = {
        "day": day,
        "season": season_for_day(day, crops),
        "weather": weather,
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
    if weather == "snow":
        return flavor("snow") or "Snow settles on the farm. The soil is wet beneath it."
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
    """Start (or restart) a day: starting player's turn, both at full energy."""
    from config import starting_player as config_starting_player
    rules = rules or load_rules()
    energy = max_energy(rules)
    starter = normalize_player(config_starting_player()) or normalize_player(rules.get("starting_player"))
    players = list(known_players()) or [p for p in (rules.get("players") or [])]
    slots = {}
    for name in players:
        key = normalize_player(name) or (str(name).strip().lower() if name else None)
        if not key:
            continue
        slots[key] = {"energy": energy, "ended_turn": False}
    for key in known_players():
        slots.setdefault(key, {"energy": energy, "ended_turn": False})
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
    if state.get("players") and state.get("current_player"):
        # Fill any missing slots without resetting mid-turn energy.
        for key in KNOWN_PLAYERS:
            if key not in state["players"]:
                state["players"][key] = {
                    "energy": max_energy(rules),
                    "ended_turn": False,
                }
                changed = True
            else:
                state["players"][key].setdefault("energy", max_energy(rules))
                state["players"][key].setdefault("ended_turn", False)
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
    if everyone_done:
        _ok, day_msg = advance_day(state, crops, rules)
        apply_new_day_turns(state, rules)
        nxt = state["current_player"]
        cap = max_energy(rules)
        header = (
            f"{display_name(player)} ends the turn. The day turns. {day_msg} "
            f"It is {display_name(nxt)}'s turn, {cap} energy."
        )
        log_append(
            state,
            f"{display_name(player)} ends the turn. A new day begins. "
            f"It is {display_name(nxt)}'s turn.",
            player,
        )
        return True, header
    nxt = other_player(player, rules)
    state["current_player"] = nxt
    # The player receiving the turn starts it with a full energy bar.
    if not player_slot(state, nxt).get("ended_turn"):
        player_slot(state, nxt)["energy"] = max_energy(rules)
    msg = (
        f"{display_name(player)} ends the turn. "
        f"It is {display_name(nxt)}'s turn, {player_slot(state, nxt)['energy']}/{max_energy(rules)} energy."
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
    state["weather"] = weather_for_day(state["day"], crops)

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
        "rain": "a rainy morning",
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
    for r, c, tile in iter_tiles(state):
        if tile["type"] == "cabin":
            continue
        crop = tile.get("crop")
        living = crop and crop.get("stage") not in (None, "withered")
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
        _ = living  # kept for readability of the living/withered split
    for kind, info in crops.get("crops", {}).items():
        price = int(info["seed_price"])
        if int(state["gold"]) >= price:
            actions.append(f"buy {kind} 1")
        if int(state["inventory"].get(kind, 0)) > 0:
            actions.append(f"sell {kind} 1")
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

    cost = energy_cost(verb, rules)
    energy = int(player_slot(state, actor)["energy"])
    if cost > energy:
        return (
            False,
            f"Not enough energy. {verb} costs {cost}; "
            f"{display_name(actor)} has {energy} left.",
        )

    if verb == "till":
        if len(args) != 2:
            return False, "Usage: till <row> <col>   example: till 1 1"
        ok, msg = till(state, crops, args[0], args[1], actor)
    elif verb == "plant":
        if len(args) != 3:
            return False, "Usage: plant <row> <col> <kind>   example: plant 1 1 kabocha"
        ok, msg = plant(state, crops, args[0], args[1], args[2], actor)
    elif verb == "water":
        if len(args) != 2:
            return False, "Usage: water <row> <col>   example: water 1 1"
        ok, msg = water(state, crops, args[0], args[1], actor)
    elif verb == "harvest":
        if len(args) != 2:
            return False, "Usage: harvest <row> <col>   example: harvest 1 1"
        ok, msg = harvest(state, crops, args[0], args[1], actor)
    elif verb == "buy":
        if len(args) != 2:
            return False, "Usage: buy <kind> <count>   example: buy kabocha 2"
        ok, msg = buy(state, crops, args[0], args[1], actor)
    elif verb == "sell":
        if len(args) != 2:
            return False, "Usage: sell <kind> <count>   example: sell kabocha 1"
        ok, msg = sell(state, crops, args[0], args[1], actor)
    elif verb == "pluck":
        if len(args) != 2:
            return False, "Usage: pluck <row> <col>   example: pluck 1 1"
        ok, msg = pluck(state, crops, args[0], args[1], actor)
    else:
        return (
            False,
            "Unknown action. Try look, till, plant, water, harvest, pluck, buy, sell, or end turn.",
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

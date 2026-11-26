"""Mine floors, ores, the pickaxe, and the forge for Lantern Farm.

Phase 2 of docs/plan-hills-and-mine.md. Slimes stay Phase 3.
"""

from __future__ import annotations

from hills import (
    AREA_FARM,
    AREA_HILLS,
    AREA_MINE,
    MINE_ENTRANCE,
    normalize_area,
    player_area,
    set_player_place,
    describe_place,
)

MINE_ROWS = 3
MINE_COLS = 3
CENTER = (2, 2)
MAX_FLOOR = 25
SAFE_FLOORS = (5, 10, 15, 20, 25)
DEFAULT_PICKAXE_PRICE = 40
DEFAULT_REST_ENERGY = 25
DEFAULT_UPGRADE_ORE = 5
DEFAULT_COPPER_ENERGY = 5
DEFAULT_IRON_BONUS = 1

# Ordinary-floor rock composition by depth. Remaining weight is plain stone.
# Safe floors have no rocks.
ORE_BANDS = (
    # (lo, hi, copper, iron, gold) — inclusive floor ranges
    (1, 4, 40, 0, 0),
    (6, 9, 50, 15, 0),
    (11, 14, 20, 45, 5),
    (16, 19, 10, 35, 25),
    (21, 24, 0, 20, 45),
)

TOOL_TIERS = ("basic", "copper", "iron", "gold")
TIER_ORE = {
    "copper": "copper_ore",
    "iron": "iron_ore",
    "gold": "gold_ore",
}
FORGE_TOOLS = ("hoe", "watering_can", "axe", "pickaxe")

ORE_LABELS = {
    "copper_ore": "copper ore",
    "iron_ore": "iron ore",
    "gold_ore": "gold ore",
    "stone": "stone",
}


def mine_rules(rules: dict | None = None) -> dict:
    from engine import load_rules

    rules = rules or load_rules()
    cfg = rules.get("mine") if isinstance(rules, dict) else None
    return cfg if isinstance(cfg, dict) else {}


def max_floor(rules: dict | None = None) -> int:
    try:
        return max(1, int(mine_rules(rules).get("max_floor") or MAX_FLOOR))
    except (TypeError, ValueError):
        return MAX_FLOOR


def safe_floors(rules: dict | None = None) -> tuple[int, ...]:
    raw = mine_rules(rules).get("safe_floors")
    if isinstance(raw, (list, tuple)) and raw:
        out = []
        for item in raw:
            try:
                n = int(item)
            except (TypeError, ValueError):
                continue
            if n not in out:
                out.append(n)
        return tuple(out) if out else SAFE_FLOORS
    return SAFE_FLOORS


def is_safe_floor(floor: int, rules: dict | None = None) -> bool:
    return int(floor) in safe_floors(rules)


def pickaxe_price(rules: dict | None = None) -> int:
    try:
        return max(1, int(mine_rules(rules).get("pickaxe_price") or DEFAULT_PICKAXE_PRICE))
    except (TypeError, ValueError):
        return DEFAULT_PICKAXE_PRICE


def rest_energy_amount(rules: dict | None = None) -> int:
    try:
        return max(0, int(mine_rules(rules).get("rest_energy") or DEFAULT_REST_ENERGY))
    except (TypeError, ValueError):
        return DEFAULT_REST_ENERGY


def upgrade_ore_cost(rules: dict | None = None) -> int:
    try:
        return max(1, int(mine_rules(rules).get("upgrade_ore") or DEFAULT_UPGRADE_ORE))
    except (TypeError, ValueError):
        return DEFAULT_UPGRADE_ORE


def copper_tool_energy(rules: dict | None = None) -> int:
    try:
        return max(1, int(mine_rules(rules).get("copper_energy") or DEFAULT_COPPER_ENERGY))
    except (TypeError, ValueError):
        return DEFAULT_COPPER_ENERGY


def iron_yield_bonus(rules: dict | None = None) -> int:
    try:
        return max(0, int(mine_rules(rules).get("iron_bonus") or DEFAULT_IRON_BONUS))
    except (TypeError, ValueError):
        return DEFAULT_IRON_BONUS


def mine_hash(*parts) -> int:
    """Deterministic mix of seed, season, floor, and salts. No RNG."""
    from engine import weather_mix

    acc = 0
    for i, part in enumerate(parts):
        if isinstance(part, str):
            n = 0
            for ch in part:
                n = (n * 131 + ord(ch)) & 0xFFFFFFFF
        else:
            try:
                n = int(part)
            except (TypeError, ValueError):
                n = 0
        acc = weather_mix(acc ^ n, i + 1, salt=acc)
    return acc & 0xFFFFFFFF


def _season_key(state: dict, crops: dict | None = None) -> tuple[str, int]:
    from engine import normalize_season, year_for_day, load_crops

    crops = crops or load_crops()
    season = normalize_season(state.get("season")) or "spring"
    year = year_for_day(int(state.get("day") or 1), crops)
    return season, year


def mine_of(state: dict) -> dict:
    mine = state.get("mine")
    if not isinstance(mine, dict):
        mine = {}
        state["mine"] = mine
    return mine


def empty_mine_tile(safe: bool = False) -> dict:
    return {
        "type": "mine_safe" if safe else "mine_floor",
        "rock": None,
        "ladder": None,
        "exit": False,
        "lantern": False,
        "elevator": False,
    }


def ore_chances(floor: int) -> tuple[int, int, int]:
    """Return (copper, iron, gold) weights out of 100 for an ordinary floor."""
    f = int(floor)
    for lo, hi, copper, iron, gold in ORE_BANDS:
        if lo <= f <= hi:
            return copper, iron, gold
    return 0, 0, 0


def ore_kind_for(floor: int, row: int, col: int, seed: int, season: str, year: int) -> str | None:
    """Kind of ore in a rock, or None for plain stone."""
    copper, iron, gold = ore_chances(floor)
    roll = mine_hash(seed, season, year, floor, row, col, 4401) % 100
    if roll < copper:
        return "copper_ore"
    if roll < copper + iron:
        return "iron_ore"
    if roll < copper + iron + gold:
        return "gold_ore"
    return None


def _pick_cell(choices: list[tuple[int, int]], seed: int, *salts) -> tuple[int, int]:
    if not choices:
        return (1, 1)
    return choices[mine_hash(seed, *salts) % len(choices)]


def generate_floor(state: dict, floor: int, rules: dict | None = None) -> dict:
    """Build one 3x3 floor from the farm seed and the current season."""
    from engine import load_crops

    season, year = _season_key(state)
    seed = int(state.get("weather_seed") or 0)
    floor = int(floor)
    safe = is_safe_floor(floor, rules)
    cells = [(r, c) for r in range(1, MINE_ROWS + 1) for c in range(1, MINE_COLS + 1)]
    arrival = _pick_cell(cells, seed, season, year, floor, 11)
    tiles = []
    for r in range(1, MINE_ROWS + 1):
        row = []
        for c in range(1, MINE_COLS + 1):
            tile = empty_mine_tile(safe=safe)
            if (r, c) == arrival:
                tile["exit"] = True
            row.append(tile)
        tiles.append(row)

    if safe:
        remaining = [cell for cell in cells if cell != arrival]
        lantern = _pick_cell(remaining, seed, season, year, floor, 22)
        remaining = [cell for cell in remaining if cell != lantern]
        lift = _pick_cell(remaining, seed, season, year, floor, 33)
        remaining = [cell for cell in remaining if cell != lift]
        tiles[lantern[0] - 1][lantern[1] - 1]["lantern"] = True
        tiles[lift[0] - 1][lift[1] - 1]["elevator"] = True
        if floor < max_floor(rules) and remaining:
            down = _pick_cell(remaining, seed, season, year, floor, 44)
            tiles[down[0] - 1][down[1] - 1]["ladder"] = "open"
    else:
        ladder_choices = [cell for cell in cells if cell != arrival and cell != CENTER]
        if not ladder_choices:
            ladder_choices = [cell for cell in cells if cell != arrival]
        hidden = _pick_cell(ladder_choices, seed, season, year, floor, 55)
        for r, c in cells:
            if (r, c) == arrival:
                continue
            tile = tiles[r - 1][c - 1]
            ore = ore_kind_for(floor, r, c, seed, season, year)
            tile["rock"] = ore or "stone"
            if (r, c) == hidden:
                tile["rock"] = "stone"
                tile["ladder"] = "hidden"
    return {"tiles": tiles, "floor": floor}


def ensure_mine(state: dict, rules: dict | None = None, crops: dict | None = None) -> bool:
    """Install or re-roll the season's mine. Does not touch farm tiles or gold."""
    changed = False
    mine = mine_of(state)
    season, year = _season_key(state, crops)
    if mine.get("season") != season or int(mine.get("year") or 0) != year:
        mine["season"] = season
        mine["year"] = year
        mine["floors"] = {}
        mine["checkpoints"] = []
        mine["deepest"] = 0
        mine["rests"] = {}
        changed = True
    mine.setdefault("floors", {})
    if not isinstance(mine["floors"], dict):
        mine["floors"] = {}
        changed = True
    if not isinstance(mine.get("checkpoints"), list):
        mine["checkpoints"] = []
        changed = True
    try:
        mine["deepest"] = max(0, int(mine.get("deepest") or 0))
    except (TypeError, ValueError):
        mine["deepest"] = 0
        changed = True
    if not isinstance(mine.get("rests"), dict):
        mine["rests"] = {}
        changed = True
    if "mine_entrance_open" not in state:
        # Derive from the hills tile when already pried open on an older pass.
        opened = False
        try:
            from hills import get_hills_tile, hills_tiles

            if hills_tiles(state):
                tile = get_hills_tile(state, *MINE_ENTRANCE)
                opened = bool(tile and tile.get("type") == "mine_entrance" and tile.get("closed") is False)
        except (IndexError, TypeError, KeyError):
            opened = False
        state["mine_entrance_open"] = opened
        changed = True
    return changed


def get_floor(state: dict, floor: int, rules: dict | None = None) -> dict:
    """Return (and lazily generate) one floor of the current season's mine."""
    ensure_mine(state, rules)
    mine = mine_of(state)
    key = str(int(floor))
    floors = mine.setdefault("floors", {})
    data = floors.get(key)
    if not isinstance(data, dict) or not isinstance(data.get("tiles"), list):
        data = generate_floor(state, floor, rules)
        floors[key] = data
    return data


def get_mine_tile(state: dict, floor: int, row: int, col: int, rules: dict | None = None) -> dict:
    data = get_floor(state, floor, rules)
    return data["tiles"][int(row) - 1][int(col) - 1]


def iter_mine_tiles(state: dict, floor: int, rules: dict | None = None):
    data = get_floor(state, floor, rules)
    for r, row in enumerate(data["tiles"], 1):
        for c, tile in enumerate(row, 1):
            yield r, c, tile


def arrival_tile(state: dict, floor: int, rules: dict | None = None) -> tuple[int, int]:
    for r, c, tile in iter_mine_tiles(state, floor, rules):
        if tile.get("exit"):
            return r, c
    return (1, 1)


def player_floor(state: dict, player: str) -> int | None:
    from engine import player_slot

    if player_area(state, player) != AREA_MINE:
        return None
    slot = player_slot(state, player)
    try:
        floor = int(slot.get("floor") or 1)
    except (TypeError, ValueError):
        floor = 1
    return max(1, min(floor, max_floor()))


def is_entrance_open(state: dict) -> bool:
    if state.get("mine_entrance_open"):
        return True
    from hills import get_hills_tile, hills_tiles

    if not hills_tiles(state):
        return False
    tile = get_hills_tile(state, *MINE_ENTRANCE)
    return bool(tile and tile.get("type") == "mine_entrance" and tile.get("closed") is False)


def open_entrance(state: dict) -> None:
    from hills import get_hills_tile, hills_tiles, ensure_hills

    ensure_hills(state)
    if hills_tiles(state):
        tile = get_hills_tile(state, *MINE_ENTRANCE)
        if tile.get("type") == "mine_entrance":
            tile["closed"] = False
    state["mine_entrance_open"] = True
    state["mine_entrance_found"] = True


def pickaxe_in_world(state: dict, rules: dict | None = None) -> bool:
    from inventory import item_count, TOOL_PICKAXE

    return item_count(state, TOOL_PICKAXE, rules) >= 1


def pickaxe_unlocked(state: dict) -> bool:
    return bool(state.get("mine_entrance_found"))


def tool_tier(state: dict, tool: str) -> str:
    tiers = state.get("tool_tiers")
    if not isinstance(tiers, dict):
        return "basic"
    raw = str(tiers.get(tool) or "basic").strip().lower()
    return raw if raw in TOOL_TIERS else "basic"


def set_tool_tier(state: dict, tool: str, tier: str) -> None:
    tiers = state.setdefault("tool_tiers", {})
    if not isinstance(tiers, dict):
        tiers = {}
        state["tool_tiers"] = tiers
    tiers[tool] = tier


def next_tool_tier(current: str) -> str | None:
    if current not in TOOL_TIERS:
        current = "basic"
    idx = TOOL_TIERS.index(current)
    if idx + 1 >= len(TOOL_TIERS):
        return None
    return TOOL_TIERS[idx + 1]


def tool_action_cost(state: dict, player: str | None, verb: str, rules: dict | None = None) -> int:
    """Energy for a tool action, reduced by a copper (or better) upgrade."""
    from engine import energy_cost
    from inventory import TOOL_HOE, TOOL_CAN, TOOL_AXE, TOOL_PICKAXE

    base = energy_cost(verb, rules)
    mapping = {
        "till": TOOL_HOE,
        "water": TOOL_CAN,
        "chop": TOOL_AXE,
        "mine": TOOL_PICKAXE,
    }
    tool = mapping.get(verb)
    if not tool:
        return base
    tier = tool_tier(state, tool)
    if tier in {"copper", "iron", "gold"}:
        return min(base, copper_tool_energy(rules))
    return base


def yield_with_upgrade(state: dict, tool: str, base: int, rules: dict | None = None) -> int:
    tier = tool_tier(state, tool)
    if tier in {"iron", "gold"}:
        return base + iron_yield_bonus(rules)
    return base


def mark_checkpoint(state: dict, floor: int) -> None:
    if not is_safe_floor(floor):
        return
    mine = mine_of(state)
    checkpoints = mine.setdefault("checkpoints", [])
    if floor not in checkpoints:
        checkpoints.append(int(floor))
        checkpoints.sort()
    mine["deepest"] = max(int(mine.get("deepest") or 0), int(floor))


def _enter_floor(state: dict, player: str, floor: int, rules: dict | None = None) -> tuple[int, int]:
    row, col = arrival_tile(state, floor, rules)
    set_player_place(state, player, AREA_MINE, row, col, floor=floor)
    mine = mine_of(state)
    mine["deepest"] = max(int(mine.get("deepest") or 0), int(floor))
    if is_safe_floor(floor, rules):
        mark_checkpoint(state, floor)
    return row, col


def enter_mine(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append, who
    from inventory import pack_has, TOOL_PICKAXE
    from hills import is_mine_entrance_tile, ensure_hills

    ensure_hills(state, rules)
    ensure_mine(state, rules)
    area = player_area(state, player)
    row, col = player_where(state, player)
    if area != AREA_HILLS or not is_mine_entrance_tile(row, col):
        return False, "Enter the mine from the entrance on the north side of the hills (row 1 col 2)."
    if not is_entrance_open(state):
        if not pack_has(state, player, TOOL_PICKAXE, 1, rules):
            if pickaxe_unlocked(state):
                return False, (
                    "The entrance is boarded. Buy a pickaxe from the shop, "
                    "then come back to pry it open."
                )
            return False, (
                "The entrance is boarded. A pickaxe would be needed to open it, "
                "once the way in has been found."
            )
        open_entrance(state)
        row, col = _enter_floor(state, player, 1, rules)
        msg = (
            f"{who(player, 'pry', 'pries')} the boards off the mine entrance "
            f"and {('step' if not player else 'steps')} onto floor 1 "
            f"({describe_place(AREA_MINE, row, col, floor=1)})."
        )
        log_append(state, msg, player)
        return True, msg
    row, col = _enter_floor(state, player, 1, rules)
    msg = (
        f"{display_name(player)} enters the mine and arrives on floor 1 "
        f"({describe_place(AREA_MINE, row, col, floor=1)})."
    )
    log_append(state, msg, player)
    return True, msg


def climb_up(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append
    from hills import set_player_place as place_on

    if player_area(state, player) != AREA_MINE:
        return False, "There is no ladder to climb here."
    floor = player_floor(state, player) or 1
    row, col = player_where(state, player)
    tile = get_mine_tile(state, floor, row, col, rules)
    if not tile.get("exit"):
        return False, "Climb up from the shaft you arrived through."
    if floor <= 1:
        place_on(state, player, AREA_HILLS, MINE_ENTRANCE[0], MINE_ENTRANCE[1])
        msg = f"{display_name(player)} climbs up and leaves the mine at the entrance in the hills."
        log_append(state, msg, player)
        return True, msg
    dest = floor - 1
    # Arrive on the down-ladder tile of the floor above if it is already revealed,
    # otherwise on that floor's arrival shaft.
    dest_row, dest_col = arrival_tile(state, dest, rules)
    for r, c, above in iter_mine_tiles(state, dest, rules):
        if above.get("ladder") in {"open", "hidden"}:
            # Hidden still "is" the way you came, but you can't stand in a hidden shaft;
            # after climbing up you appear on the arrival tile of that floor.
            if above.get("ladder") == "open":
                dest_row, dest_col = r, c
            break
    set_player_place(state, player, AREA_MINE, dest_row, dest_col, floor=dest)
    if is_safe_floor(dest, rules):
        mark_checkpoint(state, dest)
    msg = (
        f"{display_name(player)} climbs up to floor {dest} "
        f"({describe_place(AREA_MINE, dest_row, dest_col, floor=dest)})."
    )
    log_append(state, msg, player)
    return True, msg


def climb_down(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append

    if player_area(state, player) != AREA_MINE:
        return False, "There is no ladder down here."
    floor = player_floor(state, player) or 1
    if floor >= max_floor(rules):
        return False, "This is as deep as the mine goes."
    row, col = player_where(state, player)
    tile = get_mine_tile(state, floor, row, col, rules)
    if tile.get("ladder") == "hidden":
        return False, "A rock is in the way. Break it with a pickaxe first."
    if tile.get("ladder") != "open":
        return False, "There is no open ladder down on this tile."
    dest = floor + 1
    dest_row, dest_col = _enter_floor(state, player, dest, rules)
    msg = (
        f"{display_name(player)} climbs down to floor {dest} "
        f"({describe_place(AREA_MINE, dest_row, dest_col, floor=dest)})."
    )
    log_append(state, msg, player)
    return True, msg


def leave_mine(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    """Leave from floor 1's shaft, or refuse with a hint."""
    if player_area(state, player) != AREA_MINE:
        return False, "You are not in the mine."
    floor = player_floor(state, player) or 1
    if floor != 1:
        return False, "Climb up to floor 1, or take the elevator to the entrance, then leave."
    return climb_up(state, player, rules)


def mine_rock(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append, who
    from inventory import pack_has, TOOL_PICKAXE, pack_space_for, add_to_pack, sync_inventory_view, item_name, item_label, indefinite

    if player_area(state, player) != AREA_MINE:
        return False, "There are no rocks to break on the farm. Enter the mine first."
    floor = player_floor(state, player) or 1
    row, col = player_where(state, player)
    tile = get_mine_tile(state, floor, row, col, rules)
    rock = tile.get("rock")
    if not rock:
        if tile.get("ladder") == "open":
            return False, "The ladder is already clear."
        return False, "There is no rock here to break."
    if not pack_has(state, player, TOOL_PICKAXE, 1, rules):
        return False, (
            f"{display_name(player)} needs {indefinite(item_label(TOOL_PICKAXE, state=state))} in their backpack to break rock. "
            "Buy one from the shop after finding the mine entrance."
        )
    got = yield_with_upgrade(state, TOOL_PICKAXE, 1, rules)
    what = "the stone" if rock == "stone" else "the ore"
    if not pack_space_for(state, player, rock, got, rules):
        return False, f"No room in the backpack for {what}. Drop something at the cabin first."
    leftover = add_to_pack(state, player, rock, got, rules)
    if leftover:
        return False, f"No room in the backpack for {what}. Drop something at the cabin first."
    sync_inventory_view(state, rules)
    tile["rock"] = None
    revealed = tile.get("ladder") == "hidden"
    if revealed:
        tile["ladder"] = "open"
    bits = [f"and packs {item_name(rock, got)}."]
    if revealed:
        bits[-1] = bits[-1][:-1] + ", uncovering a ladder down."
    # Gold pickaxe: also break one adjacent rock (NESW).
    splash = ""
    if tool_tier(state, TOOL_PICKAXE) == "gold":
        splash = _splash_mine(state, player, floor, row, col, rules)
    msg = (
        f"{who(player, 'break', 'breaks')} the rock at "
        f"{describe_place(AREA_MINE, row, col, floor=floor)} {bits[0]}"
    )
    if splash:
        msg = msg.rstrip(".") + splash
    log_append(state, msg, player)
    return True, msg


def _splash_mine(state: dict, player: str, floor: int, row: int, col: int, rules: dict | None) -> str:
    from inventory import pack_space_for, add_to_pack, sync_inventory_view, item_name, TOOL_PICKAXE

    for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
        rr, cc = row + dr, col + dc
        if not (1 <= rr <= MINE_ROWS and 1 <= cc <= MINE_COLS):
            continue
        tile = get_mine_tile(state, floor, rr, cc, rules)
        rock = tile.get("rock")
        if not rock:
            continue
        got = yield_with_upgrade(state, TOOL_PICKAXE, 1, rules)
        if not pack_space_for(state, player, rock, got, rules):
            return "."
        leftover = add_to_pack(state, player, rock, got, rules)
        if leftover:
            return "."
        sync_inventory_view(state, rules)
        tile["rock"] = None
        extra = ""
        if tile.get("ladder") == "hidden":
            tile["ladder"] = "open"
            extra = ", uncovering a ladder down"
        return f", and a neighbouring rock ({item_name(rock, got)}{extra})."
    return "."


def rest_at_lantern(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, player_slot, display_name, log_append, max_energy, load_rules

    rules = rules or load_rules()
    if player_area(state, player) != AREA_MINE:
        return False, "Rest at a lantern on a safe floor of the mine."
    floor = player_floor(state, player) or 1
    row, col = player_where(state, player)
    tile = get_mine_tile(state, floor, row, col, rules)
    if not tile.get("lantern"):
        return False, "Stand at the lantern to rest."
    if not is_safe_floor(floor, rules):
        return False, "There is no lantern rest on this floor."
    slot = player_slot(state, player)
    day = int(state.get("day") or 1)
    key = f"{player}:{floor}:{day}"
    mine = mine_of(state)
    rests = mine.setdefault("rests", {})
    if rests.get(key):
        return False, f"{display_name(player)} has already rested at this lantern today."
    cap = max_energy(rules)
    energy = int(slot.get("energy") or 0)
    if energy >= cap:
        return False, f"{display_name(player)} is already at full energy."
    gained = min(rest_energy_amount(rules), cap - energy)
    slot["energy"] = energy + gained
    rests[key] = True
    mark_checkpoint(state, floor)
    msg = (
        f"{display_name(player)} rests by the lantern on floor {floor} "
        f"and recovers {gained} energy ({slot['energy']}/{cap})."
    )
    log_append(state, msg, player)
    return True, msg


def parse_elevator_dest(raw: str | None, rules: dict | None = None) -> str | int | None:
    text = (raw or "").strip().lower().replace("_", " ")
    if not text or text in {"entrance", "out", "hills", "mouth"}:
        return "entrance"
    try:
        floor = int(text)
    except (TypeError, ValueError):
        return None
    if floor in safe_floors(rules) or floor == 1:
        return floor
    return None


def take_elevator(state: dict, player: str, dest, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append
    from hills import set_player_place as place_on

    if player_area(state, player) != AREA_MINE:
        return False, "The elevator is in the mine, on every fifth floor."
    floor = player_floor(state, player) or 1
    row, col = player_where(state, player)
    tile = get_mine_tile(state, floor, row, col, rules)
    if not tile.get("elevator"):
        return False, "Stand on the elevator to ride it."
    mark_checkpoint(state, floor)
    target = parse_elevator_dest("" if dest is None else str(dest), rules)
    if target is None:
        return False, "Usage: elevator   or: elevator 5 / 10 / 15 / 20 / 25 / entrance"
    mine = mine_of(state)
    checkpoints = list(mine.get("checkpoints") or [])
    if target == "entrance":
        place_on(state, player, AREA_HILLS, MINE_ENTRANCE[0], MINE_ENTRANCE[1])
        msg = f"{display_name(player)} rides the elevator up to the mine entrance in the hills."
        log_append(state, msg, player)
        return True, msg
    dest_floor = int(target)
    if dest_floor not in checkpoints and dest_floor != floor:
        reached = ", ".join(str(n) for n in checkpoints) or "none yet"
        return False, (
            f"That elevator stop has not been reached this season. "
            f"Checkpoints: {reached}."
        )
    dest_row, dest_col = arrival_tile(state, dest_floor, rules)
    for r, c, other in iter_mine_tiles(state, dest_floor, rules):
        if other.get("elevator"):
            dest_row, dest_col = r, c
            break
    set_player_place(state, player, AREA_MINE, dest_row, dest_col, floor=dest_floor)
    mark_checkpoint(state, dest_floor)
    msg = (
        f"{display_name(player)} rides the elevator to floor {dest_floor} "
        f"({describe_place(AREA_MINE, dest_row, dest_col, floor=dest_floor)})."
    )
    log_append(state, msg, player)
    return True, msg


def forge_tool(state: dict, player: str, tool: str, want_tier: str | None, rules: dict | None = None) -> tuple[bool, str]:
    from engine import display_name, log_append, is_player_in_cabin
    from inventory import (
        normalize_item,
        take_available,
        item_count,
        item_label,
        TOOL_HOE,
        TOOL_CAN,
        TOOL_AXE,
        TOOL_PICKAXE,
    )

    if not is_player_in_cabin(state, player):
        return False, "Forge at the cabin."
    raw = normalize_item(tool) or str(tool or "").strip().lower().replace(" ", "_")
    if raw not in FORGE_TOOLS:
        return False, "You can forge the hoe, watering can, axe, or pickaxe."
    if raw == TOOL_PICKAXE and not pickaxe_in_world(state, rules):
        return False, "There is no pickaxe on the farm to upgrade yet. Buy one from the shop first."
    # The tool must exist in the world (shared tools).
    if raw != TOOL_PICKAXE and item_count(state, raw, rules) < 1:
        return False, f"There is no {item_label(raw)} on the farm to upgrade."
    current = tool_tier(state, raw)
    nxt = next_tool_tier(current)
    if not nxt:
        return False, f"The {item_label(raw)} is already gold-tier."
    if want_tier:
        want = str(want_tier).strip().lower()
        if want not in TIER_ORE:
            return False, "Upgrade in order: copper, then iron, then gold."
        if want != nxt:
            return False, f"The next upgrade for the {item_label(raw)} is {nxt}."
    ore = TIER_ORE[nxt]
    need = upgrade_ore_cost(rules)
    have = item_count(state, ore, rules)
    if have < need:
        return False, (
            f"Forging a {nxt} {item_label(raw)} takes {need} {ORE_LABELS[ore]}. "
            f"You have {have}."
        )
    take_available(state, ore, need, player, pack_only=False, rules=rules)
    set_tool_tier(state, raw, nxt)
    msg = f"{display_name(player)} forges the {item_label(raw)} to {nxt} at the cabin."
    log_append(state, msg, player)
    return True, msg


def last_checkpoint(state: dict, rules: dict | None = None) -> int | None:
    mine = mine_of(state)
    points = [int(n) for n in (mine.get("checkpoints") or []) if is_safe_floor(int(n), rules)]
    return max(points) if points else None


def wake_place_after_mine_passout(
    state: dict,
    rules: dict | None = None,
    *,
    season_changed: bool = False,
) -> tuple[str, int, int, int | None]:
    """Where a player who passed out in the mine wakes (pack kept, 50 energy)."""
    if season_changed:
        return AREA_HILLS, MINE_ENTRANCE[0], MINE_ENTRANCE[1], None
    floor = last_checkpoint(state, rules)
    if not floor:
        return AREA_HILLS, MINE_ENTRANCE[0], MINE_ENTRANCE[1], None
    # Prefer the elevator tile on that floor.
    row, col = arrival_tile(state, floor, rules)
    for r, c, tile in iter_mine_tiles(state, floor, rules):
        if tile.get("elevator"):
            row, col = r, c
            break
    return AREA_MINE, row, col, floor


def mine_summary(state: dict, rules: dict | None = None) -> str:
    ensure_mine(state, rules)
    if not is_entrance_open(state):
        if state.get("mine_entrance_found"):
            return "The mine: the entrance has been found, but it is still boarded."
        return "The mine: a boarded entrance waits in the north hills."
    mine = mine_of(state)
    deepest = int(mine.get("deepest") or 0)
    points = mine.get("checkpoints") or []
    if deepest:
        stops = ", ".join(f"floor {n}" for n in points) if points else "none yet"
        return f"The mine is open. Deepest this season: floor {deepest}. Elevator stops: {stops}."
    return "The mine is open. No one has gone deeper than the entrance this season."


def describe_mine_tile(state: dict, floor: int, row: int, col: int, rules: dict | None = None) -> str:
    from engine import position_name, display_name, players_at
    from sprites import sprite_key

    tile = get_mine_tile(state, floor, row, col, rules)
    here = position_name(row, col)
    bits = []
    if tile.get("rock"):
        rock = tile["rock"]
        if rock == "stone":
            bits.append("a rock")
        else:
            bits.append(f"a rock with {ORE_LABELS.get(rock, rock)}")
        if tile.get("ladder") == "hidden":
            bits.append("nothing else obvious")
    if tile.get("ladder") == "open":
        bits.append("a ladder down")
    if tile.get("exit"):
        bits.append("the shaft back up" if floor > 1 else "the way out of the mine")
    if tile.get("lantern"):
        bits.append("a lantern you can rest by")
    if tile.get("elevator"):
        bits.append("an elevator")
    body = ", ".join(bits) + "." if bits else "clear stone floor."
    typ = "a safe chamber" if tile.get("type") == "mine_safe" else "a mine tunnel"
    who_here = players_at(state, row, col, area=AREA_MINE)
    who_bit = ""
    if who_here:
        names = ", ".join(display_name(n) for n in who_here)
        who_bit = f" {names} standing here."
    key = sprite_key(tile, None, row, col, floor=floor)
    return f"  {here} on mine floor {floor} — {typ}. {body.capitalize() if body[:1].islower() else body}{who_bit} (sprite: {key})"


def map_cell_lines(tile: dict) -> tuple[str, str]:
    """Two short mini-map lines. Labels fit 10 chars."""
    if tile.get("rock"):
        rock = tile.get("rock")
        top = {"copper_ore": "copper", "iron_ore": "iron", "gold_ore": "gold"}.get(rock, "rock")
        bot = "rock"
        return top, bot
    if tile.get("ladder") == "open":
        return "ladder", "down"
    if tile.get("elevator"):
        return "elevator", "lift"
    if tile.get("lantern"):
        return "lantern", "rest"
    if tile.get("exit"):
        return "shaft", "up"
    if tile.get("type") == "mine_safe":
        return "chamber", "safe"
    return "tunnel", "floor"


def migrate_mine(state: dict, rules: dict | None = None) -> bool:
    """Idempotent mine fields. Does not touch farm tiles, gold, packs, or the turn."""
    changed = False
    if ensure_mine(state, rules):
        changed = True
    if "tool_tiers" not in state or not isinstance(state.get("tool_tiers"), dict):
        state["tool_tiers"] = {}
        changed = True
    return changed

"""Hills area, trees, forage, and area-aware places for Lantern Farm.

Phase 1 of docs/plan-hills-and-mine.md. The mine mouth is boarded.
"""

from __future__ import annotations

AREA_FARM = "farm"
AREA_HILLS = "hills"
AREAS = (AREA_FARM, AREA_HILLS)

HILLS_ROWS = 3
HILLS_COLS = 3
HILLS_GATE = (3, 3)  # bottom-right, connects to the cabin
MINE_ENTRANCE = (1, 2)  # north-centre, boarded in Phase 1

TREE_STAGES = ("sapling", "young", "grown", "stump")
TREE_NEXT = {
    "sapling": "young",
    "young": "grown",
    "stump": "sapling",
}
# Days spent in a stage before it advances. Grown stays until chopped.
DEFAULT_TREE_DAYS = {
    "sapling": 3,
    "young": 4,
    "stump": 4,
}
CHOP_WOOD = 2
FORAGE_CAP = 2
FORAGE_MIN = 0
FORAGE_MAX = 2

FORAGE_BY_SEASON = {
    "spring": "wild_onion",
    "summer": "wild_berry",
    "autumn": "wild_mushroom",
}

FORAGE_INFO = {
    "wild_onion": {
        "name": "wild onion",
        "name_plural": "wild onions",
        "sell_price": 8,
        "eat_energy": 8,
        "seasons": ("spring",),
    },
    "wild_berry": {
        "name": "wild berry",
        "name_plural": "wild berries",
        "sell_price": 10,
        "eat_energy": 10,
        "seasons": ("summer",),
    },
    "wild_mushroom": {
        "name": "wild mushroom",
        "name_plural": "wild mushrooms",
        "sell_price": 12,
        "eat_energy": 12,
        "seasons": ("autumn",),
    },
}

WOOD_INFO = {
    "name": "wood",
    "name_plural": "wood",
    "sell_price": 4,
}

DIR_ALIASES = {
    "north": "up",
    "south": "down",
    "east": "right",
    "west": "left",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}


def normalize_area(area: str | None) -> str:
    key = (area or "").strip().lower()
    if key in AREAS:
        return key
    return AREA_FARM


def normalize_direction(direction: str | None) -> str | None:
    if not direction:
        return None
    return DIR_ALIASES.get(str(direction).strip().lower())


def is_cabin_place(area: str | None, row: int, col: int) -> bool:
    from engine import CABIN_ROW, CABIN_COL

    return normalize_area(area) == AREA_FARM and int(row) == CABIN_ROW and int(col) == CABIN_COL


def hills_rules(rules: dict | None = None) -> dict:
    from engine import load_rules

    rules = rules or load_rules()
    cfg = rules.get("hills") if isinstance(rules, dict) else None
    return cfg if isinstance(cfg, dict) else {}


def tree_days_for(stage: str, rules: dict | None = None) -> int:
    cfg = hills_rules(rules)
    raw = (cfg.get("tree_days") or {}) if cfg else {}
    try:
        return max(1, int(raw.get(stage) or DEFAULT_TREE_DAYS.get(stage) or 3))
    except (TypeError, ValueError):
        return int(DEFAULT_TREE_DAYS.get(stage) or 3)


def chop_wood_count(rules: dict | None = None) -> int:
    cfg = hills_rules(rules)
    try:
        return max(1, int(cfg.get("chop_wood") or CHOP_WOOD))
    except (TypeError, ValueError):
        return CHOP_WOOD


def forage_kind_for_season(season: str | None) -> str | None:
    key = (season or "").strip().lower()
    return FORAGE_BY_SEASON.get(key)


def empty_hills_tile(kind: str = "grass") -> dict:
    return {
        "type": kind,
        "tree": None,
        "forage": None,
    }


def hills_of(state: dict) -> dict:
    hills = state.get("hills")
    if not isinstance(hills, dict):
        hills = {}
        state["hills"] = hills
    return hills


def hills_tiles(state: dict) -> list:
    hills = hills_of(state)
    tiles = hills.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != HILLS_ROWS:
        return []
    return tiles


def get_hills_tile(state: dict, row: int, col: int) -> dict:
    tiles = hills_tiles(state)
    return tiles[int(row) - 1][int(col) - 1]


def iter_hills_tiles(state: dict):
    tiles = hills_tiles(state)
    for r, row in enumerate(tiles, 1):
        for c, tile in enumerate(row, 1):
            yield r, c, tile


def is_mine_entrance_tile(row: int, col: int) -> bool:
    return (int(row), int(col)) == MINE_ENTRANCE


def tile_is_hills_workable(tile: dict | None) -> bool:
    return bool(tile) and tile.get("type") in {"grass", "hillside"}


def has_tree(tile: dict | None) -> bool:
    tree = (tile or {}).get("tree")
    return bool(isinstance(tree, dict) and tree.get("stage") in TREE_STAGES)


def has_grown_tree(tile: dict | None) -> bool:
    tree = (tile or {}).get("tree")
    return bool(isinstance(tree, dict) and tree.get("stage") == "grown")


def has_forage(tile: dict | None) -> bool:
    forage = (tile or {}).get("forage")
    return bool(isinstance(forage, dict) and forage.get("kind"))


def forage_count(state: dict) -> int:
    return sum(1 for _r, _c, tile in iter_hills_tiles(state) if has_forage(tile))


def make_tree(stage: str, planted_day: int = 1, days_grown: int = 0) -> dict:
    return {
        "stage": stage,
        "planted_day": int(planted_day),
        "days_grown": int(days_grown),
    }


def make_forage(kind: str, appeared_day: int) -> dict:
    return {"kind": kind, "appeared_day": int(appeared_day)}


def _mix(seed: int, day: int, salt: int) -> int:
    from engine import weather_mix

    return weather_mix(int(seed), int(day), salt=int(salt))


def farm_seed(state: dict) -> int:
    try:
        return int(state.get("weather_seed") or 0)
    except (TypeError, ValueError):
        return 0


def _blank_hills_grid() -> list[list[dict]]:
    tiles = []
    for r in range(1, HILLS_ROWS + 1):
        row = []
        for c in range(1, HILLS_COLS + 1):
            if is_mine_entrance_tile(r, c):
                row.append({
                    "type": "mine_entrance",
                    "closed": True,
                    "tree": None,
                    "forage": None,
                })
            elif r == 1:
                row.append(empty_hills_tile("hillside"))
            else:
                row.append(empty_hills_tile("grass"))
        tiles.append(row)
    return tiles


def generate_hills_tiles(state: dict, *, as_of_day: int = 1, rules: dict | None = None) -> list[list[dict]]:
    """Deterministic starting hills as of day 1, then grown forward if needed."""
    tiles = _blank_hills_grid()
    seed = farm_seed(state)
    # Eligible tree plots: every tile except the boarded entrance.
    plots = [
        (r, c)
        for r in range(1, HILLS_ROWS + 1)
        for c in range(1, HILLS_COLS + 1)
        if not is_mine_entrance_tile(r, c)
    ]
    # A stable shuffle from the farm seed.
    order = sorted(plots, key=lambda rc: _mix(seed, rc[0] * 10 + rc[1], salt=0xA11))
    # Five starting trees: two grown, two young, one sapling — so a new
    # (or mid-season migrated) farm always has something ready to chop.
    staged = ["grown", "grown", "young", "young", "sapling"]
    for stage, (r, c) in zip(staged, order):
        tiles[r - 1][c - 1]["tree"] = make_tree(stage, planted_day=1, days_grown=0)
    state_view = {"hills": {"tiles": tiles}, "weather_seed": seed, "day": 1, "season": "spring"}
    # Grow forward to as_of_day without spawning historical forage piles.
    # Forage is then rolled once for the current day (see migrate / tick).
    from engine import season_for_day, load_crops

    crops = load_crops()
    for day in range(1, max(1, int(as_of_day))):
        state_view["day"] = day
        state_view["season"] = season_for_day(day, crops)
        _grow_trees(state_view, rules, log=False)
    state_view["day"] = max(1, int(as_of_day))
    state_view["season"] = season_for_day(state_view["day"], crops)
    # One current-day forage pass so mid-season farms are not empty of herbs.
    _spawn_forage(state_view, rules, log=False)
    return tiles


def ensure_hills(state: dict, rules: dict | None = None) -> bool:
    """Create hills on a save that does not have them. Idempotent."""
    hills = hills_of(state)
    tiles = hills.get("tiles")
    if isinstance(tiles, list) and len(tiles) == HILLS_ROWS and all(
        isinstance(row, list) and len(row) == HILLS_COLS for row in tiles
    ):
        changed = False
        for r, c, tile in iter_hills_tiles(state):
            tile.setdefault("type", "mine_entrance" if is_mine_entrance_tile(r, c) else ("hillside" if r == 1 else "grass"))
            tile.setdefault("tree", None)
            tile.setdefault("forage", None)
            if is_mine_entrance_tile(r, c) and "closed" not in tile:
                tile["closed"] = True
                changed = True
        if "mine_entrance_found" not in state:
            state["mine_entrance_found"] = False
            changed = True
        return changed
    day = int(state.get("day") or 1)
    hills["tiles"] = generate_hills_tiles(state, as_of_day=day, rules=rules)
    state["mine_entrance_found"] = bool(state.get("mine_entrance_found"))
    return True


def mark_entrance_found(state: dict, area: str, row: int, col: int) -> bool:
    if normalize_area(area) != AREA_HILLS or not is_mine_entrance_tile(row, col):
        return False
    if state.get("mine_entrance_found"):
        return False
    state["mine_entrance_found"] = True
    return True


def _grow_trees(state: dict, rules: dict | None = None, *, log: bool = True) -> list[str]:
    notes = []
    for r, c, tile in iter_hills_tiles(state):
        tree = tile.get("tree")
        if not isinstance(tree, dict) or tree.get("stage") not in TREE_STAGES:
            continue
        stage = tree["stage"]
        if stage == "grown":
            continue
        tree["days_grown"] = int(tree.get("days_grown") or 0) + 1
        needed = tree_days_for(stage, rules)
        if tree["days_grown"] >= needed:
            nxt = TREE_NEXT[stage]
            tree["stage"] = nxt
            tree["days_grown"] = 0
            if log:
                if nxt == "grown":
                    notes.append(f"A tree at hills row {r} col {c} has grown tall.")
                elif nxt == "sapling" and stage == "stump":
                    notes.append(f"A stump at hills row {r} col {c} has sent up a sapling.")
    return notes


def _spawn_forage(state: dict, rules: dict | None = None, *, log: bool = True) -> list[str]:
    from engine import season_for_day, load_crops

    notes = []
    crops = load_crops()
    day = int(state.get("day") or 1)
    season = state.get("season") or season_for_day(day, crops)
    kind = forage_kind_for_season(season)
    if not kind:
        return notes
    have = forage_count(state)
    cap = FORAGE_CAP
    cfg = hills_rules(rules)
    try:
        cap = max(1, int(cfg.get("forage_cap") or FORAGE_CAP))
    except (TypeError, ValueError):
        cap = FORAGE_CAP
    room = max(0, cap - have)
    if room <= 0:
        return notes
    seed = farm_seed(state)
    # 0–2 new plants, never more than the remaining cap.
    roll = _mix(seed, day, salt=0xF0A) % (FORAGE_MAX - FORAGE_MIN + 1)
    want = min(room, FORAGE_MIN + roll)
    if want <= 0:
        return notes
    candidates = []
    for r, c, tile in iter_hills_tiles(state):
        if not tile_is_hills_workable(tile):
            continue
        if has_tree(tile) or has_forage(tile):
            continue
        candidates.append((r, c))
    if not candidates:
        return notes
    ranked = sorted(candidates, key=lambda rc: _mix(seed, day, salt=0xF00 + rc[0] * 10 + rc[1]))
    placed = 0
    for r, c in ranked:
        if placed >= want:
            break
        # A second mix decides whether this empty tile actually sprouts,
        # so the same seed is reproducible without always filling the cap.
        chance = _mix(seed, day, salt=0xF11 + r * 10 + c) % 100
        if chance >= 70 and placed + (len(ranked) - ranked.index((r, c))) > want:
            continue
        get_hills_tile(state, r, c)["forage"] = make_forage(kind, day)
        placed += 1
    if log and placed:
        noun = FORAGE_INFO[kind]["name"] if placed == 1 else FORAGE_INFO[kind]["name_plural"]
        notes.append(f"{placed} {noun} sprouted in the hills." if placed > 1 else f"A {noun} sprouted in the hills.")
    return notes


def tick_hills(state: dict, rules: dict | None = None) -> list[str]:
    """Day-turn growth and forage in the hills. Call after the new day is set."""
    if not hills_tiles(state):
        return []
    notes = []
    notes.extend(_grow_trees(state, rules, log=True))
    notes.extend(_spawn_forage(state, rules, log=True))
    return notes


def player_area(state: dict, player: str) -> str:
    from engine import player_slot

    slot = player_slot(state, player)
    return normalize_area(slot.get("area"))


def set_player_place(state: dict, player: str, area: str, row: int, col: int) -> None:
    from engine import player_slot, in_bounds, CABIN_ROW, CABIN_COL

    slot = player_slot(state, player)
    area = normalize_area(area)
    try:
        row, col = int(row), int(col)
    except (TypeError, ValueError):
        row, col = CABIN_ROW, CABIN_COL
        area = AREA_FARM
    if not in_bounds(row, col):
        row, col = CABIN_ROW, CABIN_COL
        area = AREA_FARM
    slot["area"] = area
    slot["row"] = row
    slot["col"] = col
    mark_entrance_found(state, area, row, col)


def migrate_player_places(state: dict, rules: dict | None = None) -> bool:
    from engine import known_players, player_slot, in_bounds, CABIN_ROW, CABIN_COL, max_energy

    changed = False
    cap_hp = max_hp(rules)
    for name in list((state.get("players") or {}).keys()) or list(known_players()):
        slot = player_slot(state, name)
        if "area" not in slot:
            slot["area"] = AREA_FARM
            changed = True
        else:
            area = normalize_area(slot.get("area"))
            if slot.get("area") != area:
                slot["area"] = area
                changed = True
        if "hp" not in slot or "hp_max" not in slot:
            slot.setdefault("hp_max", cap_hp)
            if "hp" not in slot:
                slot["hp"] = cap_hp
            changed = True
        try:
            slot["hp"] = max(0, min(int(slot.get("hp_max") or cap_hp), int(slot.get("hp"))))
            slot["hp_max"] = int(slot.get("hp_max") or cap_hp)
        except (TypeError, ValueError):
            slot["hp"] = cap_hp
            slot["hp_max"] = cap_hp
            changed = True
        try:
            row = int(slot.get("row") or 0)
            col = int(slot.get("col") or 0)
        except (TypeError, ValueError):
            row, col = 0, 0
        if not in_bounds(row, col):
            slot["row"], slot["col"], slot["area"] = CABIN_ROW, CABIN_COL, AREA_FARM
            changed = True
    return changed


def max_hp(rules: dict | None = None) -> int:
    from engine import load_rules

    rules = rules or load_rules()
    try:
        return max(1, int(rules.get("max_hp") or 100))
    except (TypeError, ValueError):
        return 100


def hp_faint_energy(rules: dict | None = None) -> int:
    from engine import load_rules

    rules = rules or load_rules()
    try:
        return max(0, int(rules.get("hp_faint_energy") or 25))
    except (TypeError, ValueError):
        return 25


def player_hp(state: dict, player: str, rules: dict | None = None) -> tuple[int, int]:
    from engine import player_slot

    slot = player_slot(state, player)
    cap = int(slot.get("hp_max") or max_hp(rules))
    try:
        hp = int(slot.get("hp"))
    except (TypeError, ValueError):
        hp = cap
    return max(0, min(cap, hp)), cap


def heal_hp(state: dict, player: str, amount: int, rules: dict | None = None) -> int:
    """Restore HP, capped at max. Returns the amount actually healed."""
    from engine import player_slot

    slot = player_slot(state, player)
    hp, cap = player_hp(state, player, rules)
    gained = max(0, min(int(amount), cap - hp))
    slot["hp"] = hp + gained
    slot["hp_max"] = cap
    return gained


def path_places(src_area: str, src: tuple[int, int], dest_area: str, dest: tuple[int, int]) -> list[tuple[str, int, int]]:
    """Shortest path of places, including one area crossing at the cabin gate."""
    from engine import path_steps, CABIN_ROW, CABIN_COL

    src_area = normalize_area(src_area)
    dest_area = normalize_area(dest_area)
    if src_area == dest_area:
        return [(src_area, r, c) for r, c in path_steps(src, dest)]
    # Only the cabin ↔ hills r3c3 crossing is legal in Phase 1.
    if src_area == AREA_FARM and dest_area == AREA_HILLS:
        to_cabin = path_steps(src, (CABIN_ROW, CABIN_COL))
        places = [(AREA_FARM, r, c) for r, c in to_cabin]
        if dest == HILLS_GATE:
            places.append((AREA_HILLS, HILLS_GATE[0], HILLS_GATE[1]))
            return places
        places.append((AREA_HILLS, HILLS_GATE[0], HILLS_GATE[1]))
        places.extend((AREA_HILLS, r, c) for r, c in path_steps(HILLS_GATE, dest))
        return places
    if src_area == AREA_HILLS and dest_area == AREA_FARM:
        to_gate = path_steps(src, HILLS_GATE)
        places = [(AREA_HILLS, r, c) for r, c in to_gate]
        places.append((AREA_FARM, CABIN_ROW, CABIN_COL))
        if dest != (CABIN_ROW, CABIN_COL):
            places.extend((AREA_FARM, r, c) for r, c in path_steps((CABIN_ROW, CABIN_COL), dest))
        return places
    return []


def area_crossing(area: str, row: int, col: int, direction: str) -> tuple[str, int, int] | None:
    """If this step leaves the area, return the landing place; else None."""
    from engine import CABIN_ROW, CABIN_COL

    direction = normalize_direction(direction)
    area = normalize_area(area)
    if area == AREA_FARM and (row, col) == (CABIN_ROW, CABIN_COL) and direction == "up":
        return (AREA_HILLS, HILLS_GATE[0], HILLS_GATE[1])
    if area == AREA_HILLS and (row, col) == HILLS_GATE and direction == "down":
        return (AREA_FARM, CABIN_ROW, CABIN_COL)
    return None


def area_title(area: str | None) -> str:
    area = normalize_area(area)
    return "the hills" if area == AREA_HILLS else "the farm"


def describe_place(area: str, row: int, col: int) -> str:
    from engine import CABIN_ROW, CABIN_COL, position_name

    area = normalize_area(area)
    if is_cabin_place(area, row, col):
        return "the cabin"
    here = position_name(row, col)
    if area == AREA_HILLS:
        if is_mine_entrance_tile(row, col):
            return f"the mine entrance ({here} in the hills)"
        return f"{here} in the hills"
    return here


def describe_where(area: str, row: int, col: int) -> str:
    from engine import position_name

    area = normalize_area(area)
    if is_cabin_place(area, row, col):
        return "in the cabin"
    here = position_name(row, col)
    if area == AREA_HILLS:
        if is_mine_entrance_tile(row, col):
            return f"at the mine entrance ({here} in the hills)"
        return f"at {here} in the hills"
    return f"at {here}"


def tree_label(stage: str | None) -> str:
    return {
        "sapling": "a sapling",
        "young": "a young tree",
        "grown": "a grown tree",
        "stump": "a stump",
    }.get(stage or "", "a tree")


def forage_label(kind: str | None, count: int = 1) -> str:
    info = FORAGE_INFO.get(kind or "") or {}
    if count == 1:
        return info.get("name") or (kind or "forage").replace("_", " ")
    return info.get("name_plural") or (forage_label(kind, 1) + "s")


def describe_hills_tile(state: dict, row: int, col: int, weather: str | None = None) -> str:
    from sprites import sprite_key
    from engine import position_name, display_name, players_at

    tile = get_hills_tile(state, row, col)
    here = position_name(row, col)
    key = sprite_key(tile, weather or state.get("weather"), row, col)
    who_here = players_at(state, row, col, area=AREA_HILLS)
    who_bit = ""
    if who_here:
        names = ", ".join(display_name(n) for n in who_here)
        who_bit = f" {names} standing here."
    if tile.get("type") == "mine_entrance":
        hint = (
            "A boarded mine entrance is set into the hill. "
            "The way in isn't open yet — a pickaxe would be needed, later."
        )
        if state.get("mine_entrance_found"):
            hint = (
                "The boarded mine entrance you found is still shut. "
                "The way in isn't open yet."
            )
        return f"  {here} in the hills — {hint}{who_bit} (sprite: {key})"
    bits = []
    typ = "hillside" if tile.get("type") == "hillside" else "grassy hillside"
    if has_tree(tile):
        stage = tile["tree"]["stage"]
        bits.append(tree_label(stage))
        if stage == "grown":
            bits.append("ready to chop")
    if has_forage(tile):
        bits.append(f"a {forage_label(tile['forage']['kind'])} to forage")
    if not bits:
        body = f"{typ}. Empty."
    else:
        body = typ + ". " + ", ".join(bits) + "."
    return f"  {here} in the hills — {body}{who_bit} (sprite: {key})"


def hills_summary(state: dict) -> str:
    if not hills_tiles(state):
        return "The hills have not been reached yet."
    grown = 0
    other_trees = 0
    forage = []
    for _r, _c, tile in iter_hills_tiles(state):
        if has_grown_tree(tile):
            grown += 1
        elif has_tree(tile):
            other_trees += 1
        if has_forage(tile):
            forage.append(tile["forage"]["kind"])
    bits = []
    if grown == 1:
        bits.append("1 grown tree ready to chop")
    elif grown:
        bits.append(f"{grown} grown trees ready to chop")
    if other_trees == 1:
        bits.append("1 younger tree still growing")
    elif other_trees:
        bits.append(f"{other_trees} younger trees still growing")
    if forage:
        counts: dict[str, int] = {}
        for kind in forage:
            counts[kind] = counts.get(kind, 0) + 1
        parts = []
        for kind, n in counts.items():
            parts.append(f"{n} {forage_label(kind, n)}" if n > 1 else f"a {forage_label(kind)}")
        bits.append("forage available (" + ", ".join(parts) + ")")
    if not bits:
        bits.append("quiet grass and hillside, nothing ready to take")
    mouth = "The mine entrance is boarded."
    if state.get("mine_entrance_found"):
        mouth = "The boarded mine entrance has been found; the way in isn't open yet."
    return "The hills: " + "; ".join(bits) + ". " + mouth


def farm_summary(state: dict, crops: dict | None = None) -> str:
    from engine import (
        iter_tiles,
        crop_can_be_harvested,
        crop_info,
        crop_is_dormant,
        load_crops,
        tile_has_weed,
    )

    crops = crops or load_crops()
    ready = 0
    thirsty = 0
    weeds = 0
    planted = 0
    for _r, _c, tile in iter_tiles(state):
        if tile.get("type") == "cabin":
            continue
        if tile_has_weed(tile):
            weeds += 1
        crop = tile.get("crop")
        if not crop or not crop.get("kind"):
            if tile.get("tilled") and not tile.get("watered"):
                thirsty += 1
            continue
        planted += 1
        info = crop_info(crops, crop.get("kind")) or {}
        if crop_can_be_harvested(crop, info, state, crops):
            ready += 1
        dormant = crop_is_dormant(crop, info, state.get("season"))
        if not tile.get("watered") and not dormant and crop.get("stage") != "withered":
            thirsty += 1
    bits = []
    if ready == 1:
        bits.append("1 crop ready to harvest")
    elif ready:
        bits.append(f"{ready} crops ready to harvest")
    if thirsty == 1:
        bits.append("1 plot needs water")
    elif thirsty:
        bits.append(f"{thirsty} plots need water")
    if weeds == 1:
        bits.append("1 weed to pluck")
    elif weeds:
        bits.append(f"{weeds} weeds to pluck")
    if not bits:
        if planted:
            bits.append("crops growing, nothing urgent")
        else:
            bits.append("quiet plots, nothing urgent")
    return "The farm: " + ", ".join(bits) + "."


def exit_summary(area: str) -> str:
    area = normalize_area(area)
    if area == AREA_HILLS:
        return "Walk south from the bottom-right hill (row 3 col 3) to return to the cabin."
    return "Walk north from the cabin to reach the hills (bottom-right, row 3 col 3)."


def elsewhere_lines(state: dict, viewer: str | None, crops: dict | None = None) -> list[str]:
    from engine import known_players, display_name, player_where, player_slot

    lines = ["Elsewhere:"]
    view_area = player_area(state, viewer) if viewer else AREA_FARM
    if view_area == AREA_FARM:
        lines.append("  " + hills_summary(state))
    else:
        lines.append("  " + farm_summary(state, crops))
    lines.append("  " + exit_summary(view_area))
    for name in known_players():
        if viewer and name == viewer:
            continue
        area = player_area(state, name)
        row, col = player_where(state, name)
        lines.append(f"  {display_name(name)} is {describe_where(area, row, col)}.")
    return lines


def map_cell_lines(tile: dict) -> tuple[str, str]:
    """Two short mini-map lines for a hills tile. Labels fit 10 chars."""
    typ = tile.get("type")
    if typ == "mine_entrance":
        return "MINE", "boarded"
    top = "hillside" if typ == "hillside" else "grass"
    bot = ""
    tree = tile.get("tree") if isinstance(tile.get("tree"), dict) else None
    forage = tile.get("forage") if isinstance(tile.get("forage"), dict) else None
    if tree and tree.get("stage"):
        top = {
            "sapling": "sapling",
            "young": "young tree",
            "grown": "TREE",
            "stump": "stump",
        }.get(tree["stage"], "tree")
    if forage and forage.get("kind"):
        bot = {
            "wild_onion": "onion",
            "wild_berry": "berry",
            "wild_mushroom": "mushroom",
        }.get(forage["kind"], "forage")
    if not bot:
        bot = "slope" if typ == "hillside" else "path"
    return top, bot


def chop(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import (
        display_name,
        player_where,
        energy_cost,
        player_slot,
        log_append,
        who,
    )
    from inventory import pack_has, TOOL_AXE, pack_space_for, add_to_pack, sync_inventory_view

    rules = rules or None
    area = player_area(state, player)
    row, col = player_where(state, player)
    if area != AREA_HILLS:
        return False, "There are no trees to chop on the farm. Walk north from the cabin to the hills."
    tile = get_hills_tile(state, row, col)
    if not has_grown_tree(tile):
        if has_tree(tile):
            stage = tile["tree"]["stage"]
            if stage == "stump":
                return False, "That's a stump. It will send up a sapling if you leave it."
            return False, f"This tree is still {stage}. Wait for it to grow."
        return False, "There is no grown tree here to chop."
    if not pack_has(state, player, TOOL_AXE, 1, rules):
        return False, (
            f"{display_name(player)} needs an axe in their backpack to chop. "
            "Take one from the cabin chest."
        )
    wood_n = chop_wood_count(rules)
    if not pack_space_for(state, player, "wood", wood_n, rules):
        return False, "No room in the backpack for the wood. Drop something at the cabin first."
    leftover = add_to_pack(state, player, "wood", wood_n, rules)
    if leftover:
        return False, "No room in the backpack for the wood. Drop something at the cabin first."
    sync_inventory_view(state, rules)
    tile["tree"] = make_tree("stump", planted_day=int(state.get("day") or 1), days_grown=0)
    msg = (
        f"{who(player, 'chop', 'chops')} the tree at {describe_place(area, row, col)} "
        f"and pack {wood_n} wood."
    )
    log_append(state, msg, player)
    return True, msg


def forage(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, log_append, who, display_name
    from inventory import pack_space_for, add_to_pack, sync_inventory_view

    area = player_area(state, player)
    row, col = player_where(state, player)
    if area != AREA_HILLS:
        return False, "There's nothing wild to forage on the farm plots. Try the hills."
    tile = get_hills_tile(state, row, col)
    if not has_forage(tile):
        return False, "There's nothing to forage here."
    kind = tile["forage"]["kind"]
    if not pack_space_for(state, player, kind, 1, rules):
        return False, "No room in the backpack. Drop something at the cabin first."
    leftover = add_to_pack(state, player, kind, 1, rules)
    if leftover:
        return False, "No room in the backpack. Drop something at the cabin first."
    sync_inventory_view(state, rules)
    tile["forage"] = None
    label = forage_label(kind)
    msg = f"{who(player, 'forage', 'forages')} a {label} at {describe_place(area, row, col)}."
    log_append(state, msg, player)
    return True, msg


def migrate_hills(state: dict, rules: dict | None = None) -> bool:
    """Idempotent hills + HP + area fields. Does not touch farm tiles or gold."""
    changed = False
    if ensure_hills(state, rules):
        changed = True
    if migrate_player_places(state, rules):
        changed = True
    if "mine_entrance_found" not in state:
        state["mine_entrance_found"] = False
        changed = True
    return changed


def faint_from_hp(state: dict, player: str, rules: dict | None = None) -> str:
    """Wake at the mine entrance with hp_faint_energy and full HP. Pack is kept."""
    from engine import player_slot, display_name, log_append, max_energy

    set_player_place(state, player, AREA_HILLS, MINE_ENTRANCE[0], MINE_ENTRANCE[1])
    slot = player_slot(state, player)
    cap = max_hp(rules)
    energy = hp_faint_energy(rules)
    slot["energy"] = energy
    slot["hp"] = cap
    slot["hp_max"] = cap
    msg = (
        f"{display_name(player)} passes out from their wounds and wakes at the "
        f"mine entrance with {energy} energy and full HP."
    )
    log_append(state, msg, player)
    return msg

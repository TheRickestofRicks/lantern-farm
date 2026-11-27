"""Hills area, trees, forage, and area-aware places for Lantern Farm.

Phase 1 of docs/plan-hills-and-mine.md. Phase 2 opens the mine mouth.
"""

from __future__ import annotations

AREA_FARM = "farm"
AREA_HILLS = "hills"
AREA_MINE = "mine"
AREA_CABIN = "cabin"
AREA_TOWN = "town"
AREAS = (AREA_FARM, AREA_HILLS, AREA_MINE, AREA_CABIN, AREA_TOWN)

HILLS_ROWS = 3
HILLS_COLS = 3
HILLS_GATE = (3, 3)  # bottom-right, connects to the cabin
MINE_ENTRANCE = (1, 2)  # north-centre, boarded in Phase 1

TREE_STAGES = ("sapling", "young", "grown", "stump", "mushroom_log")
TREE_NEXT = {
    "sapling": "young",
    "young": "grown",
    "stump": "sapling",
}
# Days spent in a stage before it advances. Grown stays until chopped.
# mushroom_log ticks forage separately and does not use TREE_NEXT.
DEFAULT_TREE_DAYS = {
    "sapling": 3,
    "young": 4,
    "stump": 4,
}
DEFAULT_LOG_FORAGE_DAYS = 3
STUMP_LOG_SALT = 0x10C
STUMP_LOG_CHANCE = 3  # 1 in 3 stumps become a mushroom log
CHOP_WOOD = 2
UNEARTH_STUMP_WOOD = 1  # plain stumps only; mushroom logs give no wood
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
    "oyster_mushroom": {
        "name": "oyster mushroom",
        "name_plural": "oyster mushrooms",
        "seasons": ("spring", "summer", "autumn"),
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
    """Farm cabin tile or anywhere inside the cabin interior."""
    from engine import CABIN_ROW, CABIN_COL

    area = normalize_area(area)
    if area == AREA_CABIN:
        return True
    return area == AREA_FARM and int(row) == CABIN_ROW and int(col) == CABIN_COL


def hills_rules(rules: dict | None = None) -> dict:
    from engine import load_rules

    rules = rules or load_rules()
    cfg = rules.get("hills") if isinstance(rules, dict) else None
    return cfg if isinstance(cfg, dict) else {}


def log_forage_days(rules: dict | None = None) -> int:
    cfg = hills_rules(rules)
    try:
        return max(1, int(cfg.get("log_forage_days") or DEFAULT_LOG_FORAGE_DAYS))
    except (TypeError, ValueError):
        return int(DEFAULT_LOG_FORAGE_DAYS)


def stump_becomes_log(state: dict, row: int, col: int, day: int | None = None) -> bool:
    """Exclusive daily roll: True if this stump becomes a mushroom log."""
    seed = farm_seed(state)
    if day is None:
        try:
            day = int(state.get("day") or 1)
        except (TypeError, ValueError):
            day = 1
    salt = STUMP_LOG_SALT + int(row) * 10 + int(col)
    return _mix(seed, int(day), salt=salt) % STUMP_LOG_CHANCE == 0


def can_unearth_hills_tile(tile: dict | None) -> bool:
    tree = (tile or {}).get("tree")
    return bool(isinstance(tree, dict) and tree.get("stage") in {"stump", "mushroom_log"})


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


def log_forage_kind_for_season(season: str | None) -> str | None:
    """Oyster mushrooms on logs, or None if they do not fruit this season."""
    key = (season or "").strip().lower()
    info = FORAGE_INFO.get("oyster_mushroom") or {}
    if key in (info.get("seasons") or ()):
        return "oyster_mushroom"
    return None


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


def finish_pending_tree_growth(tile: dict | None, rules: dict | None = None) -> bool:
    """Advance sapling/young trees that already have enough days in their stage.

    Dawn growth adds a day and then advances. This only repairs a tree whose
    days already met the threshold without the stage being updated, so a
    'grown tall' tree is always choppable. Stumps still wait for the dawn roll.
    Returns True if the tree is grown afterwards.
    """
    if not has_tree(tile):
        return False
    tree = tile["tree"]
    while tree.get("stage") in {"sapling", "young"}:
        stage = tree["stage"]
        needed = tree_days_for(stage, rules)
        if int(tree.get("days_grown") or 0) < needed:
            break
        tree["stage"] = TREE_NEXT[stage]
        tree["days_grown"] = 0
    return has_grown_tree(tile)


def has_forage(tile: dict | None) -> bool:
    forage = (tile or {}).get("forage")
    return bool(isinstance(forage, dict) and forage.get("kind"))


def forage_count(state: dict) -> int:
    return sum(1 for _r, _c, tile in iter_hills_tiles(state) if has_forage(tile))


def make_tree(
    stage: str,
    planted_day: int = 1,
    days_grown: int = 0,
    log_placed_day: int | None = None,
) -> dict:
    tree = {
        "stage": stage,
        "planted_day": int(planted_day),
        "days_grown": int(days_grown),
    }
    if log_placed_day is not None:
        tree["log_placed_day"] = int(log_placed_day)
    return tree


def log_lifetime_days(crops: dict | None = None) -> int:
    """Mushroom logs last one in-game year (days_per_season × the four seasons)."""
    from engine import days_per_year

    return max(1, int(days_per_year(crops)))


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
    from engine import season_for_day, load_crops

    notes = []
    day = int(state.get("day") or 1)
    season = state.get("season") or season_for_day(day, load_crops())
    for r, c, tile in iter_hills_tiles(state):
        tree = tile.get("tree")
        if not isinstance(tree, dict) or tree.get("stage") not in TREE_STAGES:
            continue
        stage = tree["stage"]
        if stage == "grown":
            continue
        if stage == "mushroom_log":
            if tree.get("log_placed_day") is None:
                tree["log_placed_day"] = day
            try:
                placed = int(tree.get("log_placed_day") or day)
            except (TypeError, ValueError):
                placed = day
                tree["log_placed_day"] = day
            lifetime = log_lifetime_days(load_crops())
            if day >= placed + lifetime:
                tile["tree"] = None
                tile["forage"] = None
                if log:
                    notes.append(
                        f"A mushroom log at hills row {r} col {c} has finished its year "
                        "and the ground is grass again."
                    )
                continue
            tree["days_grown"] = int(tree.get("days_grown") or 0) + 1
            needed = log_forage_days(rules)
            kind = log_forage_kind_for_season(season)
            if kind and tree["days_grown"] >= needed and not has_forage(tile):
                tile["forage"] = make_forage(kind, day)
                tree["days_grown"] = 0
                if log:
                    notes.append(
                        f"Oyster mushrooms sprouted on a log at hills row {r} col {c}."
                    )
            continue
        tree["days_grown"] = int(tree.get("days_grown") or 0) + 1
        needed = tree_days_for(stage, rules)
        if tree["days_grown"] < needed:
            continue
        if stage == "stump":
            if stump_becomes_log(state, r, c, day):
                tree["stage"] = "mushroom_log"
                tree["days_grown"] = 0
                tree["log_placed_day"] = day
                if log:
                    notes.append(f"A stump at hills row {r} col {c} has become a mushroom log.")
            else:
                tree["stage"] = "sapling"
                tree["days_grown"] = 0
                if log:
                    notes.append(f"A stump at hills row {r} col {c} has sent up a sapling.")
            continue
        nxt = TREE_NEXT[stage]
        tree["stage"] = nxt
        tree["days_grown"] = 0
        if log and nxt == "grown":
            notes.append(f"A tree at hills row {r} col {c} has grown tall.")
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


def set_player_place(
    state: dict,
    player: str,
    area: str,
    row: int,
    col: int,
    floor: int | None = None,
) -> None:
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
    if area == AREA_MINE:
        try:
            slot["floor"] = max(1, int(floor or slot.get("floor") or 1))
        except (TypeError, ValueError):
            slot["floor"] = 1
    else:
        slot.pop("floor", None)
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


def away_hp_restore_cap(rules: dict | None = None) -> int:
    """Max HP restored by a sleeping bag or a mid-day faint (cabin sleep is full)."""
    from engine import load_rules

    rules = rules or load_rules()
    try:
        return max(0, int(rules.get("away_hp_restore_cap") or 50))
    except (TypeError, ValueError):
        return 50


def restore_hp_after_rest(
    state: dict,
    player: str,
    rules: dict | None = None,
    *,
    in_cabin: bool,
    used_bag: bool,
) -> None:
    """Cabin sleep fills HP. A sleeping bag restores up to away_hp_restore_cap, never lowering it."""
    from engine import player_slot

    slot = player_slot(state, player)
    hp, cap = player_hp(state, player, rules)
    if in_cabin:
        slot["hp"] = cap
        slot["hp_max"] = cap
        return
    if used_bag:
        limit = min(cap, away_hp_restore_cap(rules))
        if hp < limit:
            slot["hp"] = limit
        slot["hp_max"] = cap


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


def hurt_hp(state: dict, player: str, amount: int, rules: dict | None = None) -> int:
    """Deal HP damage, floored at 0. Returns the amount actually lost."""
    from engine import player_slot

    slot = player_slot(state, player)
    hp, cap = player_hp(state, player, rules)
    lost = max(0, min(int(amount), hp))
    slot["hp"] = hp - lost
    slot["hp_max"] = cap
    return lost


def path_places(src_area: str, src: tuple[int, int], dest_area: str, dest: tuple[int, int]) -> list[tuple[str, int, int]]:
    """Shortest path of places, including one area crossing at the cabin gate."""
    from engine import path_steps, CABIN_ROW, CABIN_COL

    src_area = normalize_area(src_area)
    dest_area = normalize_area(dest_area)
    if src_area == AREA_MINE or dest_area == AREA_MINE:
        return []
    if src_area == AREA_CABIN or dest_area == AREA_CABIN:
        # Enter and leave the interior through the door; don't path across it.
        return []
    if src_area == dest_area:
        return [(src_area, r, c) for r, c in path_steps(src, dest)]
    from town import TOWN_ENTRANCE, AREA_TOWN as _TOWN
    # Cabin tile ↔ town entrance, possibly chained through the cabin for hills ↔ town.
    if src_area == AREA_FARM and dest_area == _TOWN:
        to_cabin = path_steps(src, (CABIN_ROW, CABIN_COL))
        places = [(AREA_FARM, r, c) for r, c in to_cabin]
        places.append((_TOWN, TOWN_ENTRANCE[0], TOWN_ENTRANCE[1]))
        if dest != TOWN_ENTRANCE:
            places.extend((_TOWN, r, c) for r, c in path_steps(TOWN_ENTRANCE, dest))
        return places
    if src_area == _TOWN and dest_area == AREA_FARM:
        to_gate = path_steps(src, TOWN_ENTRANCE)
        places = [(_TOWN, r, c) for r, c in to_gate]
        places.append((AREA_FARM, CABIN_ROW, CABIN_COL))
        if dest != (CABIN_ROW, CABIN_COL):
            places.extend((AREA_FARM, r, c) for r, c in path_steps((CABIN_ROW, CABIN_COL), dest))
        return places
    if src_area == AREA_HILLS and dest_area == _TOWN:
        via_cabin = path_places(src_area, src, AREA_FARM, (CABIN_ROW, CABIN_COL))
        onward = path_places(AREA_FARM, (CABIN_ROW, CABIN_COL), _TOWN, dest)
        return via_cabin + onward
    if src_area == _TOWN and dest_area == AREA_HILLS:
        via_cabin = path_places(src_area, src, AREA_FARM, (CABIN_ROW, CABIN_COL))
        onward = path_places(AREA_FARM, (CABIN_ROW, CABIN_COL), AREA_HILLS, dest)
        return via_cabin + onward
    # Cabin ↔ hills r3c3 crossing.
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
    from town import TOWN_ENTRANCE, AREA_TOWN as _TOWN
    if area == AREA_FARM and (row, col) == (CABIN_ROW, CABIN_COL) and direction == "right":
        return (_TOWN, TOWN_ENTRANCE[0], TOWN_ENTRANCE[1])
    if area == _TOWN and (row, col) == TOWN_ENTRANCE and direction == "left":
        return (AREA_FARM, CABIN_ROW, CABIN_COL)
    return None


def area_title(area: str | None, floor: int | None = None) -> str:
    area = normalize_area(area)
    if area == AREA_HILLS:
        return "the hills"
    if area == AREA_MINE:
        if floor:
            return f"the mine, floor {int(floor)}"
        return "the mine"
    if area == AREA_CABIN:
        return "the cabin"
    if area == AREA_TOWN:
        return "the market town"
    return "the farm"


def describe_place(area: str, row: int, col: int, floor: int | None = None) -> str:
    from engine import CABIN_ROW, CABIN_COL, position_name

    area = normalize_area(area)
    if area == AREA_CABIN:
        from cabin import describe_cabin_place
        return describe_cabin_place(row, col)
    if is_cabin_place(area, row, col):
        return "the cabin"
    here = position_name(row, col)
    if area == AREA_HILLS:
        if is_mine_entrance_tile(row, col):
            return f"the mine entrance ({here} in the hills)"
        return f"{here} in the hills"
    if area == AREA_MINE:
        if floor:
            return f"{here} on mine floor {int(floor)}"
        return f"{here} in the mine"
    if area == AREA_TOWN:
        from town import TOWN_STALL, TOWN_STORE, TOWN_FORGE, TOWN_ENTRANCE
        if (row, col) == TOWN_STALL:
            return f"the market stall ({here} in town)"
        if (row, col) == TOWN_STORE:
            return f"the honour store ({here} in town)"
        if (row, col) == TOWN_FORGE:
            return f"the town forge ({here} in town)"
        if (row, col) == TOWN_ENTRANCE:
            return f"the town entrance ({here} in town)"
        return f"{here} in town"
    return here


def describe_where(area: str, row: int, col: int, floor: int | None = None) -> str:
    from engine import position_name

    area = normalize_area(area)
    if area == AREA_CABIN:
        from cabin import describe_cabin_where
        return describe_cabin_where(row, col)
    if is_cabin_place(area, row, col):
        return "in the cabin"
    here = position_name(row, col)
    if area == AREA_HILLS:
        if is_mine_entrance_tile(row, col):
            return f"at the mine entrance ({here} in the hills)"
        return f"at {here} in the hills"
    if area == AREA_MINE:
        if floor:
            return f"at {here} on mine floor {int(floor)}"
        return f"at {here} in the mine"
    if area == AREA_TOWN:
        from town import TOWN_STALL, TOWN_STORE, TOWN_FORGE, TOWN_ENTRANCE
        if (row, col) == TOWN_STALL:
            return f"at the market stall ({here} in town)"
        if (row, col) == TOWN_STORE:
            return f"at the honour store ({here} in town)"
        if (row, col) == TOWN_FORGE:
            return f"at the town forge ({here} in town)"
        if (row, col) == TOWN_ENTRANCE:
            return f"at the town entrance ({here} in town)"
        return f"at {here} in town"
    return f"at {here}"


def tree_label(stage: str | None) -> str:
    return {
        "sapling": "a sapling",
        "young": "a young tree",
        "grown": "a grown tree",
        "stump": "a stump",
        "mushroom_log": "a mushroom log",
    }.get(stage or "", "a tree")


def forage_label(kind: str | None, count: int = 1) -> str:
    info = FORAGE_INFO.get(kind or "") or {}
    if count == 1:
        return info.get("name") or (kind or "forage").replace("_", " ")
    return info.get("name_plural") or (forage_label(kind, 1) + "s")


def describe_hills_tile(state: dict, row: int, col: int, weather: str | None = None) -> str:
    from sprites import sprite_key
    from engine import position_name, display_name, players_at
    from inventory import ground_look_phrase

    tile = get_hills_tile(state, row, col)
    here = position_name(row, col)
    key = sprite_key(tile, weather or state.get("weather"), row, col)
    who_here = players_at(state, row, col, area=AREA_HILLS)
    who_bit = ""
    if who_here:
        names = ", ".join(display_name(n) for n in who_here)
        who_bit = f" {names} standing here."
    if tile.get("type") == "mine_entrance":
        from mine import is_entrance_open
        if is_entrance_open(state) or tile.get("closed") is False:
            hint = "The mine entrance is open. Enter the mine from here."
        elif state.get("mine_entrance_found"):
            hint = (
                "The boarded mine entrance you found is still shut. "
                "Buy a pickaxe from the honour store in town, then enter mine to pry it open."
            )
        else:
            hint = (
                "A boarded mine entrance is set into the hill. "
                "The way in isn't open yet — a pickaxe would be needed."
            )
        return f"  {here} in the hills — {hint}{ground_look_phrase(state, AREA_HILLS, row, col)}{who_bit} (sprite: {key})"
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
    from inventory import ground_look_phrase
    return f"  {here} in the hills — {body}{ground_look_phrase(state, AREA_HILLS, row, col)}{who_bit} (sprite: {key})"


def hills_summary(state: dict) -> str:
    if not hills_tiles(state):
        return "The hills have not been reached yet."
    grown = 0
    other_trees = 0
    forage = []
    for _r, _c, tile in iter_hills_tiles(state):
        finish_pending_tree_growth(tile)
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
    from mine import is_entrance_open
    mouth = "The mine entrance is boarded."
    if is_entrance_open(state):
        mouth = "The mine entrance is open."
    elif state.get("mine_entrance_found"):
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
        return "Walk south from the bottom-right hill (row 3 col 3) to return to the cabin. The mine entrance is at row 1 col 2."
    if area == AREA_MINE:
        return "Climb up the shaft to the entrance, then walk home from the hills."
    if area == AREA_CABIN:
        return "Leave through the door at bottom-left (row 3 col 1) to step back onto the farm cabin tile."
    if area == AREA_TOWN:
        return (
            "Walk west from the town entrance (row 1 col 1) to return to the cabin. "
            "The stall is row 1 col 2, the honour store row 2 col 1, and the forge row 2 col 3."
        )
    return (
        "Walk north from the cabin to reach the hills (bottom-right, row 3 col 3). "
        "Walk east from the cabin to reach the market town (entrance row 1 col 1). "
        "Press E to step inside the cabin."
    )


def elsewhere_lines(state: dict, viewer: str | None, crops: dict | None = None) -> list[str]:
    from engine import known_players, display_name, player_where, player_slot
    from mine import mine_summary, player_floor

    lines = ["Elsewhere:"]
    view_area = player_area(state, viewer) if viewer else AREA_FARM
    from town import town_summary, AREA_TOWN as _TOWN
    if view_area == AREA_FARM:
        lines.append("  " + hills_summary(state))
        lines.append("  " + town_summary(state))
        lines.append("  " + mine_summary(state))
    elif view_area == AREA_HILLS:
        lines.append("  " + farm_summary(state, crops))
        lines.append("  " + town_summary(state))
        lines.append("  " + mine_summary(state))
    elif view_area == AREA_CABIN:
        from cabin import cabin_summary
        lines.append("  " + farm_summary(state, crops))
        lines.append("  " + hills_summary(state))
        lines.append("  " + town_summary(state))
        lines.append("  " + cabin_summary(state))
    elif view_area == _TOWN:
        lines.append("  " + farm_summary(state, crops))
        lines.append("  " + hills_summary(state))
        lines.append("  " + mine_summary(state))
    else:
        lines.append("  " + farm_summary(state, crops))
        lines.append("  " + hills_summary(state))
        lines.append("  " + town_summary(state))
    lines.append("  " + exit_summary(view_area))
    for name in known_players():
        if viewer and name == viewer:
            continue
        area = player_area(state, name)
        row, col = player_where(state, name)
        floor = player_floor(state, name) if area == AREA_MINE else None
        lines.append(f"  {display_name(name)} is {describe_where(area, row, col, floor=floor)}.")
    return lines


def map_cell_lines(tile: dict) -> tuple[str, str]:
    """Two short mini-map lines for a hills tile. Labels fit 10 chars."""
    typ = tile.get("type")
    if typ == "mine_entrance":
        if tile.get("closed") is False:
            return "MINE", "open"
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
            "mushroom_log": "log",
        }.get(tree["stage"], "tree")
    if forage and forage.get("kind"):
        bot = {
            "wild_onion": "onion",
            "wild_berry": "berry",
            "wild_mushroom": "mushroom",
            "oyster_mushroom": "oyster",
        }.get(forage["kind"], "forage")
    if not bot:
        bot = "slope" if typ == "hillside" else "path"
    return top, bot


def _gold_axe_splash(state: dict, player: str, row: int, col: int, rules: dict | None) -> str:
    from inventory import pack_space_for, add_to_pack, sync_inventory_view, TOOL_AXE
    from mine import yield_with_upgrade, tool_tier
    for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
        rr, cc = int(row) + dr, int(col) + dc
        if not (1 <= rr <= HILLS_ROWS and 1 <= cc <= HILLS_COLS):
            continue
        tile = get_hills_tile(state, rr, cc)
        if not has_grown_tree(tile):
            continue
        wood_n = yield_with_upgrade(state, TOOL_AXE, chop_wood_count(rules), rules)
        if not pack_space_for(state, player, "wood", wood_n, rules):
            return ""
        leftover = add_to_pack(state, player, "wood", wood_n, rules)
        if leftover:
            return ""
        sync_inventory_view(state, rules)
        tile["tree"] = make_tree("stump", planted_day=int(state.get("day") or 1), days_grown=0)
        return f", and the gold axe also chops the tree at {describe_place(AREA_HILLS, rr, cc)} for {wood_n} wood."
    return ""


def chop(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import (
        display_name,
        player_where,
        energy_cost,
        player_slot,
        log_append,
        who,
    )
    from inventory import pack_has, TOOL_AXE, pack_space_for, add_to_pack, sync_inventory_view, item_label, indefinite

    rules = rules or None
    area = player_area(state, player)
    row, col = player_where(state, player)
    if area != AREA_HILLS:
        return False, "There are no trees to chop on the farm. Walk north from the cabin to the hills."
    tile = get_hills_tile(state, row, col)
    finish_pending_tree_growth(tile, rules)
    if not has_grown_tree(tile):
        if has_tree(tile):
            stage = tile["tree"]["stage"]
            if stage == "stump":
                return False, (
                    "That's a stump. Leave it to send up a sapling or become a mushroom log, "
                    "or unearth it with a shovel for 1 wood."
                )
            if stage == "mushroom_log":
                return False, (
                    "That's a mushroom log. Leave it to grow oyster mushrooms, "
                    "or unearth it with a shovel."
                )
            return False, f"This tree is still {stage}. Wait for it to grow."
        return False, "There is no grown tree here to chop."
    if not pack_has(state, player, TOOL_AXE, 1, rules):
        return False, (
            f"{display_name(player)} needs {indefinite(item_label(TOOL_AXE, state=state))} in their backpack to chop. "
            "Take one from the cabin chest."
        )
    from mine import yield_with_upgrade
    from inventory import TOOL_AXE
    wood_n = yield_with_upgrade(state, TOOL_AXE, chop_wood_count(rules), rules)
    from inventory import give_or_drop_at_player
    packed, dropped, phrase = give_or_drop_at_player(state, player, "wood", wood_n, rules)
    tile["tree"] = make_tree("stump", planted_day=int(state.get("day") or 1), days_grown=0)
    if dropped and not packed:
        msg = f"{who(player, 'chop', 'chops')} the tree at {describe_place(area, row, col)}. {phrase}"
    else:
        msg = (
            f"{who(player, 'chop', 'chops')} the tree at {describe_place(area, row, col)} "
            f"{phrase}."
        )
    from mine import tool_tier
    if player and tool_tier(state, TOOL_AXE) == "gold":
        extra = _gold_axe_splash(state, player, row, col, rules)
        if extra:
            msg = msg.rstrip(".") + extra
    log_append(state, msg, player)
    return True, msg


def unearth_hills(
    state: dict,
    player: str | None,
    rules: dict | None = None,
    row: int | None = None,
    col: int | None = None,
) -> tuple[bool, str]:
    """Dig up a stump or mushroom log, leaving plain grass that will not resprout."""
    from engine import (
        display_name,
        player_where,
        log_append,
        who,
        parse_row_col,
    )
    from inventory import pack_has, TOOL_SHOVEL

    area = player_area(state, player) if player else AREA_HILLS
    if area != AREA_HILLS:
        return False, "There's nothing to unearth here in the hills."
    if row is None or col is None:
        row, col = player_where(state, player)
    else:
        r, c, err = parse_row_col(row, col)
        if err:
            return False, err
        row, col = r, c
    tile = get_hills_tile(state, row, col)
    here = describe_place(AREA_HILLS, row, col)
    if not can_unearth_hills_tile(tile):
        return False, "There's nothing to unearth here in the hills."
    if player and not pack_has(state, player, TOOL_SHOVEL, 1, rules):
        return False, (
            f"{display_name(player)} needs a shovel in their backpack to unearth a stump. "
            "Take one from the cabin chest."
        )
    stage = tile["tree"]["stage"]
    label = "stump" if stage == "stump" else "mushroom log"
    extra = ""
    if has_forage(tile):
        extra = f" and the {forage_label(tile['forage']['kind'])}"
    tile["tree"] = None
    tile["forage"] = None
    msg = (
        f"{who(player, 'unearth', 'unearths')} the {label}{extra} at {here}, "
        "returning the ground to plain grass"
    )
    if stage == "stump":
        from inventory import give_or_drop_at_player
        packed, dropped, phrase = give_or_drop_at_player(
            state, player, "wood", UNEARTH_STUMP_WOOD, rules
        )
        if dropped and not packed:
            msg = f"{msg}. {phrase}"
        else:
            msg = f"{msg} {phrase}."
    else:
        msg = f"{msg}."
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
    from inventory import give_or_drop_at_player
    packed, dropped, phrase = give_or_drop_at_player(state, player, kind, 1, rules)
    tile["forage"] = None
    label = forage_label(kind)
    here = describe_place(area, row, col)
    if dropped and not packed:
        msg = f"{who(player, 'forage', 'forages')} a {label} at {here}. {phrase}"
    else:
        msg = f"{who(player, 'forage', 'forages')} a {label} at {here} {phrase}."
    log_append(state, msg, player)
    return True, msg


def migrate_mushroom_log_dates(state: dict) -> bool:
    """Give existing mushroom logs a placed day of today if they have none."""
    if not hills_tiles(state):
        return False
    try:
        today = int(state.get("day") or 1)
    except (TypeError, ValueError):
        today = 1
    changed = False
    for _r, _c, tile in iter_hills_tiles(state):
        tree = tile.get("tree")
        if not isinstance(tree, dict) or tree.get("stage") != "mushroom_log":
            continue
        if tree.get("log_placed_day") is not None:
            continue
        tree["log_placed_day"] = today
        changed = True
    return changed


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
    if migrate_mushroom_log_dates(state):
        changed = True
    from mine import migrate_mine
    if migrate_mine(state, rules):
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
    # Passing out from wounds caps restored HP; it never fills past the away cap.
    slot["hp"] = min(cap, away_hp_restore_cap(rules))
    slot["hp_max"] = cap
    msg = (
        f"{display_name(player)} passes out from their wounds and wakes at the "
        f"mine entrance with {energy} energy and full HP."
    )
    log_append(state, msg, player)
    return msg

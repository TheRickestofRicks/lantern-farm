"""Enterable 3x3 cabin interior for Lantern Farm.

See docs/plan-hills-and-mine.md. Layout (rows top to bottom, columns left
to right):

    (1,1) double bed    (1,2) chest         (1,3) empty floor
    (2,1) free floor    (2,2) Creation Table (2,3) fireplace
    (3,1) door          (3,2) kitchen       (3,3) free floor

The top-right floor tile is reserved for a buildable display case later.
Movement inside costs no energy. Being anywhere in the interior counts as
"in the cabin" for sleep and together rest.
"""

from __future__ import annotations

CABIN_ROWS = 3
CABIN_COLS = 3

CABIN_BED = (1, 1)
CABIN_CHEST = (1, 2)
CABIN_DISPLAY = (1, 3)  # reserved; stays plain floor in this pass
CABIN_TABLE = (2, 2)
CABIN_FIREPLACE = (2, 3)
CABIN_DOOR = (3, 1)
CABIN_KITCHEN = (3, 2)

# kind -> tile type used in view payloads and sprites
TILE_KIND = {
    CABIN_BED: "bed",
    CABIN_CHEST: "chest",
    CABIN_TABLE: "table",
    CABIN_FIREPLACE: "fireplace",
    CABIN_DOOR: "door",
    CABIN_KITCHEN: "kitchen",
}

KIND_LABEL = {
    "bed": "double bed",
    "chest": "chest",
    "table": "Creation Table",
    "fireplace": "fireplace",
    "door": "door",
    "kitchen": "kitchen",
    "floor": "floor",
}


def cabin_tile_kind(row: int, col: int, state: dict | None = None) -> str:
    """Furniture kind at this interior tile.

    The north-wall nook (1, 2) is the chest site. Until a chest is built it
    reads as floor; pass state so the sprite and walk descriptions match.
    Without state, the designated kind is returned (the reserved chest spot).
    """
    try:
        row, col = int(row), int(col)
    except (TypeError, ValueError):
        return "floor"
    kind = TILE_KIND.get((row, col), "floor")
    if kind == "chest" and state is not None:
        from chest import chest_is_built
        if not chest_is_built(state):
            return "floor"
    return kind


def is_cabin_interior(area: str | None) -> bool:
    from hills import AREA_CABIN, normalize_area

    return normalize_area(area) == AREA_CABIN


def is_farm_cabin_tile(area: str | None, row: int, col: int) -> bool:
    """True only for the cabin tile on the farm, not the interior."""
    from hills import AREA_FARM, normalize_area
    from engine import CABIN_ROW, CABIN_COL

    return normalize_area(area) == AREA_FARM and int(row) == CABIN_ROW and int(col) == CABIN_COL


def get_cabin_tile(state: dict, row: int, col: int) -> dict:
    from engine import fireplace_is_fueled, stove_is_fueled

    kind = cabin_tile_kind(row, col, state)
    tile = {"type": f"cabin_{kind}" if kind != "floor" else "cabin_floor"}
    if kind == "fireplace":
        tile["fire"] = bool(fireplace_is_fueled(state))
    elif kind == "kitchen":
        tile["fire"] = bool(stove_is_fueled(state))
    elif kind == "chest":
        from chest import chest_tier, chest_band_color
        tile["chest_tier"] = chest_tier(state)
        tile["chest_band"] = chest_band_color(state)
    return tile


def iter_cabin_tiles(state: dict):
    for row in range(1, CABIN_ROWS + 1):
        for col in range(1, CABIN_COLS + 1):
            yield row, col, get_cabin_tile(state, row, col)


def cabin_tiles(state: dict) -> list[list[dict]]:
    return [
        [get_cabin_tile(state, r, c) for c in range(1, CABIN_COLS + 1)]
        for r in range(1, CABIN_ROWS + 1)
    ]


def player_cabin_kind(state: dict, player: str | None) -> str | None:
    if not player:
        return None
    from hills import player_area
    from engine import player_where

    if not is_cabin_interior(player_area(state, player)):
        return None
    row, col = player_where(state, player)
    return cabin_tile_kind(row, col, state)


def player_at_cabin_tile(state: dict, player: str | None, kind: str) -> bool:
    return player_cabin_kind(state, player) == kind


def describe_cabin_place(row: int, col: int) -> str:
    from engine import position_name

    kind = cabin_tile_kind(row, col)
    label = KIND_LABEL.get(kind, "floor")
    here = position_name(row, col)
    if kind == "floor":
        return f"{here} in the cabin"
    return f"the {label} ({here} in the cabin)"


def describe_cabin_where(row: int, col: int) -> str:
    from engine import position_name

    kind = cabin_tile_kind(row, col)
    label = KIND_LABEL.get(kind, "floor")
    here = position_name(row, col)
    if kind == "floor":
        return f"at {here} in the cabin"
    if kind == "door":
        return f"at the door ({here} in the cabin)"
    return f"at the {label} ({here} in the cabin)"


def describe_cabin_tile(state: dict, row: int, col: int) -> str:
    from hills import AREA_CABIN
    from inventory import ground_look_phrase

    kind = cabin_tile_kind(row, col)
    place = describe_cabin_place(row, col)
    if kind == "bed":
        body = f"{place} — a double bed. Ending your turn anywhere inside is still cabin sleep."
    elif kind == "chest":
        body = f"{place} — the cabin chest. Open it from this tile."
    elif kind == "table":
        body = (
            f"{place} — the Creation Table. Craft runestones here any day; "
            "on an aurora night you can enchant a pickaxe or boots."
        )
    elif kind == "fireplace":
        from engine import fireplace_is_fueled

        if fireplace_is_fueled(state):
            body = f"{place} — the fireplace, already fueled for tonight."
        else:
            body = f"{place} — the fireplace. Fuel it from this tile."
    elif kind == "door":
        body = f"{place} — the door back out to the farm."
    elif kind == "kitchen":
        body = f"{place} — the kitchen. Cook from this tile."
    else:
        from creation import table_tile, table_is_built
        tr, tc = table_tile()
        if (int(row), int(col)) == (tr, tc) and not table_is_built(state):
            body = f"{place} — wooden floor, a clear space for a Creation Table (free to build)."
        else:
            body = f"{place} — wooden floor."
    return body + ground_look_phrase(state, AREA_CABIN, row, col)


def map_cell_lines(tile: dict) -> tuple[str, str]:
    typ = (tile or {}).get("type") or "cabin_floor"
    if typ == "cabin_bed":
        return "bed", ""
    if typ == "cabin_chest":
        return "chest", ""
    if typ == "cabin_fireplace":
        return "fire", "lit" if tile.get("fire") else ""
    if typ == "cabin_door":
        return "door", ""
    if typ == "cabin_table":
        return "table", ""
    if typ == "cabin_kitchen":
        return "kitchen", ""
    return "floor", ""


def cabin_summary(state: dict) -> str:
    from engine import fireplace_is_fueled, known_players, display_name, player_where
    from hills import player_area, AREA_CABIN

    bits = ["Inside the cabin: a 3x3 room. The door is bottom-left."]
    if fireplace_is_fueled(state):
        bits.append("The fireplace is fueled for tonight.")
    who = []
    for name in known_players():
        if player_area(state, name) == AREA_CABIN:
            row, col = player_where(state, name)
            who.append(f"{display_name(name)} is {describe_cabin_where(row, col)}")
    if who:
        bits.append("; ".join(who) + ".")
    return " ".join(bits)


def enter_cabin(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append
    from hills import player_area, set_player_place, AREA_CABIN, AREA_FARM

    area = player_area(state, player)
    row, col = player_where(state, player)
    if is_cabin_interior(area):
        return True, f"{display_name(player)} is already in the cabin."
    if not is_farm_cabin_tile(area, row, col):
        return False, "Enter the cabin from the cabin tile on the farm (top-right)."
    dest_r, dest_c = CABIN_DOOR
    set_player_place(state, player, AREA_CABIN, dest_r, dest_c)
    msg = (
        f"{display_name(player)} steps into the cabin and stands at "
        f"{describe_cabin_place(dest_r, dest_c)}."
    )
    log_append(state, msg, player)
    return True, msg


def leave_cabin(state: dict, player: str, rules: dict | None = None) -> tuple[bool, str]:
    from engine import player_where, display_name, log_append, CABIN_ROW, CABIN_COL
    from hills import player_area, set_player_place, AREA_FARM, AREA_CABIN

    area = player_area(state, player)
    row, col = player_where(state, player)
    if not is_cabin_interior(area):
        return False, "Leave the cabin through the door inside (bottom-left)."
    walked = cabin_tile_kind(row, col) != "door"
    if walked:
        # Moves inside the cabin are free, so walking to the door costs nothing.
        set_player_place(state, player, AREA_CABIN, CABIN_DOOR[0], CABIN_DOOR[1])
    set_player_place(state, player, AREA_FARM, CABIN_ROW, CABIN_COL)
    if walked:
        msg = f"{display_name(player)} walks to the door and leaves the cabin, standing at the doorstep."
    else:
        msg = f"{display_name(player)} leaves the cabin and stands at the doorstep."
    log_append(state, msg, player)
    return True, msg

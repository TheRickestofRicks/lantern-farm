"""East market town: stall, honour store, and forge for Lantern Farm."""

from __future__ import annotations

AREA_TOWN = "town"
TOWN_ROWS = 3
TOWN_COLS = 3
TOWN_ENTRANCE = (1, 1)  # grassy entry, east of the farm cabin tile
TOWN_STALL = (1, 2)
TOWN_STORE = (2, 1)
TOWN_FORGE = (2, 3)

TILE_GRASS = "town_grass"
TILE_STALL = "town_stall"
TILE_STORE = "town_store"
TILE_FORGE = "town_forge"

DEFAULT_INSTANT_SELL_ENERGY = 50

_FEATURE_TILES = {
    TOWN_STALL: TILE_STALL,
    TOWN_STORE: TILE_STORE,
    TOWN_FORGE: TILE_FORGE,
}


def town_rules(rules: dict | None = None) -> dict:
    from engine import load_rules

    rules = rules or load_rules()
    cfg = rules.get("town") if isinstance(rules, dict) else None
    return cfg if isinstance(cfg, dict) else {}


def instant_sell_energy(rules: dict | None = None) -> int:
    cfg = town_rules(rules)
    raw = cfg.get("instant_sell_energy", DEFAULT_INSTANT_SELL_ENERGY)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return int(DEFAULT_INSTANT_SELL_ENERGY)


def town_of(state: dict) -> dict:
    town = state.get("town")
    if not isinstance(town, dict):
        town = {}
        state["town"] = town
    return town


def town_tiles(state: dict) -> list | None:
    tiles = town_of(state).get("tiles")
    if (
        isinstance(tiles, list)
        and len(tiles) == TOWN_ROWS
        and all(isinstance(row, list) and len(row) == TOWN_COLS for row in tiles)
    ):
        return tiles
    return None


def generate_town_tiles() -> list[list[dict]]:
    tiles = []
    for r in range(1, TOWN_ROWS + 1):
        row = []
        for c in range(1, TOWN_COLS + 1):
            typ = _FEATURE_TILES.get((r, c), TILE_GRASS)
            row.append({"type": typ})
        tiles.append(row)
    return tiles


def ensure_town(state: dict, rules: dict | None = None) -> bool:
    """Create the east market town on a save that does not have it. Idempotent.

    Does not move players or change day, season, weather, gold, energy, or the turn.
    """
    del rules  # reserved for later town rules; layout is fixed
    town = town_of(state)
    tiles = town_tiles(state)
    changed = False
    if tiles is None:
        town["tiles"] = generate_town_tiles()
        changed = True
        tiles = town["tiles"]
    else:
        for r in range(1, TOWN_ROWS + 1):
            for c in range(1, TOWN_COLS + 1):
                tile = tiles[r - 1][c - 1]
                if not isinstance(tile, dict):
                    tiles[r - 1][c - 1] = {"type": _FEATURE_TILES.get((r, c), TILE_GRASS)}
                    changed = True
                    continue
                want = _FEATURE_TILES.get((r, c), TILE_GRASS)
                if tile.get("type") not in {TILE_GRASS, TILE_STALL, TILE_STORE, TILE_FORGE}:
                    tile["type"] = want
                    changed = True
    if "stall" not in town or not isinstance(town.get("stall"), list):
        town["stall"] = []
        changed = True
    return changed


def migrate_town(state: dict, rules: dict | None = None) -> bool:
    """Idempotent town fields. Does not touch farm tiles, gold, or the current turn."""
    return ensure_town(state, rules)


def get_town_tile(state: dict, row: int, col: int) -> dict:
    tiles = town_tiles(state)
    if not tiles:
        ensure_town(state)
        tiles = town_tiles(state)
    return tiles[int(row) - 1][int(col) - 1]


def iter_town_tiles(state: dict):
    tiles = town_tiles(state)
    if not tiles:
        return
    for r in range(1, TOWN_ROWS + 1):
        for c in range(1, TOWN_COLS + 1):
            yield r, c, tiles[r - 1][c - 1]


def is_town_area(area: str | None) -> bool:
    from hills import normalize_area

    return normalize_area(area) == AREA_TOWN


def is_town_feature(row: int, col: int, feature: tuple[int, int]) -> bool:
    return (int(row), int(col)) == feature


def player_at_town_tile(state: dict, player: str | None, feature: tuple[int, int]) -> bool:
    if not player:
        return False
    from hills import player_area, normalize_area
    from engine import player_where

    if normalize_area(player_area(state, player)) != AREA_TOWN:
        return False
    return player_where(state, player) == feature


def is_player_at_stall(state: dict, player: str | None) -> bool:
    return player_at_town_tile(state, player, TOWN_STALL)


def is_player_at_store(state: dict, player: str | None) -> bool:
    return player_at_town_tile(state, player, TOWN_STORE)


def is_player_at_forge(state: dict, player: str | None) -> bool:
    return player_at_town_tile(state, player, TOWN_FORGE)


def stall_of(state: dict) -> list:
    ensure_town(state)
    town = town_of(state)
    stall = town.get("stall")
    if not isinstance(stall, list):
        stall = []
        town["stall"] = stall
    return stall


def stall_stack_size(rules: dict | None = None) -> int:
    from inventory import CHEST_STACK
    from engine import load_rules

    rules = rules or load_rules()
    raw = (rules.get("chest_stack") if isinstance(rules, dict) else None) or CHEST_STACK
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return int(CHEST_STACK)


def stall_counts(state: dict, rules: dict | None = None) -> dict[str, int]:
    from inventory import stack_count

    counts: dict[str, int] = {}
    stall = stall_of(state)
    seen = []
    for slot in stall:
        if not isinstance(slot, dict):
            continue
        item = slot.get("item")
        if not item or item in seen:
            continue
        seen.append(item)
        counts[item] = stack_count(stall, item)
    return counts


def stall_item_count(state: dict, item: str, rules: dict | None = None) -> int:
    from inventory import stack_count, normalize_item

    item = normalize_item(item) or item
    return stack_count(stall_of(state), item)


def stall_is_empty(state: dict) -> bool:
    for slot in stall_of(state):
        if isinstance(slot, dict) and slot.get("item") and int(slot.get("count") or 0) > 0:
            return False
    return True


def add_to_stall(state: dict, item: str, n: int, rules: dict | None = None) -> int:
    """Add n of item to the stall. Returns leftover (always 0; the stall has no slot cap)."""
    from inventory import normalize_item, sync_inventory_view

    item = normalize_item(item) or item
    n = int(n)
    if n <= 0:
        return 0
    # Prefer add_to_slots if it exists; otherwise mirror chest stacking.
    leftover = _add_to_slot_list(stall_of(state), item, n, stall_stack_size(rules))
    try:
        sync_inventory_view(state, rules)
    except TypeError:
        sync_inventory_view(state)
    return int(leftover or 0)


def _add_to_slot_list(slots: list, item: str, n: int, stack: int) -> int:
    left = int(n)
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("item") == item and int(slot.get("count") or 0) < stack:
            room = stack - int(slot.get("count") or 0)
            take = min(room, left)
            slot["count"] = int(slot.get("count") or 0) + take
            left -= take
            if left <= 0:
                return 0
    while left > 0:
        take = min(stack, left)
        slots.append({"item": item, "count": take})
        left -= take
    return 0


def remove_from_stall(state: dict, item: str, n: int, rules: dict | None = None) -> int:
    from inventory import normalize_item, stack_count, sync_inventory_view

    item = normalize_item(item) or item
    n = int(n)
    if n <= 0:
        return 0
    stall = stall_of(state)
    have = stack_count(stall, item)
    take = min(have, n)
    left = take
    for slot in stall:
        if not isinstance(slot, dict) or slot.get("item") != item:
            continue
        have_here = int(slot.get("count") or 0)
        used = min(have_here, left)
        slot["count"] = have_here - used
        left -= used
        if left <= 0:
            break
    # Drop empty slots.
    kept = []
    for slot in stall:
        if isinstance(slot, dict) and slot.get("item") and int(slot.get("count") or 0) > 0:
            kept.append(slot)
    state["town"]["stall"] = kept
    try:
        sync_inventory_view(state, rules)
    except TypeError:
        sync_inventory_view(state)
    return take - left


def stall_sell_price(item: str, crops: dict | None = None, rules: dict | None = None) -> int | None:
    """Gold the stall pays for one of this item, or None if it will not take it."""
    from inventory import (
        item_sell_price,
        is_forage_item,
        recipes,
        recipe_is_sellable,
        normalize_item,
    )
    from engine import load_crops, load_rules

    crops = crops or load_crops()
    rules = rules or load_rules()
    item = normalize_item(item) or item
    if is_forage_item(item):
        return None
    recs = recipes(rules)
    rec = recs.get(item)
    if rec and not recipe_is_sellable(item, rec):
        return None
    return item_sell_price(item, crops, rules)


def stall_unsellable_reason(item: str, crops: dict | None = None, rules: dict | None = None) -> str:
    from inventory import is_forage_item, recipes, recipe_is_sellable, normalize_item, item_name
    from engine import load_crops, load_rules

    crops = crops or load_crops()
    rules = rules or load_rules()
    item = normalize_item(item) or item
    if is_forage_item(item):
        return "The stall doesn't buy foraged goods."
    recs = recipes(rules)
    rec = recs.get(item)
    if rec and not recipe_is_sellable(item, rec):
        return "The stall only buys jam among cooked meals. Eat cooked meals, or keep them for later."
    label = item
    try:
        label = item_name(item, 1, crops, rules)
    except Exception:
        label = item
    return f"The stall doesn't buy {label}."


def honour_purchase_message(
    player: str | None,
    label: str,
    price: int,
    where: str,
    gold_left: int,
) -> str:
    from engine import display_name

    who_name = display_name(player) if player else "You"
    has = "has" if player else "have"
    return (
        f"{who_name} left {int(price)}G in the tin for {label} ({where}). "
        f"{who_name} {has} {int(gold_left)}G left."
    )


def store_too_far_message() -> str:
    return (
        "The honour store is in the market town, east of the cabin "
        "(row 2 col 1). Walk there to buy."
    )


def stall_too_far_message() -> str:
    return (
        "Sell at the market stall in town, east of the cabin "
        "(row 1 col 2). Drop goods in the stall; they sell when the day ends."
    )


def forge_too_far_message() -> str:
    return "The forge is in the market town, east of the cabin (row 2 col 3)."


def cash_out_item(
    state: dict,
    crops: dict,
    kind,
    n,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Immediate sale from the chest or shared inventory, used when no player is standing at the stall (tests and unattended calls)."""
    from inventory import (
        normalize_item,
        item_name,
        item_count,
        take_available,
        chest_of,
        stack_count,
    )
    from engine import load_rules, load_crops, log_append, _parse_count, normalize_kind

    rules = rules or load_rules()
    crops = crops or load_crops()
    item = normalize_item(str(kind)) or normalize_kind(str(kind))
    price = stall_sell_price(item, crops, rules)
    if price is None:
        return False, stall_unsellable_reason(item, crops, rules)
    count, err = _parse_count(n)
    if err:
        return False, err
    have = item_count(state, item, rules)
    if have < count:
        return False, f"You only have {have} to sell."
    taken = take_available(state, item, count, None, pack_only=False, rules=rules)
    if taken < count:
        return False, f"You only have {taken} to sell."
    gold = int(price) * taken
    state["gold"] = int(state.get("gold") or 0) + gold
    noun = item_name(item, taken, crops, rules, state=state)
    msg = f"You sell {noun} for {gold}G. You now have {state['gold']}G."
    log_append(state, msg)
    return True, msg


def deposit_in_stall(
    state: dict,
    crops: dict,
    kind,
    n,
    player: str | None = None,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Move sellable goods from the pack into the stall. They sell at day end."""
    from inventory import (
        normalize_item,
        item_name,
        pack_of,
        stack_count,
        remove_from_pack,
        sync_inventory_view,
        prefer_available_stock,
    )
    from engine import (
        load_rules,
        load_crops,
        display_name,
        log_append,
        who,
        _parse_count,
        normalize_kind,
    )

    rules = rules or load_rules()
    crops = crops or load_crops()
    if player and not is_player_at_stall(state, player):
        return False, stall_too_far_message()
    from inventory import parse_item_and_count
    if isinstance(kind, list):
        item, n, err = parse_item_and_count(kind)
        if err:
            return False, err
        kind = item
    item = normalize_item(str(kind)) or normalize_kind(str(kind))
    if player:
        item = prefer_available_stock(item, [pack_of(state, player, rules)], crops, rules)
    price = stall_sell_price(item, crops, rules)
    if price is None:
        return False, stall_unsellable_reason(item, crops, rules)
    count, err = _parse_count(n)
    if err:
        return False, err
    if not player:
        return False, "Stand at the stall to put goods in it."
    have = stack_count(pack_of(state, player, rules), item)
    if have < count:
        noun = item_name(item, max(have, 1), crops, rules, state=state)
        if have < 1:
            return False, (
                f"There's no {item_name(item, 1, crops, rules, state=state).split(' ', 1)[-1]} "
                "in the backpack. Take goods from the chest, then walk them to the stall."
            )
        return False, f"You only have {noun} in the backpack to put in the stall."
    removed = remove_from_pack(state, player, item, count, rules)
    if removed < count:
        if removed:
            add_to_stall(state, item, removed, rules)
        return False, "Couldn't move everything into the stall."
    leftover = add_to_stall(state, item, removed, rules)
    if leftover:
        from inventory import add_to_pack

        add_to_pack(state, player, item, leftover, rules)
        removed -= leftover
    sync_inventory_view(state, rules)
    if removed <= 0:
        return False, "Nothing was put in the stall."
    noun = item_name(item, removed, crops, rules, state=state)
    gold = int(price) * removed
    msg = (
        f"{who(player, 'put', 'puts')} {noun} in the stall. "
        f"It will sell for {gold}G when the day ends "
        f"(or spend {instant_sell_energy(rules)} energy to sell now)."
    )
    log_append(state, msg, player)
    return True, msg


def settle_stall(
    state: dict,
    crops: dict | None = None,
    rules: dict | None = None,
    *,
    log: bool = True,
) -> tuple[int, str]:
    """Sell everything currently in the stall. Returns (gold earned, message). Empty stall is a no-op."""
    from inventory import item_name
    from engine import load_crops, load_rules, log_append

    crops = crops or load_crops()
    rules = rules or load_rules()
    if stall_is_empty(state):
        return 0, ""
    sold: list[tuple[str, int, int]] = []
    leftover_slots = []
    total = 0
    for slot in list(stall_of(state)):
        if not isinstance(slot, dict):
            continue
        item = slot.get("item")
        count = int(slot.get("count") or 0)
        if not item or count <= 0:
            continue
        price = stall_sell_price(item, crops, rules)
        if price is None:
            leftover_slots.append(slot)
            continue
        gold = int(price) * count
        total += gold
        sold.append((item, count, gold))
    state["town"]["stall"] = leftover_slots
    if total:
        state["gold"] = int(state.get("gold") or 0) + total
    if not sold:
        return 0, ""
    bits = []
    for item, count, gold in sold:
        bits.append(item_name(item, count, crops, rules, state=state))
    if len(bits) == 1:
        sold_list = bits[0]
    elif len(bits) == 2:
        sold_list = f"{bits[0]} and {bits[1]}"
    else:
        sold_list = ", ".join(bits[:-1]) + f", and {bits[-1]}"
    msg = f"The stall sold {sold_list} for {total}G."
    if leftover_slots:
        msg += " Unsold goods were left in the stall."
    if log:
        log_append(state, msg)
    return total, msg


def sell_stall_now(
    state: dict,
    player: str,
    crops: dict | None = None,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Spend energy to sell everything in the stall immediately. Caller does not charge energy."""
    from engine import load_crops, load_rules, display_name, player_slot, log_append

    rules = rules or load_rules()
    crops = crops or load_crops()
    if player and not is_player_at_stall(state, player):
        return False, stall_too_far_message()
    if stall_is_empty(state):
        return False, "The stall is empty."
    cost = instant_sell_energy(rules)
    if player:
        slot = player_slot(state, player)
        energy = int(slot.get("energy") or 0)
        if energy < cost:
            return False, (
                f"Not enough energy. Selling the stall now costs {cost}; "
                f"{display_name(player)} has {energy} left."
            )
        slot["energy"] = energy - cost
    gold, sold_msg = settle_stall(state, crops, rules, log=False)
    if not sold_msg:
        # Refund energy if nothing actually sold.
        if player:
            slot["energy"] = int(slot.get("energy") or 0) + cost
        return False, "The stall has nothing the market will buy."
    who_name = display_name(player) if player else "You"
    verb = "sells" if player else "sell"
    msg = (
        f"{who_name} {verb} the stall's goods now ({cost} energy). {sold_msg} "
        f"{who_name} {'has' if player else 'have'} {int(state.get('gold') or 0)}G."
    )
    log_append(state, msg, player)
    return True, msg


def describe_town_tile(state: dict, row: int, col: int, weather: str | None = None) -> str:
    from engine import position_name
    from inventory import item_name
    from engine import load_crops, load_rules

    tile = get_town_tile(state, row, col)
    typ = (tile or {}).get("type") or TILE_GRASS
    here = position_name(row, col)
    weather = (weather or "").strip().lower()
    snow = " A light snow has settled on the square." if weather == "snow" else ""
    if typ == TILE_STALL:
        crops = load_crops()
        rules = load_rules()
        counts = stall_counts(state, rules)
        if not counts:
            stock = "The stall is empty."
        else:
            bits = [item_name(item, n, crops, rules, state=state) for item, n in counts.items()]
            if len(bits) == 1:
                stock = f"In the stall: {bits[0]}."
            elif len(bits) == 2:
                stock = f"In the stall: {bits[0]} and {bits[1]}."
            else:
                stock = "In the stall: " + ", ".join(bits[:-1]) + f", and {bits[-1]}."
        return (
            f"  {here} — the market stall, under a blue awning. "
            "Drop goods here; they sell when the day ends. "
            f"Spend {instant_sell_energy(rules)} energy to sell everything now. {stock}{snow}"
        )
    if typ == TILE_STORE:
        return (
            f"  {here} — the honour store. There's no shopkeeper; "
            "leave coins in the tin for seeds, fertilizer, staples, and (once the mine is found) a pickaxe."
            f"{snow}"
        )
    if typ == TILE_FORGE:
        return (
            f"  {here} — the town forge. Upgrade a hoe, watering can, axe, or pickaxe here."
            f"{snow}"
        )
    if (row, col) == TOWN_ENTRANCE:
        return (
            f"  {here} — a grassy entrance to the market town. "
            "West leads back to the cabin. The stall is to the east, the store to the south."
            f"{snow}"
        )
    return f"  {here} — a grassy square in the market town.{snow}"


def map_cell_lines(tile: dict) -> tuple[str, str]:
    typ = (tile or {}).get("type")
    if typ == TILE_STALL:
        return "STALL", "blue awning"
    if typ == TILE_STORE:
        return "STORE", "honour tin"
    if typ == TILE_FORGE:
        return "FORGE", "anvil"
    return "grass", "town"


def town_summary(state: dict) -> str:
    del state
    return "The market town is east of the cabin: stall, honour store, and forge."


def sprite_key_for_town_tile(tile: dict, weather: str | None = None) -> str:
    typ = (tile or {}).get("type") or TILE_GRASS
    if typ not in {TILE_GRASS, TILE_STALL, TILE_STORE, TILE_FORGE}:
        typ = TILE_GRASS
    if (weather or "").strip().lower() == "snow":
        return typ + "_snow"
    return typ

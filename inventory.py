"""Pack, cabin chest, tools, and cozy recipes for Lantern Farm."""

from __future__ import annotations

from typing import Iterable

PACK_SLOTS = 4
PACK_STACK = 8
CHEST_STACK = 16
TILL_HOLD_DAYS = 5

TOOL_HOE = "hoe"
TOOL_CAN = "watering_can"

TOOLS = {
    TOOL_HOE: {
        "name": "hoe",
        "name_plural": "hoes",
        "starting": 1,
    },
    TOOL_CAN: {
        "name": "watering can",
        "name_plural": "watering cans",
        "starting": 2,
    },
}

# Default recipes if rules.json has not listed them yet.
DEFAULT_RECIPES = {
    "strawberry_jam": {
        "name": "strawberry jam",
        "berries": 3,
        "ingredients": {},
        "eat_energy": 50,
        "sell_price": 90,
        "description": "Three berries simmered down to a jar of jam. A hearty snack, or a little more gold than the fruit alone.",
    },
    "kabocha_soup": {
        "name": "kabocha soup",
        "ingredients": {"kabocha": 1},
        "eat_energy": 45,
        "sell_price": 40,
        "description": "A bowl of roasted kabocha soup. Restores more energy than eating the squash raw.",
    },
    "root_stew": {
        "name": "root stew",
        "ingredients": {"carrot": 1, "turnip": 1},
        "eat_energy": 40,
        "sell_price": 60,
        "description": "A carrot and a turnip stewed together. Warm, filling, and a little more gold than selling them raw.",
    },
}

FERTILIZERS = {
    "fertilizer_general": {
        "kind": "general",
        "name": "general fertilizer",
        "name_plural": "bags of general fertilizer",
        "price": 15,
        "description": "A little health now, and a small bump to the harvest.",
    },
    "fertilizer_yield": {
        "kind": "yield",
        "name": "yield-boost fertilizer",
        "name_plural": "bags of yield-boost fertilizer",
        "price": 25,
        "description": "A stronger bump to how much the plant is likely to yield.",
    },
    "fertilizer_growth": {
        "kind": "growth",
        "name": "growth-boost fertilizer",
        "name_plural": "bags of growth-boost fertilizer",
        "price": 20,
        "description": "Helps a watered plant put on growth a little faster.",
    },
}

FERTILIZER_SHOP_SEASONS = ("spring", "summer")

FERT_KIND_TO_ITEM = {info["kind"]: item for item, info in FERTILIZERS.items()}

ITEM_ALIASES = {
    "hoe": TOOL_HOE,
    "watering_can": TOOL_CAN,
    "watering-can": TOOL_CAN,
    "wateringcan": TOOL_CAN,
    "watering can": TOOL_CAN,
    "can": TOOL_CAN,
    "cans": TOOL_CAN,
    "watering cans": TOOL_CAN,
    "jam": "strawberry_jam",
    "strawberry jam": "strawberry_jam",
    "strawberry_jam": "strawberry_jam",
    "soup": "kabocha_soup",
    "kabocha soup": "kabocha_soup",
    "kabocha_soup": "kabocha_soup",
    "stew": "root_stew",
    "root stew": "root_stew",
    "root_stew": "root_stew",
    "fertilizer_general": "fertilizer_general",
    "general fertilizer": "fertilizer_general",
    "general fert": "fertilizer_general",
    "fertilizer general": "fertilizer_general",
    "fert general": "fertilizer_general",
    "fertilizer_yield": "fertilizer_yield",
    "yield fertilizer": "fertilizer_yield",
    "yield-boost fertilizer": "fertilizer_yield",
    "yield boost fertilizer": "fertilizer_yield",
    "yield fert": "fertilizer_yield",
    "fertilizer yield": "fertilizer_yield",
    "fert yield": "fertilizer_yield",
    "fertilizer_growth": "fertilizer_growth",
    "growth fertilizer": "fertilizer_growth",
    "growth-boost fertilizer": "fertilizer_growth",
    "growth boost fertilizer": "fertilizer_growth",
    "growth fert": "fertilizer_growth",
    "fertilizer growth": "fertilizer_growth",
    "fert growth": "fertilizer_growth",
}


def pack_slots(rules: dict | None = None) -> int:
    rules = rules or {}
    try:
        n = int((rules.get("pack_slots") if rules else None) or PACK_SLOTS)
    except (TypeError, ValueError):
        n = PACK_SLOTS
    return max(1, n)


def pack_stack_limit(rules: dict | None = None) -> int:
    rules = rules or {}
    try:
        n = int((rules.get("pack_stack") if rules else None) or PACK_STACK)
    except (TypeError, ValueError):
        n = PACK_STACK
    return max(1, n)


def chest_stack_limit(rules: dict | None = None) -> int:
    rules = rules or {}
    try:
        n = int((rules.get("chest_stack") if rules else None) or CHEST_STACK)
    except (TypeError, ValueError):
        n = CHEST_STACK
    return max(1, n)


def till_hold_days(rules: dict | None = None) -> int:
    rules = rules or {}
    try:
        n = int((rules.get("till_hold_days") if rules else None) or TILL_HOLD_DAYS)
    except (TypeError, ValueError):
        n = TILL_HOLD_DAYS
    return max(1, n)


def recipes(rules: dict | None = None) -> dict:
    rules = rules or {}
    data = dict(DEFAULT_RECIPES)
    custom = rules.get("recipes") if isinstance(rules, dict) else None
    if isinstance(custom, dict):
        for key, rec in custom.items():
            if not isinstance(rec, dict):
                continue
            item = normalize_item(key) or str(key).strip().lower().replace(" ", "_")
            base = dict(data.get(item) or {})
            base.update(rec)
            if "ingredients" in rec and isinstance(rec["ingredients"], dict):
                base["ingredients"] = {
                    (normalize_item(k) or k): int(v)
                    for k, v in rec["ingredients"].items()
                }
            data[item] = base
    return data


def is_tool(item: str | None) -> bool:
    return (item or "") in TOOLS


def is_fertilizer(item: str | None) -> bool:
    return (item or "") in FERTILIZERS


def fertilizer_info(item: str | None, rules: dict | None = None) -> dict | None:
    item = item or ""
    if item not in FERTILIZERS:
        return None
    info = dict(FERTILIZERS[item])
    custom = (rules or {}).get("fertilizers") if isinstance(rules, dict) else None
    if isinstance(custom, dict) and isinstance(custom.get(item), dict):
        info.update(custom[item])
    try:
        info["price"] = int(info.get("price") or FERTILIZERS[item]["price"])
    except (TypeError, ValueError):
        info["price"] = FERTILIZERS[item]["price"]
    return info


def fertilizer_item_for_kind(kind: str | None) -> str | None:
    if not kind:
        return None
    text = str(kind).strip().lower().replace("-", " ").replace("_", " ")
    compact = text.replace(" ", "")
    if text in ITEM_ALIASES and ITEM_ALIASES[text] in FERTILIZERS:
        return ITEM_ALIASES[text]
    if compact in {"general", "yield", "growth"}:
        return FERT_KIND_TO_ITEM[compact]
    if text in FERT_KIND_TO_ITEM:
        return FERT_KIND_TO_ITEM[text]
    item = ITEM_ALIASES.get(text) or ITEM_ALIASES.get(compact)
    if item in FERTILIZERS:
        return item
    if kind in FERTILIZERS:
        return kind
    return None


def is_recipe_item(item: str | None, rules: dict | None = None) -> bool:
    return (item or "") in recipes(rules)


def max_stack_for(item: str, *, in_chest: bool = False, rules: dict | None = None) -> int:
    if is_tool(item):
        # Tools may share a chest slot (the two cans together) but each
        # occupies its own pack slot.
        return chest_stack_limit(rules) if in_chest else 1
    return chest_stack_limit(rules) if in_chest else pack_stack_limit(rules)


def normalize_item(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).strip().lower().replace("_", " ").replace("-", " ").split())
    if not text:
        return None
    compact = text.replace(" ", "")
    if text in ITEM_ALIASES:
        return ITEM_ALIASES[text]
    if compact in ITEM_ALIASES:
        return ITEM_ALIASES[compact]
    from engine import crop_info, load_crops, normalize_kind, stock_key

    crops = load_crops()
    if text.endswith(" seeds"):
        kind = normalize_kind(text[: -len(" seeds")])
        info = crop_info(crops, kind)
        if info:
            return stock_key(kind, info)
    if text.endswith(" seed"):
        kind = normalize_kind(text[: -len(" seed")])
        info = crop_info(crops, kind)
        if info:
            return stock_key(kind, info)
    if text.endswith(" seedlings"):
        kind = normalize_kind(text[: -len(" seedlings")])
        info = crop_info(crops, kind)
        if info:
            return stock_key(kind, info)
    if text.endswith(" seedling"):
        kind = normalize_kind(text[: -len(" seedling")])
        info = crop_info(crops, kind)
        if info:
            return stock_key(kind, info)
    kind = normalize_kind(text.replace(" ", "_"))
    if crop_info(crops, kind):
        return kind
    # stock keys already ending in _seed / _seedling
    underscored = text.replace(" ", "_")
    if underscored.endswith("_seed") or underscored.endswith("_seedling"):
        kind = underscored.rsplit("_", 1)[0]
        if crop_info(crops, kind):
            return underscored
    if underscored in recipes():
        return underscored
    if underscored in TOOLS:
        return underscored
    if underscored in FERTILIZERS:
        return underscored
    fert = fertilizer_item_for_kind(text) or fertilizer_item_for_kind(underscored)
    if fert:
        return fert
    return None


def item_name(item: str, count: int = 1, crops: dict | None = None, rules: dict | None = None) -> str:
    item = item or ""
    if item in TOOLS:
        noun = TOOLS[item]["name"] if count == 1 else TOOLS[item]["name_plural"]
        return f"{count} {noun}"
    if item in FERTILIZERS:
        info = fertilizer_info(item, rules) or FERTILIZERS[item]
        noun = info["name"] if count == 1 else info["name_plural"]
        return f"{count} {noun}"
    rec = recipes(rules).get(item)
    if rec:
        name = rec.get("name") or item.replace("_", " ")
        if count == 1:
            return f"{count} {name}"
        # jams, soups, stews: add s if it does not already end in s
        plural = rec.get("name_plural") or (name if name.endswith("s") else name + "s")
        return f"{count} {plural}"
    from engine import crop_info, crop_name, crop_name_plural, load_crops, stock_noun

    crops = crops or load_crops()
    stock = None
    kind = item
    if item.endswith("_seedling"):
        kind = item[: -len("_seedling")]
        stock = "seedling"
    elif item.endswith("_seed"):
        kind = item[: -len("_seed")]
        stock = "seed"
    info = crop_info(crops, kind) or {}
    if stock:
        noun = stock_noun(info, count) if info else (stock if count == 1 else stock + "s")
        return f"{count} {crop_name(kind, info)} {noun}"
    return f"{count} {crop_name_plural(kind, info, count)}"


def item_sell_price(item: str, crops: dict | None = None, rules: dict | None = None) -> int | None:
    rec = recipes(rules).get(item)
    if rec:
        price = rec.get("sell_price")
        if price is None:
            return None
        try:
            return int(price)
        except (TypeError, ValueError):
            return None
    from engine import crop_info, load_crops

    info = crop_info(crops or load_crops(), item)
    if not info:
        return None
    try:
        return int(info["sell_price"])
    except (KeyError, TypeError, ValueError):
        return None


def item_eat_energy(item: str, crops: dict | None = None, rules: dict | None = None) -> int | None:
    rec = recipes(rules).get(item)
    if rec and rec.get("eat_energy") is not None:
        try:
            return max(0, int(rec["eat_energy"]))
        except (TypeError, ValueError):
            return None
    from engine import eat_energy_for, load_crops

    return eat_energy_for(crops or load_crops(), item)


def empty_pack(rules: dict | None = None) -> list:
    return [None] * pack_slots(rules)


def _clean_stack(slot, *, in_chest: bool = False, rules: dict | None = None) -> dict | None:
    if not slot or not isinstance(slot, dict):
        return None
    item = normalize_item(slot.get("item") or slot.get("kind") or slot.get("id"))
    if not item:
        return None
    try:
        count = int(slot.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return None
    cap = max_stack_for(item, in_chest=in_chest, rules=rules)
    return {"item": item, "count": min(count, cap) if in_chest or is_tool(item) else min(count, cap)}


def normalize_pack(raw, rules: dict | None = None) -> list:
    slots = pack_slots(rules)
    pack = [None] * slots
    if not raw:
        return pack
    if isinstance(raw, dict) and "slots" in raw:
        raw = raw.get("slots")
    if not isinstance(raw, list):
        return pack
    i = 0
    for slot in raw:
        if i >= slots:
            break
        cleaned = _clean_stack(slot, in_chest=False, rules=rules)
        pack[i] = cleaned
        i += 1
    return pack


def normalize_chest(raw, rules: dict | None = None) -> list:
    out: list[dict] = []
    if not raw:
        return out
    if isinstance(raw, dict):
        # Legacy count map.
        for key, val in raw.items():
            item = normalize_item(key)
            try:
                count = int(val or 0)
            except (TypeError, ValueError):
                count = 0
            if item and count > 0:
                _push_stacks(out, item, count, in_chest=True, rules=rules)
        return out
    if not isinstance(raw, list):
        return out
    for slot in raw:
        cleaned = _clean_stack(slot, in_chest=True, rules=rules)
        if cleaned:
            _push_stacks(out, cleaned["item"], cleaned["count"], in_chest=True, rules=rules)
    return out


def _push_stacks(dest: list, item: str, count: int, *, in_chest: bool, rules: dict | None = None) -> int:
    """Add as many as will fit. Returns the leftover count."""
    if count <= 0:
        return 0
    cap = max_stack_for(item, in_chest=in_chest, rules=rules)
    for slot in dest:
        if not slot or slot.get("item") != item:
            continue
        room = cap - int(slot.get("count") or 0)
        if room <= 0:
            continue
        take = min(room, count)
        slot["count"] = int(slot["count"]) + take
        count -= take
        if count <= 0:
            return 0
    while count > 0:
        take = min(cap, count)
        dest.append({"item": item, "count": take})
        count -= take
    return 0


def stack_count(slots: Iterable, item: str) -> int:
    total = 0
    for slot in slots or []:
        if slot and slot.get("item") == item:
            total += int(slot.get("count") or 0)
    return total


def _remove_from_slots(slots: list, item: str, count: int) -> int:
    """Remove up to count, later slots first. Returns how many were removed."""
    removed = 0
    if count <= 0:
        return 0
    for i in range(len(slots) - 1, -1, -1):
        slot = slots[i]
        if not slot or slot.get("item") != item:
            continue
        have = int(slot.get("count") or 0)
        take = min(have, count - removed)
        have -= take
        removed += take
        if have <= 0:
            slots[i] = None
        else:
            slot["count"] = have
        if removed >= count:
            break
    # Compact None holes in a chest list (not a fixed pack).
    return removed


def compact_chest(chest: list) -> list:
    return [slot for slot in chest if slot and int(slot.get("count") or 0) > 0]


def pack_of(state: dict, player: str | None, rules: dict | None = None) -> list:
    from engine import player_slot

    if not player:
        return empty_pack(rules)
    slot = player_slot(state, player)
    pack = normalize_pack(slot.get("pack"), rules)
    slot["pack"] = pack
    return pack


def chest_of(state: dict, rules: dict | None = None) -> list:
    chest = normalize_chest(state.get("chest"), rules)
    state["chest"] = chest
    return chest


def pack_has(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> bool:
    if not player:
        return False
    return stack_count(pack_of(state, player, rules), item) >= n


def pack_space_for(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> bool:
    if not player or n <= 0:
        return False
    pack = pack_of(state, player, rules)
    cap = max_stack_for(item, in_chest=False, rules=rules)
    remaining = n
    for slot in pack:
        if slot is None:
            remaining -= cap
        elif slot.get("item") == item:
            remaining -= max(0, cap - int(slot.get("count") or 0))
        if remaining <= 0:
            return True
    return remaining <= 0


def add_to_pack(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> int:
    """Add to the player's pack. Returns leftover that did not fit."""
    if not player or n <= 0:
        return max(0, n)
    pack = pack_of(state, player, rules)
    cap = max_stack_for(item, in_chest=False, rules=rules)
    left = n
    for i, slot in enumerate(pack):
        if slot and slot.get("item") == item:
            room = cap - int(slot.get("count") or 0)
            if room <= 0:
                continue
            take = min(room, left)
            slot["count"] = int(slot["count"]) + take
            left -= take
            if left <= 0:
                return 0
    for i, slot in enumerate(pack):
        if slot is None:
            take = min(cap, left)
            pack[i] = {"item": item, "count": take}
            left -= take
            if left <= 0:
                return 0
    return left


def remove_from_pack(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> int:
    """Remove up to n from the pack. Returns how many were removed."""
    if not player or n <= 0:
        return 0
    pack = pack_of(state, player, rules)
    return _remove_from_slots(pack, item, n)


def add_to_chest(state: dict, item: str, n: int = 1, rules: dict | None = None) -> None:
    if n <= 0:
        return
    chest = chest_of(state, rules)
    _push_stacks(chest, item, n, in_chest=True, rules=rules)
    state["chest"] = compact_chest(chest)


def remove_from_chest(state: dict, item: str, n: int = 1, rules: dict | None = None) -> int:
    if n <= 0:
        return 0
    chest = chest_of(state, rules)
    removed = _remove_from_slots(chest, item, n)
    state["chest"] = compact_chest(chest)
    return removed


def all_stores(state: dict, rules: dict | None = None) -> list[dict]:
    """Every stack in the chest and every pack."""
    from engine import known_players

    stacks = list(chest_of(state, rules))
    players = state.get("players") or {}
    names = list(players) or list(known_players())
    for name in names:
        stacks.extend([s for s in pack_of(state, name, rules) if s])
    return stacks


def item_count(state: dict, item: str, rules: dict | None = None) -> int:
    return stack_count(all_stores(state, rules), item)


def counts_map(state: dict, rules: dict | None = None) -> dict[str, int]:
    totals: dict[str, int] = {}
    for slot in all_stores(state, rules):
        if not slot:
            continue
        item = slot.get("item")
        if not item:
            continue
        totals[item] = totals.get(item, 0) + int(slot.get("count") or 0)
    return totals


def sync_inventory_view(state: dict, rules: dict | None = None) -> dict[str, int]:
    """Keep a totals map on the state for older readers, never as a second store."""
    from engine import load_crops, stock_key

    totals = counts_map(state, rules)
    view = dict(totals)
    crops = load_crops()
    for kind, info in (crops.get("crops") or {}).items():
        view.setdefault(stock_key(kind, info), 0)
        view.setdefault(kind, 0)
    for item in FERTILIZERS:
        view.setdefault(item, 0)
    state["inventory"] = view
    return view


def take_available(
    state: dict,
    item: str,
    n: int,
    player: str | None = None,
    *,
    pack_only: bool = False,
    rules: dict | None = None,
) -> int:
    """Remove items, pack first then chest. Returns how many were taken."""
    if n <= 0:
        return 0
    taken = 0
    if player:
        taken += remove_from_pack(state, player, item, n, rules)
    if taken < n and not pack_only:
        taken += remove_from_chest(state, item, n - taken, rules)
    sync_inventory_view(state, rules)
    return taken


def store_item(
    state: dict,
    item: str,
    n: int,
    player: str | None = None,
    *,
    prefer: str = "pack",
    rules: dict | None = None,
) -> int:
    """Store items in pack and/or chest. Returns leftover that did not fit (always 0 if chest is used)."""
    if n <= 0:
        return 0
    left = n
    if player and prefer == "pack":
        left = add_to_pack(state, player, item, left, rules)
    if left and prefer != "pack_only":
        add_to_chest(state, item, left, rules)
        left = 0
    elif left and prefer == "pack_only":
        pass
    sync_inventory_view(state, rules)
    return left


def parse_item_and_count(args: list[str]) -> tuple[str | None, int | None, str | None]:
    """Parse `hoe`, `2 carrot`, or `watering can` / `strawberry 3`."""
    if not args:
        return None, None, "Say which item, like: take hoe"
    tokens = [str(a) for a in args]
    count = None
    # Leading or trailing whole number is the count.
    if tokens[0].isdigit():
        count = int(tokens[0])
        tokens = tokens[1:]
    elif tokens[-1].isdigit() and len(tokens) > 1:
        count = int(tokens[-1])
        tokens = tokens[:-1]
    if not tokens:
        return None, None, "Say which item, like: take hoe"
    if count is None:
        count = 1
    if count < 1:
        return None, None, "Choose a count of at least 1."
    item = normalize_item(" ".join(tokens))
    if not item:
        return None, None, f"Unknown item {' '.join(tokens)!r}."
    return item, count, None


def starting_tool_counts(rules: dict | None = None) -> dict[str, int]:
    rules = rules or {}
    custom = rules.get("tools") if isinstance(rules, dict) else None
    out = {key: int(info["starting"]) for key, info in TOOLS.items()}
    if isinstance(custom, dict):
        for key, val in custom.items():
            item = normalize_item(key) or key
            if item not in TOOLS:
                continue
            try:
                out[item] = max(0, int(val))
            except (TypeError, ValueError):
                continue
    return out


def ensure_starting_tools(state: dict, rules: dict | None = None) -> bool:
    """Put any missing world tools into the chest. Never duplicates extras."""
    changed = False
    wanted = starting_tool_counts(rules)
    for item, need in wanted.items():
        have = item_count(state, item, rules)
        if have < need:
            add_to_chest(state, item, need - have, rules)
            changed = True
    return changed


def move_legacy_inventory_to_chest(state: dict, rules: dict | None = None) -> bool:
    """Fold a legacy count-map inventory into the chest, once."""
    raw = state.get("inventory")
    if not isinstance(raw, dict):
        return False
    # If packs or chest already exist and inventory is only a totals view,
    # do not dump the view back into the chest.
    if state.get("_inventory_is_view"):
        return False
    moved = False
    for key, val in list(raw.items()):
        item = normalize_item(key) or (str(key).strip().lower() if key else None)
        try:
            count = int(val or 0)
        except (TypeError, ValueError):
            count = 0
        if not item or count <= 0:
            continue
        add_to_chest(state, item, count, rules)
        moved = True
    if moved:
        state["inventory"] = {}
    return moved


def migrate_inventory(state: dict, crops: dict | None = None, rules: dict | None = None) -> bool:
    """Install packs and a cabin chest. Idempotent. Tools start in the chest."""
    from engine import known_players, player_slot

    rules = rules or {}
    changed = False
    if "chest" not in state:
        state["chest"] = []
        changed = True
        # First time: move the old shared pack into the chest.
        if move_legacy_inventory_to_chest(state, rules):
            changed = True
    else:
        # Normalize any odd shapes, but do not re-import the totals view.
        before = list(state.get("chest") or [])
        chest_of(state, rules)
        if state.get("chest") != before:
            changed = True

    for name in list((state.get("players") or {}).keys()) or list(known_players()):
        slot = player_slot(state, name)
        if "pack" not in slot:
            slot["pack"] = empty_pack(rules)
            changed = True
        else:
            normalized = normalize_pack(slot.get("pack"), rules)
            if slot.get("pack") != normalized:
                slot["pack"] = normalized
                changed = True

    if ensure_starting_tools(state, rules):
        changed = True
    state["_inventory_is_view"] = True
    sync_inventory_view(state, rules)
    return changed


def reset_till_hold(tile: dict, rules: dict | None = None) -> None:
    if tile.get("type") == "cabin":
        tile.pop("untilled_in", None)
        return
    tile["untilled_in"] = till_hold_days(rules)


def clear_till_hold(tile: dict) -> None:
    tile.pop("untilled_in", None)


def till_hold_left(tile: dict, rules: dict | None = None) -> int | None:
    if not tile.get("tilled"):
        return None
    crop = tile.get("crop")
    if crop and crop.get("stage") not in (None, "withered"):
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

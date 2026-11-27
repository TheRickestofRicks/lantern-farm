"""Buildable cabin chest: slots, tiers, starting goods, and upgrades."""

from __future__ import annotations

from typing import Iterable

CHEST_KEY = "chest"
BUILT_KEY = "chest_built"
TIER_KEY = "chest_tier"
STARTING_GOODS_KEY = "starting_goods_placed"

TIER_WOOD = "wood"
TIER_COPPER = "copper"
TIER_IRON = "iron"
TIER_GOLD = "gold"
TIER_ORDER = (TIER_WOOD, TIER_COPPER, TIER_IRON, TIER_GOLD)

# Defaults also live in rules.json; these are fallbacks only.
DEFAULT_BUILD_COST = {"wood": 5}
DEFAULT_BUILD_ROW = 1
DEFAULT_BUILD_COL = 2
DEFAULT_STACK = 16
DEFAULT_TIERS = {
    TIER_WOOD: {"slots": 12, "rows": 1, "cols": 12, "band": "#7a4e24"},
    TIER_COPPER: {
        "slots": 24,
        "rows": 2,
        "cols": 12,
        "band": "#b87333",
        "cost": {"copper_ore": 8},
    },
    TIER_IRON: {
        "slots": 36,
        "rows": 3,
        "cols": 12,
        "band": "#8a8d91",
        "cost": {"iron_ore": 10},
    },
    TIER_GOLD: {
        "slots": 48,
        "rows": 4,
        "cols": 12,
        "band": "#d4a017",
        "cost": {"gold_ore": 12},
    },
}

BAND_COLORS = {
    TIER_WOOD: "#7a4e24",
    TIER_COPPER: "#b87333",
    TIER_IRON: "#8a8d91",
    TIER_GOLD: "#d4a017",
}


def chest_rules(rules: dict | None = None) -> dict:
    raw = rules.get("chest") if isinstance(rules, dict) else None
    return raw if isinstance(raw, dict) else {}


def _load_rules(rules: dict | None = None) -> dict:
    if rules is not None:
        return rules
    from engine import load_rules

    return load_rules()


def build_tile(rules: dict | None = None) -> tuple[int, int]:
    cfg = chest_rules(rules)
    try:
        row = int(cfg.get("build_row") or DEFAULT_BUILD_ROW)
        col = int(cfg.get("build_col") or DEFAULT_BUILD_COL)
    except (TypeError, ValueError):
        row, col = DEFAULT_BUILD_ROW, DEFAULT_BUILD_COL
    return row, col


def build_cost(rules: dict | None = None) -> dict[str, int]:
    cfg = chest_rules(rules)
    raw = cfg.get("build") if isinstance(cfg.get("build"), dict) else DEFAULT_BUILD_COST
    out: dict[str, int] = {}
    for key, val in raw.items():
        try:
            n = int(val)
        except (TypeError, ValueError):
            continue
        if n > 0:
            out[str(key)] = n
    return out or dict(DEFAULT_BUILD_COST)


def chest_stack_limit(rules: dict | None = None) -> int:
    from inventory import chest_stack_limit as _limit

    return _limit(rules)


def _tier_table(rules: dict | None = None) -> dict:
    cfg = chest_rules(rules)
    raw = cfg.get("tiers") if isinstance(cfg.get("tiers"), dict) else {}
    table = {}
    for name, default in DEFAULT_TIERS.items():
        info = dict(default)
        custom = raw.get(name)
        if isinstance(custom, dict):
            if "slots" in custom:
                try:
                    info["slots"] = max(1, int(custom["slots"]))
                except (TypeError, ValueError):
                    pass
            if "rows" in custom:
                try:
                    info["rows"] = max(1, int(custom["rows"]))
                except (TypeError, ValueError):
                    pass
            if "cols" in custom:
                try:
                    info["cols"] = max(1, int(custom["cols"]))
                except (TypeError, ValueError):
                    pass
            if custom.get("band"):
                info["band"] = str(custom["band"])
            if isinstance(custom.get("cost"), dict):
                info["cost"] = {str(k): int(v) for k, v in custom["cost"].items() if int(v) > 0}
        table[name] = info
    return table


def normalize_tier(raw, rules: dict | None = None) -> str:
    name = str(raw or TIER_WOOD).strip().lower()
    if name in {"base", "basic", "starter", "plain"}:
        name = TIER_WOOD
    return name if name in _tier_table(rules) else TIER_WOOD


def chest_is_built(state: dict | None) -> bool:
    if not isinstance(state, dict):
        return False
    return bool(state.get(BUILT_KEY))


def chest_tier(state: dict, rules: dict | None = None) -> str:
    if not chest_is_built(state):
        return TIER_WOOD
    return normalize_tier(state.get(TIER_KEY), rules)


def chest_tier_info(state: dict, rules: dict | None = None) -> dict:
    return dict(_tier_table(rules)[chest_tier(state, rules)])


def chest_slot_count(state: dict, rules: dict | None = None) -> int:
    if not chest_is_built(state):
        return 0
    return int(chest_tier_info(state, rules)["slots"])


def chest_band_color(state: dict, rules: dict | None = None) -> str:
    info = chest_tier_info(state, rules)
    return str(info.get("band") or BAND_COLORS.get(chest_tier(state, rules), BAND_COLORS[TIER_WOOD]))


def chest_display_name(state: dict, rules: dict | None = None) -> str:
    if not chest_is_built(state):
        return "chest"
    tier = chest_tier(state, rules)
    if tier == TIER_WOOD:
        return "wooden chest"
    return f"{tier}-banded chest"


def next_tier(state: dict, rules: dict | None = None) -> str | None:
    if not chest_is_built(state):
        return None
    current = chest_tier(state, rules)
    try:
        i = TIER_ORDER.index(current)
    except ValueError:
        return TIER_COPPER
    if i + 1 >= len(TIER_ORDER):
        return None
    return TIER_ORDER[i + 1]


def upgrade_cost(state: dict, rules: dict | None = None) -> dict[str, int]:
    nxt = next_tier(state, rules)
    if not nxt:
        return {}
    info = _tier_table(rules).get(nxt) or {}
    raw = info.get("cost") if isinstance(info.get("cost"), dict) else {}
    return {str(k): int(v) for k, v in raw.items() if int(v) > 0}


def _clean_slot(slot, rules: dict | None = None):
    from inventory import _clean_stack

    if not slot or not isinstance(slot, dict):
        return None
    return _clean_stack(slot, in_chest=True, rules=rules)


def pad_chest_slots(slots: list, size: int) -> list:
    """Keep every existing stack (including overflow) and pad with empty slots."""
    out = list(slots)
    while len(out) < size:
        out.append(None)
    return out


def filled_count(slots: Iterable) -> int:
    n = 0
    for slot in slots or []:
        if slot and slot.get("item") and int(slot.get("count") or 0) > 0:
            n += 1
    return n


def normalize_built_chest(raw, rules: dict | None = None, *, slots: int = 12) -> list:
    """Preserve hole positions. Never drop stacks that exceed the slot count."""
    from inventory import normalize_item, _push_stacks, _with_tier, is_tool, stack_tool_tier

    size = max(1, int(slots or 12))
    if not raw:
        return [None] * size
    if isinstance(raw, dict):
        compact: list = []
        for key, val in raw.items():
            item = normalize_item(key)
            try:
                count = int(val or 0)
            except (TypeError, ValueError):
                count = 0
            if item and count > 0:
                _push_stacks(compact, item, count, in_chest=True, rules=rules)
        return pad_chest_slots(compact, size)
    if not isinstance(raw, list):
        return [None] * size
    from inventory import max_stack_for, _with_tier, normalize_item

    out: list = []
    for slot in raw:
        if slot is None or slot is False or slot == {}:
            out.append(None)
            continue
        cleaned = _clean_slot(slot, rules)
        if not cleaned:
            out.append(None)
            continue
        item = cleaned.get("item")
        try:
            raw_count = int(slot.get("count") or cleaned.get("count") or 0)
        except (TypeError, ValueError, AttributeError):
            raw_count = int(cleaned.get("count") or 0)
        cap = max_stack_for(item, in_chest=True, rules=rules)
        left = max(raw_count, 0)
        first = True
        while left > 0:
            take = min(cap, left)
            piece = _with_tier(item, take, cleaned.get("tier"))
            if first:
                out.append(piece)
                first = False
            else:
                out.append(piece)
            left -= take
    return pad_chest_slots(out, size)


def install_built_chest(state: dict, rules: dict | None = None, *, tier: str | None = None) -> list:
    """Mark the chest built and normalize its slots in place."""
    rules = _load_rules(rules)
    state[BUILT_KEY] = True
    state[TIER_KEY] = normalize_tier(tier or state.get(TIER_KEY), rules)
    size = chest_slot_count(state, rules)
    slots = normalize_built_chest(state.get(CHEST_KEY), rules, slots=size)
    state[CHEST_KEY] = slots
    state[STARTING_GOODS_KEY] = True
    return slots


def chest_slots(state: dict, rules: dict | None = None) -> list:
    """Live slot list for a built chest, including empty holes and overflow."""
    if not chest_is_built(state):
        return []
    rules = _load_rules(rules)
    size = chest_slot_count(state, rules)
    slots = normalize_built_chest(state.get(CHEST_KEY), rules, slots=size)
    state[CHEST_KEY] = slots
    return slots


def chest_has_room(state: dict, item: str, n: int = 1, rules: dict | None = None) -> bool:
    return chest_space_count(state, item, rules) >= n


def chest_space_count(state: dict, item: str, rules: dict | None = None) -> int:
    if not chest_is_built(state) or n_safe(item) is None:
        return 0
    from inventory import max_stack_for

    cap = max_stack_for(item, in_chest=True, rules=rules)
    room = 0
    size = chest_slot_count(state, rules)
    for i, slot in enumerate(chest_slots(state, rules)):
        if i >= size:
            break
        if slot is None:
            room += cap
        elif slot.get("item") == item:
            room += max(0, cap - int(slot.get("count") or 0))
    return room


def n_safe(item) -> str | None:
    from inventory import normalize_item

    return normalize_item(item) if item else None


def add_to_built_chest(
    state: dict,
    item: str,
    n: int = 1,
    rules: dict | None = None,
    tier: str | None = None,
    *,
    allow_overflow: bool = False,
) -> int:
    """Add to a built chest. Returns leftover that did not fit.

    Overflow (stacks past the slot cap) is only used when migrating a live
    save so nothing is deleted. Player drops must pass allow_overflow=False.
    """
    if not chest_is_built(state) or n <= 0 or not item:
        return max(0, n)
    from inventory import max_stack_for, is_tool, stack_tool_tier, _with_tier

    rules = _load_rules(rules)
    slots = chest_slots(state, rules)
    size = chest_slot_count(state, rules)
    cap = max_stack_for(item, in_chest=True, rules=rules)
    want = stack_tool_tier(tier) if is_tool(item) else None
    left = n
    for i, slot in enumerate(slots):
        if i >= size and not allow_overflow:
            break
        if slot and slot.get("item") == item:
            if is_tool(item) and stack_tool_tier(slot) != want:
                continue
            room = cap - int(slot.get("count") or 0)
            if room <= 0:
                continue
            take = min(room, left)
            slot["count"] = int(slot["count"]) + take
            left -= take
            if left <= 0:
                return 0
    for i, slot in enumerate(slots):
        if i >= size and not allow_overflow:
            break
        if slot is None:
            take = min(cap, left)
            slots[i] = _with_tier(item, take, want)
            left -= take
            if left <= 0:
                return 0
    if allow_overflow and left > 0:
        while left > 0:
            take = min(cap, left)
            slots.append(_with_tier(item, take, want))
            left -= take
    state[CHEST_KEY] = slots
    return left


def player_at_build_tile(state: dict, player: str | None, rules: dict | None = None) -> bool:
    if not player:
        return False
    from hills import player_area, AREA_CABIN
    from engine import player_where

    if player_area(state, player) != AREA_CABIN:
        return False
    row, col = player_where(state, player)
    want = build_tile(rules)
    return (row, col) == want


def _have_cost(state: dict, player: str, cost: dict[str, int], rules: dict | None = None) -> tuple[bool, str]:
    from inventory import item_name, pack_has, stack_count, chest_of

    missing = []
    for item, need in cost.items():
        have = 0
        if player:
            from inventory import pack_of

            have += stack_count(pack_of(state, player, rules), item)
        if chest_is_built(state):
            have += stack_count(chest_of(state, rules), item)
        if have < need:
            missing.append(item_name(item, need, state=state))
    if missing:
        return False, "Need " + " and ".join(missing) + "."
    return True, ""


def _pay_cost(state: dict, player: str, cost: dict[str, int], rules: dict | None = None) -> None:
    """Spend from the pack first, then the chest."""
    from inventory import remove_from_pack, remove_from_chest

    for item, need in cost.items():
        left = need
        if player:
            left -= remove_from_pack(state, player, item, left, rules)
        if left > 0 and chest_is_built(state):
            left -= remove_from_chest(state, item, left, rules)


def place_starting_goods(state: dict, crops: dict | None = None, rules: dict | None = None) -> bool:
    """Put starting tools and seeds on the cabin chest-site floor. Once only.

    New games have no chest; the hoe, shovel, axe, two watering cans, and
    the starting strawberry seeds sit on the floor at row 1 col 2 (the
    tile where the chest is later built).
    """
    if state.get(STARTING_GOODS_KEY):
        return False
    if chest_is_built(state):
        state[STARTING_GOODS_KEY] = True
        return False
    from inventory import (
        starting_tool_counts,
        add_to_ground,
        world_item_count,
    )
    from hills import AREA_CABIN

    rules = _load_rules(rules)
    crops = crops or {}
    row, col = build_tile(rules)
    for item, need in starting_tool_counts(rules).items():
        have = world_item_count(state, item, rules)
        if have < need:
            add_to_ground(state, AREA_CABIN, row, col, item, need - have, rules=rules)
    starting = crops.get("starting_inventory") if isinstance(crops, dict) else None
    if isinstance(starting, dict):
        for key, val in starting.items():
            try:
                n = int(val or 0)
            except (TypeError, ValueError):
                n = 0
            if n <= 0:
                continue
            have = world_item_count(state, key, rules)
            if have < n:
                add_to_ground(state, AREA_CABIN, row, col, key, n - have, rules=rules)
    state[STARTING_GOODS_KEY] = True
    return True


def migrate_chest(state: dict, crops: dict | None = None, rules: dict | None = None) -> bool:
    """Install chest fields. Grandfather an existing chest; never delete items.

    A save that already has a `chest` key (the live farm, or any older game)
    becomes a built wooden (base) chest of 12 slots. If it holds more stacks
    than 12, the extras stay as overflow — nothing is deleted, and the chest
    is not auto-upgraded. Brand-new games have no chest; starting tools go
    on the cabin floor.
    """
    rules = _load_rules(rules)
    changed = False
    built = state.get(BUILT_KEY)
    has_key = CHEST_KEY in state
    raw = state.get(CHEST_KEY)
    has_items = False
    if isinstance(raw, list):
        has_items = any(s and isinstance(s, dict) and s.get("item") for s in raw)
    elif isinstance(raw, dict):
        has_items = any(raw.values())

    if built is True or (built is None and has_key):
        before = list(raw) if isinstance(raw, list) else raw
        before_tier = state.get(TIER_KEY)
        before_built = state.get(BUILT_KEY)
        install_built_chest(state, rules, tier=state.get(TIER_KEY) or TIER_WOOD)
        if state.get(BUILT_KEY) != before_built or state.get(TIER_KEY) != before_tier or state.get(CHEST_KEY) != before:
            changed = True
        if not state.get(STARTING_GOODS_KEY):
            state[STARTING_GOODS_KEY] = True
            changed = True
        return changed

    if built is not False:
        state[BUILT_KEY] = False
        changed = True
    if has_key and not has_items and not chest_is_built(state):
        # A leftover empty list from a new-game helper; drop the key.
        state.pop(CHEST_KEY, None)
        changed = True
    if place_starting_goods(state, crops, rules):
        changed = True
    elif not state.get(STARTING_GOODS_KEY):
        state[STARTING_GOODS_KEY] = True
        changed = True
    return changed


def build_chest(state: dict, player: str, rules: dict | None = None, crops=None) -> tuple[bool, str]:
    """Spend 5 wood at the cabin chest site and place a 12-slot wooden chest."""
    from engine import log_append, display_name
    from inventory import sync_inventory_view, item_name

    rules = _load_rules(rules)
    if chest_is_built(state):
        return False, f"The {chest_display_name(state, rules)} is already built."
    if not player_at_build_tile(state, player, rules):
        row, col = build_tile(rules)
        return False, (
            f"Stand at row {row} col {col} in the cabin (the north-wall nook) to build a chest."
        )
    cost = build_cost(rules)
    ok, err = _have_cost(state, player, cost, rules)
    if not ok:
        parts = " and ".join(item_name(k, v, crops, state=state) for k, v in cost.items())
        return False, f"Building a chest needs {parts}. {err}"
    _pay_cost(state, player, cost, rules)
    install_built_chest(state, rules, tier=TIER_WOOD)
    sync_inventory_view(state, rules)
    msg = (
        f"{display_name(player)} builds a wooden chest at the north wall. "
        "It holds 12 slots, with stacks of 16."
    )
    log_append(state, msg, player)
    return True, msg


def upgrade_chest(state: dict, player: str, rules: dict | None = None, crops=None) -> tuple[bool, str]:
    """Upgrade the banding and slot count: copper, then iron, then gold."""
    from engine import log_append, display_name
    from inventory import sync_inventory_view, item_name
    from cabin import player_at_cabin_tile

    rules = _load_rules(rules)
    if not chest_is_built(state):
        row, col = build_tile(rules)
        return False, f"There isn't a chest yet. Stand at row {row} col {col} in the cabin and build one (5 wood)."
    nxt = next_tier(state, rules)
    if not nxt:
        return False, f"The {chest_display_name(state, rules)} is already fully upgraded."
    if not player_at_cabin_tile(state, player, "chest"):
        return False, "Stand at the chest to upgrade it."
    cost = upgrade_cost(state, rules)
    ok, err = _have_cost(state, player, cost, rules)
    if not ok:
        parts = " and ".join(item_name(k, v, crops, state=state) for k, v in cost.items())
        return False, f"Upgrading the chest to {nxt} needs {parts}. {err}"
    _pay_cost(state, player, cost, rules)
    state[TIER_KEY] = nxt
    # Re-pad to the new slot count; keep any leftover overflow if still over.
    chest_slots(state, rules)
    sync_inventory_view(state, rules)
    info = chest_tier_info(state, rules)
    msg = (
        f"{display_name(player)} upgrades the chest with {nxt} banding. "
        f"It now has {int(info['slots'])} slots."
    )
    log_append(state, msg, player)
    return True, msg


def swap_chest_slots(state: dict, a: int, b: int, rules: dict | None = None) -> tuple[bool, str]:
    if not chest_is_built(state):
        return False, "There isn't a chest yet."
    slots = chest_slots(state, rules)
    try:
        i, j = int(a), int(b)
    except (TypeError, ValueError):
        return False, "Use chest slot numbers starting at 1."
    if i < 1 or j < 1 or i > len(slots) or j > len(slots):
        return False, "That chest slot is not on this chest."
    slots[i - 1], slots[j - 1] = slots[j - 1], slots[i - 1]
    state[CHEST_KEY] = slots
    return True, "The chest is rearranged."


def move_pack_chest_slot(
    state: dict,
    player: str,
    src: str,
    src_i: int,
    dest: str,
    dest_i: int,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Move one stack between a pack slot and a chest slot (1-indexed)."""
    from inventory import pack_of, pack_slots, sync_inventory_view, item_name, max_stack_for, is_tool, stack_tool_tier

    src = (src or "").strip().lower()
    dest = (dest or "").strip().lower()
    if src not in {"pack", "chest"} or dest not in {"pack", "chest"}:
        return False, "Move a stack between pack and chest slots."
    if src == dest == "chest":
        return swap_chest_slots(state, src_i, dest_i, rules)
    if src == dest == "pack":
        pack = pack_of(state, player, rules)
        try:
            i, j = int(src_i), int(dest_i)
        except (TypeError, ValueError):
            return False, "Use backpack slot numbers starting at 1."
        if i < 1 or j < 1 or i > len(pack) or j > len(pack):
            return False, "That backpack slot is empty or missing."
        pack[i - 1], pack[j - 1] = pack[j - 1], pack[i - 1]
        sync_inventory_view(state, rules)
        return True, "The backpack is rearranged."
    if not chest_is_built(state):
        return False, "There isn't a chest yet."
    pack = pack_of(state, player, rules)
    chest = chest_slots(state, rules)
    size = chest_slot_count(state, rules)
    try:
        si, di = int(src_i), int(dest_i)
    except (TypeError, ValueError):
        return False, "Use slot numbers starting at 1."
    if src == "pack":
        if si < 1 or si > len(pack):
            return False, "That backpack slot is missing."
        if di < 1 or di > max(len(chest), size):
            return False, "That chest slot is not on this chest."
        if di > size:
            return False, "That chest slot is overflow; take something out first."
        moving = pack[si - 1]
        target = chest[di - 1] if di <= len(chest) else None
        pack[si - 1], chest[di - 1] = target, moving
    else:
        if si < 1 or si > len(chest):
            return False, "That chest slot is missing."
        if di < 1 or di > len(pack):
            return False, "That backpack slot is missing."
        moving = chest[si - 1]
        target = pack[di - 1]
        chest[si - 1], pack[di - 1] = target, moving
    state[CHEST_KEY] = chest
    sync_inventory_view(state, rules)
    return True, "Moved."


def public_chest(state: dict, rules: dict | None = None) -> dict:
    """Safe payload for the web UI: no credentials."""
    rules = _load_rules(rules)
    row, col = build_tile(rules)
    if not chest_is_built(state):
        return {
            "built": False,
            "tier": None,
            "name": "chest",
            "slots": 0,
            "rows": 0,
            "cols": 0,
            "stack": chest_stack_limit(rules),
            "band": None,
            "items": [],
            "overflow": 0,
            "build_row": row,
            "build_col": col,
            "build_cost": build_cost(rules),
            "upgrade_cost": {},
            "next_tier": None,
        }
    info = chest_tier_info(state, rules)
    slots = chest_slots(state, rules)
    size = int(info["slots"])
    overflow = max(0, filled_count(slots) - size)
    items = []
    for slot in slots:
        if not slot or not slot.get("item"):
            items.append(None)
        else:
            items.append(dict(slot))
    return {
        "built": True,
        "tier": chest_tier(state, rules),
        "name": chest_display_name(state, rules),
        "slots": size,
        "rows": int(info.get("rows") or 1),
        "cols": int(info.get("cols") or 12),
        "stack": chest_stack_limit(rules),
        "band": chest_band_color(state, rules),
        "items": items,
        "overflow": overflow,
        "build_row": row,
        "build_col": col,
        "build_cost": build_cost(rules),
        "upgrade_cost": upgrade_cost(state, rules),
        "next_tier": next_tier(state, rules),
    }

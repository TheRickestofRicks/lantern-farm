"""Worn clothes, boots, and the hands slot for Lantern Farm.

The backpack stays four general slots. Each player also has clothes, boots,
and hands. Leather boots are equipped on migrate so walking still costs 5.
Hiking boots (honour store, 50G) cost 4 per step in the hills and the mine.
A Nimble enchant (Creation Table, aurora night, overall level 10) subtracts
1 from a paid step; cabin walking stays free.
"""

from __future__ import annotations

from typing import Any

SLOT_CLOTHES = "clothes"
SLOT_BOOTS = "boots"
SLOT_HANDS = "hands"
GEAR_SLOTS = (SLOT_CLOTHES, SLOT_BOOTS, SLOT_HANDS)

LEATHER_BOOTS = "leather_boots"
HIKING_BOOTS = "hiking_boots"
DEFAULT_HIKING_PRICE = 50
DEFAULT_MOVE = 5
DEFAULT_HIKING_MOVE = 4
HIKING_AREAS = frozenset({"hills", "mine"})

BLUE_SWEATER = "blue_sweater"
GREEN_HOODIE = "green_hoodie"

CLOTHES = {
    BLUE_SWEATER: {
        "name": "blue sweater",
        "name_plural": "blue sweaters",
        "description": "A soft blue sweater. Cosmetic only.",
    },
    GREEN_HOODIE: {
        "name": "green hoodie",
        "name_plural": "green hoodies",
        "description": "A green hoodie. Cosmetic only.",
    },
}

BOOTS = {
    LEATHER_BOOTS: {
        "name": "leather boots",
        "name_plural": "leather boots",
        "shop": False,
        "description": "Sturdy everyday boots. Walking costs 5 energy everywhere except inside the cabin, which is free.",
    },
    HIKING_BOOTS: {
        "name": "hiking boots",
        "name_plural": "hiking boots",
        "price": DEFAULT_HIKING_PRICE,
        "description": (
            "Sure-footed boots for rough ground. Walking costs 4 energy in the "
            "hills and the mine, and 5 everywhere else on the farm or in town. "
            "Cabin walking stays free."
        ),
    },
}

ENCHANT_NIMBLE = "nimble"


def is_clothes(item: str | None) -> bool:
    return (item or "") in CLOTHES


def is_boots(item: str | None) -> bool:
    return (item or "") in BOOTS


def clothes_info(item: str | None) -> dict | None:
    item = item or ""
    if item not in CLOTHES:
        return None
    return dict(CLOTHES[item])


def boots_info(item: str | None, rules: dict | None = None) -> dict | None:
    item = item or ""
    if item not in BOOTS:
        return None
    info = dict(BOOTS[item])
    custom = None
    if isinstance(rules, dict):
        block = rules.get("boots")
        if isinstance(block, dict) and isinstance(block.get(item), dict):
            custom = block[item]
    if isinstance(custom, dict):
        info.update(custom)
    if info.get("price") is not None:
        try:
            info["price"] = int(info["price"])
        except (TypeError, ValueError):
            info["price"] = BOOTS[item].get("price")
    return info


def hiking_boots_price(rules: dict | None = None) -> int:
    info = boots_info(HIKING_BOOTS, rules) or BOOTS[HIKING_BOOTS]
    try:
        return max(0, int(info.get("price") or DEFAULT_HIKING_PRICE))
    except (TypeError, ValueError):
        return DEFAULT_HIKING_PRICE


def starting_clothes_item(player: str | None) -> str | None:
    """Optional starting clothes from the player record in config.

    Tests stay free of cosmetics unless a player record sets starting_clothes.
    """
    if not player:
        return None
    try:
        from config import player_record
    except Exception:
        return None
    rec = player_record(player) or {}
    raw = rec.get("starting_clothes") or rec.get("clothes")
    from inventory import normalize_item

    item = normalize_item(str(raw or "").strip())
    if item and is_clothes(item):
        return item
    # Lumen's signature sweater, keyed only on the configured id/name "lumen".
    pid = str(rec.get("id") or player or "").strip().lower()
    name = str(rec.get("name") or "").strip().lower()
    if pid == "lumen" or name == "lumen":
        return BLUE_SWEATER
    return None


def _as_stack(slot: Any, *, allowed) -> dict | None:
    from inventory import _clean_stack

    cleaned = _clean_stack(slot, in_chest=False)
    if not cleaned:
        return None
    item = cleaned.get("item")
    if item not in allowed and not (allowed is True):
        # allowed may be a container or a predicate
        if callable(allowed):
            if not allowed(item):
                return None
        elif item not in allowed:
            return None
    return cleaned


def gear_of(state: dict, player: str | None, kind: str) -> dict | None:
    if not player or kind not in GEAR_SLOTS:
        return None
    from engine import player_slot

    slot = player_slot(state, player)
    raw = slot.get(kind)
    if not raw:
        return None
    if kind == SLOT_CLOTHES:
        return _as_stack(raw, allowed=CLOTHES)
    if kind == SLOT_BOOTS:
        return _as_stack(raw, allowed=BOOTS)
    from inventory import is_tool

    return _as_stack(raw, allowed=is_tool)


def set_gear(state: dict, player: str, kind: str, stack: dict | None) -> None:
    from engine import player_slot

    slot = player_slot(state, player)
    if stack and stack.get("item") and int(stack.get("count") or 0) > 0:
        slot[kind] = stack
    else:
        slot[kind] = None


def gear_item(state: dict, player: str | None, kind: str) -> str | None:
    stack = gear_of(state, player, kind)
    return str(stack.get("item")) if stack else None


def boots_enchant(state: dict, player: str | None) -> str | None:
    from inventory import stack_enchant

    return stack_enchant(gear_of(state, player, SLOT_BOOTS))


def held_tool_slot(state: dict, player: str | None, tool: str | None = None):
    """The hands stack, or a matching tool in the pack, or None."""
    from inventory import normalize_item, pack_of

    want = normalize_item(tool) if tool else None
    hands = gear_of(state, player, SLOT_HANDS)
    if hands:
        if not want or normalize_item(hands.get("item")) == want:
            return hands, "hands", 0
    if not player:
        return None, None, None
    for i, slot in enumerate(pack_of(state, player)):
        if not slot:
            continue
        if want and normalize_item(slot.get("item")) != want:
            continue
        if not want:
            continue
        return slot, "pack", i
    return None, None, None


def migrate_player_gear(state: dict, rules: dict | None = None) -> bool:
    """Equip leather boots, fill starting clothes, and add XP maps. Idempotent."""
    del rules
    from engine import known_players, player_slot
    from inventory import empty_pack, normalize_pack, _with_tier
    from xp import empty_xp, SKILLS

    changed = False
    if "table_built" not in state:
        state["table_built"] = False
        changed = True

    names = list((state.get("players") or {}).keys()) or list(known_players())
    for name in names:
        slot = player_slot(state, name)
        if "pack" not in slot:
            slot["pack"] = empty_pack()
            changed = True
        else:
            normalized = normalize_pack(slot.get("pack"))
            if slot.get("pack") != normalized:
                slot["pack"] = normalized
                changed = True
        if SLOT_CLOTHES not in slot:
            item = starting_clothes_item(name)
            slot[SLOT_CLOTHES] = _with_tier(item, 1) if item else None
            changed = True
        if SLOT_BOOTS not in slot:
            slot[SLOT_BOOTS] = _with_tier(LEATHER_BOOTS, 1)
            changed = True
        if SLOT_HANDS not in slot:
            slot[SLOT_HANDS] = None
            changed = True
        raw_xp = slot.get("xp")
        if not isinstance(raw_xp, dict):
            slot["xp"] = empty_xp()
            changed = True
        else:
            for skill in SKILLS:
                if skill not in raw_xp:
                    raw_xp[skill] = 0
                    changed = True
                else:
                    try:
                        raw_xp[skill] = max(0, int(raw_xp[skill] or 0))
                    except (TypeError, ValueError):
                        raw_xp[skill] = 0
                        changed = True
    return changed


def gear_stacks(state: dict, player: str | None) -> list[dict]:
    """Non-empty worn/held stacks, for world counts."""
    out = []
    for kind in GEAR_SLOTS:
        stack = gear_of(state, player, kind)
        if stack:
            out.append(stack)
    return out


def gear_item_count(state: dict, player: str | None, item: str) -> int:
    from inventory import normalize_item

    want = normalize_item(item) or item
    total = 0
    for stack in gear_stacks(state, player):
        if stack.get("item") == want:
            total += int(stack.get("count") or 0)
    return total


def move_step_cost(
    state: dict | None,
    player: str | None,
    area: str | None,
    rules: dict | None = None,
    default: int = DEFAULT_MOVE,
) -> int:
    """Energy for one paid step in this area. Cabin callers should pass 0 instead."""
    from hills import AREA_CABIN, normalize_area

    area = normalize_area(area) if area else ""
    if area == AREA_CABIN:
        return 0
    cost = int(default)
    hiking_cost = DEFAULT_HIKING_MOVE
    hiking_areas = set(HIKING_AREAS)
    if isinstance(rules, dict):
        movement = rules.get("movement") if isinstance(rules.get("movement"), dict) else {}
        try:
            if movement.get("default") is not None:
                cost = int(movement.get("default"))
        except (TypeError, ValueError):
            pass
        try:
            if movement.get("hiking_boots") is not None:
                hiking_cost = int(movement.get("hiking_boots"))
        except (TypeError, ValueError):
            pass
        extra = movement.get("hiking_areas")
        if isinstance(extra, list) and extra:
            hiking_areas = {str(a).strip().lower() for a in extra}
    if gear_item(state, player, SLOT_BOOTS) == HIKING_BOOTS and area in hiking_areas:
        cost = hiking_cost
    if boots_enchant(state, player) == ENCHANT_NIMBLE:
        cost = max(0, cost - 1)
    return cost


def _pack_index(raw) -> tuple[int | None, str | None]:
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return None, "Use a backpack slot number starting at 1."
    if idx < 1:
        return None, "Use a backpack slot number starting at 1."
    return idx, None


def equip_from_pack(
    state: dict,
    player: str,
    pack_n,
    dest: str,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Move a pack slot into clothes, boots, or hands, swapping if needed."""
    from inventory import pack_of, is_tool, item_label, sync_inventory_view

    dest = str(dest or "").strip().lower()
    if dest not in GEAR_SLOTS:
        return False, "Equip to clothes, boots, or hands."
    idx, err = _pack_index(pack_n)
    if err:
        return False, err
    pack = pack_of(state, player, rules)
    if idx > len(pack):
        return False, "That backpack slot is empty."
    src = pack[idx - 1]
    if not src or not src.get("item"):
        return False, "That backpack slot is empty."
    item = src.get("item")
    if dest == SLOT_CLOTHES and not is_clothes(item):
        return False, f"{item_label(item, state=state)} is not clothing."
    if dest == SLOT_BOOTS and not is_boots(item):
        return False, f"{item_label(item, state=state)} are not boots."
    if dest == SLOT_HANDS and not is_tool(item):
        return False, f"{item_label(item, state=state)} cannot be held in your hands."
    worn = gear_of(state, player, dest)
    pack[idx - 1] = worn  # may be None
    set_gear(state, player, dest, src)
    sync_inventory_view(state, rules)
    label = item_label(item, state=state)
    if dest == SLOT_HANDS:
        return True, f"You take the {label} in your hands."
    if dest == SLOT_BOOTS:
        return True, f"You pull on the {label}."
    return True, f"You put on the {label}."


def unequip_to_pack(
    state: dict,
    player: str,
    kind: str,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Move worn/held gear into the first empty pack slot."""
    from inventory import pack_of, item_label, sync_inventory_view

    kind = str(kind or "").strip().lower()
    if kind not in GEAR_SLOTS:
        return False, "Unequip clothes, boots, or hands."
    worn = gear_of(state, player, kind)
    if not worn:
        return False, f"Nothing is in your {kind} slot."
    pack = pack_of(state, player, rules)
    empty = next((i for i, slot in enumerate(pack) if not slot), None)
    if empty is None:
        return False, "Your backpack is full. Make a space first."
    pack[empty] = worn
    set_gear(state, player, kind, None)
    sync_inventory_view(state, rules)
    label = item_label(worn.get("item"), state=state)
    if kind == SLOT_HANDS:
        return True, f"You put the {label} away."
    return True, f"You take off the {label}."


def gear_view(state: dict, player: str | None, rules: dict | None = None) -> dict:
    """Inventory-window payload for worn slots (plus pack is sent separately)."""
    from inventory import pack_of
    from xp import xp_view

    def _copy(stack):
        if not stack:
            return None
        out = dict(stack)
        return out

    return {
        "clothes": _copy(gear_of(state, player, SLOT_CLOTHES)),
        "boots": _copy(gear_of(state, player, SLOT_BOOTS)),
        "hands": _copy(gear_of(state, player, SLOT_HANDS)),
        "pack": [(_copy(s) if s else None) for s in pack_of(state, player, rules)],
        "xp": xp_view(state, player, rules),
    }

"""Creation Table: build, craft runestones, and aurora-night enchants."""

from __future__ import annotations

TABLE_KEY = "table_built"
DEFAULT_ROW = 2
DEFAULT_COL = 2
RUNESTONE = "runestone"
RUNESTONE_ORE = "runestone_ore"

ENCHANT_IMPROVED = "improved_yield"
ENCHANT_SUPERIOR = "superior_yield"
ENCHANT_NIMBLE = "nimble"

PICKAXE_ENCHANTS = (ENCHANT_IMPROVED, ENCHANT_SUPERIOR)


def _rules(rules: dict | None = None) -> dict:
    if rules is not None:
        return rules
    from engine import load_rules

    return load_rules()


def creation_rules(rules: dict | None = None) -> dict:
    raw = _rules(rules).get("creation")
    return raw if isinstance(raw, dict) else {}


def table_tile(rules: dict | None = None) -> tuple[int, int]:
    cfg = creation_rules(rules).get("table") or {}
    try:
        row = int(cfg.get("row") or DEFAULT_ROW)
        col = int(cfg.get("col") or DEFAULT_COL)
    except (TypeError, ValueError):
        row, col = DEFAULT_ROW, DEFAULT_COL
    return row, col


def table_is_built(state: dict | None) -> bool:
    return bool(state and state.get(TABLE_KEY))


def player_at_table_site(state: dict, player: str | None, rules: dict | None = None) -> bool:
    if not player:
        return False
    from hills import player_area, AREA_CABIN
    from engine import player_where

    if player_area(state, player) != AREA_CABIN:
        return False
    row, col = player_where(state, player)
    want = table_tile(rules)
    return (row, col) == want


def is_aurora(state: dict | None) -> bool:
    return str((state or {}).get("weather") or "") == "aurora"


def runestone_recipe(rules: dict | None = None) -> dict:
    cfg = creation_rules(rules).get("runestone") or {}
    try:
        ore = max(1, int(cfg.get("ore") or 1))
    except (TypeError, ValueError):
        ore = 1
    try:
        out = max(1, int(cfg.get("out") or 1))
    except (TypeError, ValueError):
        out = 1
    try:
        energy = max(0, int(cfg.get("energy") or 5))
    except (TypeError, ValueError):
        energy = 5
    return {"ore": ore, "out": out, "energy": energy}


def enchant_info(kind: str, rules: dict | None = None) -> dict | None:
    kind = normalize_enchant(kind)
    if not kind:
        return None
    block = (creation_rules(rules).get("enchants") or {}).get(kind)
    if not isinstance(block, dict):
        return None
    info = dict(block)
    info["id"] = kind
    return info


def normalize_enchant(raw: str | None) -> str | None:
    text = " ".join(str(raw or "").strip().lower().replace("-", " ").split())
    if not text:
        return None
    aliases = {
        "improved yield": ENCHANT_IMPROVED,
        "improved_yield": ENCHANT_IMPROVED,
        "improved": ENCHANT_IMPROVED,
        "superior yield": ENCHANT_SUPERIOR,
        "superior_yield": ENCHANT_SUPERIOR,
        "superior": ENCHANT_SUPERIOR,
        "nimble": ENCHANT_NIMBLE,
    }
    return aliases.get(text) or aliases.get(text.replace(" ", "_"))


def enchant_energy(kind: str, rules: dict | None = None) -> int:
    info = enchant_info(kind, rules) or {}
    try:
        return max(0, int(info.get("energy") or 0))
    except (TypeError, ValueError):
        return 0


def build_table(state: dict, player: str, rules: dict | None = None, crops=None) -> tuple[bool, str]:
    """Place the Creation Table at cabin row 2 col 2. Free to build."""
    del crops
    from engine import log_append, display_name

    rules = _rules(rules)
    if table_is_built(state):
        return False, "The Creation Table is already built."
    if not player_at_table_site(state, player, rules):
        row, col = table_tile(rules)
        return False, (
            f"Stand at row {row} col {col} in the cabin (the middle of the room) "
            "to build the Creation Table."
        )
    state[TABLE_KEY] = True
    msg = (
        f"{display_name(player)} sets up the Creation Table in the middle of the cabin. "
        "Craft runestones here any day; on an aurora night you can enchant a pickaxe or boots."
    )
    log_append(state, msg, player)
    return True, msg


def craft_runestone(
    state: dict,
    player: str,
    rules: dict | None = None,
    crops=None,
    count: int = 1,
) -> tuple[bool, str]:
    """Turn runestone ore into runestones at the Creation Table, any weather."""
    from engine import log_append, display_name, who
    from inventory import pack_has, take_available, give_or_drop_at_player, item_name, item_label

    rules = _rules(rules)
    if not table_is_built(state):
        row, col = table_tile(rules)
        return False, (
            f"There is no Creation Table yet. Stand at row {row} col {col} in the cabin "
            "and build one (free)."
        )
    if not player_at_table_site(state, player, rules):
        return False, "Stand at the Creation Table to craft runestones."
    rec = runestone_recipe(rules)
    try:
        times = int(count or 1)
    except (TypeError, ValueError):
        times = 1
    if times < 1:
        return False, "Craft at least one runestone."
    need = rec["ore"] * times
    if not pack_has(state, player, RUNESTONE_ORE, need, rules):
        return False, (
            f"Crafting {item_name(RUNESTONE, times, crops, rules, state=state)} needs "
            f"{item_name(RUNESTONE_ORE, need, crops, rules, state=state)} in the backpack."
        )
    taken = take_available(state, RUNESTONE_ORE, need, player, pack_only=True, rules=rules)
    if taken < need:
        return False, (
            f"Crafting needs {item_name(RUNESTONE_ORE, need, crops, rules, state=state)} "
            "in the backpack."
        )
    made = rec["out"] * times
    packed, dropped, phrase = give_or_drop_at_player(state, player, RUNESTONE, made, rules)
    del packed, dropped
    noun = item_label(RUNESTONE, crops, rules, state=state)
    if times == 1:
        msg = f"{who(player, 'craft', 'crafts')} a {noun} at the Creation Table {phrase}."
    else:
        msg = (
            f"{who(player, 'craft', 'crafts')} "
            f"{item_name(RUNESTONE, made, crops, rules, state=state)} at the Creation Table {phrase}."
        )
    # phrase already includes "and packs …" or a full sentence; tidy double spaces
    msg = " ".join(msg.split())
    if msg.endswith(".."):
        msg = msg[:-1]
    log_append(state, msg, player)
    return True, msg


def _need_aurora() -> str:
    return "Enchants can only be worked at the Creation Table on an aurora night."


def _check_table(state: dict, player: str, rules: dict | None) -> str | None:
    if not table_is_built(state):
        row, col = table_tile(rules)
        return (
            f"There is no Creation Table yet. Stand at row {row} col {col} in the cabin "
            "and build one (free)."
        )
    if not player_at_table_site(state, player, rules):
        return "Stand at the Creation Table to work an enchant."
    if not is_aurora(state):
        return _need_aurora()
    return None


def _pay_runestones(state: dict, player: str, need: int, rules: dict | None) -> str | None:
    from inventory import pack_has, take_available, item_name

    if need <= 0:
        return None
    if not pack_has(state, player, RUNESTONE, need, rules):
        return f"This enchant needs {item_name(RUNESTONE, need, state=state)} in the backpack."
    taken = take_available(state, RUNESTONE, need, player, pack_only=True, rules=rules)
    if taken < need:
        return f"This enchant needs {item_name(RUNESTONE, need, state=state)} in the backpack."
    return None


def enchant_pickaxe(
    state: dict,
    player: str,
    kind: str,
    rules: dict | None = None,
    crops=None,
) -> tuple[bool, str]:
    """Apply Improved or Superior Yield to the player's pickaxe (hands, then pack)."""
    del crops
    from engine import log_append, display_name
    from inventory import TOOL_PICKAXE, item_label, stack_enchant, sync_inventory_view
    from gear import held_tool_slot
    from xp import skill_level
    from mine import tool_tier

    rules = _rules(rules)
    kind = normalize_enchant(kind)
    if kind not in PICKAXE_ENCHANTS:
        return False, "Enchant the pickaxe with Improved Yield or Superior Yield."
    blocked = _check_table(state, player, rules)
    if blocked:
        return False, blocked
    info = enchant_info(kind, rules) or {}
    need_skill = int(info.get("skill_level") or 0)
    have = skill_level(state, player, "mining", rules)
    if have < need_skill:
        return False, (
            f"{info.get('name') or 'This enchant'} needs mining level {need_skill} "
            f"(you are mining level {have})."
        )
    slot, where, _idx = held_tool_slot(state, player, TOOL_PICKAXE)
    if not slot:
        return False, (
            f"{display_name(player)} needs a pickaxe in their hands or backpack to enchant it."
        )
    current = stack_enchant(slot)
    if current == kind:
        return False, f"This pickaxe already has {info.get('name') or kind}."
    if kind == ENCHANT_IMPROVED and current == ENCHANT_SUPERIOR:
        return False, "This pickaxe already has Superior Yield, which is stronger."
    need = int(info.get("runestones") or 0)
    err = _pay_runestones(state, player, need, rules)
    if err:
        return False, err
    # pack_of rewrites the pack list; look the tool up again after paying.
    slot, where, _idx = held_tool_slot(state, player, TOOL_PICKAXE)
    if not slot:
        return False, (
            f"{display_name(player)} needs a pickaxe in their hands or backpack to enchant it."
        )
    slot["enchant"] = kind
    sync_inventory_view(state, rules)
    tier = tool_tier(state, TOOL_PICKAXE, player=player)
    del tier
    noun = item_label(TOOL_PICKAXE, state=state)
    where_txt = "in their hands" if where == "hands" else "in their backpack"
    msg = (
        f"{display_name(player)} works {info.get('name') or kind} into the {noun} "
        f"{where_txt} at the Creation Table."
    )
    log_append(state, msg, player)
    return True, msg


def enchant_boots(
    state: dict,
    player: str,
    rules: dict | None = None,
    crops=None,
) -> tuple[bool, str]:
    """Apply Nimble to the boots the player is wearing."""
    del crops
    from engine import log_append, display_name
    from inventory import item_label, stack_enchant, sync_inventory_view
    from gear import gear_of, SLOT_BOOTS, ENCHANT_NIMBLE as NIMBLE
    from xp import overall_level, overall_cap

    rules = _rules(rules)
    blocked = _check_table(state, player, rules)
    if blocked:
        return False, blocked
    info = enchant_info(ENCHANT_NIMBLE, rules) or {}
    need_level = int(info.get("overall_level") or 10)
    have = overall_level(state, player, rules)
    cap = overall_cap(rules)
    if have < need_level:
        return False, (
            f"Nimble needs overall level {need_level} out of {cap} (you are overall level {have} out of {cap})."
        )
    boots = gear_of(state, player, SLOT_BOOTS)
    if not boots:
        return False, "Put on a pair of boots first, then enchant them at the table."
    if stack_enchant(boots) == NIMBLE:
        return False, "These boots already have Nimble."
    need = int(info.get("runestones") or 0)
    err = _pay_runestones(state, player, need, rules)
    if err:
        return False, err
    boots["enchant"] = NIMBLE
    from gear import set_gear

    set_gear(state, player, SLOT_BOOTS, boots)
    sync_inventory_view(state, rules)
    label = item_label(boots.get("item"), state=state)
    msg = (
        f"{display_name(player)} works Nimble into the {label} at the Creation Table. "
        "Paid steps cost 1 less energy; walking inside the cabin stays free."
    )
    log_append(state, msg, player)
    return True, msg


def enchant(
    state: dict,
    player: str,
    args: list[str],
    rules: dict | None = None,
    crops=None,
) -> tuple[bool, str]:
    """Parse `enchant pickaxe improved yield`, `enchant boots nimble`, etc."""
    text = " ".join(str(a) for a in (args or [])).strip().lower()
    if not text:
        return False, (
            "Usage: enchant pickaxe improved yield, enchant pickaxe superior yield, "
            "or enchant boots nimble."
        )
    kind = normalize_enchant(text)
    if kind is None:
        # "pickaxe improved yield" / "boots nimble"
        for prefix in ("pickaxe ", "the pickaxe ", "axe ", "boots ", "the boots "):
            if text.startswith(prefix):
                kind = normalize_enchant(text[len(prefix):])
                break
    if kind in PICKAXE_ENCHANTS:
        return enchant_pickaxe(state, player, kind, rules, crops)
    if kind == ENCHANT_NIMBLE or text in {"boots", "boots nimble", "nimble boots"}:
        return enchant_boots(state, player, rules, crops)
    return False, (
        "Usage: enchant pickaxe improved yield, enchant pickaxe superior yield, "
        "or enchant boots nimble."
    )


def legal_table_actions(state: dict, player: str, rules: dict | None = None) -> list[str]:
    """Actions available while standing on the table tile (built or not)."""
    from engine import energy_cost
    from engine import player_slot
    from inventory import pack_has
    from xp import skill_level, overall_level
    from inventory import TOOL_PICKAXE
    from gear import held_tool_slot, gear_of, SLOT_BOOTS
    from inventory import stack_enchant

    rules = _rules(rules)
    if not player_at_table_site(state, player, rules):
        return []
    energy = int(player_slot(state, player).get("energy") or 0)
    out: list[str] = []
    if not table_is_built(state):
        return out
    rec = runestone_recipe(rules)
    if pack_has(state, player, RUNESTONE_ORE, rec["ore"], rules) and energy >= rec["energy"]:
        out.append("craft runestone")
    if not is_aurora(state):
        return out
    # Enchants only when the player can actually do them.
    slot, _where, _idx = held_tool_slot(state, player, TOOL_PICKAXE)
    current = stack_enchant(slot) if slot else None
    for kind in PICKAXE_ENCHANTS:
        info = enchant_info(kind, rules) or {}
        need_lvl = int(info.get("skill_level") or 0)
        need_n = int(info.get("runestones") or 0)
        need_e = int(info.get("energy") or 0)
        if not slot:
            continue
        if current == kind or (kind == ENCHANT_IMPROVED and current == ENCHANT_SUPERIOR):
            continue
        if skill_level(state, player, "mining", rules) < need_lvl:
            continue
        if not pack_has(state, player, RUNESTONE, need_n, rules):
            continue
        if energy < need_e:
            continue
        if kind == ENCHANT_IMPROVED:
            out.append("enchant pickaxe improved yield")
        else:
            out.append("enchant pickaxe superior yield")
    boots = gear_of(state, player, SLOT_BOOTS)
    info = enchant_info(ENCHANT_NIMBLE, rules) or {}
    if (
        boots
        and stack_enchant(boots) != ENCHANT_NIMBLE
        and overall_level(state, player, rules) >= int(info.get("overall_level") or 10)
        and pack_has(state, player, RUNESTONE, int(info.get("runestones") or 0), rules)
        and energy >= int(info.get("energy") or 0)
    ):
        out.append("enchant boots nimble")
    return out


def table_view(state: dict, player: str | None, rules: dict | None = None) -> dict:
    rules = _rules(rules)
    row, col = table_tile(rules)
    rec = runestone_recipe(rules)
    enchants = {}
    for kind in (ENCHANT_IMPROVED, ENCHANT_SUPERIOR, ENCHANT_NIMBLE):
        info = enchant_info(kind, rules) or {}
        enchants[kind] = {
            "id": kind,
            "name": info.get("name") or kind,
            "runestones": int(info.get("runestones") or 0),
            "energy": int(info.get("energy") or 0),
            "skill": info.get("skill"),
            "skill_level": info.get("skill_level"),
            "overall_level": info.get("overall_level"),
        }
    return {
        "built": table_is_built(state),
        "row": row,
        "col": col,
        "aurora": is_aurora(state),
        "at_site": bool(player and player_at_table_site(state, player, rules)),
        "runestone": rec,
        "enchants": enchants,
        "legal": legal_table_actions(state, player, rules) if player else [],
    }

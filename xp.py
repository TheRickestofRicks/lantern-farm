"""Tunable experience-point amounts and skill levels for Lantern Farm.

Numbers live in a single ``xp`` table in ``rules.json`` so they are easy to
tune. XP is granted during play from that table. Each skill's level is capped
at 10; XP may still accumulate. Overall level uses the same thresholds on the
sum of all skill XP.
"""

from __future__ import annotations

# Fallback if rules.json has no xp table yet.
DEFAULT_XP = {
    "mining": {
        "stone": 2,
        "copper_ore": 5,
        "iron_ore": 8,
        "gold_ore": 12,
        "runestone_ore": 15,
        "gem_bonus": 5,
    },
    "woodcutting": {
        "tree": 5,
    },
    "farming": {
        "plant": 1,
        "harvest": 4,
        "water": 0,
    },
    "combat": {
        "slime": 10,
    },
}

SKILLS = ("mining", "woodcutting", "farming", "combat")

# Cumulative XP thresholds for levels 1 through 10.
DEFAULT_LEVELS = [0, 40, 100, 200, 350, 550, 800, 1100, 1500, 2000]
DEFAULT_LEVEL_CAP = 10

# Rock kinds currently placed on mine tiles (quartz is a gem drop, not a rock).
MINING_ROCKS = ("stone", "copper_ore", "iron_ore", "gold_ore", "runestone_ore")


def _load_rules(rules: dict | None = None) -> dict:
    if rules is not None:
        return rules
    from engine import load_rules

    return load_rules()


def xp_table(rules: dict | None = None) -> dict:
    """Return the xp table, filled with defaults for any missing section or key."""
    raw = _load_rules(rules).get("xp")
    table = {}
    if isinstance(raw, dict):
        table = raw
    out = {}
    for section, defaults in DEFAULT_XP.items():
        got = table.get(section)
        merged = dict(defaults)
        if isinstance(got, dict):
            for key, value in got.items():
                try:
                    merged[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
        out[section] = merged
    return out


def _section(name: str, rules: dict | None = None) -> dict:
    return xp_table(rules).get(name) or dict(DEFAULT_XP[name])


def _amount(section: dict, key: str, default: int = 0) -> int:
    try:
        return max(0, int(section.get(key, default)))
    except (TypeError, ValueError):
        return max(0, int(default))


def mining_xp(rock: str | None, *, gem: bool = False, rules: dict | None = None) -> int:
    """XP for breaking a rock. Add gem=True when a gem (such as quartz) drops."""
    mining = _section("mining", rules)
    kind = str(rock or "stone").strip().lower() or "stone"
    if kind == "gem_bonus":
        kind = "stone"
    amount = _amount(mining, kind, _amount(mining, "stone", 2))
    if gem:
        amount += _amount(mining, "gem_bonus", 5)
    return amount


def woodcutting_xp(kind: str = "tree", rules: dict | None = None) -> int:
    """XP for chopping a tree."""
    chopping = _section("woodcutting", rules)
    key = str(kind or "tree").strip().lower() or "tree"
    return _amount(chopping, key, _amount(chopping, "tree", 5))


def farming_xp(action: str, rules: dict | None = None) -> int:
    """XP for a farming action: plant, harvest, or water (water is 0)."""
    farming = _section("farming", rules)
    key = str(action or "").strip().lower()
    if key in {"pluck", "pick"}:
        key = "harvest"
    return _amount(farming, key, 0)


def combat_xp(kind: str | None = "slime", rules: dict | None = None) -> int:
    """XP for defeating a slime. Unknown kinds use the generic slime amount."""
    combat = _section("combat", rules)
    key = str(kind or "slime").strip().lower() or "slime"
    if key not in combat:
        key = "slime"
    return _amount(combat, key, 10)


def level_cap(rules: dict | None = None) -> int:
    raw = _load_rules(rules).get("xp")
    if isinstance(raw, dict) and raw.get("level_cap") is not None:
        try:
            return max(1, int(raw.get("level_cap")))
        except (TypeError, ValueError):
            pass
    return DEFAULT_LEVEL_CAP


def level_thresholds(rules: dict | None = None) -> list[int]:
    """Cumulative XP required to be at each level, starting at level 1 = 0."""
    raw = _load_rules(rules).get("xp")
    got = raw.get("levels") if isinstance(raw, dict) else None
    cap = level_cap(rules)
    out: list[int] = []
    if isinstance(got, list):
        for value in got:
            try:
                out.append(max(0, int(value)))
            except (TypeError, ValueError):
                continue
    if not out:
        out = list(DEFAULT_LEVELS)
    out = sorted(set(out))
    if not out or out[0] != 0:
        out = [0] + [n for n in out if n > 0]
    # Ensure we have `cap` entries (levels 1..cap).
    while len(out) < cap:
        prev = out[-1]
        step = out[-1] - out[-2] if len(out) >= 2 else 50
        out.append(prev + max(1, step))
    return out[:cap]


def level_for_xp(xp: int, rules: dict | None = None) -> int:
    """Skill or overall level for this much XP, capped at the level cap."""
    try:
        amount = max(0, int(xp or 0))
    except (TypeError, ValueError):
        amount = 0
    thresholds = level_thresholds(rules)
    level = 1
    for i, need in enumerate(thresholds, start=1):
        if amount >= need:
            level = i
        else:
            break
    return min(level, level_cap(rules))


def xp_into_level(xp: int, rules: dict | None = None) -> tuple[int, int, int | None]:
    """Return (level, xp into this level, xp needed for next or None if capped)."""
    thresholds = level_thresholds(rules)
    cap = level_cap(rules)
    level = level_for_xp(xp, rules)
    current = thresholds[level - 1] if 0 <= level - 1 < len(thresholds) else 0
    into = max(0, int(xp or 0) - current)
    if level >= cap or level >= len(thresholds):
        return level, into, None
    nxt = thresholds[level]
    return level, into, max(0, nxt - int(xp or 0))


def empty_xp() -> dict[str, int]:
    return {skill: 0 for skill in SKILLS}


def player_xp_map(state: dict, player: str | None) -> dict[str, int]:
    """Live XP map on the player's slot, filled with missing skills at 0."""
    from engine import player_slot

    out = empty_xp()
    if not player:
        return out
    slot = player_slot(state, player)
    raw = slot.get("xp")
    if not isinstance(raw, dict):
        raw = {}
        slot["xp"] = raw
    for skill in SKILLS:
        try:
            val = int(raw.get(skill) or 0)
        except (TypeError, ValueError):
            val = 0
        raw[skill] = max(0, val)
        out[skill] = raw[skill]
    return out


def total_xp(state: dict, player: str | None) -> int:
    return sum(player_xp_map(state, player).values())


def skill_level(state: dict, player: str | None, skill: str, rules: dict | None = None) -> int:
    amounts = player_xp_map(state, player)
    key = str(skill or "").strip().lower()
    return level_for_xp(int(amounts.get(key) or 0), rules)


def overall_level(state: dict, player: str | None, rules: dict | None = None) -> int:
    return level_for_xp(total_xp(state, player), rules)


def grant_xp(
    state: dict,
    player: str | None,
    skill: str,
    amount: int,
    rules: dict | None = None,
) -> int:
    """Add XP to a skill. Returns the amount actually granted (0 if none)."""
    del rules
    if not player:
        return 0
    try:
        add = int(amount or 0)
    except (TypeError, ValueError):
        add = 0
    if add <= 0:
        return 0
    key = str(skill or "").strip().lower()
    if key not in SKILLS:
        return 0
    amounts = player_xp_map(state, player)
    amounts[key] = int(amounts.get(key) or 0) + add
    from engine import player_slot

    player_slot(state, player)["xp"] = amounts
    return add


def xp_view(state: dict, player: str | None, rules: dict | None = None) -> dict:
    """Payload for the inventory window: overall level and per-skill progress."""
    amounts = player_xp_map(state, player)
    skills = {}
    for skill in SKILLS:
        xp = int(amounts.get(skill) or 0)
        level, into, needed = xp_into_level(xp, rules)
        skills[skill] = {
            "xp": xp,
            "level": level,
            "into": into,
            "next": needed,
            "capped": needed is None,
        }
    total = total_xp(state, player)
    level, into, needed = xp_into_level(total, rules)
    return {
        "total_xp": total,
        "overall_level": level,
        "overall_into": into,
        "overall_next": needed,
        "overall_capped": needed is None,
        "level_cap": level_cap(rules),
        "skills": skills,
    }

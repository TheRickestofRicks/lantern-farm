"""Tunable experience-point amounts for Lantern Farm.

Numbers live in a single ``xp`` table in ``rules.json`` so they are easy to
tune. They are pending a final okay and are not granted during play yet.
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

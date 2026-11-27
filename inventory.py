"""Pack, cabin chest, tools, and cozy recipes for Lantern Farm."""

from __future__ import annotations

from typing import Iterable

PACK_SLOTS = 4
PACK_STACK = 8
CHEST_STACK = 16
TILL_HOLD_DAYS = 5

TOOL_HOE = "hoe"
TOOL_CAN = "watering_can"
TOOL_SHOVEL = "shovel"
TOOL_AXE = "axe"
TOOL_PICKAXE = "pickaxe"

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
    TOOL_SHOVEL: {
        "name": "shovel",
        "name_plural": "shovels",
        "starting": 1,
    },
    TOOL_AXE: {
        "name": "axe",
        "name_plural": "axes",
        "starting": 1,
    },
    TOOL_PICKAXE: {
        "name": "pickaxe",
        "name_plural": "pickaxes",
        "starting": 0,
    },
}

SLEEPING_BAG = "sleeping_bag"
DEFAULT_SLEEPING_BAG_PRICE = 120

# Bought equipment. A sleeping bag occupies one backpack slot (pack stack 1).
EQUIPMENT = {
    SLEEPING_BAG: {
        "name": "sleeping bag",
        "name_plural": "sleeping bags",
        "price": DEFAULT_SLEEPING_BAG_PRICE,
        "description": (
            "A rolled blanket you can sleep in anywhere. End your turn with it "
            "in your backpack (and not in a bed) to wake on the same spot with "
            "100 energy and no cabin comfort bonuses."
        ),
    },
}

# Shop staples: cheap, year-round, lightly filling.
STAPLES = {
    "bread": {
        "name": "bread",
        "name_plural": "loaves of bread",
        "price": 8,
        "sell_price": 4,
        "eat_energy": 5,
        "description": "A small loaf from the village bakery. Eat one half (+5 energy) and leave the other half for a companion.",
    },
    "bread_half": {
        "name": "half loaf",
        "name_plural": "half loaves",
        "sell_price": 2,
        "eat_energy": 5,
        "shop": False,
        "description": "The other half of a loaf. A small snack, or a share left in the chest for a companion.",
    },
    "butter": {
        "name": "butter",
        "name_plural": "pats of butter",
        "price": 10,
        "sell_price": 5,
        "eat_energy": 6,
        "description": "A pale pat of butter. Nice on bread, or in a pan with kabocha.",
    },
    "milk": {
        "name": "milk",
        "name_plural": "bottles of milk",
        "price": 8,
        "sell_price": 4,
        "eat_energy": 8,
        "description": "A bottle of fresh milk. Good on its own, or with berries and soup.",
    },
    "sugar": {
        "name": "sugar",
        "name_plural": "bags of sugar",
        "price": 5,
        "sell_price": 2,
        "description": "A small bag of sugar from the village shop. Needed when you cook jam.",
    },
    "herbal_tea": {
        "name": "herbal tea",
        "name_plural": "cups of herbal tea",
        "price": 15,
        "sell_price": 7,
        "description": (
            "A warm cup of herbs from the village shop. Drink one a day; "
            "if you sleep in the cabin, you wake with +10 energy. "
            "Stacks with the fire and a good meal."
        ),
    },
}

# Forage and gathered materials (hills). Not shop stock.
MATERIALS = {
    "wood": {
        "name": "wood",
        "name_plural": "wood",
        "sell_price": 4,
        "description": "A small bundle of firewood, chopped in the hills.",
    },
    "stone": {
        "name": "stone",
        "name_plural": "stone",
        "sell_price": 1,
        "description": "A piece of broken stone from the mine. Not worth much, but it stacks, and may be useful later.",
    },
    "copper_ore": {
        "name": "copper ore",
        "name_plural": "copper ore",
        "sell_price": 8,
        "description": "A chunk of copper ore, chipped from the upper mine floors.",
    },
    "iron_ore": {
        "name": "iron ore",
        "name_plural": "iron ore",
        "sell_price": 12,
        "description": "A chunk of iron ore, found deeper in the mine.",
    },
    "gold_ore": {
        "name": "gold ore",
        "name_plural": "gold ore",
        "sell_price": 20,
        "description": "A chunk of gold ore, from the deepest mine floors.",
    },
    "quartz": {
        "name": "quartz",
        "name_plural": "quartz",
        "sell_price": 6,
        "description": "A clear shard of quartz, sometimes found in ordinary stone on the upper mine floors.",
    },
    "runestone_ore": {
        "name": "runestone ore",
        "name_plural": "runestone ore",
        "sell_price": 15,
        "description": "A smooth, rounded runestone ore, rare in the upper mine and more common deeper. Craft it into a runestone at the Creation Table.",
    },
    "runestone": {
        "name": "runestone",
        "name_plural": "runestones",
        "sell_price": 20,
        "description": "A finished runestone, cut from runestone ore at the Creation Table. Used to enchant tools and boots on an aurora night.",
    },
    "goo": {
        "name": "goo",
        "name_plural": "goo",
        "sell_price": 8,
        "description": "A sticky dollop of grey slime goo. The stall will buy it; a recipe can wait.",
    },
}

FORAGE_ITEMS = {
    "wild_onion": {
        "name": "wild onion",
        "name_plural": "wild onions",
        "eat_energy": 6,
        "seasons": ("spring",),
        "description": "A wild spring onion, pulled from the hills. A small snack, or the start of a soup.",
    },
    "wild_berry": {
        "name": "wild berry",
        "name_plural": "wild berries",
        "eat_energy": 8,
        "seasons": ("summer",),
        "description": "A handful of wild summer berries. Good raw, or simmered into jam.",
    },
    "wild_mushroom": {
        "name": "wild mushroom",
        "name_plural": "wild mushrooms",
        "seasons": ("autumn",),
        "description": "A wild autumn mushroom from the hills. Not safe to eat raw — cook it into a soup.",
    },
    "oyster_mushroom": {
        "name": "oyster mushroom",
        "name_plural": "oyster mushrooms",
        "seasons": ("spring", "summer", "autumn"),
        "description": (
            "A pale shelf mushroom from a hills log. "
            "Not safe to eat raw — cook it into mushroom soup."
        ),
    },
}

# Berry kinds that can stand in for strawberry_jam's `berries` requirement.
JAM_BERRY_ITEMS = ("strawberry", "everbearing", "wild_berry")

# Mushrooms that can stand in for mushroom_soup's wild mushroom.
SOUP_MUSHROOM_ITEMS = ("wild_mushroom", "oyster_mushroom")

# Recipes that are already in the book when a farm begins (or an older save is migrated).
STARTING_DISCOVERED_RECIPES = ("strawberry_jam", "kabocha_soup")

# Default recipes if rules.json has not listed them yet.
DEFAULT_RECIPES = {
    "strawberry_jam": {
        "name": "strawberry jam",
        "berries": 3,
        "ingredients": {"sugar": 1},
        "eat_energy": 40,
        "sell_price": 90,
        "sellable": True,
        "description": "Three berries simmered with sugar into a jar of jam. A hearty snack, still worth a little more than the fruit and sugar apart.",
    },
    "kabocha_soup": {
        "name": "kabocha soup",
        "ingredients": {"kabocha": 1},
        "eat_energy": 55,
        "sell_price": 70,
        "sellable": False,
        "description": "A bowl of roasted kabocha soup. Restores more energy than eating the squash raw.",
    },
    "root_stew": {
        "name": "root stew",
        "ingredients": {"carrot": 1, "turnip": 1},
        "eat_energy": 50,
        "sell_price": 70,
        "sellable": False,
        "description": "A carrot and a turnip stewed together. Warm and filling.",
    },
    "bread_and_butter": {
        "name": "bread and butter",
        "ingredients": {"bread": 1, "butter": 1},
        "eat_energy": 22,
        "sell_price": 28,
        "sellable": False,
        "description": "A loaf split and spread with butter. More filling than eating them separately.",
    },
    "jam_toast": {
        "name": "jam toast",
        "ingredients": {"bread": 1, "strawberry_jam": 1},
        "eat_energy": 58,
        "sell_price": 115,
        "sellable": False,
        "description": "Toast with a spoon of strawberry jam. A sweeter snack than the jam alone.",
    },
    "strawberry_milk": {
        "name": "strawberry milk",
        "ingredients": {"milk": 1, "strawberry": 1},
        "eat_energy": 45,
        "sell_price": 45,
        "sellable": False,
        "description": "Cold milk stirred with a crushed strawberry. Restores more than the fruit and milk on their own.",
    },
    "buttered_kabocha": {
        "name": "buttered kabocha",
        "ingredients": {"kabocha": 1, "butter": 1},
        "eat_energy": 42,
        "sell_price": 75,
        "sellable": False,
        "description": "Roasted kabocha with a melt of butter. Heartier than the squash raw.",
    },
    "kabocha_cream_soup": {
        "name": "kabocha cream soup",
        "ingredients": {"kabocha": 1, "milk": 1, "butter": 1},
        "eat_energy": 70,
        "sell_price": 88,
        "sellable": False,
        "description": "A richer kabocha soup finished with milk and butter. The coziest bowl in the kitchen.",
    },
    "rhubarb_strawberry_jam": {
        "name": "rhubarb strawberry jam",
        "ingredients": {"rhubarb": 2, "strawberry": 1, "sugar": 1},
        "eat_energy": 45,
        "sell_price": 95,
        "sellable": True,
        "description": "Tart rhubarb simmered with a strawberry and sugar. A brighter jam than strawberries alone, and worth more than the fruit and sugar apart.",
    },
    "garden_salad": {
        "name": "garden salad",
        "ingredients": {"lettuce": 1, "tomato": 1, "cucumber": 1},
        "eat_energy": 36,
        "sell_price": 72,
        "sellable": False,
        "description": "A bowl of lettuce, tomato, and cucumber. Cooler than eating the vegetables raw.",
    },
    "roasted_potatoes": {
        "name": "roasted potatoes",
        "name_plural": "servings of roasted potatoes",
        "ingredients": {"potato": 2, "butter": 1},
        "eat_energy": 42,
        "sell_price": 52,
        "sellable": False,
        "description": "Two potatoes roasted with a pat of butter. Heartier than the potatoes raw.",
    },
    "pumpkin_soup": {
        "name": "pumpkin soup",
        "ingredients": {"pumpkin": 1},
        "eat_energy": 52,
        "sell_price": 62,
        "sellable": False,
        "description": "A bowl of roasted pumpkin soup. Restores more energy than eating the pumpkin raw.",
    },
    "wild_onion_soup": {
        "name": "wild onion soup",
        "ingredients": {"wild_onion": 1, "milk": 1},
        "eat_energy": 28,
        "sell_price": 32,
        "sellable": False,
        "description": "A small pot of soup from a wild onion and a bottle of milk. More filling than eating them raw.",
    },
    "wild_berry_jam": {
        "name": "wild berry jam",
        "ingredients": {"wild_berry": 3, "sugar": 1},
        "eat_energy": 32,
        "sell_price": 55,
        "sellable": True,
        "description": "Three handfuls of wild berries simmered with sugar into a jar of jam. A sweeter snack than the berries raw.",
    },
    "mushroom_soup": {
        "name": "mushroom soup",
        "ingredients": {"wild_mushroom": 1, "milk": 1},
        "eat_energy": 32,
        "sell_price": 40,
        "sellable": False,
        "description": "A cooked wild mushroom simmered with milk. The safe way to eat what you find in the autumn hills.",
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
    "hoes": TOOL_HOE,
    "watering_can": TOOL_CAN,
    "shovel": TOOL_SHOVEL,
    "shovels": TOOL_SHOVEL,
    "axe": TOOL_AXE,
    "axes": TOOL_AXE,
    "pickaxe": TOOL_PICKAXE,
    "pickaxes": TOOL_PICKAXE,
    "sleeping_bag": SLEEPING_BAG,
    "sleeping bag": SLEEPING_BAG,
    "sleeping bags": SLEEPING_BAG,
    "bedroll": SLEEPING_BAG,
    "bed roll": SLEEPING_BAG,
    "pick-axe": TOOL_PICKAXE,
    "pick axe": TOOL_PICKAXE,
    "pick": TOOL_PICKAXE,
    "wood": "wood",
    "stone": "stone",
    "stones": "stone",
    "copper": "copper_ore",
    "copper ore": "copper_ore",
    "copper_ore": "copper_ore",
    "iron": "iron_ore",
    "iron ore": "iron_ore",
    "iron_ore": "iron_ore",
    "gold ore": "gold_ore",
    "gold_ore": "gold_ore",
    "quartz": "quartz",
    "runestone": "runestone",
    "runestones": "runestone",
    "rune stone": "runestone",
    "rune stones": "runestone",
    "runestone ore": "runestone_ore",
    "runestone_ore": "runestone_ore",
    "leather boots": "leather_boots",
    "leather_boots": "leather_boots",
    "hiking boots": "hiking_boots",
    "hiking_boots": "hiking_boots",
    "blue sweater": "blue_sweater",
    "blue_sweater": "blue_sweater",
    "green hoodie": "green_hoodie",
    "green_hoodie": "green_hoodie",
    "goo": "goo",
    "slime goo": "goo",
    "firewood": "wood",
    "wild_onion": "wild_onion",
    "wild onion": "wild_onion",
    "wild onions": "wild_onion",
    "wild_berry": "wild_berry",
    "wild berry": "wild_berry",
    "wild berries": "wild_berry",
    "wild_mushroom": "wild_mushroom",
    "wild mushroom": "wild_mushroom",
    "wild mushrooms": "wild_mushroom",
    "oyster_mushroom": "oyster_mushroom",
    "oyster mushroom": "oyster_mushroom",
    "oyster mushrooms": "oyster_mushroom",
    "oyster": "oyster_mushroom",
    "oysters": "oyster_mushroom",
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
    "bread": "bread",
    "loaf": "bread",
    "loaf of bread": "bread",
    "loaves of bread": "bread",
    "bread_half": "bread_half",
    "bread half": "bread_half",
    "half loaf": "bread_half",
    "half-loaf": "bread_half",
    "halfloaf": "bread_half",
    "half bread": "bread_half",
    "half loaves": "bread_half",
    "butter": "butter",
    "pat of butter": "butter",
    "pats of butter": "butter",
    "milk": "milk",
    "bottle of milk": "milk",
    "bottles of milk": "milk",
    "sugar": "sugar",
    "bag of sugar": "sugar",
    "bags of sugar": "sugar",
    "bread and butter": "bread_and_butter",
    "bread_and_butter": "bread_and_butter",
    "jam toast": "jam_toast",
    "jam_toast": "jam_toast",
    "toast": "jam_toast",
    "strawberry milk": "strawberry_milk",
    "strawberry_milk": "strawberry_milk",
    "buttered kabocha": "buttered_kabocha",
    "buttered_kabocha": "buttered_kabocha",
    "kabocha cream soup": "kabocha_cream_soup",
    "kabocha_cream_soup": "kabocha_cream_soup",
    "cream soup": "kabocha_cream_soup",
    "rhubarb strawberry jam": "rhubarb_strawberry_jam",
    "rhubarb_strawberry_jam": "rhubarb_strawberry_jam",
    "rhubarb jam": "rhubarb_strawberry_jam",
    "strawberry rhubarb jam": "rhubarb_strawberry_jam",
    "garden salad": "garden_salad",
    "garden_salad": "garden_salad",
    "salad": "garden_salad",
    "roasted potatoes": "roasted_potatoes",
    "roasted_potatoes": "roasted_potatoes",
    "roast potatoes": "roasted_potatoes",
    "pumpkin soup": "pumpkin_soup",
    "pumpkin_soup": "pumpkin_soup",
    "wild onion soup": "wild_onion_soup",
    "wild_onion_soup": "wild_onion_soup",
    "onion soup": "wild_onion_soup",
    "wild berry jam": "wild_berry_jam",
    "wild_berry_jam": "wild_berry_jam",
    "berry jam": "wild_berry_jam",
    "mushroom soup": "mushroom_soup",
    "mushroom_soup": "mushroom_soup",
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
    "herbal_tea": "herbal_tea",
    "herbal tea": "herbal_tea",
    "tea": "herbal_tea",
    "cup of tea": "herbal_tea",
    "cups of tea": "herbal_tea",
    "cup of herbal tea": "herbal_tea",
    "cups of herbal tea": "herbal_tea",
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


def is_equipment(item: str | None) -> bool:
    from gear import is_boots

    return (item or "") in EQUIPMENT or is_boots(item)


def is_fertilizer(item: str | None) -> bool:
    return (item or "") in FERTILIZERS


def is_staple(item: str | None) -> bool:
    return (item or "") in STAPLES


def is_forage_item(item: str | None) -> bool:
    return (item or "") in FORAGE_ITEMS


def staple_info(item: str | None, rules: dict | None = None) -> dict | None:
    item = item or ""
    if item not in STAPLES:
        return None
    info = dict(STAPLES[item])
    custom = (rules or {}).get("staples") if isinstance(rules, dict) else None
    if isinstance(custom, dict) and isinstance(custom.get(item), dict):
        info.update(custom[item])
    for key in ("price", "sell_price", "eat_energy"):
        if info.get(key) is None:
            continue
        try:
            info[key] = int(info[key])
        except (TypeError, ValueError):
            info[key] = STAPLES[item].get(key)
    return info


def staple_is_sold(item: str | None, rules: dict | None = None) -> bool:
    """True when the shop sells this staple (half loaves are leftover, not stock)."""
    info = staple_info(item, rules)
    if not info:
        return False
    if info.get("shop") is False:
        return False
    return info.get("price") is not None



def equipment_info(item: str | None, rules: dict | None = None) -> dict | None:
    item = item or ""
    from gear import is_boots, boots_info

    if is_boots(item):
        return boots_info(item, rules)
    if item not in EQUIPMENT:
        return None
    info = dict(EQUIPMENT[item])
    custom = (rules or {}).get("sleeping_bag") if item == SLEEPING_BAG and isinstance(rules, dict) else None
    if isinstance(custom, dict):
        info.update(custom)
    if info.get("price") is not None:
        try:
            info["price"] = int(info["price"])
        except (TypeError, ValueError):
            info["price"] = int(EQUIPMENT[item]["price"])
    return info


def sleeping_bag_price(rules: dict | None = None) -> int:
    info = equipment_info(SLEEPING_BAG, rules) or EQUIPMENT[SLEEPING_BAG]
    try:
        return max(0, int(info.get("price") or DEFAULT_SLEEPING_BAG_PRICE))
    except (TypeError, ValueError):
        return DEFAULT_SLEEPING_BAG_PRICE


def equipment_shop_items(rules: dict | None = None) -> list[str]:
    """Year-round honour-store equipment (sleeping bag, hiking boots)."""
    out: list[str] = []
    from gear import BOOTS

    for item in list(EQUIPMENT) + list(BOOTS):
        info = equipment_info(item, rules) or {}
        if info.get("shop") is False:
            continue
        if info.get("price") is None:
            continue
        out.append(item)
    return out


def staple_shop_items(rules: dict | None = None) -> list[str]:
    """Staples are sold year-round."""
    items = [item for item in STAPLES if staple_is_sold(item, rules)]
    custom = (rules or {}).get("staples") if isinstance(rules, dict) else None
    if isinstance(custom, dict):
        for key in custom:
            item = normalize_item(key) or str(key).strip().lower().replace(" ", "_")
            if item not in items and staple_is_sold(item, rules):
                items.append(item)
    return items


def recipe_ingredients(rec: dict | None) -> list[tuple[str, int]]:
    """Normalized (item, count) pairs, including jam's berry requirement."""
    if not rec:
        return []
    out: list[tuple[str, int]] = []
    berries = int(rec.get("berries") or 0)
    if berries:
        out.append(("strawberry", berries))
    for raw, n in (rec.get("ingredients") or {}).items():
        item = normalize_item(raw) or str(raw).strip().lower().replace(" ", "_")
        try:
            count = int(n)
        except (TypeError, ValueError):
            continue
        if item and count > 0:
            out.append((item, count))
    return out


def ingredient_cost(rec: dict, crops: dict | None = None, rules: dict | None = None) -> int:
    """Gold value of a recipe's ingredients (shop price for staples, sell price otherwise)."""
    total = 0
    for item, n in recipe_ingredients(rec):
        if item in STAPLES:
            info = staple_info(item, rules) or STAPLES[item]
            try:
                total += n * int(info.get("price") or 0)
            except (TypeError, ValueError):
                pass
            continue
        price = item_sell_price(item, crops, rules)
        if price:
            total += n * int(price)
    return total


def ingredient_eat_total(rec: dict, crops: dict | None = None, rules: dict | None = None) -> int:
    total = 0
    for item, n in recipe_ingredients(rec):
        # Jam's berry slot is "any strawberry"; June-bearing energy is the fair comparison.
        energy = item_eat_energy(item, crops, rules)
        if energy:
            total += n * int(energy)
    return total


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
    from gear import is_clothes, is_boots

    if is_tool(item) or is_equipment(item) or is_clothes(item) or is_boots(item):
        # Tools, boots, clothes, and the sleeping bag occupy their own pack slot.
        return chest_stack_limit(rules) if in_chest else 1
    return chest_stack_limit(rules) if in_chest else pack_stack_limit(rules)


def _folded_item_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().replace("_", " ").replace("-", " ").split())


_STOCK_TEXT_SUFFIXES = (
    " starters",
    " starter",
    " seedlings",
    " seedling",
    " seeds",
    " seed",
    " crowns",
    " crown",
)


def _canonical_crop_kind(text: str, crops: dict) -> str | None:
    from engine import crop_info, crop_name, crop_name_plural, normalize_kind, stock_prefix

    folded = _folded_item_text(text)
    if not folded:
        return None
    kind = normalize_kind(folded.replace(" ", "_"))
    table = crops.get("crops") or {}
    if kind in table:
        return kind
    for crop_kind, info in table.items():
        names = [
            stock_prefix(crop_kind, info),
            crop_name(crop_kind, info),
            crop_name_plural(crop_kind, info, 2),
            crop_kind,
            crop_kind.replace("_", " "),
        ]
        shop = (info or {}).get("shop_name") or ""
        if shop:
            names.append(shop)
        for cand in names:
            if _folded_item_text(cand) == folded:
                return crop_kind
    if crop_info(crops, kind) and kind in table:
        return kind
    return None


def normalize_item(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = _folded_item_text(raw)
    if not text:
        return None
    compact = text.replace(" ", "")
    if text in ITEM_ALIASES:
        return ITEM_ALIASES[text]
    if compact in ITEM_ALIASES:
        return ITEM_ALIASES[compact]
    from engine import crop_info, load_crops, stock_key

    crops = load_crops()
    stock_hint = False
    kind_text = text
    for suffix in _STOCK_TEXT_SUFFIXES:
        if text.endswith(suffix):
            kind_text = text[: -len(suffix)].strip()
            stock_hint = True
            break
    kind = _canonical_crop_kind(kind_text, crops)
    if kind:
        info = crop_info(crops, kind)
        if stock_hint and info:
            return stock_key(kind, info)
        if not stock_hint:
            return kind
    underscored = text.replace(" ", "_")
    if underscored.endswith("_seed") or underscored.endswith("_seedling") or underscored.endswith("_crown"):
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
    # Display names for forged tools ("copper pickaxe", "iron watering can").
    # "copper ore" is already handled by ITEM_ALIASES above.
    words = text.split()
    if len(words) >= 2 and words[0] in {"copper", "iron", "gold"}:
        rest = " ".join(words[1:])
        found = None
        if rest in ITEM_ALIASES:
            found = ITEM_ALIASES[rest]
        else:
            compact_rest = rest.replace(" ", "")
            if compact_rest in ITEM_ALIASES:
                found = ITEM_ALIASES[compact_rest]
            else:
                under_rest = rest.replace(" ", "_")
                if under_rest in TOOLS:
                    found = under_rest
        if found and found in TOOLS:
            return found
    if underscored in EQUIPMENT:
        return underscored
    return None


def prefer_available_stock(item: str, containers: list, crops: dict | None = None, rules: dict | None = None) -> str:
    """If a crop short name isn't in the containers but its seeds/crowns are, use those."""
    from engine import crop_info, load_crops, stock_key

    crops = crops or load_crops()
    have = sum(stack_count(container, item) if container is not None else 0 for container in containers)
    if have > 0:
        return item
    table = crops.get("crops") or {}
    if item not in table:
        return item
    info = crop_info(crops, item)
    key = stock_key(item, info)
    if key != item and any(
        stack_count(container, key) > 0 for container in containers if container is not None
    ):
        return key
    return item


def item_label(item: str, crops: dict | None = None, rules: dict | None = None, state: dict | None = None) -> str:
    """Singular display name with spaces and no leading count."""
    text = item_name(item, 1, crops, rules, state=state)
    return text[2:] if text.startswith("1 ") else text


def indefinite(noun: str) -> str:
    """'a copper axe', 'an iron hoe', 'an axe'."""
    text = " ".join(str(noun or "").split())
    if not text:
        return "a"
    initial = text.split()[0][:1].lower()
    article = "an" if initial in "aeiou" else "a"
    return f"{article} {text}"


def tool_display_noun(item: str, count: int = 1, state: dict | None = None, tier: str | None = None) -> str:
    """Tool noun, with a copper/iron/gold prefix when that tool is forged."""
    info = TOOLS.get(item) or {}
    noun = info.get("name") if count == 1 else (info.get("name_plural") or info.get("name") or item)
    noun = noun or item.replace("_", " ")
    from mine import FORGE_TOOLS, tool_tier
    if item not in FORGE_TOOLS:
        return noun
    if tier is None and state is not None:
        tier = tool_tier(state, item)
    if tier and tier not in {"basic", ""}:
        return f"{tier} {noun}"
    return noun


def item_name(
    item: str,
    count: int = 1,
    crops: dict | None = None,
    rules: dict | None = None,
    state: dict | None = None,
    tier: str | None = None,
) -> str:
    item = item or ""
    if item in TOOLS:
        noun = tool_display_noun(item, count, state, tier=tier)
        return f"{count} {noun}"
    if item in EQUIPMENT:
        info = equipment_info(item, rules) or EQUIPMENT[item]
        noun = info["name"] if count == 1 else info.get("name_plural") or info["name"]
        return f"{count} {noun}"
    from gear import CLOTHES, BOOTS, clothes_info, boots_info

    if item in CLOTHES:
        info = clothes_info(item) or CLOTHES[item]
        noun = info["name"] if count == 1 else info.get("name_plural") or info["name"]
        return f"{count} {noun}"
    if item in BOOTS:
        info = boots_info(item, rules) or BOOTS[item]
        noun = info["name"] if count == 1 else info.get("name_plural") or info["name"]
        return f"{count} {noun}"
    if item in STAPLES:
        info = staple_info(item, rules) or STAPLES[item]
        noun = info["name"] if count == 1 else info.get("name_plural") or info["name"]
        return f"{count} {noun}"
    if item in MATERIALS:
        info = MATERIALS[item]
        noun = info["name"] if count == 1 else info.get("name_plural") or info["name"]
        return f"{count} {noun}"
    if item in FORAGE_ITEMS:
        info = FORAGE_ITEMS[item]
        noun = info["name"] if count == 1 else info.get("name_plural") or info["name"]
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
    from engine import crop_info, crop_name_plural, load_crops, stock_label

    crops = crops or load_crops()
    stock = None
    kind = item
    if item.endswith("_seedling"):
        kind = item[: -len("_seedling")]
        stock = "seedling"
    elif item.endswith("_crowns"):
        kind = item[: -len("_crowns")]
        stock = "crown"
    elif item.endswith("_crown"):
        kind = item[: -len("_crown")]
        stock = "crown"
    elif item.endswith("_seed"):
        kind = item[: -len("_seed")]
        stock = "seed"
    info = crop_info(crops, kind) or {}
    if stock:
        return f"{count} {stock_label(kind, info, count)}"
    return f"{count} {crop_name_plural(kind, info, count)}"


def _recipe_looks_like_jam(item: str | None, rec: dict | None = None) -> bool:
    """True for jars of jam, not for meals that merely use jam (like jam toast)."""
    key = str(item or "").strip().lower().replace(" ", "_")
    name = str((rec or {}).get("name") or "").strip().lower()
    return key.endswith("_jam") or name.endswith(" jam") or name == "jam"


def recipe_is_sellable(item: str | None, rec: dict | None = None) -> bool:
    """True when the shop will buy this cooked recipe. Jams only, for now."""
    rec = rec or {}
    if "sellable" in rec:
        return bool(rec.get("sellable"))
    return _recipe_looks_like_jam(item, rec)



_PLANTING_STOCK_SUFFIXES = ("_seedling", "_seed", "_crown", "_crowns")


def planting_stock_kind(item: str | None) -> str | None:
    """Crop kind if this item is a seed, seedling, or crown; otherwise None."""
    key = normalize_item(item) if item else None
    if not key:
        key = (str(item or "").strip().lower().replace("-", " ").replace(" ", "_"))
    if not key:
        return None
    for suffix in _PLANTING_STOCK_SUFFIXES:
        if key.endswith(suffix):
            kind = key[: -len(suffix)]
            return kind or None
    return None


def item_sell_price(item: str, crops: dict | None = None, rules: dict | None = None) -> int | None:
    if item in MATERIALS:
        try:
            return int(MATERIALS[item]["sell_price"])
        except (KeyError, TypeError, ValueError):
            return None
    if item in FORAGE_ITEMS:
        # Foraged goods are not sold at the shop.
        raw = FORAGE_ITEMS[item].get("sell_price")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if item in STAPLES:
        stap = staple_info(item, rules) or STAPLES[item]
        try:
            return int(stap["sell_price"])
        except (KeyError, TypeError, ValueError):
            return None
    rec = recipes(rules).get(item)
    if rec:
        # Keep sell_price on the recipe for later, but only jams are for sale now.
        if not recipe_is_sellable(item, rec):
            return None
        price = rec.get("sell_price")
        if price is None:
            return None
        try:
            return int(price)
        except (TypeError, ValueError):
            return None
    from engine import crop_info, load_crops

    # crop_info() strips _seed/_seedling/_crown, so planting stock must be
    # priced before that lookup. The stall (and any other sell path) pays
    # half the shop buy price, rounded down — not the harvested crop's price.
    stock_kind = planting_stock_kind(item)
    if stock_kind:
        info = crop_info(crops or load_crops(), stock_kind)
        if not info:
            return None
        try:
            buy = int(info["seed_price"])
        except (KeyError, TypeError, ValueError):
            return None
        price = buy // 2
        return price if price > 0 else None

    info = crop_info(crops or load_crops(), item)
    if not info:
        return None
    try:
        return int(info["sell_price"])
    except (KeyError, TypeError, ValueError):
        return None


def item_eat_energy(item: str, crops: dict | None = None, rules: dict | None = None) -> int | None:
    if item in FORAGE_ITEMS:
        raw = FORAGE_ITEMS[item].get("eat_energy")
        if raw is None:
            return None
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return None
    if item in STAPLES:
        stap = staple_info(item, rules) or STAPLES[item]
        if stap.get("eat_energy") is None:
            return None
        try:
            return max(0, int(stap["eat_energy"]))
        except (TypeError, ValueError):
            return None
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


def stack_tool_tier(slot, default: str | None = None) -> str:
    """Forge tier on a tool stack. 'basic' (or missing) is the starting tier."""
    if isinstance(slot, dict):
        raw = slot.get("tier")
    else:
        raw = slot
    text = str(raw or default or "basic").strip().lower()
    return text if text else "basic"


def stack_enchant(slot) -> str | None:
    """Enchant id on a tool or boots stack, or None."""
    if not isinstance(slot, dict):
        return None
    raw = str(slot.get("enchant") or "").strip().lower().replace(" ", "_")
    return raw or None


def _with_tier(item: str, count: int, tier: str | None = None, enchant: str | None = None) -> dict:
    slot = {"item": item, "count": int(count)}
    if is_tool(item):
        t = stack_tool_tier(tier)
        if t != "basic":
            slot["tier"] = t
    if enchant:
        slot["enchant"] = str(enchant).strip().lower().replace(" ", "_")
    return slot


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
    return _with_tier(item, min(count, cap), slot.get("tier"), stack_enchant(slot))


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
        if not slot or not isinstance(slot, dict):
            continue
        item = normalize_item(slot.get("item") or slot.get("kind") or slot.get("id"))
        if not item:
            continue
        try:
            count = int(slot.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            # Push un-capped so leftover over the stack limit splits,
            # and same-item partial stacks merge on load.
            _push_stacks(out, item, count, in_chest=True, rules=rules, tier=slot.get("tier"), enchant=stack_enchant(slot))
    return out


def _push_stacks(dest: list, item: str, count: int, *, in_chest: bool, rules: dict | None = None, tier: str | None = None, enchant: str | None = None) -> int:
    """Add as many as will fit. Returns the leftover count.

    Pickaxes (and other tooled stacks with a forge tier) only merge with the
    same tier, so a copper pickaxe never folds into a basic one. Enchanted
    tools and boots stay on their own stack.
    """
    if count <= 0:
        return 0
    cap = max_stack_for(item, in_chest=in_chest, rules=rules)
    want = stack_tool_tier(tier) if is_tool(item) else None
    want_enchant = (str(enchant).strip().lower().replace(" ", "_") or None) if enchant else None
    for slot in dest:
        if not slot or slot.get("item") != item:
            continue
        if is_tool(item) and stack_tool_tier(slot) != want:
            continue
        if stack_enchant(slot) != want_enchant:
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
        dest.append(_with_tier(item, take, want, want_enchant))
        count -= take
    return 0


def stack_count(slots: Iterable, item: str) -> int:
    total = 0
    for slot in slots or []:
        if slot and slot.get("item") == item:
            total += int(slot.get("count") or 0)
    return total


def _remove_stacks_from_slots(slots: list, item: str, count: int) -> list[dict]:
    """Remove up to count, later slots first. Returns the stacks taken (with tier)."""
    taken: list[dict] = []
    if count <= 0:
        return taken
    removed = 0
    for i in range(len(slots) - 1, -1, -1):
        slot = slots[i]
        if not slot or slot.get("item") != item:
            continue
        have = int(slot.get("count") or 0)
        take = min(have, count - removed)
        have -= take
        removed += take
        taken.append(_with_tier(item, take, slot.get("tier")))
        if have <= 0:
            slots[i] = None
        else:
            slot["count"] = have
        if removed >= count:
            break
    return taken


def _remove_from_slots(slots: list, item: str, count: int) -> int:
    """Remove up to count, later slots first. Returns how many were removed."""
    return sum(int(s.get("count") or 0) for s in _remove_stacks_from_slots(slots, item, count))


def compact_chest(chest: list) -> list:
    return [slot for slot in chest if slot and int(slot.get("count") or 0) > 0]


def ground_map(state: dict) -> dict:
    """Per-tile ground stacks, keyed by area (and mine floor). Missing means empty."""
    raw = state.get("ground")
    if not isinstance(raw, dict):
        state["ground"] = {}
        return state["ground"]
    return raw


def ground_key(area: str | None, row: int, col: int, floor: int | None = None) -> str:
    from hills import normalize_area, AREA_MINE

    area = normalize_area(area)
    try:
        row, col = int(row), int(col)
    except (TypeError, ValueError):
        row, col = 1, 1
    if area == AREA_MINE:
        try:
            floor = max(1, int(floor or 1))
        except (TypeError, ValueError):
            floor = 1
        return f"mine:{floor}:{row}:{col}"
    return f"{area}:{row}:{col}"


def _normalize_ground_stacks(raw, rules: dict | None = None) -> list:
    out: list[dict] = []
    if not raw:
        return out
    if isinstance(raw, dict):
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
        if not slot or not isinstance(slot, dict):
            continue
        item = normalize_item(slot.get("item") or slot.get("kind") or slot.get("id"))
        if not item:
            continue
        try:
            count = int(slot.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            _push_stacks(out, item, count, in_chest=True, rules=rules, tier=slot.get("tier"), enchant=stack_enchant(slot))
    return compact_chest(out)


def ground_of(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    floor: int | None = None,
    rules: dict | None = None,
) -> list:
    key = ground_key(area, row, col, floor)
    store = ground_map(state)
    stacks = _normalize_ground_stacks(store.get(key), rules)
    if stacks:
        store[key] = stacks
    elif key in store:
        store.pop(key, None)
    return stacks


def add_to_ground(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    item: str,
    n: int = 1,
    floor: int | None = None,
    rules: dict | None = None,
    tier: str | None = None,
) -> None:
    if n <= 0 or not item:
        return
    stacks = ground_of(state, area, row, col, floor, rules)
    _push_stacks(stacks, item, n, in_chest=True, rules=rules, tier=tier)
    key = ground_key(area, row, col, floor)
    store = ground_map(state)
    store[key] = compact_chest(stacks)


def remove_from_ground(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    item: str,
    n: int = 1,
    floor: int | None = None,
    rules: dict | None = None,
) -> int:
    if n <= 0 or not item:
        return 0
    stacks = ground_of(state, area, row, col, floor, rules)
    removed = _remove_from_slots(stacks, item, n)
    key = ground_key(area, row, col, floor)
    store = ground_map(state)
    stacks = compact_chest(stacks)
    if stacks:
        store[key] = stacks
    else:
        store.pop(key, None)
    return removed


def ground_counts(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    floor: int | None = None,
    rules: dict | None = None,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for slot in ground_of(state, area, row, col, floor, rules):
        if not slot:
            continue
        item = slot.get("item")
        if not item:
            continue
        totals[item] = totals.get(item, 0) + int(slot.get("count") or 0)
    return totals


def clear_mine_ground(state: dict) -> int:
    """Remove every ground pile on mine tiles. Farm, hills, and town are left alone.

    Called when the mine resets (a new season, or any other floor regen).
    Returns how many mine tiles were cleared.
    """
    store = ground_map(state)
    keys = [key for key in list(store) if str(key).startswith("mine:")]
    for key in keys:
        store.pop(key, None)
    return len(keys)


def ground_item_count(state: dict, item: str, rules: dict | None = None) -> int:
    """Count one item across every ground tile. Used for world-unique tools."""
    total = 0
    for stacks in ground_map(state).values():
        total += stack_count(_normalize_ground_stacks(stacks, rules), item)
    return total


def ground_look_phrase(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    floor: int | None = None,
    crops: dict | None = None,
    rules: dict | None = None,
) -> str:
    stacks = ground_of(state, area, row, col, floor, rules)
    if not stacks:
        return ""
    bits = [
        item_name(
            slot["item"],
            int(slot.get("count") or 0),
            crops,
            rules,
            state=state,
            tier=slot.get("tier"),
        )
        for slot in stacks
    ]
    if len(bits) == 1:
        body = bits[0]
    elif len(bits) == 2:
        body = f"{bits[0]} and {bits[1]}"
    else:
        body = ", ".join(bits[:-1]) + f", and {bits[-1]}"
    return f" On the ground: {body}."


def player_ground_place(state: dict, player: str | None) -> tuple[str, int, int, int | None] | None:
    """Area, row, col, and mine floor (if any) for the tile the player stands on."""
    if not player:
        return None
    from hills import player_area, AREA_MINE
    from engine import player_where
    from mine import player_floor

    area = player_area(state, player)
    row, col = player_where(state, player)
    floor = player_floor(state, player) if area == AREA_MINE else None
    return area, row, col, floor


def can_use_ground(state: dict, player: str | None) -> bool:
    """True when drop/take on this tile is ground, not the chest or stall."""
    if not player:
        return False
    from cabin import player_at_cabin_tile
    from town import is_player_at_stall

    if player_at_cabin_tile(state, player, "chest"):
        return False
    if is_player_at_stall(state, player):
        return False
    return player_ground_place(state, player) is not None


def migrate_ground(state: dict, rules: dict | None = None) -> bool:
    """Install the ground map and fold legacy mine tile drops into it. Idempotent."""
    changed = False
    raw = state.get("ground")
    if not isinstance(raw, dict):
        state["ground"] = {}
        changed = True
    else:
        # Re-normalize keys and merge stacks so older saves compact cleanly.
        store = state["ground"]
        cleaned: dict = {}
        for key, val in list(store.items()):
            stacks = _normalize_ground_stacks(val, rules)
            if stacks:
                cleaned[str(key)] = stacks
        if cleaned != store:
            state["ground"] = cleaned
            changed = True
    mine = state.get("mine")
    if isinstance(mine, dict):
        floors = mine.get("floors")
        if isinstance(floors, dict):
            for fkey, data in floors.items():
                try:
                    floor = int(fkey)
                except (TypeError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue
                tiles = data.get("tiles")
                if not isinstance(tiles, list):
                    continue
                for r, row in enumerate(tiles, 1):
                    if not isinstance(row, list):
                        continue
                    for c, tile in enumerate(row, 1):
                        if not isinstance(tile, dict):
                            continue
                        drop = tile.get("drop")
                        if not drop:
                            continue
                        item = normalize_item(drop) or str(drop).strip().lower()
                        if item:
                            add_to_ground(state, "mine", r, c, item, 1, floor=floor, rules=rules)
                        tile["drop"] = None
                        changed = True
    return changed



def give_or_drop_at_player(
    state: dict,
    player: str | None,
    item: str,
    n: int,
    rules: dict | None = None,
    *,
    tier: str | None = None,
) -> tuple[int, int, str]:
    """Pack as much as fits; leftover goes on this tile's ground.

    Returns (packed, dropped, phrase). The phrase is a complete sentence when
    nothing was packed ('Your pack is full, so the copper ore lands at your
    feet.') or a clause starting with 'and packs …' otherwise.
    """
    packed = 0
    left = max(0, int(n or 0))
    if player and left:
        room = pack_space_count(state, player, item, rules)
        take = min(room, left)
        if take:
            leftover = add_to_pack(state, player, item, take, rules, tier=tier)
            packed = take - leftover
            left = left - packed
    if left:
        place = player_ground_place(state, player) if player else None
        if place:
            area, row, col, floor = place
            add_to_ground(state, area, row, col, item, left, floor=floor, rules=rules, tier=tier)
        else:
            # No tile to drop on — should not happen for mine/hills/farm work.
            left = 0
    from engine import load_crops
    crops = None
    try:
        crops = load_crops()
    except Exception:
        crops = None
    noun_one = item_name(item, 1, crops, rules, state=state, tier=tier)
    noun = item_name(item, packed or left or n, crops, rules, state=state, tier=tier)
    bare_one = noun_one.split(" ", 1)[-1] if noun_one else item.replace("_", " ")
    sync_inventory_view(state, rules)
    if packed and not left:
        return packed, 0, f"and packs {item_name(item, packed, crops, rules, state=state, tier=tier)}"
    if packed and left:
        rest = item_name(item, left, crops, rules, state=state, tier=tier)
        return packed, left, (
            f"and packs {item_name(item, packed, crops, rules, state=state, tier=tier)}. "
            f"Your pack is full, so {rest} land{'s' if left == 1 else ''} at your feet"
        )
    if left:
        if left == 1:
            return 0, left, f"Your pack is full, so the {bare_one} lands at your feet."
        return 0, left, (
            f"Your pack is full, so {item_name(item, left, crops, rules, state=state, tier=tier)} "
            "land at your feet."
        )
    return 0, 0, f"and packs {item_name(item, n, crops, rules, state=state, tier=tier)}"


def pack_of(state: dict, player: str | None, rules: dict | None = None) -> list:
    from engine import player_slot

    if not player:
        return empty_pack(rules)
    slot = player_slot(state, player)
    pack = normalize_pack(slot.get("pack"), rules)
    slot["pack"] = pack
    return pack


def chest_of(state: dict, rules: dict | None = None) -> list:
    """Live chest slots, including empty holes, or an empty list if unbuilt."""
    from chest import chest_is_built, chest_slots

    if not chest_is_built(state):
        return []
    return chest_slots(state, rules)


def pack_has(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> bool:
    if not player:
        return False
    have = stack_count(pack_of(state, player, rules), item)
    from gear import gear_item_count

    have += gear_item_count(state, player, item)
    return have >= n


def pack_space_count(state: dict, player: str | None, item: str, rules: dict | None = None) -> int:
    """How many of this item still fit in the player's backpack."""
    if not player:
        return 0
    pack = pack_of(state, player, rules)
    cap = max_stack_for(item, in_chest=False, rules=rules)
    room = 0
    for slot in pack:
        if slot is None:
            room += cap
        elif slot.get("item") == item:
            room += max(0, cap - int(slot.get("count") or 0))
    return room


def pack_space_for(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> bool:
    if not player or n <= 0:
        return False
    return pack_space_count(state, player, item, rules) >= n


def add_to_pack(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None, tier: str | None = None) -> int:
    """Add to the player's pack. Returns leftover that did not fit."""
    if not player or n <= 0:
        return max(0, n)
    pack = pack_of(state, player, rules)
    cap = max_stack_for(item, in_chest=False, rules=rules)
    left = n
    want = stack_tool_tier(tier) if is_tool(item) else None
    for i, slot in enumerate(pack):
        if slot and slot.get("item") == item:
            if is_tool(item) and stack_tool_tier(slot) != want:
                continue
            if stack_enchant(slot):
                # Enchanted tools and boots stay on their own stack.
                continue
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
            pack[i] = _with_tier(item, take, want)
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


def remove_stacks_from_pack(state: dict, player: str | None, item: str, n: int = 1, rules: dict | None = None) -> list[dict]:
    if not player or n <= 0:
        return []
    pack = pack_of(state, player, rules)
    return _remove_stacks_from_slots(pack, item, n)


def add_to_chest(state: dict, item: str, n: int = 1, rules: dict | None = None, tier: str | None = None) -> int:
    """Add to a built chest. Returns leftover that did not fit.

    Overflow past the slot cap is kept so items are never deleted. Player
    drop actions should check chest_has_room first.
    """
    from chest import chest_is_built, add_to_built_chest

    if n <= 0:
        return 0
    if not chest_is_built(state):
        return max(0, n)
    return add_to_built_chest(state, item, n, rules, tier=tier, allow_overflow=True)


def remove_from_chest(state: dict, item: str, n: int = 1, rules: dict | None = None) -> int:
    if n <= 0:
        return 0
    from chest import chest_is_built, pad_chest_slots, chest_slot_count

    if not chest_is_built(state):
        return 0
    chest = chest_of(state, rules)
    removed = _remove_from_slots(chest, item, n)
    state["chest"] = pad_chest_slots(chest, max(chest_slot_count(state, rules), len(chest)))
    return removed


def remove_stacks_from_chest(state: dict, item: str, n: int = 1, rules: dict | None = None) -> list[dict]:
    if n <= 0:
        return []
    from chest import chest_is_built, pad_chest_slots, chest_slot_count

    if not chest_is_built(state):
        return []
    chest = chest_of(state, rules)
    taken = _remove_stacks_from_slots(chest, item, n)
    state["chest"] = pad_chest_slots(chest, max(chest_slot_count(state, rules), len(chest)))
    return taken


def remove_stacks_from_ground(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    item: str,
    n: int = 1,
    floor: int | None = None,
    rules: dict | None = None,
) -> list[dict]:
    if n <= 0 or not item:
        return []
    stacks = ground_of(state, area, row, col, floor, rules)
    taken = _remove_stacks_from_slots(stacks, item, n)
    key = ground_key(area, row, col, floor)
    store = ground_map(state)
    stacks = compact_chest(stacks)
    if stacks:
        store[key] = stacks
    else:
        store.pop(key, None)
    return taken


def add_stacks_to_pack(state: dict, player: str | None, stacks: list, rules: dict | None = None) -> list[dict]:
    """Add transferred stacks, preserving forge tiers. Returns leftovers."""
    leftover = []
    for slot in stacks or []:
        if not slot:
            continue
        item = slot.get("item")
        n = int(slot.get("count") or 0)
        if not item or n <= 0:
            continue
        left = add_to_pack(state, player, item, n, rules, tier=slot.get("tier"))
        if left:
            leftover.append(_with_tier(item, left, slot.get("tier")))
    return leftover


def add_stacks_to_chest(state: dict, stacks: list, rules: dict | None = None) -> None:
    for slot in stacks or []:
        if not slot:
            continue
        item = slot.get("item")
        n = int(slot.get("count") or 0)
        if item and n > 0:
            add_to_chest(state, item, n, rules, tier=slot.get("tier"))


def add_stacks_to_ground(
    state: dict,
    area: str | None,
    row: int,
    col: int,
    stacks: list,
    floor: int | None = None,
    rules: dict | None = None,
) -> None:
    for slot in stacks or []:
        if not slot:
            continue
        item = slot.get("item")
        n = int(slot.get("count") or 0)
        if item and n > 0:
            add_to_ground(state, area, row, col, item, n, floor=floor, rules=rules, tier=slot.get("tier"))


def all_stores(state: dict, rules: dict | None = None) -> list[dict]:
    """Every stack in the chest, every pack, and worn/held gear."""
    from engine import known_players
    from gear import gear_stacks

    stacks = list(chest_of(state, rules))
    players = state.get("players") or {}
    names = list(players) or list(known_players())
    for name in names:
        stacks.extend([s for s in pack_of(state, name, rules) if s])
        stacks.extend(gear_stacks(state, name))
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
    chest_only: bool = False,
    rules: dict | None = None,
) -> int:
    """Remove items, pack first then chest. Returns how many were taken."""
    if n <= 0:
        return 0
    taken = 0
    if player and not chest_only:
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


_DESTINATION_SUFFIXES = (
    ("into", "the", "stall"),
    ("in", "the", "stall"),
    ("into", "stall"),
    ("in", "stall"),
    ("into", "the", "chest"),
    ("in", "the", "chest"),
    ("into", "chest"),
    ("in", "chest"),
)


def strip_item_destination(args: list[str]) -> list[str]:
    """Drop a trailing 'in stall' / 'in the chest' phrase from a take/drop command."""
    tokens = [str(a) for a in args]
    lower = [t.lower() for t in tokens]
    for suffix in _DESTINATION_SUFFIXES:
        n = len(suffix)
        if len(lower) >= n and tuple(lower[-n:]) == suffix:
            return tokens[:-n]
    return tokens


def parse_item_and_count(args: list[str]) -> tuple[str | None, int | str | None, str | None]:
    """Parse `hoe`, `2 carrot`, `strawberry 3`, `everbearing all`, or `all wood in stall`."""
    if not args:
        return None, None, "Say which item, like: take hoe"
    tokens = strip_item_destination([str(a) for a in args])
    if not tokens:
        return None, None, "Say which item, like: take hoe"
    count = None
    # Leading or trailing whole number is the count; "all" means the whole stack.
    if tokens[0].isdigit():
        count = int(tokens[0])
        tokens = tokens[1:]
    elif tokens[0].lower() == "all" and len(tokens) > 1:
        count = "all"
        tokens = tokens[1:]
    elif tokens[-1].lower() == "all" and len(tokens) > 1:
        count = "all"
        tokens = tokens[:-1]
    elif tokens[-1].isdigit() and len(tokens) > 1:
        count = int(tokens[-1])
        tokens = tokens[:-1]
    if not tokens:
        return None, None, "Say which item, like: take hoe"
    if count is None:
        count = 1
    if count != "all" and count < 1:
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


def world_item_count(state: dict, item: str, rules: dict | None = None) -> int:
    """Count an item across packs, the chest, the stall, and ground piles."""
    total = stack_count(all_stores(state, rules), item)
    store = ground_map(state)
    for stacks in store.values():
        total += stack_count(stacks if isinstance(stacks, list) else [], item)
    # Read the stall if it already exists. Do not call stall_of(), which
    # would create the town as a side effect during migrate_state.
    town = state.get("town")
    if isinstance(town, dict):
        stall = town.get("stall")
        if isinstance(stall, list):
            total += stack_count(stall, item)
    return total


def ensure_starting_tools(state: dict, rules: dict | None = None) -> bool:
    """Make sure the starting tools exist somewhere in the world.

    New games put them on the cabin floor (no starting chest). An already
    built chest still receives any missing tools, never duplicates.
    """
    from chest import chest_is_built, place_starting_goods

    if not chest_is_built(state):
        changed = place_starting_goods(state, None, rules)
        from chest import build_tile
        from hills import AREA_CABIN
        row, col = build_tile(rules)
        wanted = starting_tool_counts(rules)
        for item, need in wanted.items():
            have = world_item_count(state, item, rules)
            if have < need:
                add_to_ground(state, AREA_CABIN, row, col, item, need - have, rules=rules)
                changed = True
        return changed
    changed = False
    wanted = starting_tool_counts(rules)
    for item, need in wanted.items():
        have = world_item_count(state, item, rules)
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
    """Install packs and chest fields. Idempotent. New games start with no chest."""
    from engine import known_players, player_slot
    from chest import migrate_chest, install_built_chest, chest_is_built

    rules = rules or {}
    changed = False
    # A pre-pack save (inventory is the only store, no backpacks yet) folds
    # into a grandfathered chest. New games already have packs by this point
    # and must not grow a free chest from starting seeds.
    def _any_pack(st):
        for slot in (st.get("players") or {}).values():
            if isinstance(slot, dict) and "pack" in slot:
                return True
        return False
    if "chest" not in state and state.get("chest_built") is None and not state.get("_inventory_is_view") and not _any_pack(state):
        if isinstance(state.get("inventory"), dict) and any(
            (isinstance(v, int) or str(v).lstrip("-").isdigit()) and int(v or 0) > 0
            for v in state.get("inventory").values()
        ):
            install_built_chest(state, rules)
            if move_legacy_inventory_to_chest(state, rules):
                changed = True
    if migrate_chest(state, crops, rules):
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
    from gear import migrate_player_gear

    if migrate_player_gear(state, rules):
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



def transfer_inventory_slot(
    state: dict,
    player: str,
    src: str,
    src_i,
    dest: str,
    dest_i,
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Move one stack between backpack slots and worn/held gear. Never copies.

    Chest transfers stay on move_pack_chest_slot (they need you at the chest).
    Pack-to-pack works from the inventory window anywhere on your turn.
    """
    from gear import (
        GEAR_SLOTS,
        SLOT_BOOTS,
        SLOT_CLOTHES,
        SLOT_HANDS,
        gear_of,
        is_boots,
        is_clothes,
        set_gear,
    )

    src = (src or "").strip().lower()
    dest = (dest or "").strip().lower()
    allowed = {"pack", *GEAR_SLOTS}
    if src not in allowed or dest not in allowed:
        return False, "Move a stack between the backpack and clothes, boots, or hands."
    if src == "chest" or dest == "chest":
        return False, "Use transfer with chest only at the chest."

    pack = pack_of(state, player, rules)

    def _pack_index(raw, label):
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            return None, f"Use {label} slot numbers starting at 1."
        if idx < 1 or idx > len(pack):
            return None, "That backpack slot is missing."
        return idx, None

    def _copy(stack):
        return dict(stack) if stack else None

    def _read(store, index):
        if store == "pack":
            idx, err = _pack_index(index, "backpack")
            if err:
                return None, err, None
            return _copy(pack[idx - 1]), None, idx
        return _copy(gear_of(state, player, store)), None, 1

    def _write(store, index, stack):
        if store == "pack":
            pack[index - 1] = stack
        else:
            set_gear(state, player, store, stack)

    def _fits_dest(store, stack) -> str | None:
        if not stack or not stack.get("item"):
            return None
        item = stack.get("item")
        if store == SLOT_CLOTHES and not is_clothes(item):
            return f"{item_label(item, state=state)} is not clothing."
        if store == SLOT_BOOTS and not is_boots(item):
            return f"{item_label(item, state=state)} are not boots."
        if store == SLOT_HANDS and not is_tool(item):
            return f"{item_label(item, state=state)} cannot be held in your hands."
        return None

    src_stack, err, src_idx = _read(src, src_i)
    if err:
        return False, err
    if src == dest and (src == "pack") and str(src_i) == str(dest_i):
        return True, "Moved."
    if src == dest and src != "pack":
        return True, "Moved."
    if not src_stack or not src_stack.get("item"):
        return False, "That slot is empty."

    dest_stack, err, dest_idx = _read(dest, dest_i)
    if err:
        return False, err

    fit = _fits_dest(dest, src_stack)
    if fit:
        return False, fit
    if dest_stack and dest_stack.get("item"):
        fit = _fits_dest(src, dest_stack)
        if fit:
            return False, fit

    # Swap (or move onto an empty slot). Each stack is written once.
    _write(dest, dest_idx, src_stack)
    _write(src, src_idx, dest_stack)
    sync_inventory_view(state, rules)
    return True, "Moved."

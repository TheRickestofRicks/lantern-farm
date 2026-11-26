"""Shared tile -> sprite-key mapping, plus cozy SVG tiles generated in code."""

from __future__ import annotations

SIZE = 160


VINE_STAGES = frozenset({"seed", "sprouting", "seedling"})
# Longest names first so parse_sprite_key can strip suffixes unambiguously.
VINE_DIRECTIONS = (
    "northwest",
    "northeast",
    "southwest",
    "southeast",
    "north",
    "south",
    "east",
    "west",
)


def parse_runner_from(crop: dict | None) -> tuple[int, int] | None:
    """Return the parent plot (1-indexed row, col) a runner came from, if recorded."""
    raw = (crop or {}).get("runner_from")
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return int(raw[0]), int(raw[1])
        except (TypeError, ValueError):
            return None
    return None


def runner_vine_visible(crop: dict | None) -> bool:
    """The vine shows only while the new plant is still establishing."""
    if not crop or not parse_runner_from(crop):
        return False
    return str(crop.get("stage") or "") in VINE_STAGES


def runner_vine_direction(crop: dict | None, row: int | None = None, col: int | None = None) -> str | None:
    """Direction of the parent from this plot, or None if the vine is gone."""
    if not runner_vine_visible(crop) or row is None or col is None:
        return None
    pr, pc = parse_runner_from(crop)
    dr, dc = pr - int(row), pc - int(col)
    if dr == 0 and dc == 0:
        return None
    ns = "north" if dr < 0 else ("south" if dr > 0 else "")
    ew = "west" if dc < 0 else ("east" if dc > 0 else "")
    name = ns + ew
    return name if name in set(VINE_DIRECTIONS) else None


def sprite_key(tile: dict, weather: str | None = None, row: int | None = None, col: int | None = None, floor: int | None = None) -> str:
    """Map a state.json tile to a sprite key. Used by both renderers."""
    typ = (tile or {}).get("type")
    if typ in {"mine_floor", "mine_safe"}:
        key = "mine_safe" if typ == "mine_safe" else "mine_floor"
        rock = tile.get("rock")
        if rock:
            if rock in {"copper_ore", "iron_ore", "gold_ore"}:
                key += "_rock_" + rock.replace("_ore", "")
            else:
                key += "_rock"
        else:
            if tile.get("ladder") == "open":
                key += "_ladder"
            if tile.get("exit"):
                try:
                    fl = int(floor) if floor is not None else 0
                except (TypeError, ValueError):
                    fl = 0
                if fl >= 2:
                    key += "_ladder_up"
                else:
                    key += "_shaft"
            if tile.get("lantern"):
                key += "_lantern"
            if tile.get("elevator"):
                key += "_elevator"
        return key
    if typ in {"cabin_floor", "cabin_bed", "cabin_chest", "cabin_fireplace", "cabin_door", "cabin_kitchen"}:
        kind = typ[len("cabin_"):]
        if typ == "cabin_fireplace" and tile.get("fire"):
            return "cabin_interior_fireplace_lit"
        return f"cabin_interior_{kind}"
    if typ in {"grass", "hillside", "mine_entrance"}:
        if typ == "mine_entrance":
            key = "mine_entrance_closed" if tile.get("closed", True) else "mine_entrance"
        else:
            key = typ if typ != "grass" else "hills_grass"
        if (weather or "").strip().lower() == "snow":
            key += "_snow"
        tree = tile.get("tree") if isinstance(tile.get("tree"), dict) else None
        if tree and tree.get("stage"):
            key += f"_tree_{tree['stage']}"
        forage = tile.get("forage") if isinstance(tile.get("forage"), dict) else None
        if forage and forage.get("kind"):
            key += f"_forage_{forage['kind']}"
        return key
    if not tile or tile.get("type") == "cabin":
        w = (weather or "").strip().lower()
        if w in {"rain", "snow", "storm", "cloud"}:
            key = f"cabin_{w}"
        else:
            key = "cabin"
        if tile and tile.get("fire"):
            key += "_fire"
        return key
    watered = bool(tile.get("watered"))
    tilled = bool(tile.get("tilled"))
    crop = tile.get("crop")
    if crop and crop.get("kind") and crop.get("stage"):
        moist = "wet" if watered else "dry"
        key = f"{crop['kind']}_{crop['stage']}_{moist}"
    elif watered and tilled:
        key = "soil_watered"
    elif watered:
        key = "soil_wet"
    elif tilled:
        key = "soil_tilled"
    else:
        key = "soil"
    if (weather or "").strip().lower() == "snow":
        key += "_snow"
    if tile.get("weedy"):
        key += "_weedy"
    elif tile.get("weed"):
        key += "_weed"
    fert = tile.get("fertilizer") if isinstance(tile.get("fertilizer"), dict) else None
    if fert and fert.get("kind") in {"general", "yield", "growth"}:
        key += f"_fert_{fert['kind']}"
    vine = runner_vine_direction(crop, row, col)
    if vine:
        key += f"_vine_{vine}"
    return key



def _parse_hills_sprite_key(key: str) -> dict | None:
    """Parse hills / mine-entrance sprite keys. Returns None if it is not one."""
    raw = key
    forage = None
    tree = None
    snow = False
    # forage and tree suffixes, longest first
    for kind in ("oyster_mushroom", "wild_mushroom", "wild_onion", "wild_berry"):
        suffix = "_forage_" + kind
        if raw.endswith(suffix):
            forage = kind
            raw = raw[: -len(suffix)]
            break
    for stage in ("mushroom_log", "sapling", "young", "grown", "stump"):
        suffix = "_tree_" + stage
        if raw.endswith(suffix):
            tree = stage
            raw = raw[: -len(suffix)]
            break
    if raw.endswith("_snow"):
        snow = True
        raw = raw[: -len("_snow")]
    grounds = {
        "hills_grass": "grass",
        "grass": "grass",
        "hillside": "hillside",
        "mine_entrance": "mine_entrance",
        "mine_entrance_closed": "mine_entrance",
    }
    typ = grounds.get(raw)
    if not typ:
        return None
    return {
        "kind": typ,
        "type": typ,
        "closed": raw.endswith("closed"),
        "tree": tree,
        "forage": forage,
        "snow": snow,
        "hills": True,
    }


def parse_sprite_key(key: str) -> dict:
    """Inverse of sprite_key, for the SVG generator."""
    key = (key or "").strip().lower()
    mine = _parse_mine_sprite_key(key)
    if mine:
        return mine
    hills = _parse_hills_sprite_key(key)
    if hills:
        return hills
    interior = _parse_cabin_interior_sprite_key(key)
    if interior:
        return interior
    if key == "cabin" or key.startswith("cabin_"):
        weather = "sun"
        fire = False
        tail = key[6:] if key.startswith("cabin_") else ""
        parts = [p for p in tail.split("_") if p]
        if parts and parts[-1] == "fire":
            fire = True
            parts = parts[:-1]
        if parts and parts[0] in {"rain", "snow", "storm", "cloud", "sun"}:
            weather = parts[0]
        return {"kind": "cabin", "weather": weather, "fire": fire}
    weedy = False
    weed = False
    snow = False
    fertilizer = None
    vine = None
    for direction in VINE_DIRECTIONS:
        suffix = "_vine_" + direction
        if key.endswith(suffix):
            vine = direction
            key = key[: -len(suffix)]
            break
    for kind in ("general", "yield", "growth"):
        suffix = "_fert_" + kind
        if key.endswith(suffix):
            fertilizer = kind
            key = key[: -len(suffix)]
            break
    if key.endswith("_weedy"):
        weedy = True
        key = key[: -len("_weedy")]
    elif key.endswith("_weed"):
        weed = True
        key = key[: -len("_weed")]
    if key.endswith("_snow"):
        snow = True
        key = key[: -len("_snow")]
    soil_keys = {
        "soil": {"tilled": False, "watered": False},
        "soil_tilled": {"tilled": True, "watered": False},
        "soil_watered": {"tilled": True, "watered": True},
        "soil_wet": {"tilled": False, "watered": True},
    }
    if key in soil_keys:
        return {"kind": "soil", "weed": weed, "weedy": weedy, "snow": snow, "fertilizer": fertilizer, "vine": vine, **soil_keys[key]}
    parts = key.split("_")
    if len(parts) >= 3 and parts[-1] in {"wet", "dry"}:
        moist = parts[-1]
        stage = parts[-2]
        kind = "_".join(parts[:-2])
        return {
            "kind": kind,
            "stage": stage,
            "watered": moist == "wet",
            "tilled": True,
            "weed": weed,
            "weedy": weedy,
            "snow": snow,
            "fertilizer": fertilizer,
            "vine": vine,
        }
    if weed or weedy:
        return {"kind": "unknown", "raw": key, "weed": weed, "weedy": weedy, "snow": snow, "fertilizer": fertilizer, "vine": vine}
    return {"kind": "unknown", "raw": key, "snow": snow, "fertilizer": fertilizer, "vine": vine}


# Warm, slightly dusk palette — lantern light on earth.
P = {
    "sky": "#c9b898",
    "edge": "#2a1c12",
    "soil": "#7a4f2e",
    "soil_dark": "#5a351c",
    "soil_deep": "#3d2414",
    "soil_light": "#9a6a40",
    "tilled": "#623c20",
    "wet": "#3a2a1c",
    "wet_top": "#4a3824",
    "sheen": "#8eb8c4",
    "pebble": "#b08a62",
    "pebble2": "#4a301c",
    "tuft": "#4a6b38",
    "weed": "#5a8a48",
    "weed2": "#3d6b38",
    "weed_tip": "#8fbf5a",
    "weed_flower": "#c9d47a",
    "cabin_wall": "#7a4a28",
    "cabin_wall_d": "#5c3418",
    "cabin_trim": "#3a2414",
    "roof": "#3a2a28",
    "roof_ridge": "#2a1c1c",
    "door": "#4a2c18",
    "step": "#6a4630",
    "glow": "#ffcc66",
    "glow2": "#ffb347",
    "glow_soft": "#ffe2a0",
    "window_in": "#6a3a10",
    "chimney": "#4a3838",
    "smoke": "#d8d0c4",
    "leaf": "#3d6b3a",
    "leaf2": "#2a4a28",
    "leaf3": "#6a9a48",
    "stem": "#3a5a28",
    "kabocha": "#3a6b2a",
    "kabocha_hi": "#5a8a3a",
    "kabocha_stripe": "#c8d48a",
    "kabocha_stem": "#5a4020",
    "turnip": "#f2e6d8",
    "turnip_top": "#7a4d8a",
    "turnip_hi": "#fff8f0",
    "carrot": "#e07a3d",
    "carrot_d": "#c45a22",
    "carrot_hi": "#f0a060",
    "radish": "#d0506a",
    "radish_tip": "#f2e6d8",
    "lettuce": "#6aaa4a",
    "lettuce_hi": "#c6e08a",
    "spinach": "#2f6b38",
    "pea": "#7a9a40",
    "pea_pod": "#5a8a38",
    "beet": "#7a2040",
    "beet_hi": "#c05070",
    "potato": "#d2b07a",
    "potato_d": "#8a6840",
    "bean": "#3d8a3a",
    "bean_pod": "#5aaa48",
    "cucumber": "#3d8a4a",
    "cucumber_stripe": "#c8e0a0",
    "zucchini": "#4a8a28",
    "zucchini_hi": "#8aba50",
    "tomato": "#c43c28",
    "tomato_hi": "#e87850",
    "pumpkin": "#e07a28",
    "pumpkin_hi": "#f0a050",
    "pumpkin_rib": "#b85a18",
    "corn": "#e8c84a",
    "corn_husk": "#5a8a38",
    "onion": "#d8c078",
    "onion_skin": "#c9a050",
    "rhubarb": "#c04048",
    "rhubarb_leaf": "#3d6b3a",
    "asparagus": "#4a7a38",
    "asparagus_tip": "#6a9a48",
    "berry": "#c43c3c",
    "berry_hi": "#e07060",
    "berry_seed": "#f2e6c8",
    "berry_unripe": "#7a9a48",
    "berry_flower": "#f4efe6",
    "seed": "#d8c070",
    "seed_d": "#8a7030",
    "mound": "#8a5a30",
    "wither": "#8a7a54",
    "wither_d": "#5a4a30",
}


def _svg(body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" '
        f'width="{SIZE}" height="{SIZE}">\n{body}\n</svg>\n'
    )


def _soil_layer(tilled: bool, watered: bool) -> str:
    if watered:
        base, top, edge = P["wet"], P["wet_top"], P["soil_deep"]
    elif tilled:
        base, top, edge = P["tilled"], P["soil_dark"], P["soil_deep"]
    else:
        base, top, edge = P["soil"], P["soil_light"], P["soil_dark"]
    parts = [
        f'<rect width="{SIZE}" height="{SIZE}" fill="{top}"/>',
        f'<ellipse cx="80" cy="92" rx="74" ry="58" fill="{base}"/>',
        f'<ellipse cx="80" cy="96" rx="70" ry="50" fill="{base}"/>',
        f'<path d="M8,100 Q40,86 80,92 Q120,98 152,88 L152,160 L8,160 Z" '
        f'fill="{edge}" opacity="0.35"/>',
    ]
    if tilled:
        furrow = P["soil_deep"] if not watered else "#241810"
        for y, dx in ((70, 0), (86, 6), (102, -4), (118, 5)):
            parts.append(
                f'<path d="M18,{y} Q50,{y-8+dx} 80,{y+2} Q110,{y+8} 142,{y-2}" '
                f'stroke="{furrow}" stroke-width="4" fill="none" '
                f'stroke-linecap="round" opacity="0.7"/>'
            )
    else:
        parts.append(f'<circle cx="36" cy="108" r="4" fill="{P["pebble"]}" opacity="0.7"/>')
        parts.append(f'<circle cx="118" cy="96" r="3" fill="{P["pebble2"]}" opacity="0.55"/>')
        parts.append(f'<circle cx="96" cy="124" r="3.5" fill="{P["pebble"]}" opacity="0.45"/>')
        parts.append(
            f'<path d="M24,78 c4,-10 10,-8 8,0" fill="{P["tuft"]}" opacity="0.8"/>'
        )
        parts.append(
            f'<path d="M132,84 c3,-8 8,-6 6,1" fill="{P["tuft"]}" opacity="0.7"/>'
        )
    if watered:
        parts.append(
            f'<ellipse cx="58" cy="110" rx="18" ry="7" fill="{P["sheen"]}" opacity="0.28"/>'
        )
        parts.append(
            f'<ellipse cx="108" cy="122" rx="14" ry="5" fill="{P["sheen"]}" opacity="0.22"/>'
        )
        parts.append(
            f'<path d="M44,104 q8,-6 16,0" stroke="{P["sheen"]}" stroke-width="1.4" '
            f'fill="none" opacity="0.45"/>'
        )
    return "\n".join(parts)


def _snow_ground_overlay(tilled: bool) -> str:
    """A soft snow blanket for Classic SVG tiles, with earth still showing through."""
    patches = [
        (40, 48, 22, 12, 0.72),
        (90, 42, 26, 14, 0.65),
        (128, 70, 18, 11, 0.6),
        (28, 88, 24, 13, 0.7),
        (80, 84, 30, 16, 0.55),
        (118, 108, 22, 12, 0.68),
        (52, 122, 26, 12, 0.62),
        (96, 134, 20, 10, 0.58),
        (18, 54, 12, 8, 0.5),
        (140, 128, 14, 8, 0.55),
    ]
    if tilled:
        # Sit the snow more in the hollows, leave clod tops browner.
        patches = [
            (36, 78, 28, 8, 0.7),
            (86, 70, 32, 9, 0.62),
            (124, 86, 24, 8, 0.66),
            (48, 100, 30, 8, 0.6),
            (100, 110, 28, 9, 0.68),
            (30, 122, 22, 8, 0.58),
            (78, 132, 26, 8, 0.64),
            (130, 124, 18, 7, 0.55),
        ]
    parts = []
    for x, y, rx, ry, op in patches:
        parts.append(
            f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" '
            f'fill="#f2efe8" opacity="{op}"/>'
        )
        parts.append(
            f'<ellipse cx="{x-4}" cy="{y-2}" rx="{int(rx*0.45)}" ry="{int(ry*0.45)}" '
            f'fill="#ffffff" opacity="0.35"/>'
        )
    return "\n".join(parts)


def _seed_sprout_xy() -> tuple[int, int]:
    return 80, 96


def _draw_seed(x: int, y: int) -> str:
    return (
        f'<ellipse cx="{x}" cy="{y+8}" rx="16" ry="7" fill="{P["mound"]}"/>'
        f'<ellipse cx="{x}" cy="{y+2}" rx="7" ry="5" fill="{P["seed"]}" '
        f'stroke="{P["seed_d"]}" stroke-width="1"/>'
        f'<path d="M{x-3},{y+2} q3,-3 6,0" stroke="{P["seed_d"]}" '
        f'stroke-width="0.8" fill="none"/>'
    )


def _sprout(x: int, y: int, leaf: str) -> str:
    return (
        f'<path d="M{x},{y+14} C{x},{y+4} {x},{y-4} {x},{y-10}" '
        f'stroke="{P["stem"]}" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        f'<ellipse cx="{x-8}" cy="{y-8}" rx="8" ry="5" fill="{leaf}" '
        f'transform="rotate(-30 {x-8} {y-8})"/>'
        f'<ellipse cx="{x+8}" cy="{y-7}" rx="8" ry="5" fill="{P["leaf3"]}" '
        f'transform="rotate(25 {x+8} {y-7})"/>'
    )


def _growing_leaves(x: int, y: int, extra: str = "") -> str:
    return (
        f'<path d="M{x},{y+16} C{x-2},{y} {x-1},{y-20} {x},{y-28}" '
        f'stroke="{P["stem"]}" stroke-width="3" fill="none" stroke-linecap="round"/>'
        f'<ellipse cx="{x-14}" cy="{y-10}" rx="12" ry="7" fill="{P["leaf"]}" '
        f'transform="rotate(-35 {x-14} {y-10})"/>'
        f'<ellipse cx="{x+14}" cy="{y-12}" rx="13" ry="7" fill="{P["leaf3"]}" '
        f'transform="rotate(30 {x+14} {y-12})"/>'
        f'<ellipse cx="{x-8}" cy="{y-24}" rx="9" ry="5" fill="{P["leaf2"]}" '
        f'transform="rotate(-15 {x-8} {y-24})"/>'
        f"{extra}"
    )


def _kabocha_fruit(x: int, y: int, scale: float = 1.0) -> str:
    rx, ry = 22 * scale, 18 * scale
    return (
        f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{P["kabocha"]}"/>'
        f'<ellipse cx="{x-4}" cy="{y-3}" rx="{rx*0.45}" ry="{ry*0.4}" '
        f'fill="{P["kabocha_hi"]}" opacity="0.45"/>'
        f'<path d="M{x},{y-ry} Q{x-8},{y} {x},{y+ry}" stroke="{P["kabocha_stripe"]}" '
        f'stroke-width="{1.6*scale}" fill="none" opacity="0.7"/>'
        f'<path d="M{x-10*scale},{y-ry+3} Q{x-14*scale},{y} {x-8*scale},{y+ry-2}" '
        f'stroke="{P["kabocha_stripe"]}" stroke-width="{1.4*scale}" fill="none" opacity="0.55"/>'
        f'<path d="M{x+10*scale},{y-ry+3} Q{x+14*scale},{y} {x+8*scale},{y+ry-2}" '
        f'stroke="{P["kabocha_stripe"]}" stroke-width="{1.4*scale}" fill="none" opacity="0.55"/>'
        f'<rect x="{x-2*scale}" y="{y-ry-6*scale}" width="{4*scale}" height="{8*scale}" '
        f'rx="1.5" fill="{P["kabocha_stem"]}"/>'
    )


def _turnip_fruit(x: int, y: int, scale: float = 1.0) -> str:
    return (
        f'<ellipse cx="{x}" cy="{y+2}" rx="{16*scale}" ry="{14*scale}" fill="{P["turnip"]}"/>'
        f'<path d="M{x-16*scale},{y} Q{x},{y-8*scale} {x+16*scale},{y} '
        f'Q{x},{y+4*scale} {x-16*scale},{y}" fill="{P["turnip_top"]}"/>'
        f'<ellipse cx="{x-5}" cy="{y+4}" rx="{5*scale}" ry="{4*scale}" '
        f'fill="{P["turnip_hi"]}" opacity="0.7"/>'
        f'<path d="M{x},{y-10*scale} C{x-10},{y-22*scale} {x-18},{y-18*scale} {x-16},{y-12*scale}" '
        f'stroke="{P["leaf"]}" stroke-width="2" fill="none"/>'
        f'<path d="M{x},{y-10*scale} C{x+4},{y-24*scale} {x+14},{y-22*scale} {x+12},{y-12*scale}" '
        f'stroke="{P["leaf3"]}" stroke-width="2" fill="none"/>'
        f'<path d="M{x},{y-10*scale} C{x-2},{y-26*scale} {x+6},{y-28*scale} {x+2},{y-16*scale}" '
        f'stroke="{P["leaf2"]}" stroke-width="2" fill="none"/>'
    )


def _carrot_fruit(x: int, y: int, scale: float = 1.0) -> str:
    return (
        f'<path d="M{x},{y-6*scale} L{x+8*scale},{y+2*scale} L{x},{y+26*scale} '
        f'L{x-8*scale},{y+2*scale} Z" fill="{P["carrot"]}"/>'
        f'<path d="M{x-2*scale},{y-2*scale} L{x},{y+16*scale}" stroke="{P["carrot_hi"]}" '
        f'stroke-width="1.2" opacity="0.7"/>'
        f'<path d="M{x},{y-6*scale} C{x-8},{y-22*scale} {x-18},{y-16*scale} {x-14},{y-8*scale}" '
        f'stroke="{P["leaf"]}" stroke-width="2" fill="none"/>'
        f'<path d="M{x},{y-6*scale} C{x+2},{y-24*scale} {x-4},{y-28*scale} {x},{y-16*scale}" '
        f'stroke="{P["leaf3"]}" stroke-width="2" fill="none"/>'
        f'<path d="M{x},{y-6*scale} C{x+10},{y-22*scale} {x+16},{y-14*scale} {x+12},{y-6*scale}" '
        f'stroke="{P["leaf2"]}" stroke-width="2" fill="none"/>'
    )


def _round_root(x: int, y: int, fill: str, hi: str, scale: float = 1.0, leaves: bool = True) -> str:
    body = (
        f'<ellipse cx="{x}" cy="{y+4}" rx="{15*scale}" ry="{13*scale}" fill="{fill}"/>'
        f'<ellipse cx="{x-4}" cy="{y+2}" rx="{5*scale}" ry="{4*scale}" fill="{hi}" opacity="0.55"/>'
    )
    if leaves:
        body += (
            f'<path d="M{x},{y-8*scale} C{x-10},{y-20*scale} {x-16},{y-16*scale} {x-14},{y-10*scale}" '
            f'stroke="{P["leaf"]}" stroke-width="2" fill="none"/>'
            f'<path d="M{x},{y-8*scale} C{x+8},{y-22*scale} {x+16},{y-16*scale} {x+12},{y-8*scale}" '
            f'stroke="{P["leaf3"]}" stroke-width="2" fill="none"/>'
        )
    return body


def _leafy_head(x: int, y: int, fill: str, hi: str, scale: float = 1.0) -> str:
    return (
        f'<ellipse cx="{x}" cy="{y}" rx="{18*scale}" ry="{14*scale}" fill="{fill}"/>'
        f'<ellipse cx="{x-6}" cy="{y-2}" rx="{8*scale}" ry="{6*scale}" fill="{hi}" opacity="0.55"/>'
        f'<ellipse cx="{x+8}" cy="{y+3}" rx="{7*scale}" ry="{5*scale}" fill="{P["leaf2"]}" opacity="0.5"/>'
        f'<ellipse cx="{x}" cy="{y-8*scale}" rx="{10*scale}" ry="{5*scale}" fill="{fill}"/>'
    )


def _pod_cluster(x: int, y: int, fill: str, n: int = 3, scale: float = 1.0) -> str:
    bits = [_growing_leaves(x, y - 8)]
    for i, dx in enumerate((-12, 0, 12)[:n]):
        yy = y + 4 + (i % 2) * 4
        bits.append(
            f'<ellipse cx="{x+dx*scale}" cy="{yy}" rx="{8*scale}" ry="{3.5*scale}" '
            f'fill="{fill}" transform="rotate({-25+i*20} {x+dx*scale} {yy})"/>'
        )
    return "".join(bits)


def _vine_fruit(x: int, y: int, fill: str, hi: str, rx: float, ry: float, scale: float = 1.0) -> str:
    return (
        _growing_leaves(x, y - 10)
        + f'<ellipse cx="{x}" cy="{y+8}" rx="{rx*scale}" ry="{ry*scale}" fill="{fill}"/>'
        + f'<ellipse cx="{x-4*scale}" cy="{y+6}" rx="{rx*0.35*scale}" ry="{ry*0.3*scale}" fill="{hi}" opacity="0.5"/>'
    )


def _corn_ear(x: int, y: int, scale: float = 1.0) -> str:
    return (
        _growing_leaves(x, y - 16)
        + f'<rect x="{x-7*scale}" y="{y-6*scale}" width="{14*scale}" height="{28*scale}" rx="{6*scale}" fill="{P["corn_husk"]}"/>'
        + f'<rect x="{x-5*scale}" y="{y-2*scale}" width="{10*scale}" height="{20*scale}" rx="{4*scale}" fill="{P["corn"]}"/>'
    )


def _onion_bulb(x: int, y: int, scale: float = 1.0) -> str:
    return (
        f'<ellipse cx="{x}" cy="{y+6}" rx="{14*scale}" ry="{13*scale}" fill="{P["onion"]}"/>'
        f'<path d="M{x-10*scale},{y+2} Q{x},{y-4} {x+10*scale},{y+2}" stroke="{P["onion_skin"]}" fill="none" stroke-width="1.2"/>'
        f'<path d="M{x},{y-6*scale} C{x-4},{y-20*scale} {x-10},{y-18*scale} {x-8},{y-10*scale}" stroke="{P["leaf3"]}" stroke-width="2" fill="none"/>'
        f'<path d="M{x},{y-6*scale} C{x+6},{y-22*scale} {x+12},{y-16*scale} {x+8},{y-8*scale}" stroke="{P["leaf"]}" stroke-width="2" fill="none"/>'
    )


def _rhubarb_mature(x: int, y: int, scale: float = 1.0) -> str:
    return (
        f'<path d="M{x-8},{y+12} L{x-10},{y-8}" stroke="{P["rhubarb"]}" stroke-width="{4*scale}" fill="none" stroke-linecap="round"/>'
        f'<path d="M{x+2},{y+12} L{x+4},{y-14}" stroke="{P["rhubarb"]}" stroke-width="{4.5*scale}" fill="none" stroke-linecap="round"/>'
        f'<path d="M{x+10},{y+12} L{x+14},{y-6}" stroke="{P["rhubarb"]}" stroke-width="{3.5*scale}" fill="none" stroke-linecap="round"/>'
        f'<ellipse cx="{x-12}" cy="{y-12}" rx="{12*scale}" ry="{8*scale}" fill="{P["rhubarb_leaf"]}"/>'
        f'<ellipse cx="{x+6}" cy="{y-18}" rx="{14*scale}" ry="{9*scale}" fill="{P["leaf"]}"/>'
        f'<ellipse cx="{x+16}" cy="{y-10}" rx="{11*scale}" ry="{7*scale}" fill="{P["leaf3"]}"/>'
    )


def _asparagus_spears(x: int, y: int, scale: float = 1.0, n: int = 3) -> str:
    bits = []
    for i, dx in enumerate((-10, 0, 10)[:n]):
        bits.append(
            f'<path d="M{x+dx},{y+14} L{x+dx},{y-10}" stroke="{P["asparagus"]}" '
            f'stroke-width="{3.2*scale}" fill="none" stroke-linecap="round"/>'
            f'<ellipse cx="{x+dx}" cy="{y-12}" rx="{3.5*scale}" ry="{5*scale}" fill="{P["asparagus_tip"]}"/>'
        )
    return "".join(bits)


def _potato_hill(x: int, y: int, scale: float = 1.0) -> str:
    return (
        _growing_leaves(x, y - 8)
        + f'<ellipse cx="{x-10}" cy="{y+10}" rx="{9*scale}" ry="{6*scale}" fill="{P["potato"]}"/>'
        + f'<ellipse cx="{x+8}" cy="{y+12}" rx="{8*scale}" ry="{5.5*scale}" fill="{P["potato_d"]}"/>'
        + f'<ellipse cx="{x+2}" cy="{y+6}" rx="{7*scale}" ry="{5*scale}" fill="{P["potato"]}"/>'
    )


def _draw_crown(x: int, y: int) -> str:
    return (
        f'<ellipse cx="{x}" cy="{y+8}" rx="18" ry="8" fill="{P["mound"]}"/>'
        f'<ellipse cx="{x-6}" cy="{y+2}" rx="7" ry="5" fill="{P["seed"]}"/>'
        f'<ellipse cx="{x+6}" cy="{y+1}" rx="6" ry="4.5" fill="{P["seed_d"]}"/>'
        f'<path d="M{x},{y+2} L{x},{y-6}" stroke="{P["stem"]}" stroke-width="2" fill="none"/>'
    )


def _withered_plant(x: int, y: int) -> str:
    return (
        f'<path d="M{x},{y+12} C{x+6},{y} {x+14},{y-8} {x+18},{y-6}" '
        f'stroke="{P["wither_d"]}" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
        f'<ellipse cx="{x+20}" cy="{y-8}" rx="7" ry="4" fill="{P["wither"]}" '
        f'transform="rotate(25 {x+20} {y-8})"/>'
        f'<ellipse cx="{x+10}" cy="{y-2}" rx="6" ry="3" fill="{P["wither_d"]}" '
        f'transform="rotate(10 {x+10} {y-2})"/>'
    )


def _strawberry_berry(x: float, y: float, scale: float = 1.0, ripe: bool = True) -> str:
    fill = P["berry"] if ripe else P["berry_unripe"]
    rx, ry = 7 * scale, 8 * scale
    bits = [
        f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}"/>',
        f'<path d="M{x},{y-ry} L{x-2.2*scale},{y-ry-3*scale} L{x+2.2*scale},{y-ry-3*scale} Z" '
        f'fill="{P["leaf3"]}"/>',
    ]
    if ripe:
        bits.append(
            f'<ellipse cx="{x-2*scale}" cy="{y-2*scale}" rx="{2.2*scale}" ry="{1.6*scale}" '
            f'fill="{P["berry_hi"]}" opacity="0.55"/>'
        )
        for sx, sy in ((-2.0, 1.5), (1.8, 0.5), (0.2, 3.4)):
            bits.append(
                f'<circle cx="{x+sx*scale}" cy="{y+sy*scale}" r="{0.7*scale}" '
                f'fill="{P["berry_seed"]}" opacity="0.85"/>'
            )
    return "".join(bits)


def _strawberry_cluster(x: int, y: int, ripe: bool = True, scale: float = 1.0) -> str:
    if ripe:
        return (
            _strawberry_berry(x - 10 * scale, y + 2 * scale, 0.85 * scale, True)
            + _strawberry_berry(x + 11 * scale, y + 1 * scale, 0.8 * scale, True)
            + _strawberry_berry(x, y + 8 * scale, 1.05 * scale, True)
        )
    return (
        _strawberry_berry(x - 8 * scale, y + 6 * scale, 0.55 * scale, False)
        + _strawberry_berry(x + 8 * scale, y + 7 * scale, 0.5 * scale, False)
    )


def _dormant_plant(x: int, y: int, kind: str) -> str:
    """A living plant tucked in for autumn and winter — no fruit, muted leaves."""
    leaf = P.get("wither") or "#8a7a54"
    leaf_d = P.get("wither_d") or "#5a4a30"
    stem = P.get("stem") or "#3a5a28"
    if kind in {"strawberry", "everbearing"}:
        return (
            f'<path d="M{x},{y+14} C{x-1},{y+2} {x-1},{y-8} {x},{y-14}" '
            f'stroke="{stem}" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
            f'<ellipse cx="{x-9}" cy="{y-4}" rx="8" ry="4.5" fill="{leaf_d}" '
            f'transform="rotate(-28 {x-9} {y-4})"/>'
            f'<ellipse cx="{x+9}" cy="{y-6}" rx="8" ry="4.5" fill="{leaf}" '
            f'transform="rotate(24 {x+9} {y-6})"/>'
            f'<ellipse cx="{x}" cy="{y-12}" rx="6" ry="3.5" fill="{leaf_d}" '
            f'opacity="0.85"/>'
        )
    return _withered_plant(x, y)


def _crop_layer(kind: str, stage: str) -> str:
    x, y = 80, 100
    if stage == "withered":
        return _withered_plant(x, y)
    if stage == "dormant":
        return _dormant_plant(x, y, kind)
    if stage == "crown":
        return _draw_crown(x, y)
    if stage == "seed":
        return _draw_seed(x, y)
    if stage in {"sprouting", "regrowing", "seedling"}:
        leaf = {
            "kabocha": P["leaf"],
            "turnip": P["leaf3"],
            "carrot": P["leaf"],
            "strawberry": P["leaf3"],
            "everbearing": P["leaf3"],
            "radish": P["leaf3"],
            "lettuce": P["lettuce"],
            "spinach": P["spinach"],
            "pea": P["pea"],
            "beet": P["leaf"],
            "potato": P["leaf"],
            "bush_bean": P["bean"],
            "cucumber": P["cucumber"],
            "zucchini": P["zucchini"],
            "tomato": P["leaf"],
            "pumpkin": P["leaf"],
            "corn": P["corn_husk"],
            "onion": P["leaf3"],
            "rhubarb": P["rhubarb_leaf"],
            "asparagus": P["asparagus"],
        }.get(kind, P["leaf"])
        return _sprout(x, y, leaf)
    if stage == "growing":
        extra = ""
        if kind == "kabocha":
            extra = _kabocha_fruit(x, y + 6, 0.45)
        elif kind == "pumpkin":
            extra = f'<ellipse cx="{x}" cy="{y+8}" rx="10" ry="8" fill="{P["pumpkin"]}"/>'
        elif kind == "turnip":
            extra = f'<ellipse cx="{x}" cy="{y+8}" rx="8" ry="6" fill="{P["turnip_top"]}"/>'
        elif kind == "carrot":
            extra = (
                f'<path d="M{x},{y+4} L{x+4},{y+8} L{x},{y+16} L{x-4},{y+8} Z" '
                f'fill="{P["carrot"]}"/>'
            )
        elif kind == "radish":
            extra = f'<ellipse cx="{x}" cy="{y+8}" rx="7" ry="6" fill="{P["radish"]}"/>'
        elif kind == "beet":
            extra = f'<ellipse cx="{x}" cy="{y+8}" rx="8" ry="7" fill="{P["beet"]}"/>'
        elif kind == "onion":
            extra = f'<ellipse cx="{x}" cy="{y+8}" rx="7" ry="6" fill="{P["onion"]}"/>'
        elif kind == "tomato":
            extra = f'<ellipse cx="{x}" cy="{y-2}" rx="5" ry="5" fill="{P["berry_unripe"]}"/>'
        elif kind in {"strawberry", "everbearing"}:
            scale = 0.75 if kind == "everbearing" else 0.9
            extra = (
                f'<ellipse cx="{x}" cy="{y-6}" rx="4" ry="4" fill="{P["berry_flower"]}"/>'
                f'<ellipse cx="{x+12}" cy="{y-2}" rx="3.2" ry="3.2" fill="{P["berry_flower"]}"/>'
                + _strawberry_cluster(x, y, ripe=False, scale=scale)
            )
        return _growing_leaves(x, y, extra)
    # mature
    if kind == "kabocha":
        return _growing_leaves(x, y - 6) + _kabocha_fruit(x, y + 8, 1.0)
    if kind == "pumpkin":
        return _growing_leaves(x, y - 6) + (
            f'<ellipse cx="{x}" cy="{y+8}" rx="24" ry="18" fill="{P["pumpkin"]}"/>'
            f'<path d="M{x},{y-10} Q{x-6},{y+8} {x},{y+26}" stroke="{P["pumpkin_rib"]}" fill="none" stroke-width="1.6"/>'
            f'<ellipse cx="{x-6}" cy="{y+4}" rx="8" ry="6" fill="{P["pumpkin_hi"]}" opacity="0.45"/>'
            f'<rect x="{x-2}" y="{y-16}" width="4" height="8" rx="1.5" fill="{P["kabocha_stem"]}"/>'
        )
    if kind == "turnip":
        return _turnip_fruit(x, y + 4, 1.05)
    if kind == "carrot":
        return _carrot_fruit(x, y, 1.05)
    if kind == "radish":
        return _round_root(x, y + 2, P["radish"], P["radish_tip"])
    if kind == "beet":
        return _round_root(x, y + 2, P["beet"], P["beet_hi"])
    if kind == "lettuce":
        return _leafy_head(x, y, P["lettuce"], P["lettuce_hi"])
    if kind == "spinach":
        return _leafy_head(x, y, P["spinach"], P["leaf3"], 0.9)
    if kind == "pea":
        return _pod_cluster(x, y, P["pea_pod"])
    if kind == "bush_bean":
        return _pod_cluster(x, y, P["bean_pod"])
    if kind == "cucumber":
        return _vine_fruit(x, y, P["cucumber"], P["cucumber_stripe"], 18, 7)
    if kind == "zucchini":
        return _vine_fruit(x, y, P["zucchini"], P["zucchini_hi"], 16, 8)
    if kind == "tomato":
        return _growing_leaves(x, y - 4) + (
            f'<ellipse cx="{x-10}" cy="{y+6}" rx="8" ry="8" fill="{P["tomato"]}"/>'
            f'<ellipse cx="{x+8}" cy="{y+8}" rx="7" ry="7" fill="{P["tomato"]}"/>'
            f'<ellipse cx="{x}" cy="{y+2}" rx="6" ry="6" fill="{P["tomato_hi"]}"/>'
        )
    if kind == "potato":
        return _potato_hill(x, y)
    if kind == "corn":
        return _corn_ear(x, y)
    if kind == "onion":
        return _onion_bulb(x, y)
    if kind == "rhubarb":
        return _rhubarb_mature(x, y)
    if kind == "asparagus":
        return _asparagus_spears(x, y)
    if kind == "strawberry":
        return _growing_leaves(x, y - 4) + _strawberry_cluster(x, y + 4, ripe=True)
    if kind == "everbearing":
        # Same plant, slightly smaller berries and an extra blossom so the two are distinct.
        return (
            _growing_leaves(x, y - 4)
            + f'<ellipse cx="{x+16}" cy="{y-10}" rx="3.4" ry="3.4" fill="{P["berry_flower"]}"/>'
            + _strawberry_cluster(x, y + 6, ripe=True, scale=0.8)
        )
    return _growing_leaves(x, y)


def _cabin_sky(weather: str) -> tuple[str, str]:
    """Ground and sky fills. Sunny keeps the original warm dusk colours."""
    if weather == "rain":
        return "#3a4550", "#4a5868"
    if weather == "storm":
        return "#2a303c", "#3a4454"
    if weather == "snow":
        return "#5a626c", "#8a93a0"
    if weather == "cloud":
        return "#45423c", "#5c5a54"
    return "#4a3a2c", "#5c4a38"


def _cabin_weather_overlay(weather: str) -> str:
    """Rain streaks, snow on the roof and flakes, storm, or overcast clouds."""
    if weather == "cloud":
        return """
  <ellipse cx="48" cy="28" rx="22" ry="10" fill="#7a7870" opacity="0.7"/>
  <ellipse cx="66" cy="24" rx="18" ry="9" fill="#8a8880" opacity="0.65"/>
  <ellipse cx="30" cy="26" rx="12" ry="7" fill="#6e6c66" opacity="0.55"/>
"""
    if weather in {"rain", "storm"}:
        heavy = weather == "storm"
        opacity = "0.55" if heavy else "0.4"
        width = "1.6" if heavy else "1.2"
        color = "#c8d8e8" if heavy else "#b4c4d4"
        # Diagonal streaks, some in front of the cabin.
        streaks = []
        coords = [
            (12, 8, 28, 48), (32, 2, 50, 46), (54, 6, 72, 50),
            (76, 0, 94, 44), (98, 8, 116, 52), (122, 4, 140, 48),
            (148, 10, 158, 40), (20, 50, 38, 92), (60, 54, 78, 98),
            (100, 48, 118, 94), (130, 56, 148, 100), (8, 88, 24, 128),
            (44, 96, 60, 136), (88, 100, 106, 142), (126, 108, 144, 148),
        ]
        if heavy:
            coords += [
                (18, 14, 36, 58), (70, 10, 88, 54), (110, 16, 128, 62),
                (40, 70, 56, 112), (150, 70, 158, 110),
            ]
        for x1, y1, x2, y2 in coords:
            streaks.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="{color}" stroke-width="{width}" opacity="{opacity}" '
                f'stroke-linecap="round"/>'
            )
        lightning = ""
        if heavy:
            lightning = (
                '<path d="M92,8 L84,28 L90,28 L80,50" fill="none" '
                'stroke="#efe4b8" stroke-width="1.8" opacity="0.55" '
                'stroke-linejoin="round" stroke-linecap="round"/>'
            )
        return "\n  " + lightning + "\n  " + "\n  ".join(streaks) + "\n"
    if weather == "snow":
        # A soft cap along the roof ridge, plus falling flakes.
        cap = (
            '<path d="M30,60 L80,24 L130,60 L124,58 L80,30 L36,58 Z" '
            'fill="#f2efe8" opacity="0.92"/>'
            '<ellipse cx="80" cy="30" rx="10" ry="5" fill="#f7f4ee"/>'
            '<rect x="107" y="32" width="14" height="6" fill="#f2efe8" opacity="0.9"/>'
        )
        flakes = []
        spots = [
            (18, 16, 2.2), (40, 10, 1.6), (58, 22, 2.0), (92, 8, 1.8),
            (114, 18, 2.1), (138, 12, 1.7), (150, 28, 1.5), (24, 48, 1.4),
            (48, 40, 1.8), (128, 44, 1.6), (18, 80, 1.5), (146, 72, 1.7),
            (36, 108, 1.6), (70, 100, 1.3), (118, 112, 1.8), (152, 100, 1.4),
            (10, 130, 1.5), (88, 128, 1.6), (140, 138, 1.4), (54, 148, 1.3),
        ]
        for x, y, r in spots:
            flakes.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#f4f1ea" opacity="0.9"/>')
        return "\n  " + cap + "\n  " + "\n  ".join(flakes) + "\n"
    return ""


def svg_cabin(weather: str | None = None, fire: bool = False) -> str:
    weather = (weather or "sun").strip().lower()
    if weather not in {"rain", "snow", "storm", "cloud", "sun"}:
        weather = "sun"
    ground, sky = _cabin_sky(weather)
    overlay = _cabin_weather_overlay(weather)
    fire_bit = ""
    if fire:
        # Extra chimney smoke only — the weather/ground colours stay the same.
        fire_bit = (
            f'<path d="M111,24 q8,-16 18,-8" stroke="{P["smoke"]}" stroke-width="4" '
            f'fill="none" opacity="0.7" stroke-linecap="round"/>'
            f'<path d="M122,16 q8,-12 14,-4" stroke="{P["smoke"]}" stroke-width="3" '
            f'fill="none" opacity="0.45" stroke-linecap="round"/>'
        )
    body = f"""
  <rect width="{SIZE}" height="{SIZE}" fill="{ground}"/>
  <rect width="{SIZE}" height="70" fill="{sky}"/>
  <ellipse cx="80" cy="130" rx="78" ry="28" fill="{P["soil_dark"]}"/>
  <rect x="0" y="118" width="160" height="42" fill="{P["soil"]}"/>
  <path d="M0,118 Q40,110 80,116 Q120,122 160,112 L160,130 L0,130 Z" fill="{P["tilled"]}"/>
  <!-- lantern glow behind the cabin -->
  <ellipse cx="108" cy="88" rx="28" ry="22" fill="{P["glow"]}" opacity="0.35"/>
  <ellipse cx="108" cy="88" rx="16" ry="14" fill="{P["glow_soft"]}" opacity="0.45"/>
  <!-- cabin body -->
  <rect x="36" y="58" width="88" height="62" fill="{P["cabin_wall"]}" stroke="{P["cabin_trim"]}" stroke-width="2"/>
  <rect x="36" y="88" width="88" height="8" fill="{P["cabin_wall_d"]}" opacity="0.4"/>
  <!-- roof -->
  <polygon points="28,62 80,22 132,62" fill="{P["roof"]}"/>
  <polygon points="28,62 80,22 80,30 40,62" fill="{P["roof_ridge"]}" opacity="0.45"/>
  <rect x="108" y="34" width="12" height="22" fill="{P["chimney"]}"/>
  <path d="M111,28 q5,-10 12,-6" stroke="{P["smoke"]}" stroke-width="3" fill="none" opacity="0.55" stroke-linecap="round"/>
  <path d="M118,22 q6,-8 11,-3" stroke="{P["smoke"]}" stroke-width="2.2" fill="none" opacity="0.35" stroke-linecap="round"/>
  <!-- door -->
  <rect x="50" y="82" width="20" height="38" rx="2" fill="{P["door"]}"/>
  <circle cx="66" cy="102" r="1.6" fill="{P["glow"]}"/>
  <rect x="48" y="118" width="24" height="5" fill="{P["step"]}"/>
  <!-- lantern window -->
  <rect x="92" y="76" width="22" height="22" fill="{P["window_in"]}" stroke="{P["cabin_trim"]}" stroke-width="2"/>
  <rect x="93" y="77" width="20" height="20" fill="{P["glow"]}"/>
  <rect x="93" y="77" width="20" height="20" fill="{P["glow2"]}" opacity="0.6"/>
  <line x1="103" y1="77" x2="103" y2="97" stroke="{P["cabin_trim"]}" stroke-width="1.4"/>
  <line x1="93" y1="87" x2="113" y2="87" stroke="{P["cabin_trim"]}" stroke-width="1.4"/>
  <!-- hanging lantern in the window -->
  <path d="M103,80 v3" stroke="{P["cabin_trim"]}" stroke-width="1"/>
  <path d="M99,83 l8,0 l1,6 l-10,0 z" fill="#e8a020" stroke="#6a3a10" stroke-width="0.7"/>
  <circle cx="103" cy="87" r="2" fill="{P["glow_soft"]}"/>
  {fire_bit}
  {overlay}
"""
    return _svg(body)


def svg_unknown(key: str) -> str:
    safe = (
        key.replace("&", "")
        .replace("<", "")
        .replace(">", "")
        .replace('"', "")
        .replace("'", "")
    )
    return _svg(
        f'<rect width="{SIZE}" height="{SIZE}" fill="#3a2a20"/>'
        f'<text x="80" y="84" text-anchor="middle" fill="#e8d8c0" '
        f'font-size="12" font-family="serif">{safe}</text>'
    )


def _weed_clump(x: int, y: int, fuller: bool = False, flip: bool = False) -> str:
    """One small corner weed. Coordinates are the base of the stem."""
    # A little darker/more saturated than the old mid-green, so clumps read on snow.
    leaf, dark, tip, flower = "#3f6e32", "#2a4f24", "#5a8a30", "#c9d47a"
    s = -1 if flip else 1
    stem_h = 20 if fuller else 16
    parts = [
        f'<path d="M{x},{y} C{x-s},{y-8} {x},{y-stem_h} {x},{y-stem_h}" '
        f'stroke="{dark}" stroke-width="2" fill="none" stroke-linecap="round"/>',
        f'<ellipse cx="{x-7*s}" cy="{y-10}" rx="7" ry="4" fill="{leaf}" '
        f'transform="rotate({-28*s} {x-7*s} {y-10})"/>',
        f'<ellipse cx="{x+7*s}" cy="{y-12}" rx="6.5" ry="3.6" fill="{tip}" '
        f'transform="rotate({26*s} {x+7*s} {y-12})"/>',
    ]
    if fuller:
        parts.append(
            f'<path d="M{x+10*s},{y+2} C{x+12*s},{y-10} {x+9*s},{y-20} {x+9*s},{y-20}" '
            f'stroke="{dark}" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
        )
        parts.append(
            f'<ellipse cx="{x+16*s}" cy="{y-14}" rx="6" ry="3.2" fill="{leaf}" '
            f'transform="rotate({30*s} {x+16*s} {y-14})"/>'
        )
        parts.append(f'<circle cx="{x+9*s}" cy="{y-21}" r="2.2" fill="{flower}"/>')
    else:
        parts.append(f'<circle cx="{x}" cy="{y-stem_h-1}" r="1.6" fill="{flower}" opacity="0.85"/>')
    return "\n".join(parts)


def _fertilizer_overlay(kind: str | None) -> str:
    """Little teal/green granules on the dirt, under the crop."""
    if kind == "yield":
        fill, hi = "#2a6b2a", "#9ad48a"
    elif kind == "growth":
        fill, hi = "#2a5a6b", "#8ad4ce"
    else:
        fill, hi = "#1f6b5a", "#7dcec0"
    # Scattered near the soil surface, kept out of the crop's centre.
    spots = (
        (28, 118, 3.2), (48, 132, 2.6), (72, 124, 3.0), (96, 136, 2.4),
        (118, 120, 3.1), (138, 130, 2.5), (40, 108, 2.2), (86, 112, 2.8),
        (124, 108, 2.3), (62, 140, 2.7), (108, 142, 2.2), (22, 136, 2.0),
    )
    parts = []
    for x, y, r in spots:
        parts.append(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{r * 0.7}" fill="{fill}" opacity="0.9"/>')
        parts.append(
            f'<ellipse cx="{x - 0.6}" cy="{y - 0.5}" rx="{r * 0.35}" ry="{r * 0.25}" '
            f'fill="{hi}" opacity="0.7"/>'
        )
    return "\n".join(parts)


def _weed_overlay(weedy: bool = False) -> str:
    """Weeds sit in the lower corners so they stay visible beside a crop."""
    left = _weed_clump(22, 140, fuller=weedy)
    if not weedy:
        return left
    return left + "\n" + _weed_clump(138, 136, fuller=False, flip=True)


def _vine_overlay(direction: str) -> str:
    """A strawberry runner vine entering from the edge that faces the parent."""
    # Plant sits near (80, 100). Stop short of that centre.
    stems = {
        "west": [(0, 110), (24, 108), (44, 102), (58, 98)],
        "east": [(160, 110), (136, 108), (116, 102), (102, 98)],
        "north": [(80, 0), (78, 24), (79, 48), (80, 64)],
        "south": [(80, 160), (81, 140), (80, 124), (80, 112)],
        "northwest": [(0, 0), (24, 24), (44, 44), (58, 58)],
        "northeast": [(160, 0), (136, 24), (116, 44), (102, 58)],
        "southwest": [(0, 160), (24, 136), (44, 116), (58, 104)],
        "southeast": [(160, 160), (136, 136), (116, 116), (102, 104)],
    }
    pts = stems.get(direction) or stems["west"]
    path = " ".join(
        ("M" if i == 0 else "L") + f"{x:.0f},{y:.0f}" for i, (x, y) in enumerate(pts)
    )
    # Leaves sit along the stem, slightly off to the side, strawberry-sprout colours.
    leaf = P["leaf3"]
    mid = P["leaf"]
    leaves = []
    # Pick 2–3 leaf positions from the polyline.
    picks = [1, 2] if len(pts) >= 3 else [0]
    angles = {
        "west": (-28, 26),
        "east": (28, -26),
        "north": (-40, 40),
        "south": (40, -40),
        "northwest": (-20, 30),
        "northeast": (20, -30),
        "southwest": (20, -30),
        "southeast": (-20, 30),
    }.get(direction, (-28, 26))
    for i, idx in enumerate(picks):
        x, y = pts[idx]
        rot = angles[i % len(angles)]
        rx, ry = (8, 4.4) if i == 0 else (7, 3.8)
        fill = leaf if i == 0 else mid
        leaves.append(
            f'<ellipse cx="{x + (6 if i == 0 else -5)}" cy="{y - 6}" '
            f'rx="{rx}" ry="{ry}" fill="{fill}" '
            f'transform="rotate({rot} {x} {y})"/>'
        )
    # A smaller tip leaflet near the end of the vine.
    tx, ty = pts[-1]
    leaves.append(
        f'<ellipse cx="{tx}" cy="{ty - 5}" rx="5.5" ry="3.2" fill="{leaf}" '
        f'opacity="0.95"/>'
    )
    stem = (
        f'<path d="{path}" fill="none" stroke="#4a5a20" stroke-width="2.4" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="{path}" fill="none" stroke="#8a8a38" stroke-width="1.1" '
        f'stroke-linecap="round" opacity="0.7"/>'
    )
    return f'<g id="vine-{direction}">\n  {stem}\n  {"".join(leaves)}\n</g>'



def _parse_mine_sprite_key(key: str) -> dict | None:
    raw = key or ""
    rock = None
    ladder = shaft = lantern = elevator = False
    for ore, suffix in (("copper", "_rock_copper"), ("iron", "_rock_iron"), ("gold", "_rock_gold")):
        if raw.endswith(suffix):
            rock = ore + "_ore"
            raw = raw[: -len(suffix)]
            break
    if raw.endswith("_rock"):
        rock = "stone"
        raw = raw[: -len("_rock")]
    if raw.endswith("_elevator"):
        elevator = True
        raw = raw[: -len("_elevator")]
    if raw.endswith("_lantern"):
        lantern = True
        raw = raw[: -len("_lantern")]
    if raw.endswith("_shaft"):
        shaft = True
        raw = raw[: -len("_shaft")]
    ladder_up = False
    if raw.endswith("_ladder_up"):
        ladder_up = True
        raw = raw[: -len("_ladder_up")]
    if raw.endswith("_ladder"):
        ladder = True
        raw = raw[: -len("_ladder")]
    if raw not in {"mine_floor", "mine_safe"}:
        return None
    return {
        "kind": raw,
        "type": raw,
        "rock": rock,
        "ladder": "open" if ladder else None,
        "ladder_up": ladder_up,
        "exit": shaft or ladder_up,
        "shaft": shaft,
        "lantern": lantern,
        "elevator": elevator,
        "mine": True,
    }


def _mine_ground(safe: bool = False) -> str:
    fill, dark, fleck = ("#4a4034", "#2a241c", "#6a5a44") if not safe else ("#4a4638", "#3a3428", "#c9a227")
    bits = [
        f'<rect width="160" height="160" fill="{fill}"/>',
        f'<path d="M0 30 L 40 0 L 80 24 L 120 4 L 160 28 L 160 0 L 0 0 Z" fill="{dark}" opacity="0.35"/>',
        f'<circle cx="28" cy="48" r="3" fill="{fleck}" opacity="0.5"/>',
        f'<circle cx="120" cy="90" r="2.5" fill="{fleck}" opacity="0.45"/>',
        f'<circle cx="70" cy="130" r="3" fill="{fleck}" opacity="0.4"/>',
    ]
    return "\n".join(bits)


def _rock_overlay(kind: str | None) -> str:
    body = (
        '<ellipse cx="80" cy="108" rx="28" ry="18" fill="#5a5348"/>'
        '<ellipse cx="70" cy="100" rx="16" ry="12" fill="#6e675c"/>'
        '<ellipse cx="92" cy="102" rx="14" ry="11" fill="#4a443c"/>'
    )
    if kind == "copper_ore":
        body += '<circle cx="72" cy="100" r="4" fill="#b87333"/><circle cx="90" cy="108" r="3" fill="#c9843a"/>'
    elif kind == "iron_ore":
        body += '<circle cx="72" cy="100" r="4" fill="#8a96a0"/><circle cx="90" cy="108" r="3" fill="#6a7380"/>'
    elif kind == "gold_ore":
        body += '<circle cx="72" cy="100" r="4" fill="#e8b86a"/><circle cx="90" cy="108" r="3" fill="#ffcc66"/>'
    return body


def _ladder_overlay() -> str:
    # Ladder into the ground, framed by a square of beams.
    return (
        '<rect x="44" y="44" width="72" height="72" fill="#1a1410"/>'
        '<rect x="40" y="40" width="80" height="10" fill="#6b4a2b"/>'
        '<rect x="40" y="110" width="80" height="10" fill="#6b4a2b"/>'
        '<rect x="40" y="40" width="10" height="80" fill="#6b4a2b"/>'
        '<rect x="110" y="40" width="10" height="80" fill="#6b4a2b"/>'
        '<rect x="64" y="52" width="6" height="68" fill="#8a6a44"/>'
        '<rect x="90" y="52" width="6" height="68" fill="#8a6a44"/>'
        '<rect x="64" y="64" width="32" height="5" fill="#c4a574"/>'
        '<rect x="64" y="80" width="32" height="5" fill="#c4a574"/>'
        '<rect x="64" y="96" width="32" height="5" fill="#c4a574"/>'
    )


def _shaft_overlay() -> str:
    # Mineshaft door seen from inside the tunnel.
    return (
        '<ellipse cx="80" cy="86" rx="44" ry="48" fill="#2a2018"/>'
        '<rect x="56" y="58" width="48" height="58" rx="2" fill="#6b4a2b"/>'
        '<rect x="60" y="62" width="40" height="10" fill="#8a6a44"/>'
        '<rect x="60" y="76" width="40" height="10" fill="#8a6a44"/>'
        '<rect x="60" y="90" width="40" height="10" fill="#8a6a44"/>'
        '<circle cx="90" cy="88" r="2" fill="#c4a574"/>'
    )


def _ladder_up_overlay() -> str:
    # A ladder ending in midair (the way up on floors 2+).
    return (
        '<rect x="62" y="8" width="8" height="100" fill="#6b4a2b"/>'
        '<rect x="90" y="8" width="8" height="100" fill="#6b4a2b"/>'
        '<rect x="62" y="24" width="36" height="6" fill="#8a6a44"/>'
        '<rect x="62" y="44" width="36" height="6" fill="#8a6a44"/>'
        '<rect x="62" y="64" width="36" height="6" fill="#8a6a44"/>'
        '<rect x="62" y="84" width="36" height="6" fill="#8a6a44"/>'
    )


def _lantern_overlay() -> str:
    return (
        '<rect x="74" y="70" width="12" height="8" fill="#4a3a28"/>'
        '<rect x="72" y="78" width="16" height="22" rx="2" fill="#e8b86a"/>'
        '<rect x="76" y="100" width="8" height="10" fill="#4a3a28"/>'
        '<circle cx="80" cy="88" r="5" fill="#fff4c8" opacity="0.9"/>'
    )


def _elevator_overlay() -> str:
    return (
        '<rect x="52" y="50" width="56" height="70" rx="4" fill="#3a4a52"/>'
        '<rect x="58" y="56" width="44" height="52" fill="#1f2a30"/>'
        '<rect x="70" y="74" width="20" height="6" fill="#c9a227"/>'
        '<rect x="64" y="120" width="32" height="8" fill="#2a241c"/>'
    )


def svg_mine_tile(info: dict) -> str:
    layers = [_mine_ground(safe=info.get("type") == "mine_safe" or info.get("kind") == "mine_safe")]
    if info.get("rock"):
        layers.append(_rock_overlay(info.get("rock")))
    if info.get("ladder") == "open":
        layers.append(_ladder_overlay())
    if info.get("ladder_up"):
        layers.append(_ladder_up_overlay())
    elif info.get("exit") or info.get("shaft"):
        layers.append(_shaft_overlay())
    if info.get("lantern"):
        layers.append(_lantern_overlay())
    if info.get("elevator"):
        layers.append(_elevator_overlay())
    return _svg("\n".join(layers))


def _hills_ground(kind: str, snow: bool = False) -> str:
    # Warm grassy hillside, slightly greener than farm soil.
    if kind == "hillside":
        fill, dark, tuft = ("#6b7a3a", "#4d5c28", "#8a9a4a")
    elif kind == "mine_entrance":
        fill, dark, tuft = ("#5a5340", "#3a3428", "#6e6754")
    else:
        fill, dark, tuft = ("#6a8a42", "#4a6a2a", "#8aaa58")
    if snow:
        fill, dark, tuft = ("#d8dce6", "#9aa6b8", "#c8c8b8")
    bits = [
        f'<rect width="160" height="160" fill="{fill}"/>',
        f'<path d="M0 118 C 40 108, 80 128, 160 116 L 160 160 L 0 160 Z" fill="{dark}" opacity="0.35"/>',
        f'<circle cx="22" cy="28" r="6" fill="{tuft}" opacity="0.8"/>',
        f'<circle cx="138" cy="24" r="7" fill="{tuft}" opacity="0.75"/>',
        f'<circle cx="28" cy="138" r="5" fill="{tuft}" opacity="0.7"/>',
        f'<circle cx="132" cy="142" r="6" fill="{tuft}" opacity="0.7"/>',
    ]
    if kind == "hillside":
        bits.append(f'<path d="M0 70 Q 80 40 160 78" fill="none" stroke="{dark}" stroke-width="10" opacity="0.25"/>')
    if snow:
        bits.append('<circle cx="50" cy="40" r="2" fill="#f7f9fc" opacity="0.9"/>')
        bits.append('<circle cx="110" cy="60" r="2.2" fill="#f7f9fc" opacity="0.85"/>')
        bits.append('<circle cx="70" cy="100" r="1.8" fill="#f7f9fc" opacity="0.8"/>')
    return "\n".join(bits)


def _tree_overlay(stage: str) -> str:
    if stage == "stump":
        return (
            '<ellipse cx="80" cy="108" rx="18" ry="8" fill="#5a3a22"/>'
            '<rect x="66" y="86" width="28" height="22" rx="4" fill="#6b4a2b"/>'
            '<ellipse cx="80" cy="86" rx="14" ry="5" fill="#8a6a44"/>'
        )
    if stage == "mushroom_log":
        return (
            '<ellipse cx="80" cy="116" rx="34" ry="9" fill="#5a3a22"/>'
            '<rect x="48" y="104" width="64" height="16" rx="8" fill="#6b4a2b"/>'
            '<ellipse cx="48" cy="112" rx="8" ry="10" fill="#c4a06a"/>'
            '<ellipse cx="48" cy="112" rx="5" ry="6" fill="#8a6a44"/>'
            '<ellipse cx="112" cy="112" rx="8" ry="10" fill="#5a3a22"/>'
        )
    if stage == "sapling":
        return (
            '<rect x="77" y="90" width="6" height="28" rx="2" fill="#6b4a2b"/>'
            '<circle cx="80" cy="84" r="14" fill="#3d6b38"/>'
            '<circle cx="70" cy="90" r="8" fill="#4a7a40"/>'
            '<circle cx="90" cy="90" r="8" fill="#4a7a40"/>'
        )
    if stage == "young":
        return (
            '<rect x="74" y="80" width="12" height="40" rx="3" fill="#5a3a22"/>'
            '<circle cx="80" cy="70" r="28" fill="#2f5c2c"/>'
            '<circle cx="60" cy="82" r="16" fill="#3d6b38"/>'
            '<circle cx="100" cy="82" r="16" fill="#3d6b38"/>'
        )
    # grown
    return (
        '<rect x="72" y="78" width="16" height="48" rx="4" fill="#4a2e18"/>'
        '<circle cx="80" cy="62" r="40" fill="#2a4e26"/>'
        '<circle cx="50" cy="78" r="22" fill="#3d6b38"/>'
        '<circle cx="110" cy="78" r="22" fill="#3d6b38"/>'
        '<circle cx="80" cy="44" r="18" fill="#355e30"/>'
    )


def _forage_overlay(kind: str) -> str:
    if kind == "wild_berry":
        return (
            '<circle cx="58" cy="118" r="6" fill="#8b1e2d"/>'
            '<circle cx="70" cy="122" r="5.5" fill="#a02838"/>'
            '<circle cx="64" cy="110" r="5" fill="#7a1828"/>'
            '<path d="M64 104 C 60 98, 70 98, 66 104" fill="#3d6b38"/>'
        )
    if kind == "wild_mushroom":
        return (
            '<rect x="74" y="112" width="10" height="16" rx="3" fill="#e8d8b8"/>'
            '<ellipse cx="79" cy="110" rx="16" ry="10" fill="#8a5a28"/>'
            '<ellipse cx="74" cy="108" rx="3" ry="2" fill="#f0e0c0" opacity="0.7"/>'
        )
    if kind == "oyster_mushroom":
        return (
            '<ellipse cx="70" cy="102" rx="10" ry="6" fill="#efe4d0"/>'
            '<ellipse cx="80" cy="98" rx="12" ry="7" fill="#e8d8b8"/>'
            '<ellipse cx="90" cy="104" rx="9" ry="5" fill="#ddd0b8"/>'
            '<path d="M70 102 Q 70 112 80 114 Q 90 112 90 104" fill="#d9cbb0"/>'
        )
    # wild onion
    return (
        '<ellipse cx="96" cy="124" rx="8" ry="10" fill="#c8b070"/>'
        '<path d="M96 116 C 90 90, 86 80, 88 72" fill="none" stroke="#3d6b38" stroke-width="3" stroke-linecap="round"/>'
        '<path d="M96 116 C 98 92, 108 82, 112 74" fill="none" stroke="#4a7a40" stroke-width="3" stroke-linecap="round"/>'
        '<path d="M96 116 C 94 94, 100 84, 102 76" fill="none" stroke="#2f5c2c" stroke-width="2.5" stroke-linecap="round"/>'
    )


def _mine_entrance_overlay(closed: bool = True) -> str:
    bits = [
        '<path d="M40 130 L 48 70 Q 80 40 112 70 L 120 130 Z" fill="#2a241c"/>',
        '<path d="M48 126 L 54 76 Q 80 52 106 76 L 112 126 Z" fill="#1a1612"/>',
    ]
    if closed:
        # Boarded planks
        bits.append('<rect x="58" y="72" width="44" height="54" fill="#6b4a2b"/>')
        bits.append('<rect x="58" y="80" width="44" height="4" fill="#4a2e18"/>')
        bits.append('<rect x="58" y="96" width="44" height="4" fill="#4a2e18"/>')
        bits.append('<rect x="58" y="112" width="44" height="4" fill="#4a2e18"/>')
        bits.append('<circle cx="68" cy="88" r="2" fill="#2a1c12"/>')
        bits.append('<circle cx="92" cy="104" r="2" fill="#2a1c12"/>')
    return "\n".join(bits)


def svg_hills_tile(info: dict) -> str:
    typ = info.get("type") or info.get("kind") or "grass"
    layers = [_hills_ground(typ, bool(info.get("snow")))]
    if typ == "mine_entrance":
        layers.append(_mine_entrance_overlay(closed=bool(info.get("closed", True))))
    if info.get("tree"):
        layers.append(_tree_overlay(info["tree"]))
    if info.get("forage"):
        layers.append(_forage_overlay(info["forage"]))
    return _svg("\n".join(layers))



def _parse_cabin_interior_sprite_key(key: str) -> dict | None:
    if not key.startswith("cabin_interior_"):
        return None
    rest = key[len("cabin_interior_"):]
    fire = False
    if rest.endswith("_lit"):
        fire = True
        rest = rest[: -len("_lit")]
    if rest not in {"floor", "bed", "chest", "fireplace", "door", "kitchen"}:
        return None
    return {"kind": "cabin_interior", "tile": rest, "fire": fire}


def _cabin_floor_ground() -> str:
    return """
  <rect width="160" height="160" fill="#c4a06a"/>
  <rect x="0" y="0" width="160" height="160" fill="#d8b07a"/>
  <g stroke="#8a5a28" stroke-width="1.2" opacity="0.45">
    <line x1="0" y1="20" x2="160" y2="20"/>
    <line x1="0" y1="40" x2="160" y2="40"/>
    <line x1="0" y1="60" x2="160" y2="60"/>
    <line x1="0" y1="80" x2="160" y2="80"/>
    <line x1="0" y1="100" x2="160" y2="100"/>
    <line x1="0" y1="120" x2="160" y2="120"/>
    <line x1="0" y1="140" x2="160" y2="140"/>
  </g>
  <g stroke="#6b3e16" stroke-width="0.8" opacity="0.2">
    <line x1="40" y1="0" x2="40" y2="20"/>
    <line x1="110" y1="20" x2="110" y2="40"/>
    <line x1="28" y1="40" x2="28" y2="60"/>
    <line x1="96" y1="80" x2="96" y2="100"/>
    <line x1="52" y1="120" x2="52" y2="140"/>
  </g>
"""


def _cabin_interior_overlay(tile: str, fire: bool = False) -> str:
    if tile == "bed":
        return """
  <rect x="14" y="18" width="132" height="100" rx="8" fill="#6b3a28" stroke="#3a1c12" stroke-width="2"/>
  <rect x="20" y="36" width="120" height="76" rx="6" fill="#c45a5a"/>
  <rect x="20" y="36" width="120" height="18" fill="#efe4d0"/>
  <rect x="24" y="22" width="44" height="18" rx="5" fill="#f4ece0" stroke="#c8b89a" stroke-width="1"/>
  <rect x="92" y="22" width="44" height="18" rx="5" fill="#f4ece0" stroke="#c8b89a" stroke-width="1"/>
  <path d="M20,92 q60,18 120,0" fill="none" stroke="#8a2e32" stroke-width="3"/>
"""
    if tile == "chest":
        return """
  <rect x="36" y="70" width="88" height="54" rx="6" fill="#8a5520" stroke="#3a2414" stroke-width="2"/>
  <rect x="36" y="62" width="88" height="22" rx="6" fill="#a46828" stroke="#3a2414" stroke-width="2"/>
  <rect x="70" y="78" width="20" height="14" rx="3" fill="#c9a227" stroke="#6b4a10" stroke-width="1.4"/>
  <line x1="44" y1="96" x2="116" y2="96" stroke="#3a2414" stroke-width="1.5" opacity="0.5"/>
"""
    if tile == "fireplace":
        glow = "#f0a030" if fire else "#2a2420"
        flame = ""
        if fire:
            flame = """
  <path d="M80,108 c-8,-16 -4,-28 0,-36 c6,10 12,16 8,36 z" fill="#f4d060"/>
  <path d="M80,108 c-5,-10 -2,-20 0,-26 c4,6 7,10 5,26 z" fill="#f07a20"/>
"""
        return f"""
  <rect x="28" y="18" width="104" height="118" fill="#6a5a52" stroke="#2a2018" stroke-width="2"/>
  <rect x="40" y="36" width="80" height="86" fill="#3a322c"/>
  <rect x="48" y="70" width="64" height="52" fill="{glow}"/>
  {flame}
  <rect x="24" y="128" width="112" height="14" fill="#4a3a30" stroke="#2a2018" stroke-width="2"/>
"""
    if tile == "door":
        return """
  <rect x="44" y="18" width="72" height="124" fill="#6b3e16" stroke="#3a2414" stroke-width="3"/>
  <rect x="52" y="28" width="56" height="48" fill="#8a5520" stroke="#3a2414" stroke-width="1.5"/>
  <rect x="52" y="84" width="56" height="48" fill="#8a5520" stroke="#3a2414" stroke-width="1.5"/>
  <circle cx="104" cy="86" r="5" fill="#c9a227"/>
"""
    if tile == "kitchen":
        return """
  <rect x="16" y="70" width="128" height="62" fill="#6b4a28" stroke="#3a2414" stroke-width="2"/>
  <rect x="16" y="62" width="128" height="14" fill="#8a5a30" stroke="#3a2414" stroke-width="2"/>
  <rect x="28" y="86" width="36" height="28" rx="3" fill="#4a5560"/>
  <circle cx="46" cy="100" r="10" fill="#2a3038" stroke="#c0c8d0" stroke-width="1.5"/>
  <rect x="80" y="36" width="28" height="28" fill="#8a3a22" stroke="#3a2414" stroke-width="2"/>
  <rect x="84" y="28" width="20" height="10" fill="#4a3a30"/>
  <ellipse cx="118" cy="96" rx="14" ry="10" fill="#c45a3a" stroke="#6b2a18" stroke-width="1.5"/>
"""
    return ""


def svg_cabin_interior(info: dict) -> str:
    tile = (info or {}).get("tile") or "floor"
    fire = bool((info or {}).get("fire"))
    body = _cabin_floor_ground() + _cabin_interior_overlay(tile, fire)
    return _svg(body)


def svg_for_key(key: str) -> str:
    info = parse_sprite_key(key)
    kind = info.get("kind")
    if info.get("hills"):
        return svg_hills_tile(info)
    if info.get("mine") or kind in {"mine_floor", "mine_safe"}:
        return svg_mine_tile(info)
    if kind == "cabin_interior":
        return svg_cabin_interior(info)
    if kind == "cabin":
        return svg_cabin(info.get("weather") or "sun", fire=bool(info.get("fire")))
    if kind == "unknown":
        return svg_unknown(info.get("raw", key))
    tilled = bool(info.get("tilled"))
    watered = bool(info.get("watered"))
    layers = [_soil_layer(tilled, watered)]
    if info.get("snow"):
        layers.append(_snow_ground_overlay(tilled))
    if info.get("fertilizer"):
        layers.append(_fertilizer_overlay(info.get("fertilizer")))
    if kind and kind != "soil" and info.get("stage"):
        layers.append(_crop_layer(kind, info["stage"]))
    if info.get("vine"):
        layers.append(_vine_overlay(info["vine"]))
    if info.get("weedy") or info.get("weed"):
        layers.append(_weed_overlay(bool(info.get("weedy"))))
    return _svg("\n".join(layers))


def is_safe_key(key: str) -> bool:
    if not key or len(key) > 80:
        return False
    return all(ch.isalnum() or ch == "_" for ch in key)


# Placeholder item icons (simple shapes; painted art can replace them later).
_ITEM_LABELS = {
    "hoe": "HOE",
    "watering_can": "CAN",
    "shovel": "SHVL",
    "axe": "AXE",
    "pickaxe": "PICK",
    "wood": "WOOD",
    "stone": "STONE",
    "sugar": "SUGAR",
    "copper_ore": "COPPER",
    "iron_ore": "IRON",
    "gold_ore": "GOLD",
    "wild_onion": "ONION",
    "wild_berry": "BERRY",
    "wild_mushroom": "SHROOM",
    "oyster_mushroom": "OYSTER",
    "strawberry_jam": "JAM",
    "kabocha_soup": "SOUP",
    "root_stew": "STEW",
    "bread": "BREAD",
    "bread_half": "HALF",
    "butter": "BUTTER",
    "milk": "MILK",
    "bread_and_butter": "B&B",
    "jam_toast": "TOAST",
    "strawberry_milk": "MILK",
    "buttered_kabocha": "SQUASH",
    "kabocha_cream_soup": "CREAM",
    "rhubarb_strawberry_jam": "RHJAM",
    "garden_salad": "SALAD",
    "roasted_potatoes": "ROAST",
    "pumpkin_soup": "PSOUP",
    "wild_onion_soup": "OSOUP",
    "wild_berry_jam": "BJAM",
    "mushroom_soup": "MSOUP",
    "herbal_tea": "TEA",
    "fertilizer_general": "FERT",
    "fertilizer_yield": "YLD",
    "fertilizer_growth": "GRW",
}

_ITEM_COLORS = {
    "hoe": ("#6b4a2b", "#c4a574"),
    "watering_can": ("#3d5c6e", "#9ec3d4"),
    "shovel": ("#4a5560", "#c4a574"),
    "axe": ("#4a3a28", "#d4c09a"),
    "pickaxe": ("#4a5560", "#c4a574"),
    "wood": ("#6b4a2b", "#e2c48a"),
    "stone": ("#5a5348", "#c8c0b0"),
    "sugar": ("#e8dcc8", "#6b4a2b"),
    "copper_ore": ("#8a4a1a", "#e2b07a"),
    "iron_ore": ("#4a5560", "#c0c8d0"),
    "gold_ore": ("#c9a227", "#fff4c8"),
    "wild_onion": ("#3d6b38", "#d7e8b0"),
    "wild_berry": ("#8b1e2d", "#f2d4a3"),
    "wild_mushroom": ("#5a3a22", "#e2c48a"),
    "oyster_mushroom": ("#cbb89a", "#efe4d0"),
    "strawberry_jam": ("#8b1e2d", "#f2d4a3"),
    "kabocha_soup": ("#8a5a12", "#f0d48a"),
    "root_stew": ("#5a3a22", "#e2c48a"),
    "bread": ("#8a5a28", "#f0d4a0"),
    "bread_half": ("#8a5a28", "#f7e4b0"),
    "butter": ("#c9a227", "#fff4c8"),
    "milk": ("#6a7a8a", "#eef4f8"),
    "bread_and_butter": ("#8a5a28", "#f7e4b0"),
    "jam_toast": ("#8b1e2d", "#f0d4a0"),
    "strawberry_milk": ("#a05060", "#f8e0e6"),
    "buttered_kabocha": ("#8a5a12", "#f7e0a8"),
    "kabocha_cream_soup": ("#8a5a12", "#f4e8c4"),
    "rhubarb_strawberry_jam": ("#8b1e2d", "#f2d4a3"),
    "garden_salad": ("#3d6b38", "#d7e8b0"),
    "roasted_potatoes": ("#8a5a28", "#f0d4a0"),
    "pumpkin_soup": ("#b85a18", "#f0d48a"),
    "wild_onion_soup": ("#3d6b38", "#f0d4a0"),
    "wild_berry_jam": ("#6b1a4a", "#f2d4a3"),
    "mushroom_soup": ("#5a3a22", "#f0d4a0"),
    "herbal_tea": ("#3d6b38", "#f0e4c8"),
    "fertilizer_general": ("#1f6b5a", "#7dcec0"),
    "fertilizer_yield": ("#2a6b2a", "#9ad48a"),
    "fertilizer_growth": ("#2a5a6b", "#8ad4ce"),
}


_TIER_COLORS = {
    "copper": ("#8a4a1a", "#e2b07a"),
    "iron": ("#4a5560", "#c0c8d0"),
    "gold": ("#c9a227", "#fff4c8"),
}


def svg_for_item(item: str) -> str:
    """A small placeholder icon for a tool, food, or bag."""
    item = (item or "").strip().lower()
    tier = None
    base = item
    for name in ("copper", "iron", "gold"):
        suffix = "_" + name
        if item.endswith(suffix):
            tier = name
            base = item[: -len(suffix)]
            break
    label = _ITEM_LABELS.get(item) or _ITEM_LABELS.get(base)
    if tier:
        fill, ink = _TIER_COLORS[tier]
        if not label:
            label = (base[:4].upper() or "ITEM")
    else:
        fill, ink = _ITEM_COLORS.get(item, ("#5a4a38", "#f0e4c8"))
    if not label:
        if item.endswith("_seed") or item.endswith("_seedling") or item.endswith("_crown"):
            label, fill, ink = ("CRWN" if item.endswith("_crown") else "SEED"), "#3d6b38", "#d7e8b0"
        else:
            label, fill, ink = (item[:4].upper() or "ITEM"), fill, ink
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" role="img">'
        f'<rect width="80" height="80" rx="14" fill="{fill}"/>'
        f'<circle cx="40" cy="32" r="14" fill="{ink}" opacity="0.85"/>'
        f'<text x="40" y="64" text-anchor="middle" font-size="11" font-family="Georgia,serif" fill="{ink}">{label}</text>'
        f"</svg>"
    )

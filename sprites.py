"""Shared tile -> sprite-key mapping, plus cozy SVG tiles generated in code."""

from __future__ import annotations

SIZE = 160


def sprite_key(tile: dict, weather: str | None = None) -> str:
    """Map a state.json tile to a sprite key. Used by both renderers."""
    if not tile or tile.get("type") == "cabin":
        w = (weather or "").strip().lower()
        if w in {"rain", "snow", "storm", "cloud"}:
            return f"cabin_{w}"
        return "cabin"
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
    if tile.get("weedy"):
        key += "_weedy"
    elif tile.get("weed"):
        key += "_weed"
    return key


def parse_sprite_key(key: str) -> dict:
    """Inverse of sprite_key, for the SVG generator."""
    key = (key or "").strip().lower()
    if key == "cabin" or key.startswith("cabin_"):
        weather = "sun"
        if key.startswith("cabin_") and len(key) > 6:
            tail = key[6:]
            if tail in {"rain", "snow", "storm", "cloud", "sun"}:
                weather = tail
        return {"kind": "cabin", "weather": weather}
    weedy = False
    weed = False
    if key.endswith("_weedy"):
        weedy = True
        key = key[: -len("_weedy")]
    elif key.endswith("_weed"):
        weed = True
        key = key[: -len("_weed")]
    soil_keys = {
        "soil": {"tilled": False, "watered": False},
        "soil_tilled": {"tilled": True, "watered": False},
        "soil_watered": {"tilled": True, "watered": True},
        "soil_wet": {"tilled": False, "watered": True},
    }
    if key in soil_keys:
        return {"kind": "soil", "weed": weed, "weedy": weedy, **soil_keys[key]}
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
        }
    if weed or weedy:
        return {"kind": "unknown", "raw": key, "weed": weed, "weedy": weedy}
    return {"kind": "unknown", "raw": key}


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
    if kind == "strawberry":
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
    if stage == "seed":
        return _draw_seed(x, y)
    if stage in {"sprouting", "regrowing"}:
        leaf = {
            "kabocha": P["leaf"],
            "turnip": P["leaf3"],
            "carrot": P["leaf"],
            "strawberry": P["leaf3"],
        }.get(kind, P["leaf"])
        return _sprout(x, y, leaf)
    if stage == "growing":
        extra = ""
        if kind == "kabocha":
            extra = _kabocha_fruit(x, y + 6, 0.45)
        elif kind == "turnip":
            extra = f'<ellipse cx="{x}" cy="{y+8}" rx="8" ry="6" fill="{P["turnip_top"]}"/>'
        elif kind == "carrot":
            extra = (
                f'<path d="M{x},{y+4} L{x+4},{y+8} L{x},{y+16} L{x-4},{y+8} Z" '
                f'fill="{P["carrot"]}"/>'
            )
        elif kind == "strawberry":
            extra = (
                f'<ellipse cx="{x}" cy="{y-6}" rx="4" ry="4" fill="{P["berry_flower"]}"/>'
                f'<ellipse cx="{x+12}" cy="{y-2}" rx="3.2" ry="3.2" fill="{P["berry_flower"]}"/>'
                + _strawberry_cluster(x, y, ripe=False, scale=0.9)
            )
        return _growing_leaves(x, y, extra)
    # mature
    if kind == "kabocha":
        return _growing_leaves(x, y - 6) + _kabocha_fruit(x, y + 8, 1.0)
    if kind == "turnip":
        return _turnip_fruit(x, y + 4, 1.05)
    if kind == "carrot":
        return _carrot_fruit(x, y, 1.05)
    if kind == "strawberry":
        return _growing_leaves(x, y - 4) + _strawberry_cluster(x, y + 4, ripe=True)
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


def svg_cabin(weather: str | None = None) -> str:
    weather = (weather or "sun").strip().lower()
    if weather not in {"rain", "snow", "storm", "cloud", "sun"}:
        weather = "sun"
    ground, sky = _cabin_sky(weather)
    overlay = _cabin_weather_overlay(weather)
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


def _weed_overlay(weedy: bool = False) -> str:
    """A gentle little weed in the lower-left, slightly fuller if the plot is weedy."""
    # Sit to the side of the main crop so both can be seen.
    x, y = 34, 118
    leaf = P["weed"]
    dark = P["weed2"]
    tip = P["weed_tip"]
    stem_h = 22 if weedy else 16
    parts = [
        f'<path d="M{x},{y} C{x-1},{y-8} {x},{y-stem_h} {x},{y-stem_h}" '
        f'stroke="{dark}" stroke-width="2" fill="none" stroke-linecap="round"/>',
        f'<ellipse cx="{x-7}" cy="{y-10}" rx="7" ry="4" fill="{leaf}" '
        f'transform="rotate(-28 {x-7} {y-10})"/>',
        f'<ellipse cx="{x+7}" cy="{y-12}" rx="6.5" ry="3.6" fill="{tip}" '
        f'transform="rotate(26 {x+7} {y-12})"/>',
    ]
    if weedy:
        parts.append(
            f'<path d="M{x+10},{y+2} C{x+12},{y-10} {x+9},{y-20} {x+9},{y-20}" '
            f'stroke="{dark}" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
        )
        parts.append(
            f'<ellipse cx="{x+16}" cy="{y-14}" rx="6" ry="3.2" fill="{leaf}" '
            f'transform="rotate(30 {x+16} {y-14})"/>'
        )
        parts.append(f'<circle cx="{x+9}" cy="{y-21}" r="2.2" fill="{P["weed_flower"]}"/>')
    else:
        parts.append(f'<circle cx="{x}" cy="{y-stem_h-1}" r="1.6" fill="{P["weed_flower"]}" opacity="0.85"/>')
    return "\n".join(parts)


def svg_for_key(key: str) -> str:
    info = parse_sprite_key(key)
    kind = info.get("kind")
    if kind == "cabin":
        return svg_cabin(info.get("weather") or "sun")
    if kind == "unknown":
        return svg_unknown(info.get("raw", key))
    tilled = bool(info.get("tilled"))
    watered = bool(info.get("watered"))
    layers = [_soil_layer(tilled, watered)]
    if kind and kind != "soil" and info.get("stage"):
        layers.append(_crop_layer(kind, info["stage"]))
    if info.get("weedy") or info.get("weed"):
        layers.append(_weed_overlay(bool(info.get("weedy"))))
    return _svg("\n".join(layers))


def is_safe_key(key: str) -> bool:
    if not key or len(key) > 80:
        return False
    return all(ch.isalnum() or ch == "_" for ch in key)

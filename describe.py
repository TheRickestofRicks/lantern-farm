"""Full text view of Lantern Farm — every tile, exactly as the JSON is."""

from __future__ import annotations

from engine import (
    CABIN_COL,
    CABIN_ROW,
    COLS,
    ROWS,
    crop_info,
    day_in_season,
    days_per_season,
    display_name,
    get_tile,
    grow_days,
    known_players,
    legal_actions,
    load_crops,
    load_rules,
    load_state,
    max_energy,
    migrate_state,
    normalize_player,
    player_slot,
    position_name,
    stage_label,
    weather_forecast,
    wither_after,
)
from sprites import sprite_key

WEATHER_WORDS = {
    "sun": "clear and sunny",
    "cloud": "overcast",
    "rain": "rain (every plot is watered this morning)",
    "storm": "a storm (every plot is watered this morning)",
    "snow": "snow (the soil is wet beneath it)",
}

FORECAST_WORDS = {
    "sun": "clear",
    "cloud": "overcast",
    "rain": "rain",
    "storm": "storm",
    "snow": "snow",
}

INVENTORY_ORDER = [
    "kabocha_seed",
    "turnip_seed",
    "carrot_seed",
    "kabocha",
    "turnip",
    "carrot",
]


def _inventory_line(state: dict) -> str:
    inv = state.get("inventory", {})
    parts = []
    seen = set()
    for key in INVENTORY_ORDER:
        seen.add(key)
        count = int(inv.get(key, 0))
        if count <= 0:
            continue
        parts.append(_item_phrase(key, count))
    for key, count in inv.items():
        if key in seen or int(count) <= 0:
            continue
        parts.append(_item_phrase(key, int(count)))
    if not parts:
        return "  (empty)"
    return "  " + ", ".join(parts)


def _item_phrase(key: str, count: int) -> str:
    if key.endswith("_seed"):
        kind = key[: -len("_seed")]
        noun = "seed" if count == 1 else "seeds"
        return f"{count} {kind} {noun}"
    noun = key if count == 1 else f"{key}s"
    return f"{count} {noun}"


def _ascii_cell(tile: dict) -> tuple[str, str]:
    """Two short lines for the mini map cell."""
    if tile.get("type") == "cabin":
        return "CABIN", "lantern"
    crop = tile.get("crop")
    wet = "wet" if tile.get("watered") else "dry"
    if crop:
        kind = crop.get("kind", "?")
        stage = crop.get("stage", "?")
        short = {
            "seed": "seed",
            "sprouting": "sprout",
            "growing": "grow",
            "mature": "READY",
            "withered": "wilt",
        }.get(stage, stage[:5])
        mark = " *" if (tile.get("weedy") or tile.get("weed")) else ""
        return f"{kind[:7]:<7}", f"{short} {wet}{mark}"
    mark = " *" if (tile.get("weedy") or tile.get("weed")) else ""
    if tile.get("tilled"):
        return "tilled", wet + mark
    return "soil", wet + mark


def ascii_map(state: dict) -> str:
    widths = [10, 10, 10]
    # compute from content
    cells = []
    for r in range(1, ROWS + 1):
        row_cells = []
        for c in range(1, COLS + 1):
            a, b = _ascii_cell(get_tile(state, r, c))
            row_cells.append((a, b))
            widths[c - 1] = max(widths[c - 1], len(a), len(b), 8)
        cells.append(row_cells)

    def rule() -> str:
        return "  +" + "+".join("-" * (w + 2) for w in widths) + "+"

    lines = []
    header = "     " + "  ".join(f"{'col ' + str(c):^{w}}" for c, w in enumerate(widths, 1))
    lines.append(header)
    lines.append(rule())
    for r, row_cells in enumerate(cells, 1):
        top = "  |" + "|".join(f" {a:<{widths[i]}} " for i, (a, _b) in enumerate(row_cells)) + "|"
        bot = f"r{r} |" + "|".join(f" {b:<{widths[i]}} " for i, (_a, b) in enumerate(row_cells)) + "|"
        lines.append(top)
        lines.append(bot)
        lines.append(rule())
    return "\n".join(lines)


def describe_tile(state: dict, crops: dict, row: int, col: int) -> str:
    tile = get_tile(state, row, col)
    here = position_name(row, col)
    weather = str(state.get("weather") or "sun")
    key = sprite_key(tile, weather)
    if tile.get("type") == "cabin":
        from config import flavor
        cabin = flavor(f"cabin_{weather}") or flavor("cabin") or "the cabin. A warm lantern glows in the window."
        return (
            f"  {here} — {cabin} "
            f"(sprite: {key})"
        )
    moist = "watered today" if tile.get("watered") else "dry today"
    tilled = "tilled" if tile.get("tilled") else "untilled"
    weed_bit = ""
    if tile.get("weedy"):
        weed_bit = (
            " A small weed has crept in. "
            "The plot is weedy; the crop grows at half speed."
        )
    elif tile.get("weed"):
        weed_bit = " A small weed has crept in."
    crop = tile.get("crop")
    if not crop:
        return f"  {here} — {tilled} soil, {moist}. Empty.{weed_bit} (sprite: {key})"
    kind = crop["kind"]
    info = crop_info(crops, kind) or {}
    stage = crop.get("stage", "seed")
    if stage == "withered":
        return (
            f"  {here} — {tilled} soil, {moist}. "
            f"A withered {kind} (planted on day {crop.get('planted_day', '?')}, "
            f"grew {crop.get('days_grown', 0)} day(s) before it died, "
            f"{crop.get('dry_days', 0)} dry day(s)).{weed_bit} (sprite: {key})"
        )
    needed = grow_days(info) if info else "?"
    grown = crop.get("days_grown", 0)
    label = stage_label(info, stage) if info else stage
    planted = crop.get("planted_day", "?")
    dry = crop.get("dry_days", 0)
    dry_bit = ""
    if dry:
        limit = wither_after(crops)
        dry_bit = f", {dry} dry day(s) (withers at {limit})"
    ready = " Ready to harvest." if stage == "mature" else ""
    return (
        f"  {here} — {tilled} soil, {moist}. "
        f"{kind}, day {grown} of {needed}, {label}, {moist}"
        f"{dry_bit}. Planted on day {planted}.{ready}{weed_bit} (sprite: {key})"
    )


def turn_header_lines(state: dict, crops: dict | None = None, viewer: str | None = None) -> list[str]:
    """The first lines of `look` — day, weather, gold, whose turn, energy."""
    crops = crops or load_crops()
    rules = load_rules()
    migrate_state(state, rules)
    day = int(state["day"])
    season = state["season"]
    weather = state["weather"]
    sky = WEATHER_WORDS.get(weather, weather)
    within = day_in_season(day, crops)
    total = days_per_season(crops)
    gold = int(state["gold"])
    cap = max_energy(rules)
    from config import flavor, starting_player
    current = normalize_player(state.get("current_player")) or starting_player()
    bits = []
    for name in known_players():
        slot = player_slot(state, name)
        energy = int(slot.get("energy", 0))
        ended = " (ended turn)" if slot.get("ended_turn") and name != current else ""
        bits.append(f"{display_name(name)} {energy}/{cap} energy{ended}")
    lines = [
        flavor("title_line") or "Lantern Farm  🏮",
        f"Day {day}  ·  {season.capitalize()} (day {within} of {total})  ·  "
        f"{sky}  ·  {gold}G",
        f"It's {display_name(current)}'s turn.  " + "  ·  ".join(bits),
    ]
    if viewer:
        view = normalize_player(viewer)
        if view:
            lines.append(f"Playing as {display_name(view)}.")
    note = state.get("last_note") or None
    if note and note.get("text") and note.get("from"):
        lines.append(f"{display_name(note['from'])}'s note: {note['text']}")
    return lines



def forecast_lines(state: dict, crops: dict | None = None) -> list[str]:
    days = weather_forecast(state, crops)
    if not days:
        return []
    lines = ["Forecast (next 7 days):"]
    for item in days:
        word = FORECAST_WORDS.get(item["weather"], item["weather"])
        season = str(item.get("season") or "")
        lines.append(f"  Day {item['day']}, {season} — {word}")
    return lines


def describe_state(
    state: dict,
    crops: dict | None = None,
    viewer: str | None = None,
) -> str:
    crops = crops or load_crops()
    rules = load_rules()
    migrate_state(state, rules)
    viewer = normalize_player(viewer)

    lines = turn_header_lines(state, crops, viewer)
    forecast = forecast_lines(state, crops)
    if forecast:
        lines += [""] + forecast
    lines += [
        "",
        "Inventory:",
        _inventory_line(state),
        "",
        "Mini map:",
        ascii_map(state),
        "",
        "Tiles:",
    ]
    for r in range(1, ROWS + 1):
        for c in range(1, COLS + 1):
            lines.append(describe_tile(state, crops, r, c))

    current = normalize_player(state.get("current_player"))
    actions = legal_actions(state, crops, player=viewer or current, rules=rules)
    lines.append("")
    if viewer and current and viewer != current:
        lines.append(
            f"Legal actions: none right now — it's {display_name(current)}'s turn."
        )
    else:
        lines.append("Legal actions (row col, 1-indexed, row 1 is the top):")
        if actions:
            for act in actions:
                lines.append(f"  {act}")
        else:
            lines.append("  (none)")

    log = state.get("log") or []
    if log:
        lines.append("")
        lines.append("Recent log:")
        for entry in log[-8:]:
            lines.append(f"  [day {entry.get('day', '?')}] {entry.get('text', '')}")

    lines.append("")
    lines.append(
        "Notes: a crop grows 1 day only if it was watered (or rained/snowed on) "
        "that day. It withers after "
        f"{wither_after(crops)} dry day(s), or if the season turns against it. "
        f"The cabin is always top-right (row {CABIN_ROW} col {CABIN_COL}). "
        "A planted or tilled plot may sprout a gentle weed at day turn; "
        "pluck it with `pluck <row> <col>` (5 energy, key Q) before the next "
        "day, or the plot grows weedy and the crop skips every other watered day. "
        "Weeds never kill crops. "
        "The sprite key on each tile is the same one the image view uses. "
        "Till, plant, and water cost energy (see rules.json); harvest, buy, and sell are free. "
        "The day advances when both players have ended their turn."
    )
    return "\n".join(lines) + "\n"


def look(viewer: str | None = None) -> str:
    crops = load_crops()
    state = load_state(crops)
    return describe_state(state, crops, viewer=viewer)

"""Full text view of Lantern Farm — every tile, exactly as the JSON is."""

from __future__ import annotations

from engine import (
    CABIN_COL,
    CABIN_ROW,
    COLS,
    ROWS,
    crop_info,
    crop_name,
    crop_name_plural,
    day_in_season,
    days_per_season,
    describe_where,
    display_name,
    get_tile,
    crop_cycle_days,
    crop_is_dormant,
    is_perennial,
    grow_days,
    regrow_days,
    stock_noun,
    stock_word,
    known_players,
    legal_actions,
    load_crops,
    load_rules,
    load_state,
    max_energy,
    migrate_state,
    normalize_season,
    normalize_player,
    recent_notes,
    season_journal_entries,
    SEASONS,
    year_for_day,
    player_slot,
    player_where,
    players_at,
    position_name,
    sleep_outlook,
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
    "strawberry_seed",
    "strawberry",
    "everbearing_seedling",
    "everbearing",
    "kabocha_seed",
    "turnip_seed",
    "carrot_seed",
    "kabocha",
    "turnip",
    "carrot",
]


def _inventory_line(state: dict, crops: dict | None = None) -> str:
    inv = state.get("inventory", {})
    parts = []
    seen = set()
    for key in INVENTORY_ORDER:
        seen.add(key)
        count = int(inv.get(key, 0))
        if count <= 0:
            continue
        parts.append(_item_phrase(key, count, crops))
    for key, count in inv.items():
        if key in seen or int(count) <= 0:
            continue
        parts.append(_item_phrase(key, int(count), crops))
    if not parts:
        return "  (empty)"
    return "  " + ", ".join(parts)


def _item_phrase(key: str, count: int, crops: dict | None = None) -> str:
    stock = None
    kind = key
    if key.endswith("_seedling"):
        kind = key[: -len("_seedling")]
        stock = "seedling"
    elif key.endswith("_seed"):
        kind = key[: -len("_seed")]
        stock = "seed"
    info = crop_info(crops or {}, kind) if crops is not None else {}
    if not info and crops is None:
        try:
            info = crop_info(load_crops(), kind) or {}
        except Exception:
            info = {}
    if stock:
        noun = stock_noun(info, count) if info else (stock if count == 1 else stock + "s")
        name = crop_name(kind, info)
        return f"{count} {name} {noun}"
    return f"{count} {crop_name_plural(kind, info, count)}"


def _ascii_cell(tile: dict) -> tuple[str, str]:
    """Two short lines for the mini map cell."""
    if tile.get("type") == "cabin":
        return "CABIN", "lantern"
    crop = tile.get("crop")
    wet = "wet" if tile.get("watered") else "dry"
    if crop:
        kind = crop.get("kind", "?")
        stage = crop.get("stage", "?")
        label = {"everbearing": "eberry"}.get(kind, kind)
        short = {
            "seed": "seed",
            "sprouting": "sprout",
            "growing": "grow",
            "regrowing": "regrow",
            "mature": "READY",
            "dormant": "rest",
            "withered": "wilt",
        }.get(stage, stage[:5])
        mark = " *" if (tile.get("weedy") or tile.get("weed")) else ""
        return f"{str(label)[:7]:<7}", f"{short} {wet}{mark}"
    mark = " *" if (tile.get("weedy") or tile.get("weed")) else ""
    if tile.get("tilled"):
        return "tilled", wet + mark
    return "soil", wet + mark


def _avatar_mark(state: dict, row: int, col: int) -> str:
    marks = []
    seen = set()
    for name in players_at(state, row, col):
        initial = (display_name(name) or name or "?").strip()[:1].upper() or "?"
        if initial in seen:
            initial = (name or "?").strip()[:1].upper() or "?"
        seen.add(initial)
        marks.append(initial)
    return "".join(marks)


def ascii_map(state: dict) -> str:
    widths = [10, 10, 10]
    # compute from content
    cells = []
    for r in range(1, ROWS + 1):
        row_cells = []
        for c in range(1, COLS + 1):
            a, b = _ascii_cell(get_tile(state, r, c))
            mark = _avatar_mark(state, r, c)
            if mark:
                b = f"{b} {mark}".strip()
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
    who_here = players_at(state, row, col)
    who_bit = ""
    if who_here:
        names = ", ".join(display_name(n) for n in who_here)
        who_bit = f" {names} standing here."
    if tile.get("type") == "cabin":
        from config import flavor
        cabin = flavor(f"cabin_{weather}") or flavor("cabin") or "the cabin. A warm lantern glows in the window."
        return (
            f"  {here} — {cabin}{who_bit} "
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
        return f"  {here} — {tilled} soil, {moist}. Empty.{who_bit}{weed_bit} (sprite: {key})"
    kind = crop["kind"]
    info = crop_info(crops, kind) or {}
    stage = crop.get("stage", "seed")
    if stage == "withered":
        return (
            f"  {here} — {tilled} soil, {moist}. "
            f"A withered {kind} (planted on day {crop.get('planted_day', '?')}, "
            f"grew {crop.get('days_grown', 0)} day(s) before it died, "
            f"{crop.get('dry_days', 0)} dry day(s)).{who_bit}{weed_bit} (sprite: {key})"
        )
    if info and (stage == "dormant" or (crop_is_dormant(crop, info, state.get("season")) and stage != "mature")):
        return (
            f"  {here} — {tilled} soil, {moist}. "
            f"A dormant {kind}, resting until spring. It needs no water."
            f" Planted on day {crop.get('planted_day', '?')}.{who_bit}{weed_bit} (sprite: {key})"
        )
    if (
        info
        and is_perennial(info)
        and info.get("fruiting_after_dormancy", True)
        and not crop.get("overwintered")
        and not crop.get("fruiting_started")
    ):
        label_est = stage_label(info, stage) if info else stage
        return (
            f"  {here} — {tilled} soil, {moist}. "
            f"{crop_name(kind, info)}, establishing ({label_est}); it will fruit after its first winter, {moist}."
            f" Planted on day {crop.get('planted_day', '?')}.{who_bit}{weed_bit} (sprite: {key})"
        )
    needed = crop_cycle_days(info, crop) if info else "?"
    grown = crop.get("days_grown", 0)
    label = stage_label(info, stage) if info else stage
    planted = crop.get("planted_day", "?")
    dry = crop.get("dry_days", 0)
    dry_bit = ""
    if dry:
        limit = wither_after(crops)
        dry_bit = f", {dry} dry day(s) (withers at {limit})"
    ready = ""
    if stage == "mature":
        ready = " Ready to harvest."
        if info and regrow_days(info) > 0:
            ready += (
                f" It will fruit again in {regrow_days(info)} watered day(s) after you pick it."
            )
    return (
        f"  {here} — {tilled} soil, {moist}. "
        f"{kind}, day {grown} of {needed}, {label}, {moist}"
        f"{dry_bit}. Planted on day {planted}.{ready}{who_bit}{weed_bit} (sprite: {key})"
    )



def format_player_note(note: dict | None) -> str:
    """Label a handoff note as untrusted player text. Strips control characters."""
    from engine import sanitize_note
    if not note or not note.get("text") or not note.get("from"):
        return ""
    text = sanitize_note(note.get("text"))
    if not text:
        return ""
    who = display_name(note.get("from"))
    return f"Note from {who} (player text): {text}"


def format_journal_line(entry: dict | None) -> str:
    """One journal line: day plus the untrusted-player-text label."""
    if not entry:
        return ""
    labeled = format_player_note(entry)
    if not labeled:
        return ""
    day = entry.get("day")
    if day:
        return f"[day {day}] {labeled}"
    return labeled


def recent_note_lines(state: dict, limit: int | None = None) -> list[str]:
    """Last notes, most recent first, already de-duplicated and labelled."""
    entries = recent_notes(state, limit) if limit is not None else recent_notes(state)
    lines = [format_journal_line(entry) for entry in entries]
    return [line for line in lines if line]


def format_season_journal(state: dict, season: str | None = None) -> str:
    """The current year's journal, or one season of it, as labelled player text."""
    from engine import normalize_season as _norm
    if season is not None and str(season).strip() and _norm(season) is None:
        return (
            "Seasons are spring, summer, autumn (or fall), and winter.\n"
        )
    year, grouped = season_journal_entries(state, season)
    wanted = _norm(season) if season else None
    lines = [f"Lantern Farm journal — Year {year}"]
    if wanted:
        lines[0] = f"Lantern Farm journal — Year {year}, {wanted.capitalize()}"
    names = [wanted] if wanted else list(SEASONS)
    any_notes = False
    for name in names:
        if not wanted:
            lines.append("")
            lines.append(f"{name.capitalize()}:")
        entries = grouped.get(name) or []
        if not entries:
            if wanted:
                lines.append("(No notes in this season yet.)")
            else:
                lines.append("  (No notes in this season yet.)")
            continue
        any_notes = True
        for entry in entries:
            line = format_journal_line(entry)
            if line:
                lines.append(("  " if not wanted else "") + line)
    if not any_notes and wanted:
        pass
    return "\n".join(lines) + "\n"


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
        f"Year {year_for_day(day, crops)}  ·  {sky}  ·  {gold}G",
        f"It's {display_name(current)}'s turn.  " + "  ·  ".join(bits),
    ]
    places = []
    for name in known_players():
        places.append(f"{display_name(name)} is {describe_where(*player_where(state, name))}")
    if places:
        lines.append(", ".join(places) + ".")
    if current:
        lines.append(sleep_outlook(state, current) + ".")
    if viewer:
        view = normalize_player(viewer)
        if view:
            lines.append(f"Playing as {display_name(view)}.")
            snacks = int(player_slot(state, view).get("snacks_eaten") or 0)
            if snacks:
                from engine import snacks_per_turn
                lines.append(f"Snacks eaten this turn: {snacks}/{snacks_per_turn()}.")
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
        _inventory_line(state, crops),
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

    notes = recent_note_lines(state)
    if notes:
        lines.append("")
        lines.append("Recent notes (last 15, most recent first):")
        seen = set()
        for line in notes:
            if line in seen:
                continue
            seen.add(line)
            lines.append(f"  {line}")

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
        "You can only till, plant, water, harvest, or pluck the tile you are standing on. "
        "Move with `move up/down/left/right`, `move to <row> <col>`, or `go cabin`; "
        "each step costs 5 energy, diagonals included. "
        "Ending your turn in the cabin is sleep (full energy tomorrow, in the cabin). "
        "Ending it anywhere else is passing out (half energy tomorrow, where you fell). "
        "Eat a harvested crop from the pack with `eat <crop>` (free, up to 2 snacks a turn). "
        "The shop sells June-bearing strawberry seeds and everbearing strawberry seedlings "
        "in spring and summer. June-bearing plants establish in their first year and fruit "
        "every 7 days through spring into early summer after their first winter, then rest "
        "through autumn and winter. Everbearing seedlings are already started: they settle "
        "in 4 days and fruit every 7 days from spring through summer into early autumn, "
        "resting only in winter. Both live two years and may send runners into a neighbouring "
        "tilled empty plot. In autumn and winter the shop has nothing to sell for now. "
        "Later crops stay in the pack if you already grew them. "
        "Till, plant, and water cost energy (see rules.json); harvest, buy, sell, and eat are free. "
        "The day advances when both players have ended their turn."
    )
    return "\n".join(lines) + "\n"


def look(viewer: str | None = None) -> str:
    crops = load_crops()
    state = load_state(crops)
    return describe_state(state, crops, viewer=viewer)

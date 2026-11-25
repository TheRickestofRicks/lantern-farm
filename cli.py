#!/usr/bin/env python3
"""Lantern Farm command line.

Default player and names come from config.local.json (see config.example.json).
"""

from __future__ import annotations

import sys

from describe import describe_state, format_season_journal, look
from engine import do_action, normalize_season, parse_player, reset_state, session
from hey_notify import maybe_notify_after_end_turn


def usage() -> str:
    from config import default_cli_player, default_web_player, display_name, player_ids, starting_player, title
    ids = player_ids()
    cli_p = default_cli_player()
    web_p = default_web_player()
    start = starting_player()
    id_list = " or ".join(ids)
    examples = "\n".join(f'  python3 cli.py --player {i} do "<action>"' for i in ids)
    return f"""{title()}

  python3 cli.py look
  python3 cli.py recipes
  python3 cli.py journal
  python3 cli.py journal summer
  python3 cli.py do "<action>"
{examples}
  python3 cli.py new

The CLI plays as {display_name(cli_p)} ({cli_p}) by default. The web page plays as {display_name(web_p)} ({web_p}).
Use --player {id_list} to override (before or after the subcommand).

Actions:
  move up|down|left|right
  move to <row> <col>
  go cabin
  till                    (or till <row> <col> — you must be on that tile)
  plant <kind>            (or plant <row> <col> <kind>)
  water                   (or water <row> <col>)
  harvest                 (or harvest <row> <col>)
  pluck                   (or pluck <row> <col>)
  eat <crop>
  buy <kind> <count>      (at the cabin)
  sell <kind> <count>     (at the cabin, from backpack or chest)
  take <item> [count]     (chest to backpack, at the cabin; count or all)
  drop <item> [count]     (backpack to chest, at the cabin; count or all)
  craft <recipe>          (at the cabin; only recipes you can cook are listed)
  recipes                 (the recipe book of discovered recipes)
  end turn
  end turn <note>
  end turn: <note>

You can only till, plant, water, harvest, or pluck the tile you are standing on.
Till needs a hoe in your backpack; water needs a watering can. There is one hoe
and two cans in the world; they start in the cabin chest. Each player has a
4-slot backpack (tools take a slot each). Harvest goes into the backpack — if it is
full, walk home and drop something first. Buy, sell, take, drop, and craft
are done at the cabin. The shop also sells bread (8G), butter (10G), and milk
(8G) year-round. Open the recipe book with `recipes`; jam and kabocha soup
start discovered, and a recipe is learned when you first have all its
ingredients at the cabin (or cook it). Only cookable discovered recipes appear
as craft actions. Kitchen recipes include bread and butter, jam toast,
strawberry milk, buttered kabocha, and kabocha cream soup.

Each step costs 5 energy, including diagonals. Harvest, buy, sell, eat,
take and drop are free; crafting costs 5 energy. Eat a snack from the backpack (up to 2 a turn)
to restore energy: strawberry 30, everbearing 20, jam 40, soup 55, stew 50,
bread 10, butter 6, milk 8, and later crops if you have them (carrot 10, turnip 12, kabocha 25).

Ending your turn in the cabin is sleep — next day you wake there with 100
energy. Ending it anywhere else is passing out — you wake where you fell
with 50 energy. When both have ended their turn, the day advances and it
becomes {display_name(start)}'s turn.
You can leave a short note:  python3 cli.py do "end turn water the kabocha"
or  python3 cli.py do "end turn: water the kabocha"

End-turn notes are kept in a journal for the current year, one page per
season (spring, summer, autumn, winter). `look` shows the last 15 notes.
`python3 cli.py journal` prints this year's journal; add a season (fall
means autumn) to read just that page. Older years are archived and not shown.

Rows and columns are 1-indexed. Row 1 is the top, col 1 is the left.
The cabin is top-right (row 1 col 3) and cannot be farmed.

Crops: the shop sells June-bearing strawberry seeds (15G) and everbearing strawberry seedlings (40G) in spring and summer. June-bearing plants establish the first year and fruit every 7 days through spring into early summer after their first winter, then rest through autumn and winter. Everbearing seedlings settle in 4 days and fruit every 7 days from spring through summer into early autumn, resting only in winter. Both live two years and may send runners. In autumn and winter the seed rack is empty, but bread, butter, and milk stay in the shop. Turnip, carrot, and kabocha are later content — still plantable, sellable, and edible if you already have them.
"""






def _new_farm_line() -> str:
    from config import display_name, flavor, starting_player
    text = flavor("new_farm", starter=display_name(starting_player()))
    if not text:
        text = f"A new farm is ready — day 1, spring, {display_name(starting_player())}'s turn."
    if not text.endswith("\n"):
        text = text + "\n"
    return text + "\n"

def parse_argv(argv: list[str]) -> tuple[str, list[str], str | None]:
    """Return (player, remaining args, error). CLI default comes from config."""
    from config import default_cli_player, player_ids
    player = default_cli_player()
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in {"--player", "-p"}:
            if i + 1 >= len(argv):
                return player, out, "Usage: --player " + "  or  --player ".join(player_ids())
            player = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--player="):
            player = arg.split("=", 1)[1]
            i += 1
            continue
        out.append(arg)
        i += 1
    key, err = parse_player(player)
    if err or not key:
        return player, out, err or ("Players are " + " and ".join(player_ids()) + ".")
    return key, out, None


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    player, args, err = parse_argv(raw)
    if err and (not args or args[0] in {"-h", "--help", "help"}):
        # Allow --help even if --player was malformed; otherwise report the flag error.
        if not args or args[0] in {"-h", "--help", "help"}:
            sys.stdout.write(usage())
            return 0
    if not args or args[0] in {"-h", "--help", "help"}:
        sys.stdout.write(usage())
        return 0
    if err:
        sys.stderr.write(err + "\n")
        return 2
    cmd = args[0].lower()
    if cmd == "look":
        sys.stdout.write(look(viewer=player))
        return 0
    if cmd in {"recipes", "recipe"}:
        from engine import format_recipe_book, load_rules
        with session(write=True) as (state, crops):
            sys.stdout.write(format_recipe_book(state, crops, load_rules(), player=player))
        return 0
    if cmd == "journal":
        season = " ".join(args[1:]).strip()
        if season and normalize_season(season) is None:
            sys.stderr.write("Seasons are spring, summer, autumn (or fall), and winter.\n")
            return 2
        with session(write=False) as (state, _crops):
            sys.stdout.write(format_season_journal(state, season or None))
        return 0
    if cmd in {"new", "reset"}:
        reset_state()
        sys.stdout.write(_new_farm_line())
        sys.stdout.write(look(viewer=player))
        return 0
    if cmd == "do":
        action = " ".join(args[1:]).strip()
        if (action.startswith('"') and action.endswith('"')) or (
            action.startswith("'") and action.endswith("'")
        ):
            action = action[1:-1].strip()
        if not action:
            sys.stderr.write('Usage: python3 cli.py do "water 1 2"\n')
            return 2
        if action.lower() == "look":
            sys.stdout.write(look(viewer=player))
            return 0
        if action.lower() in {"new", "reset"}:
            reset_state()
            sys.stdout.write(_new_farm_line())
            sys.stdout.write(look(viewer=player))
            return 0
        with session(write=True) as (state, crops):
            ok, message = do_action(state, crops, action, player=player)
            sys.stdout.write(message + "\n")
            if ok:
                maybe_notify_after_end_turn(player, state, ok)
                sys.stdout.write("\n")
                sys.stdout.write(describe_state(state, crops, viewer=player))
            return 0 if ok else 1
    sys.stderr.write(usage())
    sys.stderr.write(f"\nUnknown command: {cmd}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

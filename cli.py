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
  buy <kind> <count>
  sell <kind> <count>
  end turn
  end turn <note>
  end turn: <note>

You can only till, plant, water, harvest, or pluck the tile you are standing on.
Each step costs 5 energy, including diagonals. Harvest, buy, sell, and eat
are free. Eat a harvested crop from the pack (up to 2 snacks a turn) to
restore energy: strawberry 30, everbearing strawberry 20, and later crops if you have them (carrot 10, turnip 12, kabocha 25). Eating spends the crop
instead of selling it.

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

Crops: the shop sells June-bearing strawberry seeds (15G) and everbearing strawberry seedlings (40G) in spring and summer. June-bearing plants establish the first year and fruit every 7 days through spring into early summer after their first winter, then rest through autumn and winter. Everbearing seedlings settle in 4 days and fruit every 7 days from spring through summer into early autumn, resting only in winter. Both live two years and may send runners. In autumn and winter the shop is empty for now. Turnip, carrot, and kabocha are later content — still plantable, sellable, and edible if you already have them.
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

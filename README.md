# Lantern Farm

A tiny text-first farming game. Two players share one farm and take turns.

The world lives in `state.json`. That file is the single source of truth. The
text view describes every tile exactly as it is; the picture view maps the
same tiles to sprite keys and draws an SVG for each one.

Player names, the default CLI and web players, the page theme, flavor text,
and an optional turn-notify hook live in `config.local.json` (gitignored).
Copy `config.example.json` to `config.local.json` and edit it. The example
file uses generic **Player 1** and **Player 2** and has no notify hook.

## The plot

A 3×3 grid. The **top-right** tile (row 1, column 3) is the cabin, lantern
already lit. The other eight tiles are farmland. Each player stands on one tile
(farmland or the cabin) and can only work the tile they are on.

Rows and columns are **1-indexed**. Row 1 is the top, column 1 is the left.

```
      col 1     col 2     col 3
row 1 farmland  farmland  CABIN
row 2 farmland  farmland  farmland
row 3 farmland  farmland  farmland
```

## Turns and energy

Two players, configured in `config.local.json`. After a night in the cabin you
wake with **100 energy**. Till, plant, and water cost **10** each; each step
(including a diagonal) costs **5**. Harvest, buy, sell, and eat are free.
Costs live in `rules.json` (`action_energy`) so they can be changed without
editing the engine.

- Each player has an avatar on the map. You can only till, plant, water,
  harvest, or pluck the tile you are standing on.
- Move with `move up/down/left/right`, `move to <row> <col>` (the shortest
  path is charged in 5-energy steps), or `go cabin`.
- The web page plays as the player named by the private farm link (or cookie).
- The CLI plays as the configured CLI player by default (`--player` to override).
- You can only act on your turn. If it isn't, the game says whose turn it is.
- **End turn** in the cabin is sleep: next day you wake in the cabin with 100
  energy. End it anywhere else and you pass out, waking where you fell with
  **50** energy.
- When **both** have ended their turn for the day, the day advances
  (growth, wither, weather — the same rules as before) and it becomes
  the starting player's turn again.
- Eat a harvested crop from the pack with `eat <crop>` (up to two snacks a
  turn). A strawberry restores 30, an everbearing strawberry 20. Later crops
  still snack if you have them (carrot 10, turnip 12, kabocha 25). Eating
  spends the crop instead of selling it.
- If `notify` is set in `config.local.json`, a short ping is sent on the
  configured handoff (for example when player 1 ends and it becomes player
  2's turn). Credentials come from a separate env file named in that
  config, never from the repo. If the hook is unset or the env file is
  missing, the game still works and the ping is skipped.

The log names who did what, using the configured display names.

## How to play

From this folder:

```bash
python3 cli.py look
python3 cli.py do "move to 1 1"
python3 cli.py do "till"
python3 cli.py do "plant strawberry"
python3 cli.py do "water"
python3 cli.py do "go cabin"
python3 cli.py do "end turn"
python3 cli.py do "harvest"
python3 cli.py do "pluck"
python3 cli.py do "eat strawberry"
python3 cli.py do "buy strawberry 1"
python3 cli.py do "buy everbearing 1"
python3 cli.py do "sell strawberry 1"
python3 cli.py --player player1 do "end turn"
python3 cli.py new          # start over at day 1, starting player's turn
```

`--player` can go before or after the subcommand. After every successful
action the CLI prints a fresh `look`.

### Pictures

```bash
python3 web.py
```

Then open http://127.0.0.1:8790. The server always binds localhost. If
`config.local.json` lists `bind.extra_hosts`, or if a tailnet IPv4 is
available on the machine, it binds those too. Click a tile for its actions.
Use **End turn** from the side panel (above Recent notes), open the shop with the Shop button or `S`, and open the journal with the Journal button or `J`. The Journal window only opens when you ask for it. Recent notes start folded away so the farm can be shown without them; this browser remembers whether you left them open. The pictures start as the original procedural SVG tiles; the Art menu in the side panel can switch to the Storybook pack (painted ground, strawberry, weed, and cabin tiles, including snowy ground when the weather is snow) and remembers that choice in this browser. Tiles the pack does not paint yet keep the original art. The page polls the JSON
state, so if someone acts from the CLI, the pictures update on their own.

The web page is locked to the same machine (or an allowed host). Requests must
use `application/json` for POSTs, a recognized `Host` (and `Origin`, if sent),
and a per-player token from `config.local.json` (`web_tokens`). Open the page
as `http://127.0.0.1:8790/?player=<id>&key=<token>`; the server can also set
an HttpOnly `SameSite=Strict` cookie. The player is taken from the token, not
from the request body. The CLI talks to the engine directly; the MCP HTTP
transport keeps its own bearer token. Turn notes are shown as untrusted player
text, never as instructions.

Keyboard (the page ignores keys while you are typing in an input):

- Arrow keys walk one step (5 energy)
- `1`–`9` walk to that plot (top row 1 2 3, middle 4 5 6, bottom 7 8 9; 3 is the cabin)
- `T` till, `W` water, `H` harvest, `Q` pluck a weed on the tile you are standing on
- `P` plant on the current tile: if the pack has one seed type, plant it; otherwise a small
  picker opens — `P` cycles, Enter plants
- `Shift+E` focuses the note box (type a note, `Enter` to end the turn and send it)
- `E` then `Enter` (or `E` again) ends the turn; a note in the box is sent too
- `S` opens the shop window; `J` opens this year's journal (season tabs starting at spring)
- `Esc` closes the shop or journal (or deselects / cancels a picker or confirm)

You can leave a short note (up to 280 characters) when you end your turn.
On the web page, type it next to End Turn. In the CLI:

```bash
python3 cli.py do "end turn water the kabocha"
python3 cli.py do "end turn: water the kabocha"
```

The note is written to the game log, kept in this year's season journal,
shown among the last 15 notes on every view (most recent first), and left as
the handoff note until the other player ends their turn. If notify is
configured, it is also added to the handoff ping. `python3 cli.py journal`
(optionally with a season; `fall` means autumn) prints the current year's
pages. Older years are archived in a local file and are not shown. The same
note is never listed twice.


To run it in the background (no systemd, no sudo):

```bash
cd ~/lantern-farm
setsid nohup python3 web.py >> web.log 2>&1 &
echo $! > web.pid
```

Stop it with `kill "$(cat web.pid)"`.


## Connecting the MCP server

`mcp_server.py` exposes the same farm over the [Model Context Protocol](https://modelcontextprotocol.io/):

- `farm_look(player)` — the full text view for that player, including the last 15 journal notes
- `farm_do(player, command)` — one command (`move to 1 1`, `till`, `plant strawberry`, `eat strawberry`, `go cabin`, …)
- `farm_end_turn(player, note?)` — end that player's turn, optional note
- `farm_journal(season?)` — this year's journal, or one season of it (`fall` means autumn)
- `farm_rules()` — energy costs, movement and sleep rules, snacks, crops, and configured players
- `farm_forecast()` — the 7-day forecast (also included in `farm_look`)

It uses the same engine, the same `state.json`, and the same turn and energy
rules as the CLI and the web page. A tool call that is not that player's turn
is refused.

### stdio (typical)

Point an MCP client at the server. For Claude Desktop or Cursor, add something
like this to the MCP config (use the real path to this folder):

```json
{
  "mcpServers": {
    "lantern-farm": {
      "command": "python3",
      "args": ["/path/to/lantern-farm/mcp_server.py"]
    }
  }
}
```

Then start the client. The process talks JSON-RPC on stdio.

### Optional streamable HTTP

HTTP is opt-in and **always binds to 127.0.0.1** only:

```bash
# Once: copy the example and put a long random token in mcp.env
# (mcp.env is gitignored; the server never prints the token)
cp mcp.env.example mcp.env
# edit mcp.env and set LANTERN_FARM_MCP_TOKEN, optionally LANTERN_FARM_MCP_PORT

python3 mcp_server.py --http
```

If `mcp.env` does not exist yet, `--http` writes one with a fresh token
(mode 600) and says so without printing the value. If the file exists but
has no token, HTTP stays disabled.

Clients should POST JSON-RPC to `http://127.0.0.1:8791/mcp` with

```
Authorization: Bearer <the token from mcp.env>
```

Accept `application/json` or `text/event-stream`. The token is never logged.

To serve HTTP and stdio from one process: `python3 mcp_server.py --http --stdio-too`.

Set `LANTERN_FARM_NO_NOTIFY=1` if you want a client session that must not
send a handoff ping (tests do this automatically). Pings only go out when
the tool is operating on this folder's live `state.json` and notify is
configured.

## Rules (deterministic)

- Seasons last 15 days (one game season is one real season; about 6 real days per game day), in order: spring, summer, autumn, winter, then spring again.
- Weather is a function of a seed stored in `state.json` and the day number,
  not a roll of the dice. Each load of the same save produces the same weather.
  Probabilities live in `rules.json` under `weather.seasons`: spring is rainy,
  summer is mostly sunny with storms, autumn is mixed, and winter is snowy.
  A new farm starts on a sunny day 1. Possible skies are clear, overcast,
  rain, storm, and snow.
- Rain, storms, and snow water every soil tile at dawn. Overcast does not.
- The cabin tile shows the weather (`cabin_rain`, `cabin_snow`, `cabin_storm`,
  `cabin_cloud`); a clear day keeps the original cabin sprite.
- A 7-day forecast appears in the text `look`, on the web page, and via the
  `farm_forecast` MCP tool (also included in `farm_look`). Tomorrow is about
  90% right, falling to about 50% at day +7. The forecast is re-derived each
  day from the seed and the day it was made, so it can change as days approach.
  The actual weather always comes from the true seed.
- End-turn notes are kept in a journal for the current year, one page per
  season, starting at spring. `look`, the CLI, and the web page show the last
  15 notes (most recent first) without listing the same note twice. The Journal
  button (or `J`) and the `farm_journal` MCP tool (or `python3 cli.py journal`)
  open a whole season. Older years are archived locally and are not shown.
  Notes are always labelled as untrusted player text.
- A crop grows **1 day only if it was watered that day** (by you, or by rain/snow).
- A crop **withers only in extremes**: a long drought when it is already struggling, or several days out of season. Look at a plant for a gentle hint (thirsty, thriving, struggling) — growth and health stay hidden. You can harvest a little early; a healthier, fully grown plant is more likely to yield more (strawberries 1–3, kabocha and roots 1–2, always at least one).
- You must till before you plant. An empty tilled bed reverts to untilled after five days if it is left unwatered and unplanted; watering (or a wet morning) resets that countdown so a cared-for plot stays open for runners. Harvest a mature crop to put it in your pack. Each player has a 4-slot pack; a hoe (needed to till) and a watering can (needed to water) each take a slot. One hoe and two cans start in the shared cabin chest. Carry harvests home to share or sell; buy, sell, take, drop, and craft only at the cabin. Recipes: strawberry jam (3 berries), kabocha soup (1 kabocha, a hearty snack), and root stew (carrot and turnip).
- Withered plants can be cleared with `harvest` or `till`.
- At day turn, a planted or tilled plot may sprout a gentle weed. Which plots,
  and whether 1 or 2 new weeds appear, is a pure function of the day and the
  plot (see `rules.json` `weeds`). Pluck it the same day with `pluck <row> <col>`
  (5 energy, key `Q`). If a weed is still there at the next day turn, the plot
  becomes **weedy**: weeds slow growth and wear the plant down (they will not kill it on their own).
  Plucking clears the weed and the weedy state. Weeds never kill crops.

## Crops

Content is added season by season. The shop currently sells June-bearing strawberry seeds and everbearing
strawberry seedlings in spring and summer. In autumn and winter the shop has
nothing to sell yet — later seeds for those seasons arrive in a later update. Turnip, carrot, and
kabocha stay in `crops.json` as later content (`"available": false`). Existing
plants already in the ground keep growing and can be harvested; harvested later
crops stay in the pack and can still be sold or eaten. Seeds you already own
can still be planted in season.

The shop opens as a window (button or `S`, `Esc` to close). Each item shows
its picture, a short description, season, grow and regrow time, prices, snack
energy, and buy or sell controls.

Crop times follow real life, scaled so one 15-day game season is about one
real season (~90 days, or ~6 real days per game day).

| Crop       | Days                                      | Seed | Sell | Eat | Seasons                          | Shop   |
|------------|-------------------------------------------|------|------|-----|----------------------------------|--------|
| strawberry (June-bearing seed) | 7, then every 7 in its fruiting window | 15G | 25G | 30 | spring, summer (dormant fall/winter) | yes |
| everbearing strawberry (seedling) | 4 to settle, then every 7 in its fruiting window | 40G | 18G | 20 | spring through early autumn (dormant winter) | yes |
| kabocha    | 17                                        | 20G  | 50G  | 25  | spring, summer (frost in autumn) | later  |
| turnip     | 9                                         | 8G   | 22G  | 12  | spring, autumn                   | later  |
| carrot     | 12                                        | 12G  | 32G  | 10  | spring, summer, autumn, winter   | later  |

Strawberries are a perennial "power fruit," grown more for fun than for gold.
Like real June-bearing plants, the first season is for roots and runners —
they will not fruit until the spring after their first winter. Then they fruit
every 7 watered days through spring into early summer (the first 5 days of
summer), go dormant in autumn and winter (they need no water and do not
wither), and live two years (8 seasons) before they die. Each day while they
are active they have a 10% deterministic chance to send a runner into an
orthogonally adjacent tilled, empty plot, at most once per plant per season:
about a 3-in-4 chance of a new plant each growing season if there is space,
without filling the farm in a week. A berry sells for 25G and snacks for +30
energy (more than a kabocha). Two pickings in the fruiting year are not a
fortune; the joy is the patch, the snack, and the runners.

The shop also sells everbearing strawberry seedlings for 40G — a started
plant, priced above a seed packet because the nursery has already raised it
past establishment (a little more than two June-bearing packets, less than
three). They settle in 4 watered days and fruit in the planting year, every
7 days from spring through summer into early autumn (the first 5 days of
fall), then go dormant only in winter. They live two years and send runners
the same way. Each berry sells for 18G and snacks for +20, a bit less than
the June-bearing handful, so the trade-off is earlier and steadier harvests
rather than a bigger berry.

Kabocha takes 17 game days (~100 real days): plant in spring, harvest in late
summer. Autumn frost kills it. Carrots take 12 days and can finish a spring
planting in summer; they don't mind the cold. Turnips take 9 days and prefer
the cool of spring or autumn.

A new farm starts on day 1 of spring with 80G and two strawberry seeds, both
players in the cabin, on the starting player's turn at 100 energy.
`eat <crop>` restores the Eat energy from a harvested crop in the pack (up to
two snacks a turn) and spends that crop instead of selling it.

Stages: seed → sprouting → growing → mature (strawberries also have
regrowing, and a dormant rest in the off-season). Everbearing seedlings
start as a small plant rather than a seed.


## Roadmap

- More seasonal shop stock, when later crops are ready to return.

## Files

- `state.json` — the live farm (gitignored). If it is missing, the engine
  creates a fresh day-1 farm. `state.example.json` is a generic starter save
  (Player 1 / Player 2) you can copy to `state.json`. The current year's
  journal lives in the save; older years are archived under `local/`
  (also gitignored).
- `crops.json` — crop data and starting conditions
- `rules.json` — energy costs, movement, sleep, snacks, max energy, and weed rules
- `config.example.json` — generic names, theme, and flavor (Player 1 / Player 2, no notify)
- `config.local.json` — your overlay (gitignored): names, theme, flavor, optional notify
- `config.py` — loads the example and overlays the local file
- `engine.py` — actions: move, till, plant, water, harvest, pluck, eat, buy, sell, end turn
- `describe.py` — the full text view, including an ASCII mini map
- `sprites.py` — shared `sprite_key(tile)` mapping, plus SVG tiles
- `hey_notify.py` — optional handoff ping if `notify` is configured
- `cli.py` — command line (default player from config)
- `web.py` — local http.server on port 8790 (default player from config)
- `mcp_server.py` — MCP tools for the same engine and save
- `mcp.env.example` — template for the optional HTTP bearer token (`mcp.env` is gitignored)
- `test_engine.py` — growth, energy, movement, sleep, snacks, turn, weed, config, and MCP tests

Python 3, standard library only. No remote git.

```bash
python3 test_engine.py
```

Tests set `LANTERN_FARM_NO_NOTIFY=1` and point the engine at a temporary
save, so they never write the live `state.json` and never send a notify ping.

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
already lit. The other eight tiles are farmland.

Rows and columns are **1-indexed**. Row 1 is the top, column 1 is the left.

```
      col 1     col 2     col 3
row 1 farmland  farmland  CABIN
row 2 farmland  farmland  farmland
row 3 farmland  farmland  farmland
```

## Turns and energy

Two players, configured in `config.local.json`. Each turn starts with **100 energy**.
Till, plant, and water cost **10** each. Harvest, buy, and sell are free.
Costs live in `rules.json` (`action_energy`) so they can be changed without
editing the engine.

- The web page plays as the configured web player by default (`?player=` to override).
- The CLI plays as the configured CLI player by default (`--player` to override).
- You can only act on your turn. If it isn't, the game says whose turn it is.
- **End turn** (`python3 cli.py do "end turn"`, or the button on the page)
  hands the farm to the other player with a fresh 100 energy.
- When **both** have ended their turn for the day, the day advances
  (growth, wither, weather — the same rules as before) and it becomes
  the starting player's turn again, both at 100 energy.
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
python3 cli.py do "till 1 1"
python3 cli.py do "plant 1 1 kabocha"
python3 cli.py do "water 1 1"
python3 cli.py do "end turn"
python3 cli.py do "harvest 1 1"
python3 cli.py do "pluck 1 1"
python3 cli.py do "buy carrot 1"
python3 cli.py do "sell kabocha 1"
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
Use **End turn** and the shop from the side panel. The page polls the JSON
state, so if someone acts from the CLI, the pictures update on their own.

Keyboard (the page ignores keys while you are typing in an input):

- `1`–`9` select a plot (top row 1 2 3, middle 4 5 6, bottom 7 8 9)
- `T` till, `W` water, `H` harvest, `Q` pluck a weed on the selected plot
- `P` plant: if the pack has one seed type, plant it; otherwise a small
  picker opens — `P` cycles, Enter plants
- `Shift+E` focuses the note box (type a note, `Enter` to end the turn and send it)
- `E` then `Enter` (or `E` again) ends the turn; a note in the box is sent too
- `Esc` deselects (or cancels a picker / confirm)

You can leave a short note (up to 280 characters) when you end your turn.
On the web page, type it next to End Turn. In the CLI:

```bash
python3 cli.py do "end turn water the kabocha"
python3 cli.py do "end turn: water the kabocha"
```

The note is written to the game log, shown on the other player's view until
they end their turn, and (if notify is configured) added to the handoff ping.


To run it in the background (no systemd, no sudo):

```bash
cd ~/lantern-farm
setsid nohup python3 web.py >> web.log 2>&1 &
echo $! > web.pid
```

Stop it with `kill "$(cat web.pid)"`.


## Connecting the MCP server

`mcp_server.py` exposes the same farm over the [Model Context Protocol](https://modelcontextprotocol.io/):

- `farm_look(player)` — the full text view for that player
- `farm_do(player, command)` — one command (`till 1 1`, `plant 2 2 kabocha`, …)
- `farm_end_turn(player, note?)` — end that player's turn, optional note
- `farm_rules()` — energy costs, weed rules, crops, and configured players

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

- Seasons last 14 days, in order: spring, summer, autumn, winter, then spring again.
- Weather is a function of the day number, not a roll of the dice. Days 3, 5,
  10, and 14 of each season are wet (rain, or snow in winter). All other days
  are sunny. Day 1 is sunny.
- Rain and snow water every soil tile at dawn.
- A crop grows **1 day only if it was watered that day** (by you, or by rain/snow).
- A crop **withers after 2 dry days**, or the morning the season turns against it.
- You must till before you plant. Harvest a mature crop to put it in your pack.
- Withered plants can be cleared with `harvest` or `till`.
- At day turn, a planted or tilled plot may sprout a gentle weed. Which plots,
  and whether 1 or 2 new weeds appear, is a pure function of the day and the
  plot (see `rules.json` `weeds`). Pluck it the same day with `pluck <row> <col>`
  (5 energy, key `Q`). If a weed is still there at the next day turn, the plot
  becomes **weedy** and the crop skips every other watered day (50% growth).
  Plucking clears the weed and the weedy state. Weeds never kill crops.

## Crops

| Crop    | Days | Seed | Sell | Seasons                    |
|---------|------|------|------|----------------------------|
| kabocha | 7    | 20G  | 50G  | spring, summer, autumn     |
| turnip  | 4    | 8G   | 20G  | spring, autumn             |
| carrot  | 5    | 12G  | 30G  | spring, autumn, winter     |

A new farm starts on day 1 of spring with 80G, two kabocha seeds, and one
turnip seed, on the starting player's turn at 100 energy.

Stages: seed → sprouting → growing → mature. A just-planted kabocha is
"day 0 of 7, seed". After three watered days it is "day 3 of 7, sprouting".

## Files

- `state.json` — the live farm (gitignored). If it is missing, the engine
  creates a fresh day-1 farm. `state.example.json` is a generic starter save
  (Player 1 / Player 2) you can copy to `state.json`.
- `crops.json` — crop data and starting conditions
- `rules.json` — energy costs, max energy, and weed rules
- `config.example.json` — generic names, theme, and flavor (Player 1 / Player 2, no notify)
- `config.local.json` — your overlay (gitignored): names, theme, flavor, optional notify
- `config.py` — loads the example and overlays the local file
- `engine.py` — actions: till, plant, water, harvest, pluck, buy, sell, end turn
- `describe.py` — the full text view, including an ASCII mini map
- `sprites.py` — shared `sprite_key(tile)` mapping, plus SVG tiles
- `hey_notify.py` — optional handoff ping if `notify` is configured
- `cli.py` — command line (default player from config)
- `web.py` — local http.server on port 8790 (default player from config)
- `mcp_server.py` — MCP tools for the same engine and save
- `mcp.env.example` — template for the optional HTTP bearer token (`mcp.env` is gitignored)
- `test_engine.py` — growth, energy, turn, weed, config, and MCP tests

Python 3, standard library only. No remote git.

```bash
python3 test_engine.py
```

Tests set `LANTERN_FARM_NO_NOTIFY=1` and point the engine at a temporary
save, so they never write the live `state.json` and never send a notify ping.

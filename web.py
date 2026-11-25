#!/usr/bin/env python3
"""Lantern Farm image view — a tiny local web server.

Binds 127.0.0.1:8790, plus any extra hosts in config.local.json and a
tailnet IPv4 when `tailscale` is on the PATH.
The page polls /api/state so it updates when the other player acts through the CLI.
Default player, theme, and copy come from config.local.json.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from describe import describe_state
from engine import (
    do_action,
    legal_actions,
    load_crops,
    load_rules,
    load_state,
    max_energy,
    migrate_state,
    normalize_player,
    session,
)
from hey_notify import maybe_notify_after_end_turn
from sprites import is_safe_key, sprite_key, svg_for_key

def default_web_player() -> str:
    from config import default_web_player as _default
    return _default()


DEFAULT_WEB_PLAYER = None  # resolved per request

PORT = 8790
LOCAL_HOST = "127.0.0.1"


def _tailnet_ipv4() -> str | None:
    """Best-effort tailnet IPv4, if the tailscale CLI is present. Never hardcoded."""
    import shutil
    import subprocess
    exe = shutil.which("tailscale")
    if not exe:
        return None
    try:
        out = subprocess.check_output([exe, "ip", "-4"], text=True, timeout=2)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None
    for token in out.split():
        parts = token.split(".")
        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return token
    return None


def bind_hosts() -> list[str]:
    from config import load_config
    hosts = [LOCAL_HOST]
    cfg = (load_config().get("bind") or {}) if callable(load_config) else {}
    extra = list(cfg.get("extra_hosts") or [])
    extra += list(cfg.get("hosts") or [])
    for host in extra:
        host = str(host or "").strip()
        if host and host not in hosts:
            hosts.append(host)
    ts = _tailnet_ipv4()
    if ts and ts not in hosts:
        hosts.append(ts)
    return hosts


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    :root {
      --bg: #1a1410;
      --bg2: #241c16;
      --panel: #2a2118;
      --ink: #f3e6d0;
      --muted: #c4b49a;
      --gold: #e8b86a;
      --gold2: #ffcc66;
      --line: #4a3a28;
      --soil: #3a2a1c;
      --ok: #b6d07a;
      --bad: #e09070;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      background:
        radial-gradient(ellipse at 70% 12%, rgba(255, 180, 80, 0.16), transparent 42%),
        radial-gradient(ellipse at 20% 80%, rgba(80, 50, 20, 0.4), transparent 50%),
        var(--bg);
      color: var(--ink);
      font-family: "Iowan Old Style", Palatino, "Palatino Linotype", "Book Antiqua", Georgia, serif;
      min-height: 100vh;
    }
    header {
      padding: 1.2rem 1.5rem 0.4rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem 1.4rem;
      align-items: baseline;
      justify-content: space-between;
    }
    h1 {
      margin: 0;
      font-weight: 600;
      font-size: 1.8rem;
      letter-spacing: 0.04em;
      color: var(--gold2);
      text-shadow: 0 0 18px rgba(255, 180, 70, 0.35);
    }
    h1 span { font-size: 1.1rem; }
    .status {
      display: flex;
      flex-wrap: wrap;
      gap: 0.8rem 1.2rem;
      color: var(--muted);
      font-size: 1.05rem;
    }
    .status b { color: var(--ink); font-weight: 600; }
    .gold { color: var(--gold); }
    .turn { color: var(--gold2); }
    .ended { opacity: 0.7; font-size: 0.95em; }
    .playing-as { width: 100%; color: var(--muted); font-size: 0.95rem; }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 1fr) minmax(280px, 360px);
      gap: 1.4rem;
      padding: 0.8rem 1.5rem 2rem;
      align-items: start;
    }
    @media (max-width: 800px) {
      main { grid-template-columns: 1fr; }
    }
    .farm {
      background: var(--bg2);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 1rem;
      box-shadow: 0 12px 40px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,220,160,0.08);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.7rem;
    }
    button.tile {
      appearance: none;
      background: var(--soil);
      border: 2px solid var(--line);
      border-radius: 14px;
      padding: 0;
      cursor: pointer;
      overflow: hidden;
      position: relative;
      aspect-ratio: 1;
      box-shadow: 0 4px 0 #120c08;
    }
    button.tile img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    button.tile .label {
      position: absolute;
      left: 0; right: 0; bottom: 0;
      background: linear-gradient(transparent, rgba(20,12,8,0.82));
      color: var(--ink);
      font-size: 0.72rem;
      padding: 1.1rem 0.35rem 0.3rem;
      letter-spacing: 0.02em;
    }
    button.tile.cabin {
      box-shadow: 0 0 18px rgba(255, 180, 70, 0.35), 0 4px 0 #120c08;
    }
    button.tile.selected {
      border-color: var(--gold2);
      box-shadow: 0 0 0 2px rgba(255, 200, 100, 0.45), 0 4px 0 #120c08;
    }
    button.tile:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 1rem 1.1rem 1.2rem;
      box-shadow: 0 12px 40px rgba(0,0,0,0.3);
    }
    .panel h2 {
      margin: 0 0 0.5rem;
      font-size: 1.05rem;
      color: var(--gold);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .panel p { margin: 0.2rem 0 0.7rem; color: var(--muted); line-height: 1.45; }
    .actions, .shop-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }
    .btn {
      appearance: none;
      border: 1px solid var(--line);
      background: #3a2c20;
      color: var(--ink);
      font: inherit;
      font-size: 0.95rem;
      padding: 0.4rem 0.7rem;
      border-radius: 999px;
      cursor: pointer;
    }
    .btn:hover { background: #4a3a28; border-color: var(--gold); }
    .btn.primary {
      background: #5a3e18;
      border-color: var(--gold);
      color: var(--gold2);
    }
    .btn:disabled { opacity: 0.4; cursor: default; }
    .sleep {
      width: 100%;
      margin-top: 0.8rem;
      padding: 0.7rem;
      border-radius: 12px;
      font-size: 1.05rem;
    }
    .shop-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
      padding: 0.45rem 0;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
    }
    .shop-item:last-child { border-bottom: 0; }
    .shop-item b { color: var(--ink); }
    .toast {
      min-height: 1.4em;
      margin: 0 0 0.7rem;
      color: var(--ok);
    }
    .toast.bad { color: var(--bad); }
    .inv { margin: 0 0 0.8rem; color: var(--ink); }
    details {
      margin-top: 1rem;
      color: var(--muted);
    }
    details summary { cursor: pointer; color: var(--gold); }
    pre.look {
      white-space: pre-wrap;
      font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.72rem;
      line-height: 1.35;
      background: #140f0c;
      color: #e8dcc8;
      padding: 0.8rem;
      border-radius: 10px;
      overflow: auto;
      max-height: 24rem;
    }
    .log {
      list-style: none;
      margin: 0.4rem 0 0;
      padding: 0;
      max-height: 9rem;
      overflow: auto;
      font-size: 0.9rem;
      color: var(--muted);
    }
    .log li { margin: 0 0 0.3rem; }
    footer {
      padding: 0 1.5rem 1.5rem;
      color: #8a7a66;
      font-size: 0.85rem;
    }
    .keys {
      margin-top: 0.85rem;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.65;
    }
    kbd {
      display: inline-block;
      min-width: 1.1em;
      padding: 0.05em 0.38em;
      margin: 0 0.08em;
      border: 1px solid var(--line);
      border-bottom-width: 2px;
      border-radius: 5px;
      background: #3a2c20;
      color: var(--gold2);
      font: inherit;
      font-size: 0.78rem;
    }
    button.tile .keynum {
      position: absolute;
      top: 0.3rem;
      left: 0.4rem;
      font-size: 0.72rem;
      color: var(--gold2);
      text-shadow: 0 1px 3px #120c08;
      opacity: 0.9;
    }
    .picker {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin: 0.35rem 0 0.55rem;
    }
    .picker .btn.on {
      border-color: var(--gold2);
      color: var(--gold2);
    }
    .confirm-end {
      margin-top: 0.45rem;
      color: var(--gold);
      font-size: 0.9rem;
    }
    .end-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
      align-items: center;
      margin-top: 0.8rem;
    }
    .end-row .sleep {
      width: auto;
      flex: 0 0 auto;
      margin-top: 0;
    }
    .end-row input[type="text"] {
      flex: 1 1 12rem;
      min-width: 10rem;
      appearance: none;
      border: 1px solid var(--line);
      background: #140f0c;
      color: var(--ink);
      font: inherit;
      font-size: 0.95rem;
      padding: 0.55rem 0.7rem;
      border-radius: 12px;
    }
    .end-row input[type="text"]:focus {
      outline: none;
      border-color: var(--gold);
    }
    .end-row input[type="text"]:disabled {
      opacity: 0.45;
    }
    .last-note {
      margin: 0.7rem 0 0;
      padding: 0.55rem 0.7rem;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #21180f;
      color: var(--ink);
      line-height: 1.4;
    }
    .last-note .who {
      color: var(--gold);
      font-weight: 600;
    }
  </style>
</head>
<body>
  <header>
    <h1><span>🏮</span> __TITLE__</h1>
    <div class="status" id="status">Loading the farm…</div>
  </header>
  <main>
    <section class="farm">
      <div class="grid" id="grid" role="grid" aria-label="Farm plot"></div>
      <p class="keys" id="keys">
        <kbd>1</kbd>–<kbd>9</kbd> select plot
        · <kbd>T</kbd> till
        · <kbd>W</kbd> water
        · <kbd>P</kbd> plant
        · <kbd>H</kbd> harvest
        · <kbd>Q</kbd> pluck a weed
        · <kbd>Shift</kbd>+<kbd>E</kbd> write a note
        · <kbd>Enter</kbd> in the note box ends the turn
        · <kbd>E</kbd> then <kbd>Enter</kbd> ends with no note
        · <kbd>Esc</kbd> deselect
      </p>
    </section>
    <aside class="panel">
      <div class="toast" id="toast"></div>
      <div class="inv" id="inv"></div>
      <h2>This tile</h2>
      <p id="tile-desc">Click a plot to till, plant, water, harvest, or pluck a weed.</p>
      <div class="actions" id="tile-actions"></div>
      <div class="last-note" id="last-note" hidden></div>
      <div class="end-row">
        <button class="btn primary sleep" id="end-turn" type="button">End turn</button>
        <input id="end-note" type="text" maxlength="280" placeholder="__NOTE_PLACEHOLDER__" autocomplete="off" spellcheck="true">
      </div>
      <div class="confirm-end" id="end-confirm" hidden>End your turn? Press <kbd>E</kbd> or <kbd>Enter</kbd> to confirm, <kbd>Esc</kbd> to cancel. A note in the box will be sent too.</div>
      <h2 style="margin-top:1.1rem">Shop</h2>
      <div id="shop"></div>
      <h2 style="margin-top:1.1rem">Log</h2>
      <ul class="log" id="log"></ul>
      <details>
        <summary>__TEXT_VIEW_SUMMARY__</summary>
        <pre class="look" id="look"></pre>
      </details>
    </aside>
  </main>
  <footer>
    __WEB_FOOTER__
  </footer>
  <script>
    const weatherWord = {sun: "clear and sunny", rain: "rain", snow: "snow"};
    const PLAYERS = __PLAYERS_JSON__;
    const CABIN_SHORT = __CABIN_SHORT__;
    const DEFAULT_PLAYER = __DEFAULT_PLAYER__;
    const PLAYER_NAMES = Object.fromEntries(PLAYERS.map(function (p) { return [p.id, p.name]; }));
    const PLAYER = (new URLSearchParams(location.search).get("player") || DEFAULT_PLAYER).toLowerCase();
    function displayName(id) { return PLAYER_NAMES[id] || cap(id); }
    let selected = null;
    let lastSig = "";
    let lastData = null;
    let plantPick = null; /* {kinds, index} while choosing a seed */
    let endConfirm = false;

    function $(id) { return document.getElementById(id); }

    function invPhrase(inv) {
      const order = ["kabocha_seed","turnip_seed","carrot_seed","kabocha","turnip","carrot"];
      const bits = [];
      const used = new Set();
      for (const key of order) {
        used.add(key);
        const n = (inv && inv[key]) || 0;
        if (n <= 0) continue;
        bits.push(itemName(key, n));
      }
      if (inv) {
        for (const [key, n] of Object.entries(inv)) {
          if (used.has(key) || n <= 0) continue;
          bits.push(itemName(key, n));
        }
      }
      return bits.length ? bits.join(", ") : "empty pack";
    }

    function itemName(key, n) {
      if (key.endsWith("_seed")) {
        const kind = key.slice(0, -5);
        return n + " " + kind + (n === 1 ? " seed" : " seeds");
      }
      return n + " " + key + (n === 1 ? "" : "s");
    }

    function tileName(r, c) {
      const names = {
        "1,1": "top-left", "1,2": "top-center", "1,3": "top-right",
        "2,1": "mid-left", "2,2": "center", "2,3": "mid-right",
        "3,1": "bottom-left", "3,2": "bottom-center", "3,3": "bottom-right"
      };
      return (names[r + "," + c] || "plot") + ", row " + r + " col " + c;
    }

    function describeTile(tile, r, c) {
      if (!tile) return "Click a plot.";
      if (tile.type === "cabin") {
        return tileName(r, c) + " — " + CABIN_SHORT;
      }
      const moist = tile.watered ? "watered today" : "dry today";
      const tilled = tile.tilled ? "tilled" : "untilled";
      const crop = tile.crop;
      let weed = "";
      if (tile.weedy) weed = " A small weed has crept in. The plot is weedy; the crop grows at half speed.";
      else if (tile.weed) weed = " A small weed has crept in.";
      if (!crop) return tileName(r, c) + " — " + tilled + " soil, " + moist + ". Empty." + weed;
      if (crop.stage === "withered") {
        return tileName(r, c) + " — a withered " + crop.kind + ", " + moist + "." + weed;
      }
      return tileName(r, c) + " — " + crop.kind + ", day " + crop.days_grown +
        ", " + crop.stage + ", " + moist + "." + weed;
    }

    function render(data) {
      lastData = data;
      const s = data.state;
      const sky = weatherWord[s.weather] || s.weather;
      const capE = data.max_energy || 100;
      const players = data.players || s.players || {};
      const current = data.current_player || s.current_player || DEFAULT_PLAYER;
      function energyBit(name) {
        const slot = players[name] || {};
        const en = (slot.energy != null) ? slot.energy : capE;
        const ended = slot.ended_turn && name !== current ? " <span class='ended'>(ended)</span>" : "";
        return displayName(name) + " <b>" + en + "/" + capE + "</b>" + ended;
      }
      const energyBits = PLAYERS.map(function (p) { return "<span>" + energyBit(p.id) + "</span>"; }).join("");
      $("status").innerHTML =
        "<span>Day <b>" + s.day + "</b></span>" +
        "<span><b>" + cap(s.season) + "</b></span>" +
        "<span>" + sky + "</span>" +
        "<span class='gold'><b>" + s.gold + "G</b></span>" +
        "<span class='turn'>Turn: <b>" + displayName(current) + "</b></span>" +
        energyBits +
        "<span class='playing-as'>Playing as " + displayName(PLAYER) +
          (data.your_turn ? "" : " — waiting, it's " + displayName(current) + "'s turn") +
        "</span>";
      $("inv").textContent = "Pack: " + invPhrase(s.inventory);
      const endBtn = $("end-turn");
      if (endBtn) {
        endBtn.disabled = !data.your_turn;
        endBtn.textContent = data.your_turn ? "End turn" : "Waiting for " + displayName(current);
      }
      const noteBox = $("end-note");
      if (noteBox) {
        noteBox.disabled = !data.your_turn;
        const otherId = PLAYERS.map(function (p) { return p.id; }).filter(function (id) { return id !== PLAYER; })[0];
        noteBox.placeholder = "Note for " + displayName(otherId || "the other player") + " (optional)";
      }
      const noteEl = $("last-note");
      if (noteEl) {
        const last = (s.last_note) || data.last_note;
        if (last && last.text && last.from) {
          noteEl.hidden = false;
          noteEl.innerHTML = "<span class='who'>" + escapeHtml(displayName(last.from)) + "'s note:</span> " +
            escapeHtml(last.text);
        } else {
          noteEl.hidden = true;
          noteEl.textContent = "";
        }
      }
      $("look").textContent = data.look || "";
      const log = (s.log || []).slice(-8).reverse();
      $("log").innerHTML = log.map(function (e) {
        return "<li>[day " + e.day + "] " + escapeHtml(e.text) + "</li>";
      }).join("");

      const grid = $("grid");
      grid.innerHTML = "";
      for (let r = 1; r <= 3; r++) {
        for (let c = 1; c <= 3; c++) {
          const tile = s.tiles[r-1][c-1];
          const key = data.sprites[r-1][c-1];
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "tile" + (tile.type === "cabin" ? " cabin" : "");
          if (selected && selected.r === r && selected.c === c) btn.classList.add("selected");
          btn.setAttribute("aria-label", tileName(r, c));
          const img = document.createElement("img");
          img.src = "/sprite/" + key + ".svg";
          img.alt = key.replace(/_/g, " ");
          const num = document.createElement("div");
          num.className = "keynum";
          num.textContent = String((r - 1) * 3 + c);
          const lab = document.createElement("div");
          lab.className = "label";
          lab.textContent = tile.type === "cabin" ? "cabin" : ("r" + r + " c" + c);
          btn.appendChild(img);
          btn.appendChild(num);
          btn.appendChild(lab);
          btn.addEventListener("click", function () {
            selected = {r: r, c: c};
            plantPick = null;
            endConfirm = false;
            render(lastData);
          });
          grid.appendChild(btn);
        }
      }
      renderSelection(data);
      renderShop(data);
      renderEndConfirm(data);
    }

    function renderSelection(data) {
      const box = $("tile-actions");
      box.innerHTML = "";
      if (!selected) {
        $("tile-desc").textContent = "Click a plot, or press 1–9, then T till, W water, P plant, H harvest, Q pluck.";
        return;
      }
      const r = selected.r, c = selected.c;
      const tile = data.state.tiles[r-1][c-1];
      $("tile-desc").textContent = describeTile(tile, r, c);
      if (!data.your_turn) {
        const who = cap(data.current_player || "the other player");
        $("tile-desc").textContent = describeTile(tile, r, c) + " It's " + who + "'s turn.";
        return;
      }
      const prefix = [
        "till " + r + " " + c,
        "water " + r + " " + c,
        "harvest " + r + " " + c,
        "pluck " + r + " " + c
      ];
      const plantPrefix = "plant " + r + " " + c + " ";
      const legal = data.actions || [];
      for (const act of legal) {
        let show = false;
        let label = act;
        if (prefix.indexOf(act) !== -1) {
          show = true;
          label = act.split(" ")[0];
        } else if (act.indexOf(plantPrefix) === 0) {
          show = true;
          label = "plant " + act.slice(plantPrefix.length);
        }
        if (!show) continue;
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn";
        b.textContent = label;
        b.addEventListener("click", function () { actCmd(act); });
        box.appendChild(b);
      }
      if (!box.childNodes.length && tile && tile.type === "cabin") {
        box.textContent = "";
      }
      if (plantPick && plantPick.kinds && plantPick.kinds.length) {
        renderPlantPicker(box, r, c, plantPick);
      }
    }

    function seedKinds(inv) {
      const order = ["kabocha", "turnip", "carrot"];
      const found = [];
      const seen = {};
      inv = inv || {};
      for (const kind of order) {
        if ((inv[kind + "_seed"] || 0) > 0) {
          found.push(kind);
          seen[kind] = true;
        }
      }
      Object.keys(inv).forEach(function (key) {
        if (key.slice(-5) === "_seed" && inv[key] > 0) {
          const kind = key.slice(0, -5);
          if (!seen[kind]) found.push(kind);
        }
      });
      return found;
    }

    function renderPlantPicker(box, r, c, pick) {
      const row = document.createElement("div");
      row.className = "picker";
      row.setAttribute("role", "listbox");
      row.setAttribute("aria-label", "Choose a seed");
      pick.kinds.forEach(function (kind, i) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn" + (i === pick.index ? " on" : "");
        b.textContent = "plant " + kind;
        b.addEventListener("click", function () {
          plantPick = null;
          actCmd("plant " + r + " " + c + " " + kind);
        });
        row.appendChild(b);
      });
      const hint = document.createElement("span");
      hint.style.color = "var(--muted)";
      hint.style.fontSize = "0.85rem";
      hint.style.alignSelf = "center";
      hint.textContent = "P to cycle, Enter to plant";
      row.appendChild(hint);
      box.appendChild(row);
    }

    function renderEndConfirm(data) {
      const el = $("end-confirm");
      if (!el) return;
      const show = !!(endConfirm && data && data.your_turn);
      el.hidden = !show;
    }

    function renderShop(data) {
      const shop = $("shop");
      shop.innerHTML = "";
      const crops = data.crops || {};
      const inv = data.state.inventory || {};
      const gold = data.state.gold;
      for (const [kind, info] of Object.entries(crops)) {
        const row = document.createElement("div");
        row.className = "shop-item";
        const seeds = inv[kind + "_seed"] || 0;
        const fruit = inv[kind] || 0;
        row.innerHTML = "<div><b>" + cap(kind) + "</b><br>" +
          info.grow_days + " days · seeds " + seeds + " · crop " + fruit +
          "<br>buy " + info.seed_price + "G · sell " + info.sell_price + "G · " +
          (info.seasons || []).join(", ") + "</div>";
        const btns = document.createElement("div");
        btns.className = "shop-row";
        const buy = document.createElement("button");
        buy.type = "button";
        buy.className = "btn";
        buy.textContent = "Buy seed";
        buy.disabled = gold < info.seed_price || !data.your_turn;
        buy.addEventListener("click", function () { actCmd("buy " + kind + " 1"); });
        const sell = document.createElement("button");
        sell.type = "button";
        sell.className = "btn";
        sell.textContent = "Sell";
        sell.disabled = fruit < 1 || !data.your_turn;
        sell.addEventListener("click", function () { actCmd("sell " + kind + " 1"); });
        btns.appendChild(buy);
        btns.appendChild(sell);
        row.appendChild(btns);
        shop.appendChild(row);
      }
    }

    function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
    function escapeHtml(s) {
      return String(s).replace(/[&<>"]/g, function (ch) {
        return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[ch];
      });
    }

    function showToast(msg, ok) {
      const el = $("toast");
      el.textContent = msg || "";
      el.className = "toast" + (ok ? "" : " bad");
    }

    async function actCmd(command) {
      try {
        const res = await fetch("/api/do", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({command: command, player: PLAYER})
        });
        const data = await res.json();
        lastSig = JSON.stringify(data.state);
        if (data.ok) {
          plantPick = null;
          endConfirm = false;
          if (String(command || "").toLowerCase().indexOf("end turn") === 0) {
            const box = $("end-note");
            if (box) box.value = "";
          }
        }
        showToast(data.message, data.ok);
        render(data);
      } catch (err) {
        showToast("Could not reach the farm server.", false);
      }
    }

    async function poll() {
      try {
        const res = await fetch("/api/state?player=" + encodeURIComponent(PLAYER), {cache: "no-store"});
        const data = await res.json();
        const sig = JSON.stringify(data.state);
        if (sig !== lastSig) {
          lastSig = sig;
          render(data);
        }
      } catch (err) {
        // Keep the last view if a poll fails.
      }
    }

    function endTurnCommand() {
      const box = $("end-note");
      let note = box ? box.value : "";
      note = String(note || "").replace(/\s+/g, " ").trim();
      if (note.length > 280) note = note.slice(0, 280).trim();
      if (note) return "end turn " + note;
      return "end turn";
    }

    function submitEndTurn() {
      if (!needTurn()) return;
      endConfirm = false;
      plantPick = null;
      actCmd(endTurnCommand());
    }

    $("end-turn").addEventListener("click", function () {
      submitEndTurn();
    });

    $("end-note").addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        ev.stopPropagation();
        submitEndTurn();
        return;
      }
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        ev.target.blur();
        endConfirm = false;
        if (lastData) renderEndConfirm(lastData);
      }
    });

    function typingInField(ev) {
      const el = ev.target;
      if (!el || el === document.body || el === document.documentElement) return false;
      const tag = (el.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return true;
      if (el.isContentEditable) return true;
      return false;
    }

    function plotFromDigit(n) {
      if (n < 1 || n > 9) return null;
      return {r: Math.floor((n - 1) / 3) + 1, c: ((n - 1) % 3) + 1};
    }

    function needPlot() {
      if (selected) return true;
      showToast("Select a plot first (1–9).", false);
      return false;
    }

    function needTurn() {
      if (lastData && lastData.your_turn) return true;
      const who = cap((lastData && lastData.current_player) || "the other player");
      showToast("It's " + who + "'s turn.", false);
      return false;
    }

    function keyTill() {
      if (!needTurn() || !needPlot()) return;
      actCmd("till " + selected.r + " " + selected.c);
    }

    function keyWater() {
      if (!needTurn() || !needPlot()) return;
      actCmd("water " + selected.r + " " + selected.c);
    }

    function keyHarvest() {
      if (!needTurn() || !needPlot()) return;
      actCmd("harvest " + selected.r + " " + selected.c);
    }

    function keyPluck() {
      if (!needTurn() || !needPlot()) return;
      actCmd("pluck " + selected.r + " " + selected.c);
    }

    function keyPlant() {
      if (!needTurn() || !needPlot()) return;
      const kinds = seedKinds((lastData && lastData.state && lastData.state.inventory) || {});
      if (!kinds.length) {
        plantPick = null;
        render(lastData);
        showToast("No seeds in the pack.", false);
        return;
      }
      if (kinds.length === 1) {
        plantPick = null;
        actCmd("plant " + selected.r + " " + selected.c + " " + kinds[0]);
        return;
      }
      if (!plantPick || plantPick.kinds.join() !== kinds.join()) {
        plantPick = {kinds: kinds, index: 0};
      } else {
        plantPick.index = (plantPick.index + 1) % plantPick.kinds.length;
      }
      render(lastData);
      showToast("Plant " + kinds[plantPick.index] + "? Enter to confirm, P to cycle.", true);
    }

    function confirmPlant() {
      if (!plantPick || !selected) return false;
      if (!needTurn()) return true;
      const kind = plantPick.kinds[plantPick.index];
      plantPick = null;
      actCmd("plant " + selected.r + " " + selected.c + " " + kind);
      return true;
    }

    function focusNoteBox() {
      if (!needTurn()) return;
      const box = $("end-note");
      if (!box) {
        submitEndTurn();
        return;
      }
      endConfirm = false;
      box.focus();
      showToast("Add a note if you like, then press Enter to end your turn.", true);
    }

    function requestEndTurn(immediate) {
      if (!needTurn()) return;
      if (immediate || endConfirm) {
        submitEndTurn();
        return;
      }
      endConfirm = true;
      render(lastData);
      showToast("End your turn? Press E or Enter to confirm, Esc to cancel.", true);
    }

    function onKey(ev) {
      if (typingInField(ev)) return;
      if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
      const key = ev.key;
      const code = ev.code || "";

      if (key === "Escape") {
        ev.preventDefault();
        if (endConfirm || plantPick) {
          endConfirm = false;
          plantPick = null;
          if (lastData) render(lastData);
          showToast("");
          return;
        }
        selected = null;
        if (lastData) render(lastData);
        return;
      }

      if (key === "Enter") {
        if (plantPick) {
          ev.preventDefault();
          confirmPlant();
          return;
        }
        if (endConfirm) {
          ev.preventDefault();
          requestEndTurn(true);
          return;
        }
        return;
      }

      let digit = null;
      if (key >= "1" && key <= "9" && !ev.shiftKey) digit = parseInt(key, 10);
      else if (/^Digit[1-9]$/.test(code) && !ev.shiftKey) digit = parseInt(code.slice(5), 10);
      if (digit) {
        ev.preventDefault();
        const plot = plotFromDigit(digit);
        selected = plot;
        plantPick = null;
        endConfirm = false;
        if (lastData) render(lastData);
        return;
      }

      const letter = (key && key.length === 1) ? key.toLowerCase() : "";
      if (letter === "t") {
        ev.preventDefault();
        endConfirm = false;
        plantPick = null;
        keyTill();
        return;
      }
      if (letter === "w") {
        ev.preventDefault();
        endConfirm = false;
        plantPick = null;
        keyWater();
        return;
      }
      if (letter === "p") {
        ev.preventDefault();
        endConfirm = false;
        keyPlant();
        return;
      }
      if (letter === "h") {
        ev.preventDefault();
        endConfirm = false;
        plantPick = null;
        keyHarvest();
        return;
      }
      if (letter === "q") {
        ev.preventDefault();
        endConfirm = false;
        plantPick = null;
        keyPluck();
        return;
      }
      if (letter === "e") {
        ev.preventDefault();
        plantPick = null;
        if (ev.shiftKey) {
          focusNoteBox();
          return;
        }
        requestEndTurn(false);
        return;
      }
    }

    document.addEventListener("keydown", onKey);
    poll();
    setInterval(poll, 1500);
  </script>
</body>
</html>
"""

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#2a1c12"/>
  <path d="M16 6 L22 16 L10 16 Z" fill="#e8b86a"/>
  <rect x="12" y="16" width="8" height="10" fill="#c4842a"/>
  <circle cx="16" cy="20" r="2" fill="#ffe2a0"/>
</svg>
"""



def render_page() -> str:
    """Fill theme, player names, and flavor text into the HTML page."""
    import json as _json
    import re
    from config import (
        default_cli_player,
        default_web_player as cfg_web,
        display_name,
        flavor,
        other_player_id,
        players_public,
        theme_css_vars,
        title as farm_title,
    )
    html = PAGE
    vars_ = theme_css_vars()
    if vars_:
        css = "\n".join(f"      --{k}: {v};" for k, v in vars_.items())
        html = re.sub(
            r":root \{.*?\n    \}",
            ":root {\n" + css + "\n    }",
            html,
            count=1,
            flags=re.S,
        )
    web_p = cfg_web()
    cli_p = default_cli_player()
    other = display_name(other_player_id(web_p))
    footer = flavor(
        "web_footer",
        web_player=display_name(web_p),
        cli_player=display_name(cli_p),
    ) or (
        "The pictures come from the same JSON state as the text view. "
        f"This page plays as {display_name(web_p)}. {display_name(cli_p)} uses the command line."
    )
    replacements = {
        "__TITLE__": farm_title(),
        "__NOTE_PLACEHOLDER__": flavor("note_placeholder", other=other) or f"Note for {other} (optional)",
        "__TEXT_VIEW_SUMMARY__": flavor("text_view_summary") or "Text view (the same one the other player reads)",
        "__WEB_FOOTER__": footer,
        "__PLAYERS_JSON__": _json.dumps(players_public()),
        "__DEFAULT_PLAYER__": _json.dumps(web_p),
        "__CABIN_SHORT__": _json.dumps(flavor("cabin_short") or "the cabin, lantern lit in the window."),
    }
    for key, val in replacements.items():
        html = html.replace(key, val)
    return html


def _crop_catalog(crops: dict) -> dict:
    out = {}
    for kind, info in crops.get("crops", {}).items():
        out[kind] = {
            "seed_price": int(info["seed_price"]),
            "sell_price": int(info["sell_price"]),
            "grow_days": int(info["grow_days"]),
            "seasons": list(info["seasons"]),
        }
    return out


def _web_player(raw) -> str:
    key = normalize_player(raw) if raw else None
    return key or default_web_player()


def api_payload(
    state: dict,
    crops: dict,
    ok: bool = True,
    message: str = "",
    player: str | None = None,
) -> dict:
    rules = load_rules()
    migrate_state(state, rules)
    viewer = _web_player(player)
    from config import starting_player
    current = normalize_player(state.get("current_player")) or starting_player()
    sprites = [[sprite_key(tile) for tile in row] for row in state["tiles"]]
    return {
        "ok": ok,
        "message": message,
        "state": state,
        "sprites": sprites,
        "actions": legal_actions(state, crops, player=viewer, rules=rules),
        "look": describe_state(state, crops, viewer=viewer),
        "crops": _crop_catalog(crops),
        "viewer": viewer,
        "current_player": current,
        "players": state.get("players") or {},
        "max_energy": max_energy(rules),
        "your_turn": viewer == current,
    }


class FarmHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body, content_type: str, cache: bool = False) -> None:
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", "public, max-age=120")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path in {"/", "/index.html"}:
            self._send(200, render_page(), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            query = urlparse(self.path).query
            params = parse_qs(query)
            player = (params.get("player") or [default_web_player()])[0]
            with session(write=False) as (state, crops):
                payload = api_payload(state, crops, player=player)
            self._send(200, json.dumps(payload), "application/json; charset=utf-8")
            return
        if path == "/favicon.svg" or path == "/favicon.ico":
            self._send(200, FAVICON, "image/svg+xml", cache=True)
            return
        if path.startswith("/sprite/") and path.endswith(".svg"):
            key = path[len("/sprite/") : -len(".svg")]
            if not is_safe_key(key):
                self._send(400, "bad sprite key\n", "text/plain; charset=utf-8")
                return
            self._send(200, svg_for_key(key), "image/svg+xml; charset=utf-8", cache=True)
            return
        self._send(404, "not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path != "/api/do":
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length < 0 or length > 4096:
            self._send(400, "bad request\n", "text/plain; charset=utf-8")
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, "invalid json\n", "text/plain; charset=utf-8")
            return
        if not isinstance(data, dict):
            self._send(400, "invalid json\n", "text/plain; charset=utf-8")
            return
        command = str(data.get("command") or data.get("action") or "")
        player = _web_player(data.get("player"))
        with session(write=True) as (state, crops):
            ok, message = do_action(state, crops, command, player=player)
            if ok:
                maybe_notify_after_end_turn(player, state, ok)
            payload = api_payload(state, crops, ok, message, player=player)
        self._send(200, json.dumps(payload), "application/json; charset=utf-8")


class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def try_bind(host: str, port: int) -> ReusableServer | None:
    try:
        return ReusableServer((host, port), FarmHandler)
    except OSError as exc:
        sys.stderr.write(f"Could not bind {host}:{port} — {exc}\n")
        return None


def serve(port: int = PORT) -> None:
    # Make sure a state file exists before the first request.
    load_state(load_crops())
    hosts = bind_hosts()

    servers = []
    for host in hosts:
        httpd = try_bind(host, port)
        if httpd is not None:
            servers.append((host, httpd))

    if not servers:
        sys.stderr.write("No address could be bound. Exiting.\n")
        sys.exit(1)

    for host, httpd in servers:
        thread = threading.Thread(target=httpd.serve_forever, name=f"http-{host}", daemon=True)
        thread.start()
        sys.stdout.write(f"Lantern Farm listening on http://{host}:{port}\n")
        sys.stdout.flush()

    sys.stdout.write("Open http://127.0.0.1:%s in a browser on this machine.\n" % port)
    for host, _httpd in servers:
        if host != LOCAL_HOST:
            sys.stdout.write(f"Also listening on http://{host}:{port}\n")
    sys.stdout.flush()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        sys.stdout.write("\nStopping.\n")
        for _host, httpd in servers:
            httpd.shutdown()


if __name__ == "__main__":
    serve()

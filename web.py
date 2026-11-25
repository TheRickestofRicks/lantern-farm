#!/usr/bin/env python3
"""Lantern Farm image view — a tiny local web server.

Binds 127.0.0.1:8790, plus any extra hosts in config.local.json and a
tailnet IPv4 when `tailscale` is on the PATH.
The page polls /api/state so it updates when the other player acts through the CLI.
Default player, theme, and copy come from config.local.json.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from describe import describe_state
from engine import (
    CABIN_COL,
    CABIN_ROW,
    COLS,
    ROWS,
    do_action,
    is_player_in_cabin,
    legal_actions,
    load_crops,
    load_rules,
    load_state,
    max_energy,
    migrate_state,
    normalize_player,
    session,
    sleep_outlook,
    weather_forecast,
)
from hey_notify import maybe_notify_after_end_turn
from packs import content_type_for, public_packs, safe_pack_file
from sprites import is_safe_key, sprite_key, svg_for_key, svg_for_item

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


# Ports this process is actually listening on (includes test servers).
_LISTEN_PORTS: set[int] = set()
# Tests may install a token map so they never read or write config.local.json.
_TEST_WEB_TOKENS: dict[str, str] | None = None

COOKIE_NAME = "lantern_farm_key"


def web_port() -> int:
    from config import load_config
    try:
        return int((load_config().get("bind") or {}).get("port") or PORT)
    except (TypeError, ValueError):
        return PORT


def _register_listen_port(port: int) -> None:
    try:
        _LISTEN_PORTS.add(int(port))
    except (TypeError, ValueError):
        return


def _host_variants(raw: str, ports: set[int]) -> set[str]:
    """Expand a configured host/origin into Host-header and origin forms."""
    item = (raw or "").strip().rstrip("/")
    if not item:
        return set()
    origin = ""
    host = item
    if item.lower().startswith("http://"):
        origin = item
        host = item[7:]
    elif item.lower().startswith("https://"):
        origin = item
        host = item[8:]
    host = host.split("/", 1)[0]
    if not host:
        return set()
    out = {host.lower()}
    name, sep, port = host.rpartition(":")
    has_port = bool(sep and port.isdigit() and name)
    base = name.lower() if has_port else host.lower()
    out.add(base)
    for p in ports:
        out.add(f"{base}:{p}")
    if origin:
        out.add(origin.lower())
    else:
        for p in ports:
            out.add(f"http://{base}:{p}")
    return {v for v in out if v}


def allowed_hosts_and_origins() -> tuple[set[str], set[str]]:
    """Return (host-header values, origin values) for this farm."""
    from config import load_config
    ports = set(_LISTEN_PORTS)
    ports.add(web_port())
    ports.add(PORT)
    hosts: set[str] = set()
    for builtin in ("127.0.0.1", "localhost"):
        hosts |= _host_variants(builtin, ports)
    cfg = load_config().get("bind") or {}
    for item in list(cfg.get("allowed_hosts") or []) + list(cfg.get("extra_hosts") or []) + list(cfg.get("hosts") or []):
        hosts |= _host_variants(str(item), ports)
    ts = _tailnet_ipv4()
    if ts:
        hosts |= _host_variants(ts, ports)
    origins = {h for h in hosts if h.startswith("http://") or h.startswith("https://")}
    host_headers = {h for h in hosts if not h.startswith("http://") and not h.startswith("https://")}
    return host_headers, origins


def web_tokens() -> dict[str, str]:
    """Player id to web token. Tests may override. Never log these values."""
    if _TEST_WEB_TOKENS is not None:
        return dict(_TEST_WEB_TOKENS)
    from config import load_config, player_ids
    raw = load_config().get("web_tokens") or {}
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for pid, token in raw.items():
            key = str(pid or "").strip().lower()
            val = str(token or "").strip()
            if key and val:
                out[key] = val
    for rec in load_config().get("players") or []:
        if not isinstance(rec, dict):
            continue
        key = str(rec.get("id") or "").strip().lower()
        val = str(rec.get("web_token") or rec.get("token") or "").strip()
        if key and val and key not in out:
            out[key] = val
    known = set(player_ids())
    if known:
        out = {k: v for k, v in out.items() if k in known}
    return out


def player_for_token(given: str | None) -> str | None:
    """Return the player id for a presented token, or None. Constant-time compare."""
    token = (given or "").strip()
    if not token:
        return None
    presented = hashlib.sha256(token.encode("utf-8")).digest()
    found: str | None = None
    for pid, stored in web_tokens().items():
        digest = hashlib.sha256(stored.encode("utf-8")).digest()
        if hmac.compare_digest(digest, presented):
            found = pid
    return found


def _parse_cookies(header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (header or "").split(";"):
        if "=" not in part:
            continue
        name, val = part.split("=", 1)
        name = name.strip()
        if name:
            out[name] = val.strip()
    return out


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
      height: 100%;
      overflow: hidden;
    }
    body {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      min-height: 100dvh;
      max-height: 100vh;
      max-height: 100dvh;
    }
    header {
      flex: 0 0 auto;
      padding: 0.65rem 1.2rem 0.3rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem 1.2rem;
      align-items: baseline;
      justify-content: space-between;
    }
    h1 {
      margin: 0;
      font-weight: 600;
      font-size: 1.45rem;
      letter-spacing: 0.04em;
      color: var(--gold2);
      text-shadow: 0 0 18px rgba(255, 180, 70, 0.35);
    }
    h1 span { font-size: 1rem; }
    .status {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      color: var(--muted);
      font-size: 0.98rem;
    }
    .status b { color: var(--ink); font-weight: 600; }
    .gold { color: var(--gold); }
    .turn { color: var(--gold2); }
    .ended { opacity: 0.7; font-size: 0.95em; }
    .playing-as { width: 100%; color: var(--muted); font-size: 0.95rem; }
    main {
      flex: 1 1 auto;
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 32vw);
      gap: 1rem;
      padding: 0.4rem 1.2rem 0.5rem;
      align-items: stretch;
      overflow: hidden;
    }
    .farm {
      background: var(--bg2);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 0.7rem;
      box-shadow: 0 12px 40px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,220,160,0.08);
      display: flex;
      flex-direction: column;
      min-height: 0;
      overflow: hidden;
    }
    .farm-map {
      flex: 1 1 auto;
      min-height: 0;
      container-type: size;
      display: grid;
      place-items: center;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: clamp(0.25rem, 1.6cqi, 0.7rem);
      width: min(100cqw, 100cqh);
      height: min(100cqw, 100cqh);
      aspect-ratio: 1;
    }
    .forecast {
      flex: 0 0 auto;
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 0.3rem;
      margin-top: 0.5rem;
      padding-top: 0.5rem;
      border-top: 1px solid var(--line);
    }
    .forecast-day {
      text-align: center;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.25;
      padding: 0.35rem 0.15rem 0.4rem;
      background: var(--panel);
      border-radius: 10px;
      border: 1px solid var(--line);
    }
    .forecast-day .fw { color: var(--ink); font-weight: 600; display: block; margin-top: 0.1rem; }
    .forecast-day .fd { font-size: 0.72rem; opacity: 0.85; }
    .forecast-day svg { display: block; width: 28px; height: 28px; margin: 0 auto 0.15rem; }
    @media (max-width: 800px) {
      .forecast { grid-template-columns: repeat(4, 1fr); }
    }
    @media (max-height: 800px) {
      header { padding: 0.4rem 1rem 0.15rem; }
      h1 { font-size: 1.22rem; }
      .status { font-size: 0.88rem; gap: 0.35rem 0.8rem; }
      .forecast-day { font-size: 0.68rem; padding: 0.2rem 0.08rem 0.25rem; }
      .forecast-day svg { width: 22px; height: 22px; }
      .keys { font-size: 0.74rem; margin-top: 0.4rem; line-height: 1.45; }
      footer { padding: 0.2rem 1rem 0.35rem; font-size: 0.75rem; }
    }
    @media (max-width: 800px) {
      html, body { overflow: auto; height: auto; max-height: none; }
      main {
        grid-template-columns: 1fr;
        overflow: visible;
        height: auto;
      }
      .farm-map {
        min-height: min(70vw, 70vh);
        height: min(70vw, 70vh);
      }
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
    button.tile img,
    button.tile .tile-art,
    button.tile .tile-art img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    button.tile .tile-art {
      position: absolute;
      inset: 0;
      z-index: 0;
    }
    button.tile .tile-art img {
      position: absolute;
      inset: 0;
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
    button.tile.here {
      box-shadow: 0 0 0 2px rgba(255, 200, 100, 0.35), 0 4px 0 #120c08;
    }
    button.tile .avatars {
      position: absolute;
      top: 0.28rem;
      right: 0.28rem;
      display: flex;
      gap: 3px;
      z-index: 2;
      pointer-events: none;
    }
    button.tile .avatar {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 2px solid #fff4e0;
      box-shadow: 0 1px 3px #120c08;
      box-sizing: border-box;
    }
    button.tile .avatar.you {
      box-shadow: 0 0 0 2px var(--gold2), 0 1px 3px #120c08;
    }
    #status.auth-needed, #status.load-error {
      color: var(--bad);
      font-weight: 600;
    }
    .sleep-outlook {
      margin: 0.45rem 0 0;
      color: var(--gold);
      font-size: 0.92rem;
      line-height: 1.4;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 0.85rem 1rem 1rem;
      box-shadow: 0 12px 40px rgba(0,0,0,0.3);
      min-height: 0;
      overflow: auto;
      overscroll-behavior: contain;
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
      max-height: 12rem;
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
      flex: 0 0 auto;
      padding: 0.25rem 1.2rem 0.45rem;
      color: #8a7a66;
      font-size: 0.8rem;
    }
    .keys {
      flex: 0 0 auto;
      margin-top: 0.5rem;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.5;
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
    .last-note, .recent-notes {
      margin: 0.7rem 0 0;
      padding: 0.55rem 0.7rem;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #21180f;
      color: var(--ink);
      line-height: 1.4;
    }
    .last-note .who, .recent-notes .who {
      color: var(--gold);
      font-weight: 600;
    }
    .recent-notes-head,
    .recent-notes > summary {
      color: var(--gold);
      font-weight: 600;
      font-size: 0.92rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin: 0 0 0.35rem;
      cursor: pointer;
    }
    .recent-notes > summary:focus-visible {
      outline: 2px solid var(--gold);
      outline-offset: 2px;
    }
    .recent-notes ul {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .recent-notes li {
      margin: 0.35rem 0 0;
    }
    .recent-notes .day {
      color: var(--muted);
      font-size: 0.88rem;
    }
    .shop-launch {
      margin: 0 0 0.8rem;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.45rem;
    }
    .art-pack-wrap {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      color: var(--muted);
      font-size: 0.9rem;
    }
    .art-pack-wrap select {
      appearance: none;
      border: 1px solid var(--line);
      background: #140f0c;
      color: var(--ink);
      font: inherit;
      font-size: 0.95rem;
      padding: 0.4rem 0.65rem;
      border-radius: 12px;
    }
    .art-pack-wrap select:focus {
      outline: none;
      border-color: var(--gold);
    }
    .journal-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin: 0.2rem 0 0.7rem;
    }
    .journal-tabs button[aria-selected="true"] {
      border-color: var(--gold);
      color: var(--gold);
    }
    .journal-entry {
      margin: 0 0 0.7rem;
      color: var(--ink);
      line-height: 1.4;
    }
    .journal-entry .day { color: var(--muted); font-size: 0.88rem; }
    .journal-empty { color: var(--muted); line-height: 1.5; }
    .shop-modal {
      position: fixed;
      inset: 0;
      z-index: 40;
      display: grid;
      place-items: center;
      padding: 1.2rem;
    }
    .shop-modal[hidden] { display: none !important; }
    .shop-backdrop {
      position: absolute;
      inset: 0;
      background: rgba(12, 8, 6, 0.72);
    }
    .shop-dialog {
      position: relative;
      z-index: 1;
      width: min(52rem, 100%);
      max-height: min(86dvh, 860px);
      overflow: auto;
      overscroll-behavior: contain;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 24px 70px rgba(0,0,0,0.55);
      padding: 1rem 1.15rem 1.2rem;
    }
    .shop-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.8rem;
      margin-bottom: 0.4rem;
    }
    .shop-head h2 { margin: 0; }
    .shop-empty {
      color: var(--muted);
      line-height: 1.5;
      margin: 0.7rem 0 1rem;
    }
    .shop-section-title {
      margin: 1rem 0 0.2rem;
      font-size: 0.92rem;
      color: var(--gold);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .shop-card {
      display: grid;
      grid-template-columns: 88px 1fr;
      gap: 0.7rem 1rem;
      padding: 0.85rem 0;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
    }
    .shop-card:last-child { border-bottom: 0; }
    .shop-card img {
      width: 88px;
      height: 88px;
      object-fit: cover;
      border-radius: 12px;
      background: var(--soil);
      border: 1px solid var(--line);
    }
    .shop-card b { color: var(--ink); font-size: 1.05rem; }
    .shop-card .desc { margin: 0.25rem 0 0.4rem; color: var(--ink); line-height: 1.4; }
    .shop-meta { font-size: 0.88rem; line-height: 1.45; }
    .shop-qty {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem;
      margin-top: 0.45rem;
    }
    .shop-qty input[type="number"] {
      width: 3.4rem;
      appearance: none;
      border: 1px solid var(--line);
      background: #140f0c;
      color: var(--ink);
      font: inherit;
      font-size: 0.95rem;
      padding: 0.3rem 0.4rem;
      border-radius: 8px;
      text-align: center;
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
      <div class="farm-map">
        <div class="grid" id="grid" role="grid" aria-label="Farm plot"></div>
      </div>
      <div class="forecast" id="forecast" hidden></div>
      <p class="keys" id="keys">
        <kbd>&uarr;</kbd><kbd>&darr;</kbd><kbd>&larr;</kbd><kbd>&rarr;</kbd> walk
        &middot; <kbd>1</kbd>&ndash;<kbd>9</kbd> walk to that plot
        &middot; <kbd>T</kbd> till
        &middot; <kbd>W</kbd> water
        &middot; <kbd>P</kbd> plant
        &middot; <kbd>H</kbd> harvest
        &middot; <kbd>Q</kbd> pluck a weed
        &middot; <kbd>S</kbd> shop
        &middot; <kbd>J</kbd> journal
        &middot; <kbd>Shift</kbd>+<kbd>E</kbd> write a note
        &middot; <kbd>Enter</kbd> in the note box ends the turn
        &middot; <kbd>E</kbd> then <kbd>Enter</kbd> ends with no note
        &middot; <kbd>Esc</kbd> closes the shop or journal or deselects
      </p>
    </section>
    <aside class="panel">
      <div class="toast" id="toast"></div>
      <div class="inv" id="inv"></div>
      <div class="shop-launch">
        <button class="btn primary" id="open-shop" type="button">Shop <kbd>S</kbd></button>
        <button class="btn" id="open-journal" type="button">Journal <kbd>J</kbd></button>
        <label class="art-pack-wrap">Art
          <select id="art-pack" aria-label="Art pack"></select>
        </label>
      </div>
      <h2>This tile</h2>
      <p id="tile-desc">Walk with the arrow keys or 1–9. T, W, P, H, and Q act on the tile you are standing on.</p>
      <div class="actions" id="tile-actions"></div>
      <div class="end-row">
        <button class="btn primary sleep" id="end-turn" type="button">End turn</button>
        <input id="end-note" type="text" maxlength="280" placeholder="__NOTE_PLACEHOLDER__" autocomplete="off" spellcheck="true">
      </div>
      <div class="sleep-outlook" id="sleep-outlook"></div>
      <div class="confirm-end" id="end-confirm" hidden>End your turn? Press <kbd>E</kbd> or <kbd>Enter</kbd> to confirm, <kbd>Esc</kbd> to cancel. A note in the box will be sent too.</div>
      <details class="recent-notes" id="recent-notes" hidden>
        <summary class="recent-notes-head">Recent notes</summary>
        <ul id="recent-notes-list"></ul>
      </details>
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
  <div id="shop-modal" class="shop-modal" hidden>
    <div class="shop-backdrop" id="shop-backdrop"></div>
    <div class="shop-dialog" role="dialog" aria-modal="true" aria-labelledby="shop-title">
      <div class="shop-head">
        <h2 id="shop-title">Shop</h2>
        <button type="button" class="btn" id="shop-close">Close</button>
      </div>
      <div id="shop" class="shop-body"></div>
    </div>
  </div>
  <div id="journal-modal" class="shop-modal" hidden>
    <div class="shop-backdrop" id="journal-backdrop"></div>
    <div class="shop-dialog" role="dialog" aria-modal="true" aria-labelledby="journal-title">
      <div class="shop-head">
        <h2 id="journal-title">Journal</h2>
        <button type="button" class="btn" id="journal-close">Close</button>
      </div>
      <div class="journal-tabs" id="journal-tabs" role="tablist"></div>
      <div id="journal-body" class="shop-body"></div>
    </div>
  </div>
  <script>
    const weatherWord = {sun: "clear and sunny", cloud: "overcast", rain: "rain", storm: "a storm", snow: "snow"};
    const forecastWord = {sun: "clear", cloud: "overcast", rain: "rain", storm: "storm", snow: "snow"};
    const PLAYERS = __PLAYERS_JSON__;
    const ROWS = __ROWS__;
    const COLS = __COLS__;
    const CABIN = __CABIN__;
    const CABIN_SHORT = __CABIN_SHORT__;
    const AUTH_NEEDED = "This page needs your private farm link (see the URL file in local/).";
    let pollTimer = null;
    let authStopped = false;
    const CABIN_BY_WEATHER = __CABIN_BY_WEATHER__;
    const DEFAULT_PLAYER = __DEFAULT_PLAYER__;
    const PLAYER_NAMES = Object.fromEntries(PLAYERS.map(function (p) { return [p.id, p.name]; }));
    let PLAYER = (new URLSearchParams(location.search).get("player") || DEFAULT_PLAYER).toLowerCase();
    function displayName(id) { return PLAYER_NAMES[id] || cap(id); }
    let selected = null;
    let lastSig = "";
    let lastData = null;
    let plantPick = null; /* {kinds, index} while choosing a seed */
    let endConfirm = false;
    let shopOpen = false;
    let journalOpen = false;
    let journalSeason = "spring";
    const JOURNAL_SEASONS = ["spring", "summer", "autumn", "winter"];
    const shopQty = {};
    const ART_PACKS = __ART_PACKS__;
    const ART_PACK_STORAGE = "lantern-farm-art-pack";
    const NOTES_OPEN_STORAGE = "lantern-farm-recent-notes-open";
    let artPackId = "classic";

    function $(id) { return document.getElementById(id); }

    function loadArtPackId() {
      try {
        const stored = localStorage.getItem(ART_PACK_STORAGE);
        if (stored && ART_PACKS.some(function (p) { return p.id === stored; })) return stored;
      } catch (err) {}
      return "classic";
    }
    function packById(id) {
      for (let i = 0; i < ART_PACKS.length; i++) {
        if (ART_PACKS[i].id === id) return ART_PACKS[i];
      }
      return ART_PACKS[0];
    }
    function parseSpriteKey(key) {
      key = String(key || "").trim().toLowerCase();
      if (key === "cabin" || key.indexOf("cabin_") === 0) {
        let weather = "sun";
        if (key.indexOf("cabin_") === 0 && key.length > 6) {
          const tail = key.slice(6);
          if (tail === "rain" || tail === "snow" || tail === "storm" || tail === "cloud" || tail === "sun") {
            weather = tail;
          }
        }
        return {kind: "cabin", weather: weather};
      }
      let weedy = false, weed = false, snow = false;
      if (key.length >= 6 && key.slice(-6) === "_weedy") {
        weedy = true;
        key = key.slice(0, -6);
      } else if (key.length >= 5 && key.slice(-5) === "_weed") {
        weed = true;
        key = key.slice(0, -5);
      }
      if (key.length >= 5 && key.slice(-5) === "_snow") {
        snow = true;
        key = key.slice(0, -5);
      }
      const soilKeys = {
        soil: {tilled: false, watered: false},
        soil_tilled: {tilled: true, watered: false},
        soil_watered: {tilled: true, watered: true},
        soil_wet: {tilled: false, watered: true}
      };
      if (soilKeys[key]) {
        const out = {kind: "soil", weed: weed, weedy: weedy, snow: snow};
        out.tilled = soilKeys[key].tilled;
        out.watered = soilKeys[key].watered;
        return out;
      }
      const parts = key.split("_");
      const moist = parts[parts.length - 1];
      if (parts.length >= 3 && (moist === "wet" || moist === "dry")) {
        return {
          kind: parts.slice(0, -2).join("_"),
          stage: parts[parts.length - 2],
          watered: moist === "wet",
          tilled: true,
          weed: weed,
          weedy: weedy,
          snow: snow
        };
      }
      if (weed || weedy) return {kind: "unknown", raw: key, weed: weed, weedy: weedy, snow: snow};
      return {kind: "unknown", raw: key, snow: snow};
    }
    function groundKeyFor(parsed) {
      if (!parsed || parsed.kind === "cabin" || parsed.kind === "unknown") return null;
      let base;
      if (parsed.kind === "soil") {
        if (parsed.tilled && parsed.watered) base = "soil_watered";
        else if (parsed.tilled) base = "soil_tilled";
        else if (parsed.watered) base = "soil_wet";
        else base = "soil";
      } else {
        base = parsed.watered ? "soil_watered" : "soil_tilled";
      }
      if (parsed.snow) return base + "_snow";
      return base;
    }
    function layersForKey(key, pack) {
      if (!pack || pack.id === "classic") return null;
      const parsed = parseSpriteKey(key);
      if (!parsed || parsed.kind === "unknown") return null;
      if (parsed.kind === "cabin") {
        const cabins = pack.cabins || {};
        const w = parsed.weather || "sun";
        const ckey = (w === "sun") ? "cabin" : ("cabin_" + w);
        const file = cabins[ckey] || cabins.cabin;
        if (!file) return null;
        return ["/static/packs/" + pack.id + "/" + file];
      }
      if (!pack.grounds) return null;
      const layers = [];
      const gkey = groundKeyFor(parsed);
      let ground = gkey && pack.grounds[gkey];
      if (!ground && gkey && gkey.slice(-5) === "_snow") ground = pack.grounds[gkey.slice(0, -5)];
      if (!ground) return null;
      layers.push("/static/packs/" + pack.id + "/" + ground);
      if (parsed.kind && parsed.kind !== "soil" && parsed.stage) {
        const crop = pack.overlays && pack.overlays[parsed.kind + "_" + parsed.stage];
        if (!crop) return null;
        layers.push("/static/packs/" + pack.id + "/" + crop);
      }
      if (parsed.weedy || parsed.weed) {
        const wkey = parsed.weedy ? "weedy" : "weed";
        const weed = pack.overlays && pack.overlays[wkey];
        if (!weed) return null;
        layers.push("/static/packs/" + pack.id + "/" + weed);
      }
      return layers;
    }
    function applyTileArt(btn, key) {
      const wrap = document.createElement("div");
      wrap.className = "tile-art";
      const layers = layersForKey(key, packById(artPackId));
      const alt = String(key || "").replace(/_/g, " ");
      function useSvg() {
        wrap.innerHTML = "";
        const img = document.createElement("img");
        img.alt = alt;
        img.src = "/sprite/" + key + ".svg";
        wrap.appendChild(img);
      }
      if (!layers) {
        useSvg();
        btn.appendChild(wrap);
        return;
      }
      let failed = false;
      layers.forEach(function (src) {
        const img = document.createElement("img");
        img.className = "layer";
        img.alt = alt;
        img.src = src;
        img.addEventListener("error", function () {
          if (failed) return;
          failed = true;
          useSvg();
        });
        wrap.appendChild(img);
      });
      btn.appendChild(wrap);
    }
    function initArtPackControl() {
      artPackId = loadArtPackId();
      const sel = $("art-pack");
      if (!sel) return;
      sel.innerHTML = "";
      (ART_PACKS || []).forEach(function (p) {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name;
        if (p.description) opt.title = p.description;
        sel.appendChild(opt);
      });
      sel.value = artPackId;
      sel.addEventListener("change", function () {
        artPackId = sel.value || "classic";
        try { localStorage.setItem(ART_PACK_STORAGE, artPackId); } catch (err) {}
        if (lastData) render(lastData);
      });
    }
    function rememberRecentNotesOpen() {
      const box = $("recent-notes");
      if (!box) return;
      try { localStorage.setItem(NOTES_OPEN_STORAGE, box.open ? "1" : "0"); } catch (err) {}
    }
    function restoreRecentNotesOpen() {
      const box = $("recent-notes");
      if (!box) return;
      try {
        box.open = localStorage.getItem(NOTES_OPEN_STORAGE) === "1";
      } catch (err) {
        box.open = false;
      }
      box.addEventListener("toggle", rememberRecentNotesOpen);
      const summary = box.querySelector("summary");
      if (summary) {
        summary.addEventListener("click", function () {
          // Persist after the default details toggle. Needed in environments
          // that change `open` on click but do not fire a `toggle` event.
          setTimeout(rememberRecentNotesOpen, 0);
        });
      }
    }

    const FALLBACK_COLORS = ["#6b8f3a", "#c47a3a", "#5a7ea6", "#a67a4a"];
    function playerColor(id) {
      for (let i = 0; i < PLAYERS.length; i++) {
        if (PLAYERS[i].id === id) {
          if (PLAYERS[i].color) return PLAYERS[i].color;
          return FALLBACK_COLORS[i % FALLBACK_COLORS.length];
        }
      }
      return FALLBACK_COLORS[0];
    }
    function cabinPos(data) {
      const c = (data && data.cabin) || CABIN || [1, 3];
      return {r: c[0], c: c[1]};
    }
    function describeWhere(r, c, data) {
      const cabin = cabinPos(data);
      if (r === cabin.r && c === cabin.c) return "in the cabin";
      const cols = COLS || 3;
      return "at plot " + ((r - 1) * cols + c);
    }
    function standingFrom(data) {
      data = data || lastData;
      const players = (data && (data.players || (data.state && data.state.players))) || {};
      const slot = players[PLAYER] || {};
      const r = parseInt(slot.row, 10);
      const c = parseInt(slot.col, 10);
      if (r && c) return {r: r, c: c};
      return cabinPos(data);
    }
    function whoAt(data, r, c) {
      const players = (data && (data.players || (data.state && data.state.players))) || {};
      const here = [];
      for (let i = 0; i < PLAYERS.length; i++) {
        const id = PLAYERS[i].id;
        const slot = players[id] || {};
        if (Number(slot.row) === r && Number(slot.col) === c) here.push(id);
      }
      return here;
    }

    function slotsPhrase(slots) {
      if (!slots || !slots.length) return "empty";
      const bits = [];
      let open = 0;
      for (const slot of slots) {
        if (!slot || !slot.item) { open += 1; continue; }
        bits.push(itemName(slot.item, slot.count || 1));
      }
      if (!bits.length) return "empty" + (open ? (" (" + open + " slots)") : "");
      return bits.join(", ");
    }

    function invPhrase(inv) {
      const order = ["strawberry_seed","strawberry","everbearing_seedling","everbearing","kabocha_seed","turnip_seed","carrot_seed","kabocha","turnip","carrot"];
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

    function cropInfo(kind) {
      return (lastData && lastData.crops && lastData.crops[kind]) || {};
    }
    function itemName(key, n) {
      let kind = key;
      let stock = null;
      if (key.endsWith("_seedling")) { kind = key.slice(0, -9); stock = "seedling"; }
      else if (key.endsWith("_seed")) { kind = key.slice(0, -5); stock = "seed"; }
      const info = cropInfo(kind);
      const name = info.name || kind;
      if (stock) {
        const noun = stock + (n === 1 ? "" : "s");
        return n + " " + name + " " + noun;
      }
      const fruit = n === 1 ? name : (info.name_plural || (name + "s"));
      return n + " " + fruit;
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
        const w = (lastData && lastData.state && lastData.state.weather) || "sun";
        const byWeather = (typeof CABIN_BY_WEATHER !== "undefined") ? CABIN_BY_WEATHER[w] : "";
        return tileName(r, c) + " — " + (byWeather || CABIN_SHORT);
      }
      const moist = tile.watered ? "watered today" : "dry today";
      const tilled = tile.tilled ? "tilled" : "untilled";
      const crop = tile.crop;
      let weed = "";
      if (tile.weedy) weed = " A small weed has crept in. The plot is weedy; the crop grows at half speed.";
      else if (tile.weed) weed = " A small weed has crept in.";
      let hold = "";
      if (tile.tilled && (tile.untilled_in != null) && !crop) {
        const n = Number(tile.untilled_in);
        if (n <= 0) hold = " It will go untilled at nightfall if it stays empty.";
        else hold = " " + n + (n === 1 ? " day" : " days") + " left until it reverts if left unwatered.";
      } else if (tile.tilled && (tile.untilled_in != null) && crop && crop.stage === "withered") {
        const n = Number(tile.untilled_in);
        if (n <= 0) hold = " It will go untilled at nightfall if it stays empty.";
        else hold = " " + n + (n === 1 ? " day" : " days") + " left until it reverts if left unwatered.";
      }
      if (!crop) return tileName(r, c) + " — " + tilled + " soil, " + moist + ". Empty." + hold + weed;
      if (crop.stage === "withered") {
        return tileName(r, c) + " — a withered " + crop.kind + ", " + moist + "." + hold + weed;
      }
      if (crop.stage === "dormant") {
        return tileName(r, c) + " — a dormant " + crop.kind + ", resting until spring. It needs no water." + weed;
      }
      const info = (lastData && lastData.crops && lastData.crops[crop.kind]) || {};
      const needed = (crop.harvests && info.regrow_days) ? info.regrow_days : info.grow_days;
      const of = needed ? (" of " + needed) : "";
      let ready = "";
      if (crop.stage === "mature") {
        ready = " Ready to harvest.";
        if (info.regrow_days) {
          ready += " It will fruit again in " + info.regrow_days + " watered day(s) after you pick it.";
        }
      }
      return tileName(r, c) + " — " + crop.kind + ", day " + crop.days_grown + of +
        ", " + crop.stage + ", " + moist + "." + ready + weed;
    }

    function forecastIcon(kind) {
      const c = "#e8d8c0";
      if (kind === "rain") {
        return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M10 14h14a6 6 0 0 0-1-12 8 8 0 0 0-15 3 6 6 0 0 0 2 9z" fill="#9aa6b2"/><path d="M11 20 l2 6 M16 19 l2 7 M21 20 l2 6" stroke="#8eb4c8" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>';
      }
      if (kind === "storm") {
        return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M9 13h15a6 6 0 0 0-1-11 8 8 0 0 0-15 3 6 6 0 0 0 1 8z" fill="#6a7380"/><path d="M16 16 l-3 6 h4 l-3 7" fill="none" stroke="#efe4b8" stroke-width="1.7" stroke-linejoin="round"/><path d="M10 20 l1.5 5 M22 19 l2 6" stroke="#8eb4c8" stroke-width="1.4" fill="none"/></svg>';
      }
      if (kind === "snow") {
        return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 6 v20 M8 10 l16 12 M8 22 l16-12" stroke="#eef2f6" stroke-width="1.6" fill="none" stroke-linecap="round"/><circle cx="16" cy="16" r="2" fill="#eef2f6"/></svg>';
      }
      if (kind === "cloud") {
        return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M10 20h14a6 6 0 0 0-1-11 8 8 0 0 0-15 3 6 6 0 0 0 2 8z" fill="#8a8880"/></svg>';
      }
      return '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="7" fill="#e8b86a"/><path d="M16 4 v4 M16 24 v4 M4 16 h4 M24 16 h4 M7 7 l3 3 M22 22 l3 3 M7 25 l3-3 M22 10 l3-3" stroke="#e8b86a" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>';
    }
    function renderForecast(data) {
      const box = $("forecast");
      if (!box) return;
      const days = data.forecast || [];
      if (!days.length) { box.hidden = true; box.innerHTML = ""; return; }
      box.hidden = false;
      box.innerHTML = days.map(function (item) {
        const word = forecastWord[item.weather] || item.weather;
        return '<div class="forecast-day">' + forecastIcon(item.weather) +
          '<span class="fd">Day ' + item.day + '</span>' +
          '<span class="fw">' + word + '</span></div>';
      }).join("");
    }
    function render(data) {
      lastData = data;
      if (data && data.viewer) PLAYER = data.viewer;
      renderForecast(data);
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
      const placeBits = PLAYERS.map(function (p) {
        const slot = players[p.id] || {};
        const r = parseInt(slot.row, 10);
        const c = parseInt(slot.col, 10);
        const where = (r && c) ? describeWhere(r, c, data) : describeWhere(cabinPos(data).r, cabinPos(data).c, data);
        return displayName(p.id) + " is " + where;
      }).join(", ");
      $("status").innerHTML =
        "<span>Day <b>" + s.day + "</b></span>" +
        "<span><b>" + cap(s.season) + "</b></span>" +
        "<span>" + sky + "</span>" +
        "<span class='gold'><b>" + s.gold + "G</b></span>" +
        "<span class='turn'>Turn: <b>" + displayName(current) + "</b></span>" +
        energyBits +
        "<span>" + escapeHtml(placeBits) + "</span>" +
        "<span class='playing-as'>Playing as " + displayName(PLAYER) +
          (data.your_turn ? "" : " — waiting, it's " + displayName(current) + "'s turn") +
        "</span>";
      const packSlots = (data.pack && data.pack.length) ? data.pack : ((players[PLAYER] || {}).pack || []);
      $("inv").textContent = "Pack: " + slotsPhrase(packSlots) + "  ·  Chest: " + slotsPhrase(s.chest || data.chest || []);
      const endBtn = $("end-turn");
      if (endBtn) {
        endBtn.disabled = !data.your_turn;
        if (!data.your_turn) {
          endBtn.textContent = "Waiting for " + displayName(current);
        } else if (data.in_cabin) {
          endBtn.textContent = "Sleep in the cabin";
        } else {
          endBtn.textContent = "End turn (you'll pass out)";
        }
      }
      const outlookEl = $("sleep-outlook");
      if (outlookEl) {
        outlookEl.textContent = data.your_turn ? (data.sleep_outlook || "") : "";
      }
      const noteBox = $("end-note");
      if (noteBox) {
        noteBox.disabled = !data.your_turn;
        const otherId = PLAYERS.map(function (p) { return p.id; }).filter(function (id) { return id !== PLAYER; })[0];
        noteBox.placeholder = "Note for " + displayName(otherId || "the other player") + " (optional)";
      }
      renderRecentNotes(data);
      if (journalOpen) renderJournal(data);
      $("look").textContent = data.look || "";
      const log = (s.log || []).slice(-8).reverse();
      $("log").innerHTML = log.map(function (e) {
        return "<li>[day " + e.day + "] " + escapeHtml(e.text) + "</li>";
      }).join("");

      const grid = $("grid");
      grid.innerHTML = "";
      const rows = ROWS || 3;
      const cols = COLS || 3;
      const stand = standingFrom(data);
      for (let r = 1; r <= rows; r++) {
        for (let c = 1; c <= cols; c++) {
          const tile = s.tiles[r-1][c-1];
          const key = data.sprites[r-1][c-1];
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "tile" + (tile.type === "cabin" ? " cabin" : "");
          if (selected && selected.r === r && selected.c === c) btn.classList.add("selected");
          if (stand && stand.r === r && stand.c === c) btn.classList.add("here");
          btn.setAttribute("aria-label", tileName(r, c));
          applyTileArt(btn, key);
          const num = document.createElement("div");
          num.className = "keynum";
          num.textContent = String((r - 1) * cols + c);
          const lab = document.createElement("div");
          lab.className = "label";
          lab.textContent = tile.type === "cabin" ? "cabin" : ("r" + r + " c" + c);
          btn.appendChild(num);
          btn.appendChild(lab);
          const here = whoAt(data, r, c);
          if (here.length) {
            const wrap = document.createElement("div");
            wrap.className = "avatars";
            for (let i = 0; i < here.length; i++) {
              const id = here[i];
              const mark = document.createElement("span");
              mark.className = "avatar" + (id === PLAYER ? " you" : "");
              mark.style.background = playerColor(id);
              mark.title = displayName(id);
              mark.setAttribute("aria-label", displayName(id));
              wrap.appendChild(mark);
            }
            btn.appendChild(wrap);
          }
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
      const stand = standingFrom(data);
      const focus = selected || stand;
      if (!focus) {
        $("tile-desc").textContent = "Walk with the arrow keys or 1–9. T, W, P, H, and Q act on the tile you are standing on.";
        return;
      }
      const r = focus.r, c = focus.c;
      const tile = data.state.tiles[r-1][c-1];
      let desc = describeTile(tile, r, c);
      const occupants = whoAt(data, r, c).map(displayName);
      if (occupants.length) desc += " " + occupants.join(" and ") + " standing here.";
      if (stand && stand.r === r && stand.c === c) desc += " You are here.";
      else desc += " You are " + describeWhere(stand.r, stand.c, data) + ".";
      $("tile-desc").textContent = desc;
      if (!data.your_turn) {
        const who = cap(data.current_player || "the other player");
        $("tile-desc").textContent = desc + " It's " + who + "'s turn.";
        return;
      }
      if (stand && (stand.r !== r || stand.c !== c)) {
        const walk = document.createElement("button");
        walk.type = "button";
        walk.className = "btn";
        walk.textContent = "Walk here";
        walk.addEventListener("click", function () { actCmd("move to " + r + " " + c); });
        box.appendChild(walk);
      }
      const workR = stand.r, workC = stand.c;
      const prefix = [
        "till " + workR + " " + workC,
        "water " + workR + " " + workC,
        "harvest " + workR + " " + workC,
        "pluck " + workR + " " + workC
      ];
      const plantPrefix = "plant " + workR + " " + workC + " ";
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
      if (plantPick && plantPick.kinds && plantPick.kinds.length) {
        renderPlantPicker(box, workR, workC, plantPick);
      }
    }

    function stockOf(kind) {
      const info = cropInfo(kind);
      return info.stock || "seed";
    }
    function stockKey(kind) {
      return kind + "_" + stockOf(kind);
    }
    function seedKinds(inv) {
      const order = ["strawberry", "everbearing", "kabocha", "turnip", "carrot"];
      const found = [];
      const seen = {};
      inv = inv || {};
      for (const kind of order) {
        if ((inv[stockKey(kind)] || 0) > 0) {
          found.push(kind);
          seen[kind] = true;
        }
      }
      Object.keys(inv).forEach(function (key) {
        let kind = null;
        if (key.endsWith("_seedling")) kind = key.slice(0, -9);
        else if (key.endsWith("_seed")) kind = key.slice(0, -5);
        if (kind && inv[key] > 0 && !seen[kind]) {
          found.push(kind);
          seen[kind] = true;
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
      if (show) {
        const outlook = data.sleep_outlook || "End your turn?";
        el.textContent = outlook + ". Press E or Enter to confirm, Esc to cancel. A note in the box will be sent too.";
      }
    }

    function noteIdentity(entry) {
      if (!entry) return "";
      return [entry.year || "", entry.season || "", entry.day || "", entry.from || "", entry.text || ""].join("\x1f");
    }
    function journalFrom(data) {
      const s = (data && data.state) || data || {};
      const journal = s.journal || data.journal || {};
      const seasons = journal.seasons || {};
      const year = journal.year || s.year || data.year || 1;
      return {year: year, seasons: seasons};
    }
    function recentNotesFrom(data) {
      const seen = {};
      const out = [];
      function add(entry) {
        if (!entry || !entry.text || !entry.from) return;
        const key = noteIdentity(entry);
        if (seen[key]) return;
        seen[key] = true;
        out.push(entry);
      }
      const listed = (data && data.recent_notes) || [];
      for (let i = 0; i < listed.length; i++) add(listed[i]);
      if (!out.length) {
        const journal = journalFrom(data);
        const pooled = [];
        JOURNAL_SEASONS.forEach(function (season) {
          (journal.seasons[season] || []).forEach(function (entry) { pooled.push(entry); });
        });
        pooled.sort(function (a, b) { return (a.day || 0) - (b.day || 0); });
        for (let i = pooled.length - 1; i >= 0 && out.length < 15; i--) add(pooled[i]);
        const last = ((data && data.state) || {}).last_note || (data && data.last_note);
        if (last && last.text && last.from) add(last);
      }
      return out;
    }
    function formatNoteHtml(entry) {
      const day = entry.day ? "<span class='day'>[day " + escapeHtml(String(entry.day)) + "]</span> " : "";
      return day + "<span class='who'>Note from " + escapeHtml(displayName(entry.from)) + " (player text):</span> " +
        escapeHtml(entry.text);
    }
    function renderRecentNotes(data) {
      const box = $("recent-notes");
      const list = $("recent-notes-list");
      if (!box || !list) return;
      const notes = recentNotesFrom(data);
      if (!notes.length) {
        box.hidden = true;
        list.innerHTML = "";
        return;
      }
      box.hidden = false;
      const seen = {};
      list.innerHTML = notes.map(function (entry) {
        const key = noteIdentity(entry);
        if (seen[key]) return "";
        seen[key] = true;
        return "<li>" + formatNoteHtml(entry) + "</li>";
      }).join("");
    }
    function openJournal() {
      closeShop();
      journalOpen = true;
      const modal = $("journal-modal");
      if (modal) modal.hidden = false;
      if (lastData) {
        const current = ((lastData.state || {}).season) || "spring";
        if (JOURNAL_SEASONS.indexOf(current) !== -1) journalSeason = current;
        renderJournal(lastData);
      } else {
        renderJournal({state: {journal: {year: 1, seasons: {}}, season: "spring"}});
      }
    }
    function closeJournal() {
      journalOpen = false;
      const modal = $("journal-modal");
      if (modal) modal.hidden = true;
    }
    function renderJournal(data) {
      const tabs = $("journal-tabs");
      const body = $("journal-body");
      const title = $("journal-title");
      if (!tabs || !body) return;
      const journal = journalFrom(data);
      if (title) title.textContent = "Journal — Year " + journal.year;
      tabs.innerHTML = "";
      JOURNAL_SEASONS.forEach(function (season) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn";
        btn.textContent = season.charAt(0).toUpperCase() + season.slice(1);
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", season === journalSeason ? "true" : "false");
        btn.addEventListener("click", function () {
          journalSeason = season;
          renderJournal(lastData || data);
        });
        tabs.appendChild(btn);
      });
      const entries = journal.seasons[journalSeason] || [];
      const seen = {};
      const unique = [];
      entries.forEach(function (entry) {
        const key = noteIdentity(entry);
        if (!entry || !entry.text || !entry.from || seen[key]) return;
        seen[key] = true;
        unique.push(entry);
      });
      unique.sort(function (a, b) { return (a.day || 0) - (b.day || 0); });
      if (!unique.length) {
        body.innerHTML = "<p class='journal-empty'>No notes in " + journalSeason + " of year " +
          journal.year + " yet.</p>";
        return;
      }
      body.innerHTML = unique.map(function (entry) {
        return "<div class='journal-entry'>" + formatNoteHtml(entry) + "</div>";
      }).join("");
    }
    function openShop() {
      closeJournal();
      shopOpen = true;
      const modal = $("shop-modal");
      if (modal) modal.hidden = false;
      if (lastData) renderShop(lastData);
    }
    function closeShop() {
      shopOpen = false;
      const modal = $("shop-modal");
      if (modal) modal.hidden = true;
    }

    function seasonLabel(list) {
      return (list || []).join(", ") || "unknown season";
    }

    function shopEmptyMessage(season) {
      const name = cap(season || "this season");
      return "Nothing in season yet. " + name + " seeds arrive in a later update.";
    }

    function appendShopCard(shop, data, kind, info, opts) {
      const inv = data.state.inventory || {};
      const gold = data.state.gold;
      const stock = info.stock || "seed";
      const seeds = inv[kind + "_" + stock] || 0;
      const fruit = inv[kind] || 0;
      const eat = info.eat_energy;
      const title = info.shop_name || info.name || kind;
      const fruitName = fruit === 1 ? (info.name || kind) : (info.name_plural || ((info.name || kind) + "s"));
      const card = document.createElement("div");
      card.className = "shop-card";
      const img = document.createElement("img");
      img.src = "/sprite/" + (info.sprite || (kind + "_mature_dry")) + ".svg";
      img.alt = title;
      card.appendChild(img);
      const body = document.createElement("div");
      let cycle = info.regrow_days
        ? (info.grow_days + " days, then every " + info.regrow_days + " days")
        : (info.grow_days + " days");
      if (info.perennial) {
        if (info.fruiting_after_dormancy === false) {
          cycle += " · perennial, fruits in the planting year, dormant in winter, lives "
            + (info.lifespan_seasons || 8) + " seasons";
          if (info.fruiting_early_autumn_days) {
            cycle += ", through spring and summer into early autumn";
          }
        } else {
          cycle += " · perennial, fruits after first winter, dormant in autumn and winter, lives "
            + (info.lifespan_seasons || 8) + " seasons";
          if (info.fruiting_early_summer_days) {
            cycle += ", through spring into early summer";
          }
        }
      }
      const desc = info.description || "";
      body.innerHTML = "<b>" + escapeHtml(title) + "</b>" +
        (desc ? '<p class="desc">' + escapeHtml(desc) + "</p>" : "") +
        '<div class="meta shop-meta">' + seasonLabel(info.shop_seasons && info.shop_seasons.length ? info.shop_seasons : info.seasons) +
        " · " + cycle +
        " · " + stock + "s " + info.seed_price + "G · sell " + info.sell_price + "G" +
        (eat ? " · eat +" + eat + " energy" : "") +
        " · pack: " + seeds + " " + stock + (seeds === 1 ? "" : "s") +
        ", " + fruit + " " + fruitName +
        "</div>";
      const row = document.createElement("div");
      row.className = "shop-qty";
      if (opts.buy) {
        if (shopQty[kind] == null) shopQty[kind] = 1;
        const minus = document.createElement("button");
        minus.type = "button";
        minus.className = "btn";
        minus.textContent = "−";
        const qty = document.createElement("input");
        qty.type = "number";
        qty.min = "1";
        qty.max = "99";
        qty.value = String(shopQty[kind]);
        qty.setAttribute("aria-label", "Quantity of " + (info.shop_name || info.name || (kind + " seeds")));
        const plus = document.createElement("button");
        plus.type = "button";
        plus.className = "btn";
        plus.textContent = "+";
        function readQty() {
          let n = parseInt(qty.value, 10);
          if (!(n > 0)) n = 1;
          if (n > 99) n = 99;
          shopQty[kind] = n;
          qty.value = String(n);
          return n;
        }
        minus.addEventListener("click", function () { qty.value = String(Math.max(1, readQty() - 1)); readQty(); });
        plus.addEventListener("click", function () { qty.value = String(Math.min(99, readQty() + 1)); readQty(); });
        qty.addEventListener("change", readQty);
        const buy = document.createElement("button");
        buy.type = "button";
        buy.className = "btn primary";
        buy.textContent = "Buy";
        buy.disabled = gold < info.seed_price || !data.your_turn || !data.in_cabin;
        buy.addEventListener("click", function () {
          actCmd("buy " + kind + " " + readQty());
        });
        row.appendChild(minus);
        row.appendChild(qty);
        row.appendChild(plus);
        row.appendChild(buy);
      }
      if (opts.sell) {
        const sell = document.createElement("button");
        sell.type = "button";
        sell.className = "btn";
        sell.textContent = "Sell 1";
        sell.disabled = fruit < 1 || !data.your_turn || !data.in_cabin;
        sell.addEventListener("click", function () { actCmd("sell " + kind + " 1"); });
        row.appendChild(sell);
        if (eat) {
          const eatBtn = document.createElement("button");
          eatBtn.type = "button";
          eatBtn.className = "btn";
          eatBtn.textContent = "Eat (+" + eat + ")";
          eatBtn.disabled = fruit < 1 || !data.your_turn;
          eatBtn.addEventListener("click", function () { actCmd("eat " + kind); });
          row.appendChild(eatBtn);
        }
      }
      body.appendChild(row);
      card.appendChild(body);
      shop.appendChild(card);
    }

    function renderShop(data) {
      const shop = $("shop");
      if (!shop) return;
      shop.innerHTML = "";
      if (!data.in_cabin) {
        const note = document.createElement("p");
        note.className = "shop-empty";
        note.textContent = "Walk to the cabin to buy, sell, craft, or use the chest. Harvested crops have to be carried home in your pack.";
        shop.appendChild(note);
      }
      const crops = data.crops || {};
      const inv = data.state.inventory || {};
      const season = (data.state && data.state.season) || "";
      const forSale = [];
      const sellables = [];
      for (const [kind, info] of Object.entries(crops)) {
        const fruit = inv[kind] || 0;
        const shopSeasons = (info.shop_seasons && info.shop_seasons.length) ? info.shop_seasons : (info.seasons || []);
        const inSeason = info.available !== false && shopSeasons.indexOf(season) !== -1;
        if (inSeason) forSale.push([kind, info]);
        if (fruit > 0) sellables.push([kind, info]);
      }
      if (!forSale.length) {
        const empty = document.createElement("p");
        empty.className = "shop-empty";
        empty.textContent = shopEmptyMessage(season);
        shop.appendChild(empty);
      } else {
        const title = document.createElement("div");
        title.className = "shop-section-title";
        title.textContent = "Seeds in season";
        shop.appendChild(title);
        forSale.forEach(function (pair) {
          appendShopCard(shop, data, pair[0], pair[1], {buy: true, sell: false});
        });
      }
      if (sellables.length) {
        const title = document.createElement("div");
        title.className = "shop-section-title";
        title.textContent = "From the pack";
        shop.appendChild(title);
        sellables.forEach(function (pair) {
          appendShopCard(shop, data, pair[0], pair[1], {buy: false, sell: true});
        });
      }
      if (data.in_cabin && data.your_turn) {
        const chestTitle = document.createElement("div");
        chestTitle.className = "shop-section-title";
        chestTitle.textContent = "Cabin chest";
        shop.appendChild(chestTitle);
        const chest = data.chest || (data.state && data.state.chest) || [];
        if (!chest.length) {
          const empty = document.createElement("p");
          empty.className = "shop-empty";
          empty.textContent = "The chest is empty.";
          shop.appendChild(empty);
        }
        chest.forEach(function (slot) {
          if (!slot || !slot.item) return;
          const row = document.createElement("div");
          row.className = "shop-card";
          const img = document.createElement("img");
          img.src = "/item/" + slot.item + ".svg";
          img.alt = slot.item;
          row.appendChild(img);
          const body = document.createElement("div");
          body.innerHTML = "<b>" + escapeHtml(itemName(slot.item, slot.count || 1)) + "</b>";
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn";
          btn.textContent = "Take";
          btn.addEventListener("click", function () { actCmd("take " + slot.item); });
          body.appendChild(btn);
          row.appendChild(body);
          shop.appendChild(row);
        });
        const pack = data.pack || [];
        const held = pack.filter(function (s) { return s && s.item; });
        if (held.length) {
          const dropTitle = document.createElement("div");
          dropTitle.className = "shop-section-title";
          dropTitle.textContent = "Put in the chest";
          shop.appendChild(dropTitle);
          held.forEach(function (slot) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn";
            btn.textContent = "Drop " + itemName(slot.item, slot.count || 1);
            btn.addEventListener("click", function () { actCmd("drop " + slot.item); });
            shop.appendChild(btn);
          });
        }
        const craftTitle = document.createElement("div");
        craftTitle.className = "shop-section-title";
        craftTitle.textContent = "Kitchen";
        shop.appendChild(craftTitle);
        [["strawberry_jam", "Strawberry jam (3 berries)"],
         ["kabocha_soup", "Kabocha soup (1 kabocha)"],
         ["root_stew", "Root stew (carrot + turnip)"]].forEach(function (pair) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn";
          btn.textContent = "Craft " + pair[1];
          btn.addEventListener("click", function () { actCmd("craft " + pair[0]); });
          shop.appendChild(btn);
        });
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
          credentials: "same-origin",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({command: command})
        });
        if (res.status === 401 || res.status === 403) {
          showAuthNeeded();
          return;
        }
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
        try {
          render(data);
          const cmd = String(command || "").toLowerCase();
          if (cmd.indexOf("move") === 0 || cmd.indexOf("go ") === 0 || cmd === "go") {
            selected = standingFrom(data);
            render(data);
          }
        } catch (err) {
          console.error("Could not draw the farm:", err);
          showLoadError("Could not draw the farm. Check the browser console for details.");
        }
      } catch (err) {
        console.error("Farm action failed:", err);
        showToast("Could not reach the farm server.", false);
      }
    }

    function showAuthNeeded() {
      if (authStopped) return;
      authStopped = true;
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      const el = $("status");
      if (el) {
        el.textContent = AUTH_NEEDED;
        el.className = "status auth-needed";
      }
      showToast(AUTH_NEEDED, false);
    }

    function showLoadError(msg) {
      const el = $("status");
      if (el && (el.textContent || "").indexOf("Loading the farm") === 0) {
        el.textContent = msg;
        el.className = "status load-error";
      }
      showToast(msg, false);
    }

    async function poll() {
      if (authStopped) return;
      try {
        const res = await fetch("/api/state", {cache: "no-store", credentials: "same-origin"});
        if (res.status === 401 || res.status === 403) {
          showAuthNeeded();
          return;
        }
        if (!res.ok) {
          throw new Error("Farm state request failed (" + res.status + ")");
        }
        const data = await res.json();
        const sig = JSON.stringify(data.state);
        if (sig !== lastSig) {
          lastSig = sig;
          try {
            render(data);
          } catch (err) {
            console.error("Could not draw the farm:", err);
            showLoadError("Could not draw the farm. Check the browser console for details.");
            return;
          }
        }
      } catch (err) {
        console.error("Farm poll failed:", err);
        if (!lastData) {
          showLoadError("Could not load the farm. Check the browser console for details.");
        }
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
      const cols = COLS || 3;
      const rows = ROWS || 3;
      if (n < 1 || n > rows * cols) return null;
      return {r: Math.floor((n - 1) / cols) + 1, c: ((n - 1) % cols) + 1};
    }

    function needHere() {
      if (lastData) return true;
      showToast("The farm is still loading.", false);
      return false;
    }

    function needTurn() {
      if (lastData && lastData.your_turn) return true;
      const who = cap((lastData && lastData.current_player) || "the other player");
      showToast("It's " + who + "'s turn.", false);
      return false;
    }

    function keyTill() {
      if (!needTurn() || !needHere()) return;
      actCmd("till");
    }

    function keyWater() {
      if (!needTurn() || !needHere()) return;
      actCmd("water");
    }

    function keyHarvest() {
      if (!needTurn() || !needHere()) return;
      actCmd("harvest");
    }

    function keyPluck() {
      if (!needTurn() || !needHere()) return;
      actCmd("pluck");
    }

    function keyPlant() {
      if (!needTurn() || !needHere()) return;
      const kinds = seedKinds((lastData && lastData.state && lastData.state.inventory) || {});
      if (!kinds.length) {
        plantPick = null;
        render(lastData);
        showToast("No seeds in the pack.", false);
        return;
      }
      if (kinds.length === 1) {
        plantPick = null;
        actCmd("plant " + kinds[0]);
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
      if (!plantPick) return false;
      if (!needTurn()) return true;
      const kind = plantPick.kinds[plantPick.index];
      plantPick = null;
      actCmd("plant " + kind);
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
      const outlook = (lastData && lastData.sleep_outlook) ? lastData.sleep_outlook + ". " : "";
      showToast(outlook + "Press E or Enter to confirm, Esc to cancel.", true);
    }

    function onKey(ev) {
      if (typingInField(ev)) return;
      if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
      const key = ev.key;
      const code = ev.code || "";

      if (key === "Escape") {
        ev.preventDefault();
        if (shopOpen) {
          closeShop();
          return;
        }
        if (journalOpen) {
          closeJournal();
          return;
        }
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

      const arrows = {ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right"};
      if (arrows[key]) {
        ev.preventDefault();
        endConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        actCmd("move " + arrows[key]);
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
        if (!needTurn()) {
          if (lastData) render(lastData);
          return;
        }
        actCmd("move to " + plot.r + " " + plot.c);
        return;
      }

      const letter = (key && key.length === 1) ? key.toLowerCase() : "";
      if (letter === "s") {
        ev.preventDefault();
        openShop();
        return;
      }
      if (letter === "j") {
        ev.preventDefault();
        openJournal();
        return;
      }
      if (shopOpen || journalOpen) return;
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
    const openBtn = $("open-shop");
    if (openBtn) openBtn.addEventListener("click", function () { openShop(); });
    const closeBtn = $("shop-close");
    if (closeBtn) closeBtn.addEventListener("click", function () { closeShop(); });
    const backdrop = $("shop-backdrop");
    if (backdrop) backdrop.addEventListener("click", function () { closeShop(); });
    const openJournalBtn = $("open-journal");
    if (openJournalBtn) openJournalBtn.addEventListener("click", function () { openJournal(); });
    const closeJournalBtn = $("journal-close");
    if (closeJournalBtn) closeJournalBtn.addEventListener("click", function () { closeJournal(); });
    const journalBackdrop = $("journal-backdrop");
    if (journalBackdrop) journalBackdrop.addEventListener("click", function () { closeJournal(); });
    initArtPackControl();
    restoreRecentNotesOpen();
    poll();
    pollTimer = setInterval(poll, 1500);
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



def render_page(viewer: str | None = None) -> str:
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
    web_p = viewer or cfg_web()
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
        "__ROWS__": _json.dumps(ROWS),
        "__COLS__": _json.dumps(COLS),
        "__CABIN__": _json.dumps([CABIN_ROW, CABIN_COL]),
        "__DEFAULT_PLAYER__": _json.dumps(web_p),
        "__CABIN_SHORT__": _json.dumps(flavor("cabin_short") or "the cabin, lantern lit in the window."),
        "__CABIN_BY_WEATHER__": _json.dumps({
            "sun": flavor("cabin_short") or "the cabin, lantern lit in the window.",
            "cloud": flavor("cabin_short_cloud") or "the cabin under a grey sky, lantern lit in the window.",
            "rain": flavor("cabin_short_rain") or "the cabin, rain drumming on the roof.",
            "storm": flavor("cabin_short_storm") or "the cabin, a storm rattling the roof.",
            "snow": flavor("cabin_short_snow") or "the cabin, snow on the roof, flakes in the air.",
        }),
        "__ART_PACKS__": _json.dumps(public_packs()),
    }
    for key, val in replacements.items():
        html = html.replace(key, val)
    return html


def _crop_catalog(crops: dict) -> dict:
    out = {}
    for kind, info in crops.get("crops", {}).items():
        out[kind] = {
            "name": info.get("name") or kind,
            "name_plural": info.get("name_plural") or "",
            "shop_name": info.get("shop_name") or "",
            "stock": info.get("stock") or "seed",
            "seed_price": int(info["seed_price"]),
            "sell_price": int(info["sell_price"]),
            "grow_days": int(info["grow_days"]),
            "regrow_days": int(info.get("regrow_days") or 0),
            "available": info.get("available", True) is not False,
            "seasons": list(info["seasons"]),
            "shop_seasons": list(info.get("shop_seasons") or info.get("seasons") or []),
            "description": info.get("description") or "",
            "sprite": f"{kind}_mature_dry",
            "perennial": bool(info.get("perennial")),
            "lifespan_seasons": int(info.get("lifespan_seasons") or 0),
            "fruiting_after_dormancy": info.get("fruiting_after_dormancy", True) is not False,
            "fruiting_early_summer_days": int(info.get("fruiting_early_summer_days") or 0),
            "fruiting_early_autumn_days": int(info.get("fruiting_early_autumn_days") or 0),
            "eat_energy": info.get("eat_energy", info.get("raw_energy")),
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
    from engine import recent_notes, year_for_day
    current = normalize_player(state.get("current_player")) or starting_player()
    sky = state.get("weather") or "sun"
    sprites = [[sprite_key(tile, sky) for tile in row] for row in state["tiles"]]
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
        "forecast": weather_forecast(state, crops, rules),
        "sleep_outlook": sleep_outlook(state, viewer, rules) if viewer else "",
        "in_cabin": is_player_in_cabin(state, viewer) if viewer else False,
        "cabin": [CABIN_ROW, CABIN_COL],
        "pack": (state.get("players") or {}).get(viewer or "", {}).get("pack") or [],
        "chest": state.get("chest") or [],
        "year": year_for_day(int(state.get("day") or 1), crops),
        "recent_notes": recent_notes(state),
    }


class FarmHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        # Never log query strings or headers: they may contain a player token.
        path = urlparse(self.path).path
        sys.stderr.write("%s - %s %s\n" % (self.address_string(), self.command, path))

    def _send(
        self,
        code: int,
        body,
        content_type: str,
        cache: bool = False,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
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
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _host_forbidden(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower().rstrip(".")
        allowed, _origins = allowed_hosts_and_origins()
        if host and host in allowed:
            return False
        self._send(403, "forbidden\n", "text/plain; charset=utf-8")
        return True

    def _origin_forbidden(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip().rstrip("/").lower()
        if not origin:
            return False
        _hosts, origins = allowed_hosts_and_origins()
        if origin in origins:
            return False
        self._send(403, "forbidden\n", "text/plain; charset=utf-8")
        return True

    def _presented_token(self) -> str:
        params = parse_qs(urlparse(self.path).query)
        keys = params.get("key") or []
        if keys and str(keys[0]).strip():
            return str(keys[0]).strip()
        cookies = _parse_cookies(self.headers.get("Cookie") or "")
        return (cookies.get(COOKIE_NAME) or "").strip()

    def _authorized_player(self) -> str | None:
        return player_for_token(self._presented_token())

    def _token_cookie_header(self, token: str) -> str:
        return (
            f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"
        )

    def _path_without_key(self) -> str:
        parsed = urlparse(self.path)
        pairs: list[tuple[str, str]] = []
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
            if key == "key":
                continue
            for value in values:
                pairs.append((key, value))
        query = urlencode(pairs)
        return parsed.path + (("?" + query) if query else "")

    def _auth_headers(self) -> list[tuple[str, str]]:
        token = self._presented_token()
        if token and player_for_token(token):
            return [("Set-Cookie", self._token_cookie_header(token))]
        return []

    def do_GET(self) -> None:  # noqa: N802
        if self._host_forbidden() or self._origin_forbidden():
            return
        path = unquote(urlparse(self.path).path)
        if path in {"/", "/index.html"}:
            player = self._authorized_player()
            if not player:
                self._send(401, "unauthorized\n", "text/plain; charset=utf-8")
                return
            params = parse_qs(urlparse(self.path).query)
            extra = self._auth_headers()
            if params.get("key"):
                extra = extra + [("Location", self._path_without_key())]
                self._send(302, "ok\n", "text/plain; charset=utf-8", extra_headers=extra)
                return
            self._send(
                200,
                render_page(viewer=player),
                "text/html; charset=utf-8",
                extra_headers=extra,
            )
            return
        if path == "/api/state":
            player = self._authorized_player()
            if not player:
                self._send(401, "unauthorized\n", "text/plain; charset=utf-8")
                return
            with session(write=False) as (state, crops):
                payload = api_payload(state, crops, player=player)
            self._send(
                200,
                json.dumps(payload),
                "application/json; charset=utf-8",
                extra_headers=self._auth_headers(),
            )
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
        if path.startswith("/item/") and path.endswith(".svg"):
            key = path[len("/item/") : -len(".svg")]
            if not is_safe_key(key):
                self._send(400, "bad item key\n", "text/plain; charset=utf-8")
                return
            self._send(200, svg_for_item(key), "image/svg+xml; charset=utf-8", cache=True)
            return
        if path.startswith("/static/packs/"):
            found = safe_pack_file(path)
            if found is None:
                self._send(404, "not found\n", "text/plain; charset=utf-8")
                return
            try:
                body = found.read_bytes()
            except OSError:
                self._send(404, "not found\n", "text/plain; charset=utf-8")
                return
            self._send(200, body, content_type_for(found), cache=True)
            return
        self._send(404, "not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self._host_forbidden() or self._origin_forbidden():
            return
        path = unquote(urlparse(self.path).path)
        if path != "/api/do":
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._send(415, "unsupported media type\n", "text/plain; charset=utf-8")
            return
        player = self._authorized_player()
        if not player:
            self._send(401, "unauthorized\n", "text/plain; charset=utf-8")
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
        # Player comes from the token, never from the body.
        command = str(data.get("command") or data.get("action") or "")
        with session(write=True) as (state, crops):
            ok, message = do_action(state, crops, command, player=player)
            if ok:
                maybe_notify_after_end_turn(player, state, ok)
            payload = api_payload(state, crops, ok, message, player=player)
        self._send(
            200,
            json.dumps(payload),
            "application/json; charset=utf-8",
            extra_headers=self._auth_headers(),
        )


class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def try_bind(host: str, port: int) -> ReusableServer | None:
    try:
        server = ReusableServer((host, port), FarmHandler)
    except OSError as exc:
        sys.stderr.write(f"Could not bind {host}:{port} — {exc}\n")
        return None
    try:
        bound = int(server.server_address[1])
    except (TypeError, ValueError, IndexError):
        bound = port
    _register_listen_port(bound)
    return server


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

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
    format_legal_action,
    load_crops,
    load_rules,
    load_state,
    max_energy,
    player_energy_cap,
    stove_is_fueled,
    migrate_state,
    normalize_player,
    session,
    sleep_outlook,
    viewer_status_banner,
    energy_cost,
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
  <meta http-equiv="Cache-Control" content="no-store">
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
      align-items: center;
      justify-content: space-between;
    }
    .header-right {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.45rem 0.8rem;
    }
    .settings-form {
      display: grid;
      gap: 0.8rem;
      margin: 0.5rem 0 0;
      color: var(--ink);
      line-height: 1.45;
    }
    .settings-form fieldset {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.7rem 0.85rem 0.85rem;
    }
    .settings-form fieldset:disabled { opacity: 0.55; }
    .settings-form legend { color: var(--gold); padding: 0 0.3rem; }
    .settings-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      margin: 0.45rem 0 0;
    }
    .settings-row input[type="number"] {
      width: 5.2rem;
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
    .settings-help, .settings-status { color: var(--muted); margin: 0; }
    .away-banner {
      margin: 0 0 0.7rem;
      padding: 0.7rem 0.8rem;
      border: 1px solid var(--gold);
      border-radius: 12px;
      color: var(--ink);
      line-height: 1.45;
    }
    .away-banner[hidden] { display: none !important; }
    .away-banner h3 { margin: 0 0 0.35rem; color: var(--gold); font-size: 1rem; }
    .away-banner p { margin: 0 0 0.5rem; }
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
    .status .stat.energy.over-max b { color: var(--gold2); }
    .gold { color: var(--gold); }
    .turn { color: var(--gold2); }
    .ended, .ready { opacity: 0.85; font-size: 0.95em; }
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
    .area-head {
      flex: 0 0 auto;
      font-weight: 600;
      letter-spacing: 0.04em;
      color: var(--gold2);
      padding: 0 0.2rem 0.25rem;
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
    button.tile .ground-badge {
      position: absolute;
      left: 0.28rem;
      right: 0.28rem;
      bottom: 1.45rem;
      z-index: 2;
      background: rgba(20, 12, 8, 0.78);
      color: #f0e2c8;
      font-size: 0.62rem;
      line-height: 1.2;
      padding: 0.12rem 0.28rem;
      border-radius: 6px;
      pointer-events: none;
      letter-spacing: 0.01em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tile-ground {
      margin: 0.15rem 0 0.85rem;
    }
    .tile-ground h3 {
      margin: 0 0 0.3rem;
      font-size: 0.95rem;
      color: var(--gold);
      font-weight: 600;
    }
    .tile-ground ul {
      margin: 0;
      padding-left: 1.15rem;
    }
    .tile-ground li {
      margin: 0.12rem 0;
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
    .status .stat {
      white-space: nowrap;
    }
    .status .stat-icon,
    .status .stat svg {
      width: 1.05em;
      height: 1.05em;
      vertical-align: -0.18em;
      margin-right: 0.2em;
      display: inline-block;
    }
    .overview-desc {
      overflow-wrap: anywhere;
      word-break: break-word;
      max-width: 100%;
      line-height: 1.45;
    }
    .actions, .shop-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }
    /* This-tile actions stack above Legal Actions; do not wrap "Walk here"
       out beside the collapsible heading. */
    #tile-actions {
      flex-direction: column;
      flex-wrap: nowrap;
      align-items: stretch;
    }
    .tile-walk {
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
    .recipe-book {
      margin: 0 0 0.9rem;
      border-top: 1px solid var(--line);
      padding-top: 0.55rem;
    }
    .recipe-book-head {
      cursor: pointer;
      color: var(--gold);
      letter-spacing: 0.06em;
      text-transform: uppercase;
      font-size: 0.92rem;
      font-weight: inherit;
      font-family: "Iowan Old Style", Palatino, "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }
    .recipe-entry {
      margin: 0.55rem 0 0;
      padding: 0.45rem 0 0.5rem;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      line-height: 1.45;
    }
    .recipe-entry:last-child { border-bottom: 0; }
    .recipe-entry b { color: var(--ink); }
    .recipe-entry .recipe-meta { font-size: 0.9rem; }
    .recipe-book .btn { margin-top: 0.4rem; }
    .recipe-entry-head {
      display: flex;
      align-items: center;
      gap: 0.55rem;
    }
    .recipe-entry-head img,
    .kitchen-craft img {
      width: 40px;
      height: 40px;
      object-fit: contain;
      border-radius: 8px;
      background: var(--soil);
      border: 1px solid var(--line);
      flex: 0 0 auto;
    }
    .kitchen-craft {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin: 0.35rem 0;
    }
    .inv-panel .shop-section-title { margin-top: 0; }
    .inv-panel .shop-card {
      grid-template-columns: 56px 1fr;
      padding: 0.55rem 0;
    }
    .inv-panel .shop-card img {
      width: 56px;
      height: 56px;
      border-radius: 10px;
    }
    .inv-slots {
      color: var(--muted);
      font-size: 0.88rem;
      margin: 0 0 0.35rem;
      line-height: 1.4;
    }
    .shop-card .item-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-top: 0.85rem;
      padding-top: 0.15rem;
    }
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
    .debug-console {
      margin: 0.55rem 0 0;
    }
    .debug-console-label {
      display: block;
      font-size: 0.78rem;
      color: var(--muted);
      margin: 0 0 0.25rem;
    }
    .debug-console-row {
      display: flex;
      gap: 0.35rem;
      align-items: center;
    }
    .debug-console-row input {
      flex: 1;
      min-width: 0;
    }
    .debug-console-status {
      margin: 0.25rem 0 0;
      font-size: 0.78rem;
      color: var(--muted);
      min-height: 1.1em;
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
    button.shop-section-title.chest-toggle,
    button.recipe-book-head.chest-toggle {
      /* Reset button chrome only. Do not use font/letter-spacing/text-transform:
         inherit — those would take the parent panel's styles and undo the heading. */
      cursor: pointer;
      background: none;
      border: 0;
      padding: 0;
      display: flex;
      align-items: center;
      gap: 0.3rem;
      width: 100%;
      text-align: left;
    }
    button.recipe-book-head.chest-toggle {
      color: var(--gold);
      letter-spacing: 0.06em;
      text-transform: uppercase;
      font-size: 0.92rem;
      font-weight: inherit;
      font-family: "Iowan Old Style", Palatino, "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }
    button.chest-toggle::before { content: "▾"; font-size: 0.85em; }
    .chest-section.is-collapsed button.chest-toggle::before { content: "▸"; }
    /* .actions sets display:flex, which would otherwise override [hidden]. */
    .chest-section.is-collapsed > .chest-section-body,
    .chest-section-body[hidden] {
      display: none !important;
    }
    .chest-dialog {
      width: min(56rem, 100%);
    }
    .chest-dialog .chest-band {
      height: 8px;
      border-radius: 8px;
      margin: 0 0 0.7rem;
    }
    .chest-grid {
      display: grid;
      gap: 0.35rem;
      margin: 0.4rem 0 0.9rem;
    }
    .chest-cell, .pack-cell {
      min-height: 4.4rem;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #20160f;
      padding: 0.25rem 0.3rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      font-size: 0.78rem;
      color: var(--ink);
      user-select: none;
      touch-action: none;
    }
    .chest-cell img, .pack-cell img {
      width: 36px;
      height: 36px;
      object-fit: contain;
      pointer-events: none;
    }
    .chest-cell.is-empty, .pack-cell.is-empty { opacity: 0.55; }
    .chest-cell.is-overflow { border-style: dashed; }
    .chest-cell.is-dragging, .pack-cell.is-dragging { opacity: 0.4; }
    .chest-cell.is-target, .pack-cell.is-target { border-color: var(--gold); }
    .chest-cell.is-selected, .pack-cell.is-selected { outline: 2px solid var(--gold); }
    .chest-cell[data-item], .pack-cell[data-item] { cursor: grab; }
    .chest-title-row {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      min-width: 0;
    }
    .chest-title-icon {
      width: 52px;
      height: 52px;
      object-fit: contain;
      flex: 0 0 auto;
    }
    .chest-drag-ghost {
      position: fixed;
      left: 0;
      top: 0;
      z-index: 80;
      pointer-events: none;
      width: 3.6rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      filter: drop-shadow(0 2px 6px rgba(0,0,0,0.45));
    }
    .chest-drag-ghost img {
      width: 2.6rem;
      height: 2.6rem;
      object-fit: contain;
    }
    .chest-drag-ghost .chest-drag-badge {
      margin-top: -0.35rem;
      background: #2a1c12;
      border: 1px solid var(--gold);
      border-radius: 999px;
      font-size: 0.72rem;
      padding: 0 0.38rem;
      color: var(--ink);
      line-height: 1.3;
    }
    .chest-item-menu {
      position: fixed;
      z-index: 70;
      background: #2a1c12;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0.35rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      min-width: 8.5rem;
    }
    .chest-item-menu button {
      font: inherit;
      color: var(--ink);
      background: #3a2a1c;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0.35rem 0.55rem;
      cursor: pointer;
      text-align: left;
    }
    .chest-meta, .chest-help { color: var(--muted); font-size: 0.9rem; margin: 0 0 0.5rem; line-height: 1.4; }
    .chest-card { touch-action: none; user-select: none; -webkit-user-select: none; }
    .chest-card.is-dragging { opacity: 0.55; }
    .chest-card[data-item] { cursor: grab; }
    .chest-card.is-dragging { cursor: grabbing; }
    .save-card {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.7rem 0.8rem;
      margin: 0.55rem 0;
    }
    .save-card.active { border-color: var(--gold); }
    .save-card .save-name { font-weight: 700; color: var(--ink); }
    .save-card .save-meta { color: var(--muted); font-size: 0.9rem; margin: 0.2rem 0 0.5rem; }
    .save-card .save-actions { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .save-new {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
      margin: 0.8rem 0 0.3rem;
      align-items: center;
    }
    .save-new input[type="text"] {
      flex: 1 1 12rem;
      min-width: 8rem;
    }
    .save-confirm {
      margin: 0.7rem 0;
      padding: 0.7rem 0.8rem;
      border: 1px solid var(--gold);
      border-radius: 12px;
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
    <div class="header-right">
      <div class="status" id="status">Loading the farm…</div>
      <button class="btn" id="open-settings" type="button">Settings</button>
    </div>
  </header>
  <main>
    <section class="farm">
      <div class="area-head" id="area-head">The farm</div>
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
        &middot; <kbd>U</kbd> unearth
        &middot; <kbd>F</kbd> fertilize
        &middot; <kbd>C</kbd> chop
        &middot; <kbd>G</kbd> forage
        &middot; <kbd>S</kbd> shop
        &middot; <kbd>J</kbd> journal
        &middot; <kbd>E</kbd> enter or interact (cabin, mine)
        &middot; <kbd>Shift</kbd>+<kbd>E</kbd> then <kbd>Enter</kbd> ends the turn
        &middot; <kbd>Enter</kbd> in the note box ends the turn (a note is sent too)
        &middot; <kbd>Esc</kbd> closes the shop, journal, saves, chest, or settings, or cancels unearth
      </p>
    </section>
    <aside class="panel">
      <div class="toast" id="toast"></div>
      <div id="away-summary" class="away-banner" hidden></div>
      <div class="inv" id="inv"></div>
      <div class="shop-launch">
        <button class="btn primary" id="open-shop" type="button" hidden>Shop <kbd>S</kbd></button>
        <button class="btn" id="open-chest" type="button" hidden>Chest</button>
        <button class="btn" id="open-journal" type="button">Journal <kbd>J</kbd></button>
        <button class="btn" id="open-saves" type="button">Saves</button>
        <label class="art-pack-wrap">Art
          <select id="art-pack" aria-label="Art pack"></select>
        </label>
      </div>
      <details class="recipe-book" id="recipe-book">
        <summary class="recipe-book-head">Recipe book</summary>
        <div id="recipe-book-body"></div>
      </details>
      <h2>Overview</h2>
      <p id="overview-desc" class="overview-desc">Looking around…</p>
      <h2>This tile</h2>
      <p id="tile-desc">Walk with the arrow keys or 1–9. T, W, P, H, and Q act on the tile you are standing on.</p>
      <div id="tile-ground" class="tile-ground" hidden>
        <h3>On the ground</h3>
        <ul id="tile-ground-list"></ul>
      </div>
      <div class="actions" id="tile-actions"></div>
      <div class="end-row">
        <button class="btn primary sleep" id="end-turn" type="button">End turn</button>
        <button class="btn" id="pass-turn" type="button">Pass turn</button>
        <button class="btn" id="walk-home" type="button" hidden>Walk them home</button>
        <input id="end-note" type="text" maxlength="280" placeholder="__NOTE_PLACEHOLDER__" autocomplete="off" spellcheck="true">
      </div>
      <div class="sleep-outlook" id="sleep-outlook"></div>
      <div class="confirm-end" id="end-confirm" hidden>End your turn? Press <kbd>Shift</kbd>+<kbd>E</kbd> then <kbd>Enter</kbd>, or press <kbd>Enter</kbd> in the note box. <kbd>Esc</kbd> cancels. A note in the box will be sent too.</div>
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
      <form class="debug-console" id="debug-console" autocomplete="off">
        <label class="debug-console-label" for="debug-cmd">Command</label>
        <div class="debug-console-row">
          <input id="debug-cmd" type="text" list="debug-cmd-list" spellcheck="false" autocomplete="off" placeholder="Type a legal action">
          <datalist id="debug-cmd-list"></datalist>
          <button type="submit" class="btn" id="debug-cmd-send">Send</button>
        </div>
        <p class="debug-console-status" id="debug-cmd-status"></p>
      </form>
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
  <div id="saves-modal" class="shop-modal" hidden>
    <div class="shop-backdrop" id="saves-backdrop"></div>
    <div class="shop-dialog" role="dialog" aria-modal="true" aria-labelledby="saves-title">
      <div class="shop-head">
        <h2 id="saves-title">Saved farms</h2>
        <button type="button" class="btn" id="saves-close">Close</button>
      </div>
      <p class="shop-empty" id="saves-intro">Both players share the active farm. Switching saves the current one first and never overwrites another slot.</p>
      <div id="saves-confirm" class="save-confirm" hidden></div>
      <div id="saves-body" class="shop-body"></div>
      <div class="save-new">
        <input id="saves-new-name" type="text" maxlength="80" placeholder="Name a new farm" autocomplete="off">
        <button type="button" class="btn primary" id="saves-new">Start a new farm</button>
      </div>
    </div>
  </div>
  <div id="chest-modal" class="shop-modal" hidden>
    <div class="shop-backdrop" id="chest-backdrop"></div>
    <div class="shop-dialog chest-dialog" role="dialog" aria-modal="true" aria-labelledby="chest-title">
      <div class="shop-head">
        <div class="chest-title-row">
          <img id="chest-title-icon" class="chest-title-icon" alt="" hidden>
          <h2 id="chest-title">Chest</h2>
        </div>
        <button type="button" class="btn" id="chest-close">Close</button>
      </div>
      <div class="chest-band" id="chest-band" hidden></div>
      <p class="chest-meta" id="chest-meta"></p>
      <div id="chest-toolbar"></div>
      <div id="chest-grid" class="chest-grid"></div>
      <h3 class="shop-section-title">Backpack</h3>
      <div id="chest-pack-grid" class="chest-grid"></div>
      <p class="chest-help" id="chest-help">Click an item for Take or Put (1 or the stack). Drag moves a full stack for the destination — up to 8 in the backpack, 16 in the chest. Leftovers stay where they were.</p>
    </div>
  </div>
  <div id="settings-modal" class="shop-modal" hidden>
    <div class="shop-backdrop" id="settings-backdrop"></div>
    <div class="shop-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div class="shop-head">
        <h2 id="settings-title">Settings</h2>
        <button type="button" class="btn" id="settings-close">Close</button>
      </div>
      <form class="settings-form" id="settings-form">
        <label>
          <input type="checkbox" id="settings-autopass" name="autopass">
          Taking a break from farming
        </label>
        <p class="settings-help">When this is on and your turn sits idle, the farm ends the day for you and passes the turn. No other action is taken on your behalf. After the maximum, it waits for you. Doing anything on the farm turns this off and counts as being back.</p>
        <fieldset id="settings-autopass-options">
          <legend>Autopass</legend>
          <div class="settings-row">
            <label for="settings-autopass-max">Maximum turns autopassed</label>
            <input type="number" id="settings-autopass-max" min="1" max="30" step="1" value="3">
          </div>
          <div class="settings-row">
            <label for="settings-autopass-timeout">Time until autopass</label>
            <span><input type="number" id="settings-autopass-timeout" min="1" max="1440" step="1" value="30"> minutes</span>
          </div>
          <p class="settings-status" id="settings-autopass-status"></p>
        </fieldset>
      </form>
    </div>
  </div>
  <script>
    const weatherWord = {sun: "clear and sunny", cloud: "overcast", rain: "rain", storm: "a storm", snow: "snow (soil stays wet, but crops don't grow today)"};
    const forecastWord = {sun: "clear", cloud: "overcast", rain: "rain", storm: "storm", snow: "snow (soil stays wet, but crops don't grow)"};
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
    let unearthConfirm = false;
    let shopOpen = false;
    let journalOpen = false;
    let savesOpen = false;
    let settingsOpen = false;
    let chestOpen = false;
    let chestBusy = false;
    let savesSwitch = null;
    let savesRenameId = null;
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
    function itemIconSrc(item, fallback) {
      const pack = packById(artPackId);
      let key = String(item || "");
      const src = lastData || {};
      const tier = src.tool_tiers && src.tool_tiers[key];
      if (tier && tier !== "basic") {
        const tierKey = key + "_" + tier;
        if (pack && pack.items && pack.items[tierKey]) key = tierKey;
        else if (!pack || pack.id === "classic") key = tierKey;
      }
      const rel = pack && pack.items && pack.items[key];
      if (rel && typeof rel === "string" && /^[a-z0-9_./-]+$/i.test(rel) && rel.indexOf("..") < 0) {
        return "/static/packs/" + pack.id + "/" + rel;
      }
      return fallback || ("/item/" + key + ".svg");
    }
    function parseMineSpriteKey(key) {
      key = String(key || "").trim().toLowerCase();
      let rock = null, ladder = false, shaft = false, lantern = false, elevator = false, ladderUp = false;
      let slime = null, drop = null;
      const dropAt = key.lastIndexOf("_drop_");
      if (dropAt !== -1) {
        drop = key.slice(dropAt + 6) || null;
        key = key.slice(0, dropAt);
      }
      const slimeAt = key.lastIndexOf("_slime_");
      if (slimeAt !== -1) {
        slime = key.slice(slimeAt + 7) || "grey";
        key = key.slice(0, slimeAt);
      }
      const ores = [["copper", "_rock_copper"], ["iron", "_rock_iron"], ["gold", "_rock_gold"], ["runestone", "_rock_runestone"]];
      for (let i = 0; i < ores.length; i++) {
        const suffix = ores[i][1];
        if (key.length >= suffix.length && key.slice(-suffix.length) === suffix) {
          rock = ores[i][0] + "_ore";
          key = key.slice(0, -suffix.length);
          break;
        }
      }
      if (key.length >= 5 && key.slice(-5) === "_rock") {
        rock = "stone";
        key = key.slice(0, -5);
      }
      if (key.length >= 9 && key.slice(-9) === "_elevator") {
        elevator = true;
        key = key.slice(0, -9);
      }
      if (key.length >= 8 && key.slice(-8) === "_lantern") {
        lantern = true;
        key = key.slice(0, -8);
      }
      if (key.length >= 6 && key.slice(-6) === "_shaft") {
        shaft = true;
        key = key.slice(0, -6);
      }
      if (key.length >= 10 && key.slice(-10) === "_ladder_up") {
        ladderUp = true;
        key = key.slice(0, -10);
      }
      if (key.length >= 7 && key.slice(-7) === "_ladder") {
        ladder = true;
        key = key.slice(0, -7);
      }
      if (key !== "mine_floor" && key !== "mine_safe") return null;
      return {
        kind: key,
        type: key,
        rock: rock,
        ladder: ladder ? "open" : null,
        ladder_up: ladderUp,
        exit: shaft || ladderUp,
        shaft: shaft,
        lantern: lantern,
        elevator: elevator,
        slime: slime,
        drop: drop,
        mine: true
      };
    }
    function parseHillsSpriteKey(key) {
      key = String(key || "").trim().toLowerCase();
      let forage = null, tree = null, snow = false;
      const forageKinds = ["oyster_mushroom", "wild_onion", "wild_berry", "wild_mushroom"];
      for (let i = 0; i < forageKinds.length; i++) {
        const suffix = "_forage_" + forageKinds[i];
        if (key.length >= suffix.length && key.slice(-suffix.length) === suffix) {
          forage = forageKinds[i];
          key = key.slice(0, -suffix.length);
          break;
        }
      }
      const treeStages = ["mushroom_log", "sapling", "young", "grown", "stump"];
      for (let i = 0; i < treeStages.length; i++) {
        const suffix = "_tree_" + treeStages[i];
        if (key.length >= suffix.length && key.slice(-suffix.length) === suffix) {
          tree = treeStages[i];
          key = key.slice(0, -suffix.length);
          break;
        }
      }
      if (key.length >= 5 && key.slice(-5) === "_snow") {
        snow = true;
        key = key.slice(0, -5);
      }
      const grounds = {
        hills_grass: "grass",
        hillside: "hillside",
        mine_entrance_closed: "mine_entrance",
        mine_entrance: "mine_entrance"
      };
      if (!grounds[key]) return null;
      return {
        kind: grounds[key],
        type: grounds[key],
        closed: grounds[key] === "mine_entrance",
        tree: tree,
        forage: forage,
        snow: snow,
        hills: true
      };
    }
    function parseTownSpriteKey(key) {
      key = String(key || "").trim().toLowerCase();
      let snow = false;
      if (key.length >= 5 && key.slice(-5) === "_snow") {
        snow = true;
        key = key.slice(0, -5);
      }
      const tiles = {town_grass: "grass", town_stall: "stall", town_store: "store", town_forge: "forge"};
      if (!tiles[key]) return null;
      return {kind: "town", tile: tiles[key], type: key, snow: snow, town: true};
    }
    function parseSpriteKey(key) {
      key = String(key || "").trim().toLowerCase();
      const mineParsed = parseMineSpriteKey(key);
      if (mineParsed) return mineParsed;
      const townParsed = parseTownSpriteKey(key);
      if (townParsed) return townParsed;
      const hillsParsed = parseHillsSpriteKey(key);
      if (hillsParsed) return hillsParsed;
      if (key.indexOf("cabin_interior_") === 0) {
        let rest = key.slice("cabin_interior_".length);
        let fire = false;
        if (rest.length > 4 && rest.slice(-4) === "_lit") {
          fire = true;
          rest = rest.slice(0, -4);
        }
        let tier = "";
        const tierMatch = /^chest_(copper|iron|gold)$/.exec(rest);
        if (tierMatch) {
          tier = tierMatch[1];
          rest = "chest";
        }
        const tiles = {floor: 1, bed: 1, chest: 1, fireplace: 1, door: 1, kitchen: 1};
        if (tiles[rest]) return {kind: "cabin_interior", tile: rest, fire: fire, tier: tier};
      }
      if (key === "cabin" || key.indexOf("cabin_") === 0) {
        let weather = "sun";
        let fire = false;
        let tail = (key.indexOf("cabin_") === 0 && key.length > 6) ? key.slice(6) : "";
        const parts = tail.split("_").filter(Boolean);
        if (parts.length && parts[parts.length - 1] === "fire") {
          fire = true;
          parts.pop();
        }
        if (parts.length && (parts[0] === "rain" || parts[0] === "snow" || parts[0] === "storm" || parts[0] === "cloud" || parts[0] === "sun")) {
          weather = parts[0];
        }
        return {kind: "cabin", weather: weather, fire: fire};
      }
      let weedy = false, weed = false, snow = false, fertilizer = null, vine = null;
      const vineOut = [];
      const vineDirs = ["northwest","northeast","southwest","southeast","north","south","east","west"];
      let stripped = true;
      while (stripped) {
        stripped = false;
        for (let i = 0; i < vineDirs.length; i++) {
          const suffix = "_vine_out_" + vineDirs[i];
          if (key.length >= suffix.length && key.slice(-suffix.length) === suffix) {
            vineOut.push(vineDirs[i]);
            key = key.slice(0, -suffix.length);
            stripped = true;
            break;
          }
        }
      }
      for (let i = 0; i < vineDirs.length; i++) {
        const suffix = "_vine_" + vineDirs[i];
        if (key.length >= suffix.length && key.slice(-suffix.length) === suffix) {
          vine = vineDirs[i];
          key = key.slice(0, -suffix.length);
          break;
        }
      }
      const fertKinds = ["general", "yield", "growth"];
      for (let i = 0; i < fertKinds.length; i++) {
        const suffix = "_fert_" + fertKinds[i];
        if (key.length >= suffix.length && key.slice(-suffix.length) === suffix) {
          fertilizer = fertKinds[i];
          key = key.slice(0, -suffix.length);
          break;
        }
      }
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
        const out = {kind: "soil", weed: weed, weedy: weedy, snow: snow, fertilizer: fertilizer, vine: vine, vineOut: vineOut};
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
          snow: snow,
          fertilizer: fertilizer,
          vine: vine,
          vineOut: vineOut
        };
      }
      if (weed || weedy) return {kind: "unknown", raw: key, weed: weed, weedy: weedy, snow: snow, fertilizer: fertilizer, vine: vine, vineOut: vineOut};
      return {kind: "unknown", raw: key, snow: snow, fertilizer: fertilizer, vine: vine, vineOut: vineOut};
    }
    function groundKeyFor(parsed) {
      if (!parsed || parsed.kind === "cabin" || parsed.kind === "unknown") return null;
      if (parsed.kind === "cabin_interior") return "cabin_floor";
      if (parsed.town || parsed.kind === "town") {
        return parsed.snow ? "town_grass_snow" : "town_grass";
      }
      if (parsed.mine || parsed.kind === "mine_floor" || parsed.kind === "mine_safe" || parsed.type === "mine_floor" || parsed.type === "mine_safe") {
        return parsed.type || parsed.kind;
      }
      if (parsed.hills) {
        let base;
        if (parsed.type === "mine_entrance" || parsed.kind === "mine_entrance") {
          base = parsed.closed ? "mine_entrance_closed" : "mine_entrance";
        }
        else if (parsed.type === "hillside" || parsed.kind === "hillside") base = "hillside";
        else base = "hills_grass";
        if (parsed.snow) return base + "_snow";
        return base;
      }
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
        const layers = ["/static/packs/" + pack.id + "/" + file];
        if (parsed.fire) {
          const smoke = pack.overlays && pack.overlays.cabin_smoke;
          if (smoke) layers.push("/static/packs/" + pack.id + "/" + smoke);
        }
        return layers;
      }
      if (!pack.grounds) return null;
      const layers = [];
      const gkey = groundKeyFor(parsed);
      let ground = gkey && pack.grounds[gkey];
      if (!ground && gkey && gkey.slice(-5) === "_snow") ground = pack.grounds[gkey.slice(0, -5)];
      if (!ground) return null;
      layers.push("/static/packs/" + pack.id + "/" + ground);
      if (parsed.kind === "cabin_interior") {
        const tile = parsed.tile || "floor";
        if (tile !== "floor") {
          const ov = pack.overlays || {};
          const name = (parsed.fire && (tile === "fireplace" || tile === "kitchen"))
            ? ("cabin_" + tile + "_lit")
            : ("cabin_" + tile);
          const tierName = (tile === "chest" && parsed.tier) ? ("cabin_chest_" + parsed.tier) : "";
          const f = (tierName && ov[tierName]) || ov[name];
          if (!f) return null;
          layers.push("/static/packs/" + pack.id + "/" + f);
        }
        return layers;
      }
      if (parsed.town || parsed.kind === "town") {
        const ov = pack.overlays || {};
        const tile = parsed.tile || "grass";
        if (tile !== "grass") {
          const name = "town_" + tile + (parsed.snow ? "_snow" : "");
          const f = ov[name] || ov["town_" + tile];
          if (!f) return null;
          layers.push("/static/packs/" + pack.id + "/" + f);
        }
        return layers;
      }
      if (parsed.mine || parsed.kind === "mine_floor" || parsed.kind === "mine_safe") {
        const ov = pack.overlays || {};
        function addOverlay(name) {
          const f = ov[name];
          if (!f) return false;
          layers.push("/static/packs/" + pack.id + "/" + f);
          return true;
        }
        if (parsed.rock) {
          let rkey = "mine_rock";
          if (parsed.rock === "copper_ore") rkey = "mine_rock_copper";
          else if (parsed.rock === "iron_ore") rkey = "mine_rock_iron";
          else if (parsed.rock === "gold_ore") rkey = "mine_rock_gold";
          else if (parsed.rock === "runestone_ore") rkey = "mine_rock_runestone";
          if (!addOverlay(rkey)) return null;
        } else {
          if (parsed.ladder === "open" && !addOverlay("mine_ladder")) return null;
          if (parsed.ladder_up) {
            if (!addOverlay("mine_ladder_up")) return null;
          } else if (parsed.exit || parsed.shaft) {
            if (!addOverlay("mine_shaft")) return null;
          }
          if (parsed.lantern && !addOverlay("mine_lantern")) return null;
          if (parsed.elevator && !addOverlay("mine_elevator")) return null;
        }
        if (parsed.drop && !addOverlay("mine_drop_" + parsed.drop)) return null;
        if (parsed.slime && !addOverlay("mine_slime_" + (parsed.slime || "grey"))) return null;
        return layers;
      }
      if (parsed.fertilizer) {
        const fkey = "fertilizer_" + parsed.fertilizer;
        const fert = pack.overlays && pack.overlays[fkey];
        if (fert) layers.push("/static/packs/" + pack.id + "/" + fert);
      }
      if (parsed.hills) {
        if (parsed.tree) {
          const snowName = parsed.snow ? ("tree_" + parsed.tree + "_snow") : null;
          const tfile = (snowName && pack.overlays && pack.overlays[snowName])
            || (pack.overlays && pack.overlays["tree_" + parsed.tree]);
          if (!tfile) return null;
          layers.push("/static/packs/" + pack.id + "/" + tfile);
        }
        if (parsed.forage) {
          const ffile = pack.overlays && pack.overlays["forage_" + parsed.forage];
          if (!ffile) return null;
          layers.push("/static/packs/" + pack.id + "/" + ffile);
        }
        return layers;
      }
      if (parsed.vine) {
        const vfile = pack.overlays && pack.overlays["vine_" + parsed.vine];
        if (vfile) layers.push("/static/packs/" + pack.id + "/" + vfile);
      }
      const vineOuts = parsed.vineOut || [];
      for (let i = 0; i < vineOuts.length; i++) {
        const vfile = pack.overlays && pack.overlays["vine_out_" + vineOuts[i]];
        if (vfile) layers.push("/static/packs/" + pack.id + "/" + vfile);
      }
      if (parsed.kind && parsed.kind !== "soil" && parsed.stage) {
        const overlays = pack.overlays || {};
        let crop = overlays[parsed.kind + "_" + parsed.stage];
        if (!crop && parsed.stage === "frost_bitten") {
          crop = overlays[parsed.kind + "_withered"] || overlays[parsed.kind + "_mature"];
        }
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
    function viewArea(data) {
      return (data && data.view_area) || "farm";
    }
    function playerArea(slot) {
      return (slot && slot.area) || "farm";
    }
    function describeWhere(r, c, data, area, floor) {
      area = area || (data && data.view_area) || "farm";
      const cabin = cabinPos(data);
      if (area === "cabin") {
        const kinds = {"1,1":"the double bed","1,2":"the chest","2,3":"the fireplace","3,1":"the door","3,2":"the kitchen"};
        const label = kinds[r + "," + c];
        const plot = "row " + r + " col " + c;
        return label ? ("at " + label + " (" + plot + " in the cabin)") : ("at " + plot + " in the cabin");
      }
      if (area === "farm" && r === cabin.r && c === cabin.c) return "in the cabin";
      const cols = COLS || 3;
      const plot = "at plot " + ((r - 1) * cols + c);
      if (area === "hills") {
        if (r === 1 && c === 2) return "at the mine entrance (row 1 col 2 in the hills)";
        return plot + " in the hills";
      }
      if (area === "mine") {
        const fl = floor || (data && data.view_floor);
        return fl ? (plot + " on floor " + fl + " of the mine") : (plot + " in the mine");
      }
      return plot;
    }
    function standingFrom(data) {
      data = data || lastData;
      const players = (data && (data.players || (data.state && data.state.players))) || {};
      const slot = players[PLAYER] || {};
      const r = parseInt(slot.row, 10);
      const c = parseInt(slot.col, 10);
      if (r && c) return {r: r, c: c, area: playerArea(slot)};
      const cabin = cabinPos(data);
      return {r: cabin.r, c: cabin.c, area: "farm"};
    }
    function whoAt(data, r, c) {
      const area = viewArea(data);
      const players = (data && (data.players || (data.state && data.state.players))) || {};
      const here = [];
      for (let i = 0; i < PLAYERS.length; i++) {
        const id = PLAYERS[i].id;
        const slot = players[id] || {};
        const sameFloor = area !== "mine" || Number(slot.floor) === Number(data && data.view_floor);
        if (Number(slot.row) === r && Number(slot.col) === c && playerArea(slot) === area && sameFloor) here.push(id);
      }
      return here;
    }
    function viewTiles(data) {
      if (data && data.view_tiles && data.view_tiles.length) return data.view_tiles;
      return (data && data.state && data.state.tiles) || [];
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
      return bits.length ? bits.join(", ") : "empty backpack";
    }

    function cropInfo(kind) {
      return (lastData && lastData.crops && lastData.crops[kind]) || {};
    }
    function itemName(key, n, data) {
      n = (n == null) ? 1 : n;
      data = data || lastData;
      const labels = data && data.item_names;
      if (labels && labels[key]) {
        const info = labels[key];
        const noun = (n === 1) ? (info.name || spacedName(key)) : (info.name_plural || ((info.name || spacedName(key)) + "s"));
        return n + " " + noun;
      }
      const fert = data && data.fertilizers && data.fertilizers[key];
      if (fert) {
        const noun = (n === 1) ? (fert.name || spacedName(key)) : ((fert.name_plural) || ((fert.name || spacedName(key)) + "s"));
        return n + " " + noun;
      }
      let kind = key;
      let stock = null;
      if (key.endsWith("_seedling")) { kind = key.slice(0, -9); stock = "seedling"; }
      else if (key.endsWith("_crown")) { kind = key.slice(0, -6); stock = "crown"; }
      else if (key.endsWith("_seed")) { kind = key.slice(0, -5); stock = "seed"; }
      const info = (data && data.crops && data.crops[kind]) || cropInfo(kind);
      if (stock) {
        const noun = (stock === "crown") ? (n === 1 ? "crown" : "crowns") : (n === 1 ? "seed" : "seeds");
        let prefix = "";
        const shop = (info && info.shop_name) || "";
        if (shop) {
          let s = String(shop).trim();
          const low = s.toLowerCase();
          if (low.startsWith("seed ") && !low.startsWith("seedling")) s = s.slice(5).trim();
          prefix = s.replace(/\s+(seedlings?|seeds?|crowns?)$/i, "").trim();
        }
        if (!prefix) prefix = (info && info.name) || spacedName(kind);
        return n + " " + prefix + " " + noun;
      }
      const name = (info && info.name) || spacedName(kind);
      const fruit = n === 1 ? name : ((info && info.name_plural) || (name + "s"));
      return n + " " + fruit;
    }
    function shopOwnedKey(kind, info, opts, data) {
      const staples = (data && data.staples) || {};
      const fertilizers = (data && data.fertilizers) || {};
      if (staples[kind] || fertilizers[kind] || (opts && opts.sell && !opts.buy)) {
        return kind;
      }
      const stockWord = (info && info.stock) || "seed";
      if (!stockWord || stockWord === "bag") return kind;
      return kind + "_" + stockWord;
    }
    function shopOwnedCount(kind, info, opts, data) {
      const inv = (data && data.state && data.state.inventory) || {};
      const key = shopOwnedKey(kind, info, opts, data);
      return itemName(key, inv[key] || 0, data);
    }
    function spacedName(key) {
      return String(key || "").replace(/_/g, " ");
    }

    function tileName(r, c) {
      const names = {
        "1,1": "top-left", "1,2": "top-center", "1,3": "top-right",
        "2,1": "mid-left", "2,2": "center", "2,3": "mid-right",
        "3,1": "bottom-left", "3,2": "bottom-center", "3,3": "bottom-right"
      };
      return (names[r + "," + c] || "plot") + ", row " + r + " col " + c;
    }

    function cropHint(tile, crop) {
      if (!crop || crop.stage === "withered" || crop.stage === "dormant" || crop.stage === "frost_bitten") return "";
      const growth = (crop.growth != null) ? Number(crop.growth) : (crop.stage === "mature" ? 100 : 0);
      const health = (crop.health != null) ? Number(crop.health) : 100;
      const bits = [];
      const mins = {kabocha: 60, carrot: 75};
      const minG = mins[crop.kind] || 70;
      if (growth < 25 && crop.stage !== "mature") bits.push("just getting started");
      if (!tile.watered && (crop.dry_days || 0) >= 2) bits.push("is drying out");
      else if (!tile.watered) bits.push("looks a little thirsty");
      if (tile.weedy) bits.push("is a little crowded by weeds");
      if (growth >= 100 && growth >= minG) bits.push("looks ready to pick");
      else if (growth >= minG) bits.push("could be picked, though it might still put on more");
      if (health <= 35) bits.push("is struggling");
      else if (health >= 85 && tile.watered && !tile.weedy && growth < minG) bits.push("is thriving");
      const unique = bits.filter(function (b, i) { return bits.indexOf(b) === i; }).slice(0, 2);
      if (!unique.length) return "";
      function form(p) {
        if (p.indexOf("is ") === 0 || p.indexOf("looks ") === 0 || p.indexOf("could ") === 0) return p;
        return "is " + p;
      }
      if (unique.length === 1) {
        const p0 = unique[0];
        return (p0.indexOf("is ") === 0 || p0.indexOf("looks ") === 0 || p0.indexOf("could ") === 0)
          ? (" It " + p0 + ".") : (" It is " + p0 + ".");
      }
      return " It " + form(unique[0]) + " and " + form(unique[1]) + ".";
    }

    function fertilizerPhrase(tile) {
      const fert = tile && tile.fertilizer;
      if (!fert || !fert.kind) return "";
      if (fert.kind === "general") return " The soil is fertilized (general).";
      if (fert.kind === "yield") return " The soil is fed with yield-boost fertilizer.";
      if (fert.kind === "growth") return " The soil is fed with growth-boost fertilizer.";
      return " The soil is fertilized.";
    }

    function tileLabel(tile, r, c, data) {
      if (viewArea(data) === "farm" && tile && tile.type === "cabin") return "cabin";
      return "r" + r + " c" + c;
    }
    function groundStacks(tile) {
      const stacks = (tile && tile.ground) || [];
      const out = [];
      for (let i = 0; i < stacks.length; i++) {
        const s = stacks[i];
        if (s && s.item && (s.count || 0) > 0) out.push(s);
      }
      if (!out.length && tile && tile.drop) out.push({ item: tile.drop, count: 1 });
      return out;
    }
    function groundPhrase(tile) {
      const stacks = groundStacks(tile);
      if (!stacks.length) return "";
      const bits = stacks.map(function (s) { return itemName(s.item, s.count || 1); });
      let body;
      if (bits.length === 1) body = bits[0];
      else if (bits.length === 2) body = bits[0] + " and " + bits[1];
      else body = bits.slice(0, -1).join(", ") + ", and " + bits[bits.length - 1];
      return " On the ground: " + body + ".";
    }
    function describeTile(tile, r, c, data) {
      return describeTileBase(tile, r, c, data) + groundPhrase(tile);
    }
    function describeTileBase(tile, r, c, data) {
      if (!tile) return "Click a plot.";
      if (tile.type === "town_stall") {
        const stall = (data && data.stall) || [];
        const held = stall.filter(function (s) { return s && s.item; });
        const stock = held.length ? (" In the stall: " + held.map(function (s) { return itemName(s.item, s.count || 1); }).join(", ") + ".") : " The stall is empty.";
        return tileName(r, c) + " — the market stall, under a blue awning. Drop goods here; they sell when the day ends. Spend " + ((data && data.instant_sell_energy) || 50) + " energy to sell everything now." + stock;
      }
      if (tile.type === "town_store") {
        return tileName(r, c) + " — the honour store. There's no shopkeeper; leave coins in the tin for seeds, fertilizer, staples, a sleeping bag, and (once the mine is found) a pickaxe.";
      }
      if (tile.type === "town_forge") {
        return tileName(r, c) + " — the town forge. Upgrade a hoe, watering can, axe, or pickaxe here.";
      }
      if (tile.type === "town_grass") {
        if (r === 1 && c === 1) return tileName(r, c) + " — the grassy entrance to the market town. West leads back to the cabin. The stall is to the east, the store to the south.";
        return tileName(r, c) + " — a grassy square in the market town.";
      }
      if (tile.type === "mine_entrance") {
        if (tile.closed === false) {
          return tileName(r, c) + " — the mine entrance is open. Step in with enter mine.";
        }
        return tileName(r, c) + " — a boarded mine entrance is set into the hill. The way in isn't open yet.";
      }
      if (tile.type === "mine_floor" || tile.type === "mine_safe") {
        const bits = [];
        if (tile.rock) {
          const rk = String(tile.rock).replace(/_ore$/, "").replace(/_/g, " ");
          if (rk === "runestone") bits.push("a smooth, rounded runestone rock");
          else bits.push(rk === "stone" || rk === "rock" ? "a rock" : ("a " + rk + " rock"));
        }
        if (tile.ladder === "open") bits.push("a ladder leading down");
        if (tile.exit) bits.push("the shaft back up");
        if (tile.lantern) bits.push("a rest lantern");
        if (tile.slime) bits.push("a " + String(tile.slime).replace(/_/g, " ") + " slime");
        if (tile.drop) bits.push(String(tile.drop).replace(/_/g, " ") + " on the ground");
        return tileName(r, c) + " — " + (bits.length ? bits.join(", ") : "bare stone floor") + ".";
      }
      if (tile.type === "grass" || tile.type === "hillside") {
        const bits = [];
        if (tile.tree && tile.tree.stage) {
          const st = tile.tree.stage;
          bits.push(st === "grown" ? "a grown tree, ready to chop" : (st === "stump" ? "a stump" : (st === "mushroom_log" ? "a mushroom log" : ("a " + st + (st === "young" ? " tree" : "")))));
        }
        if (tile.forage && tile.forage.kind) {
          bits.push("a " + String(tile.forage.kind).replace(/_/g, " ") + " to forage");
        }
        const typ = tile.type === "hillside" ? "hillside" : "grassy hillside";
        return tileName(r, c) + " in the hills — " + typ + ". " + (bits.length ? bits.join(", ") + "." : "Empty.");
      }
      if (tile.type === "cabin") {
        const w = (lastData && lastData.state && lastData.state.weather) || "sun";
        const byWeather = (typeof CABIN_BY_WEATHER !== "undefined") ? CABIN_BY_WEATHER[w] : "";
        return tileName(r, c) + " — " + (byWeather || CABIN_SHORT) + " Walk east for the market town, or north for the hills. Press E to step inside.";
      }
      if (String(tile.type || "").indexOf("cabin_") === 0) {
        const labels = {
          cabin_bed: "a double bed. Ending your turn anywhere inside is still cabin sleep.",
          cabin_chest: "the cabin chest. Open it from this tile.",
          cabin_fireplace: tile.fire ? "the fireplace, already fueled for tonight." : "the fireplace. Fuel it from this tile.",
          cabin_door: "the door back out to the farm. Press E to leave.",
          cabin_kitchen: "the kitchen. Cook from this tile.",
          cabin_floor: "wooden floor."
        };
        return tileName(r, c) + " — " + (labels[tile.type] || "inside the cabin.");
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
      }
      if (!crop) return tileName(r, c) + " — " + tilled + " soil, " + moist + ". Empty." + hold + fertilizerPhrase(tile) + weed;
      if (crop.stage === "withered") {
        return tileName(r, c) + " — a withered " + crop.kind + "." + fertilizerPhrase(tile) + weed;
      }
      if (crop.stage === "frost_bitten") {
        return tileName(r, c) + " — a frost-bitten " + crop.kind + ". The fruit can still be harvested once, then the plant must be cleared." + fertilizerPhrase(tile) + weed;
      }
      if (crop.stage === "dormant") {
        return tileName(r, c) + " — a dormant " + crop.kind + ", resting until spring. It needs no water." + fertilizerPhrase(tile) + weed;
      }
      const info = (lastData && lastData.crops && lastData.crops[crop.kind]) || {};
      let ready = "";
      if (crop.stage === "mature") {
        ready = " Ready to harvest.";
        if (info.regrow_days) {
          ready += " It will fruit again in " + info.regrow_days + " watered day(s) after you pick it.";
        }
      }
      let hint = cropHint(tile, crop);
      const name = info.name || crop.kind;
      const progress = cropProgressPhrase(crop, info);
      return tileName(r, c) + " — " + name + ", " + progress +
        ", " + crop.stage + ", " + moist + "." + ready + hint + fertilizerPhrase(tile) + weed;
    }

    function cropProgressPhrase(crop, info) {
      if (!crop) return "";
      if (crop.progress_phrase) return crop.progress_phrase;
      if (crop.stage === "withered" || crop.stage === "dormant" || crop.stage === "frost_bitten") return "";
      info = info || {};
      const afterDormancy = info.fruiting_after_dormancy !== false;
      if (info.perennial && afterDormancy && !crop.overwintered && !crop.fruiting_started && crop.stage !== "mature") {
        const n = Number(crop.days_established || 0);
        return "establishing, day " + n + " of the first year; fruits next spring";
      }
      if (info.perennial && info.fruiting_after_dormancy === false && !crop.harvests && crop.stage !== "mature" && !crop.overwintered) {
        const needed = info.grow_days;
        const grown = Number(crop.days_grown || 0);
        return "settling, day " + grown + " of " + needed;
      }
      const needed = (crop.harvests && info.regrow_days) ? info.regrow_days : info.grow_days;
      const of = needed ? (" of " + needed) : "";
      return "day " + (crop.days_grown || 0) + of;
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
      if (!settingsOpen) fillSettingsForm(data);
      else syncAutopassOptionsEnabled();
      if (chestOpen) renderChestWindow(data);
      renderAwayBanner(data);
      renderForecast(data);
      renderKeys(data);
      syncLocationLaunch(data);
      const s = data.state;
      const sky = weatherWord[s.weather] || s.weather;
      const capE = data.max_energy || 100;
      const players = data.players || s.players || {};
      const current = data.current_player || s.current_player || DEFAULT_PLAYER;
      function energyIcon() {
        return '<svg class="stat-icon" viewBox="0 0 32 32" aria-hidden="true"><path d="M18 2 L8 18 h8 l-2 12 12-16 h-8 z" fill="#e8b86a"/></svg>';
      }
      function hpIcon() {
        return '<svg class="stat-icon" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 28 C6 18 4 12 8 8 c3-3 6-2 8 1 2-3 5-4 8-1 4 4 2 10-8 20z" fill="#c45c5c"/></svg>';
      }
      function energyBit(name) {
        const slot = players[name] || {};
        const en = (slot.energy != null) ? slot.energy : capE;
        const capBase = (data.base_energy != null && data.base_energy > 0) ? data.base_energy : 100;
        const over = en > capBase;
        const capHp = data.max_hp || 100;
        const hpPair = (data.hp && data.hp[name]) || [slot.hp != null ? slot.hp : capHp, slot.hp_max || capHp];
        const readyBit = (data.ready_labels && data.ready_labels[name])
          ? " <span class='ready'>" + data.ready_labels[name] + "</span>"
          : "";
        const homesick = Number(slot.homesickness || (data.homesickness && data.homesickness[name]) || 0);
        const homeBit = homesick > 0
          ? " <span class='stat homesick' title='Homesickness' aria-label='Homesick minus " + homesick + " energy'>"
            + "homesick −" + homesick + "</span>"
          : "";
        return displayName(name)
          + " <span class='stat energy" + (over ? " over-max" : "") + "' title='Energy' aria-label='Energy " + en + " of " + capBase + "'>"
          + energyIcon() + "<b>" + en + "/" + capBase + "</b></span>"
          + " <span class='stat hp' title='HP' aria-label='HP " + hpPair[0] + " of " + hpPair[1] + "'>"
          + hpIcon() + "<b>" + hpPair[0] + "/" + hpPair[1] + "</b></span>"
          + homeBit
          + readyBit;
      }
      const energyBits = PLAYERS.map(function (p) { return "<span>" + energyBit(p.id) + "</span>"; }).join("");
      const placeBits = PLAYERS.map(function (p) {
        if (data.places && data.places[p.id]) return displayName(p.id) + " is " + data.places[p.id];
        const slot = players[p.id] || {};
        const r = parseInt(slot.row, 10);
        const c = parseInt(slot.col, 10);
        const area = playerArea(slot);
        const where = (r && c) ? describeWhere(r, c, data, area, slot.floor) : describeWhere(cabinPos(data).r, cabinPos(data).c, data, "farm");
        return displayName(p.id) + " is " + where;
      }).join(", ");
      const overview = $("overview-desc");
      if (overview) overview.textContent = placeBits;
      const areaHead = $("area-head");
      if (areaHead) areaHead.textContent = (data.area_title ? data.area_title.charAt(0).toUpperCase() + data.area_title.slice(1) : "The farm");
      const gridEl = $("grid");
      if (gridEl) gridEl.setAttribute("aria-label", data.area_title || "Farm plot");
      $("status").innerHTML =
        "<span>Day <b>" + s.day + "</b></span>" +
        "<span><b>" + cap(s.season) + "</b></span>" +
        "<span class='stat weather' title='Weather: " + sky + "' aria-label='Weather: " + sky + "'>" +
          forecastIcon(s.weather) + " " + sky + "</span>" +
        "<span class='gold'><b>" + s.gold + "G</b></span>" +
        "<span class='turn'>Turn: <b>" + displayName(current) + "</b></span>" +
        energyBits +
        "<span class='playing-as'>Playing as " + displayName(PLAYER) +
          (data.your_turn ? "" : " — waiting, it's " + displayName(current) + "'s turn") +
        "</span>";
      renderBackpack(data);
      renderRecipeBook(data);
      const endBtn = $("end-turn");
      if (endBtn) {
        endBtn.disabled = !data.your_turn;
        if (!data.your_turn) {
          endBtn.textContent = "Waiting for " + displayName(current);
        } else if (data.in_cabin) {
          endBtn.textContent = "Ready for bed";
        } else {
          endBtn.textContent = "Ready to end the day";
        }
      }
      const actions = data.actions || [];
      const passBtn = $("pass-turn");
      if (passBtn) {
        const canPass = !!(data.your_turn && actions.indexOf("pass turn") !== -1);
        passBtn.hidden = !canPass;
        passBtn.disabled = !canPass;
      }
      const walkHomeBtn = $("walk-home");
      if (walkHomeBtn) {
        let walkCmd = null;
        for (let i = 0; i < actions.length; i++) {
          if (/^carry .+ to bed$/.test(actions[i]) || /^walk .+ home$/.test(actions[i])) { walkCmd = actions[i]; break; }
        }
        if (walkCmd && data.your_turn) {
          walkHomeBtn.hidden = false;
          walkHomeBtn.disabled = false;
          walkHomeBtn.textContent = walkCmd.charAt(0).toUpperCase() + walkCmd.slice(1);
          walkHomeBtn.setAttribute("data-cmd", walkCmd);
        } else {
          walkHomeBtn.hidden = true;
          walkHomeBtn.disabled = true;
          walkHomeBtn.removeAttribute("data-cmd");
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
      if (savesOpen) renderSaves(data);
      $("look").textContent = data.look || "";
      fillDebugConsole(data);
      const log = (s.log || []).slice(-8).reverse();
      $("log").innerHTML = log.map(function (e) {
        return "<li>[day " + e.day + "] " + escapeHtml(e.text) + "</li>";
      }).join("");

      const grid = $("grid");
      grid.innerHTML = "";
      const rows = ROWS || 3;
      const cols = COLS || 3;
      const stand = standingFrom(data);
      const tiles = viewTiles(data);
      for (let r = 1; r <= rows; r++) {
        for (let c = 1; c <= cols; c++) {
          const tile = (tiles[r-1] && tiles[r-1][c-1]) || {};
          const key = (data.sprites && data.sprites[r-1] && data.sprites[r-1][c-1]) || "";
          const btn = document.createElement("button");
          btn.type = "button";
          const isCabin = (viewArea(data) === "farm" && tile.type === "cabin");
          btn.className = "tile" + (isCabin ? " cabin" : "");
          if (selected && selected.r === r && selected.c === c) btn.classList.add("selected");
          if (stand && stand.r === r && stand.c === c) btn.classList.add("here");
          const tip = describeTile(tile, r, c, data);
          btn.setAttribute("aria-label", tip);
          btn.title = tip;
          applyTileArt(btn, key);
          const num = document.createElement("div");
          num.className = "keynum";
          num.textContent = String((r - 1) * cols + c);
          const lab = document.createElement("div");
          lab.className = "label";
          lab.textContent = tileLabel(tile, r, c, data);
          btn.appendChild(num);
          btn.appendChild(lab);
          const gstack = groundStacks(tile);
          if (gstack.length) {
            const badge = document.createElement("div");
            badge.className = "ground-badge";
            const total = gstack.reduce(function (n, s) { return n + (s.count || 0); }, 0);
            const label = gstack.length === 1
              ? itemName(gstack[0].item, gstack[0].count || 1)
              : (total + " items");
            badge.textContent = label;
            btn.appendChild(badge);
          }
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
      function fillTileGround(tile) {
        const box = $("tile-ground");
        const list = $("tile-ground-list");
        if (!box || !list) return;
        const stacks = groundStacks(tile);
        list.innerHTML = "";
        if (!stacks.length) {
          box.hidden = true;
          return;
        }
        const here = !!(stand && focus && stand.r === focus.r && stand.c === focus.c && data.your_turn);
        stacks.forEach(function (s) {
          const li = document.createElement("li");
          const label = document.createElement("span");
          label.textContent = itemName(s.item, s.count || 1);
          li.appendChild(label);
          if (here && s.item) {
            const n = s.count || 1;
            const bare = itemName(s.item, 1).replace(/^1\s+/, "");
            function takeBtn(text, cmd) {
              const btn = document.createElement("button");
              btn.type = "button";
              btn.className = "btn";
              btn.textContent = text;
              btn.addEventListener("click", function () { actCmd(cmd); });
              li.appendChild(btn);
            }
            if (n <= 1) takeBtn("Take " + bare, "take " + s.item + " 1");
            else {
              takeBtn("Take 1 " + bare, "take " + s.item + " 1");
              takeBtn("Take all " + itemName(s.item, n).replace(/^\d+\s+/, ""), "take " + s.item + " all");
            }
          }
          list.appendChild(li);
        });
        box.hidden = false;
      }
      if (!focus) {
        $("tile-desc").textContent = "Walk with the arrow keys or 1–9. T, W, P, H, and Q act on the tile you are standing on.";
        fillTileGround(null);
        return;
      }
      const r = focus.r, c = focus.c;
      const tile = (viewTiles(data)[r-1] && viewTiles(data)[r-1][c-1]) || {};
      let desc = describeTile(tile, r, c, data);
      const occupants = whoAt(data, r, c).map(displayName);
      if (occupants.length) desc += " " + occupants.join(" and ") + " standing here.";
      if (stand && stand.r === r && stand.c === c) desc += " You are here.";
      else desc += " You are " + describeWhere(stand.r, stand.c, data) + ".";
      $("tile-desc").textContent = desc;
      fillTileGround(tile);
      if (!data.your_turn) {
        const who = cap(data.current_player || "the other player");
        $("tile-desc").textContent = desc + " It's " + who + "'s turn.";
        return;
      }
      const legalWrap = document.createElement("div");
      legalWrap.className = "chest-section legal-actions-section";
      const legalOpen = legalActionsIsOpen();
      if (!legalOpen) legalWrap.classList.add("is-collapsed");
      const legalTitle = document.createElement("button");
      legalTitle.type = "button";
      legalTitle.className = "recipe-book-head chest-toggle";
      legalTitle.textContent = "LEGAL ACTIONS";
      legalTitle.setAttribute("aria-expanded", legalOpen ? "true" : "false");
      const legalBody = document.createElement("div");
      legalBody.className = "chest-section-body actions";
      if (!legalOpen) legalBody.hidden = true;
      legalTitle.addEventListener("click", function () {
        const next = legalBody.hidden;
        legalBody.hidden = !next;
        legalTitle.setAttribute("aria-expanded", next ? "true" : "false");
        legalWrap.classList.toggle("is-collapsed", !next);
        setLegalActionsOpen(next);
      });
      legalWrap.appendChild(legalTitle);
      legalWrap.appendChild(legalBody);
      const workR = stand.r, workC = stand.c;
      const prefix = [
        "till " + workR + " " + workC,
        "water " + workR + " " + workC,
        "harvest " + workR + " " + workC,
        "pluck " + workR + " " + workC,
        "unearth " + workR + " " + workC,
        "chop",
        "forage",
        "go north",
        "go south",
        "go cabin",
        "enter cabin",
        "leave cabin",
        "enter mine",
        "leave mine",
        "climb up",
        "climb down",
        "fuel fireplace",
        "fuel stove",
        "mine",
        "rest",
        "strike"
      ];
      const plantPrefix = "plant " + workR + " " + workC + " ";
      const fertPrefix = "fertilize " + workR + " " + workC;
      const legal = data.actions || [];
      const lines = data.action_lines || {};
      function actionLabel(act, fallback) {
        const line = lines[act];
        if (!line) return fallback || act;
        const bare = (fallback || act.split(" ")[0]);
        const desc = line.match(/ \((.*)\)$/);
        return desc ? (bare + " (" + desc[1] + ")") : (line || bare);
      }
      function addHotkeyHint(label, hint) {
        if (!hint) return label;
        const m = String(label || "").match(/^(.*)\((.*)\)\s*$/);
        if (m) return m[1].replace(/\s+$/, "") + " (" + m[2] + ", " + hint + ")";
        return label + " (" + hint + ")";
      }
      function hotkeyForAction(act) {
        if (act === "enter cabin" || act === "leave cabin" || act === "enter mine" || act === "climb up" || act === "climb down" || act === "leave mine" || act === "fuel fireplace" || act === "fuel stove") return "E";
        if (act === "mine") return "M";
        if (act === "rest") return "R";
        if (act === "strike") return "K";
        return "";
      }
      // List every action the engine says is legal from the tile you
      // stand on (moves, area exits, enter cabin, build chest, and the rest).
      // A short prefix used to hide most of them — including go east/west
      // and move to r c — which is why the farm cabin tile only showed two.
      function legalActionLabel(act) {
        if (act.indexOf("unearth ") === 0) return actionLabel(act, "unearth");
        if (act.indexOf(plantPrefix) === 0) return actionLabel(act, "plant " + act.slice(plantPrefix.length));
        if (act === fertPrefix || act.indexOf(fertPrefix + " ") === 0) {
          return actionLabel(act, act.replace(fertPrefix + " ", "fertilize ").replace(fertPrefix, "fertilize"));
        }
        return actionLabel(act, act);
      }
      for (const act of legal) {
        let label = addHotkeyHint(legalActionLabel(act), hotkeyForAction(act));
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn";
        b.textContent = label;
        b.addEventListener("click", function () {
          if (act.indexOf("unearth ") === 0) { keyUnearth(false); return; }
          actCmd(act);
        });
        legalBody.appendChild(b);
      }
      if (legalBody.childNodes.length) box.appendChild(legalWrap);
      // Walk here is a This-tile action for the plot you clicked, not the
      // standing-tile list. Keep it outside the Legal Actions collapsible
      // (above it) so it stays reachable when that list is folded away.
      if (stand && (stand.r !== r || stand.c !== c)) {
        const walkCmd = "move to " + r + " " + c;
        const walkRow = document.createElement("div");
        walkRow.className = "tile-walk";
        const walk = document.createElement("button");
        walk.type = "button";
        walk.className = "btn";
        walk.id = "walk-here";
        walk.textContent = actionLabel(walkCmd, "Walk here");
        walk.addEventListener("click", function () { actCmd(walkCmd); });
        walkRow.appendChild(walk);
        if (legalWrap.parentNode === box) box.insertBefore(walkRow, legalWrap);
        else box.appendChild(walkRow);
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
    function syncAutopassOptionsEnabled() {
      const box = $("settings-autopass");
      const opts = $("settings-autopass-options");
      if (opts) opts.disabled = !(box && box.checked);
    }
    function fillSettingsForm(data) {
      const ap = (data && data.autopass) || {};
      const enabled = !!ap.enabled;
      const maxTurns = (ap.max_turns != null) ? ap.max_turns : 3;
      const timeout = (ap.timeout_minutes != null) ? ap.timeout_minutes : 30;
      const box = $("settings-autopass");
      const maxBox = $("settings-autopass-max");
      const timeBox = $("settings-autopass-timeout");
      const status = $("settings-autopass-status");
      if (box) box.checked = enabled;
      if (maxBox) maxBox.value = String(maxTurns);
      if (timeBox) timeBox.value = String(timeout);
      syncAutopassOptionsEnabled();
      if (status) {
        const used = Number(ap.turns_used || 0);
        status.textContent = enabled
          ? (used + " of " + maxTurns + " turns autopassed")
          : "";
      }
    }
    function settingsPayload() {
      const box = $("settings-autopass");
      const maxBox = $("settings-autopass-max");
      const timeBox = $("settings-autopass-timeout");
      return {
        autopass: {
          enabled: !!(box && box.checked),
          max_turns: maxBox ? maxBox.value : 3,
          timeout_minutes: timeBox ? timeBox.value : 30
        }
      };
    }
    async function saveSettings(extra) {
      const body = settingsPayload();
      if (extra && extra.acknowledge_away) body.acknowledge_away = true;
      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        if (res.status === 401 || res.status === 403) {
          showAuthNeeded();
          return;
        }
        const data = await res.json();
        lastSig = JSON.stringify(data.state);
        try { render(data); } catch (err) { console.error("Could not draw the farm:", err); }
      } catch (err) {
        console.error("Could not save settings:", err);
        showToast("Could not save settings.", false);
      }
    }
    function openSettings() {
      closeShop();
      closeJournal();
      closeSaves();
      closeChest();
      settingsOpen = true;
      const modal = $("settings-modal");
      if (modal) modal.hidden = false;
      if (lastData) fillSettingsForm(lastData);
    }
    function closeSettings() {
      settingsOpen = false;
      const modal = $("settings-modal");
      if (modal) modal.hidden = true;
    }
    function renderAwayBanner(data) {
      const el = $("away-summary");
      if (!el) return;
      const text = (data && data.away_summary) ? String(data.away_summary) : "";
      if (!text) {
        el.hidden = true;
        el.innerHTML = "";
        return;
      }
      el.hidden = false;
      el.innerHTML = "";
      const h = document.createElement("h3");
      h.textContent = "While you were away";
      const p = document.createElement("p");
      p.textContent = text.replace(/^While you were away:\s*/i, "");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn";
      btn.textContent = "Dismiss";
      btn.addEventListener("click", function () { saveSettings({acknowledge_away: true}); });
      el.appendChild(h);
      el.appendChild(p);
      el.appendChild(btn);
    }
    function openJournal() {
      closeShop();
      closeSaves();
      closeSettings();
      closeChest();
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
    function openSaves() {
      closeShop();
      closeJournal();
      closeSettings();
      closeChest();
      savesOpen = true;
      const modal = $("saves-modal");
      if (modal) modal.hidden = false;
      if (lastData) renderSaves(lastData);
    }
    function closeSaves() {
      savesOpen = false;
      savesSwitch = null;
      savesRenameId = null;
      const modal = $("saves-modal");
      if (modal) modal.hidden = true;
      const confirm = $("saves-confirm");
      if (confirm) { confirm.hidden = true; confirm.innerHTML = ""; }
    }
    async function postSaves(body) {
      const res = await fetch("/api/saves", {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body || {})
      });
      if (res.status === 401 || res.status === 403) {
        showAuthNeeded();
        return null;
      }
      const data = await res.json();
      lastData = data;
      lastSig = JSON.stringify(data.state);
      if (data.message) showToast(data.message, data.ok);
      try { render(data); } catch (err) { console.error(err); }
      if (savesOpen) renderSaves(data);
      return data;
    }
    function renderSaves(data) {
      const body = $("saves-body");
      if (!body) return;
      const info = (data && data.saves) || {};
      const slots = info.slots || [];
      body.innerHTML = "";
      if (!slots.length) {
        const empty = document.createElement("p");
        empty.className = "shop-empty";
        empty.textContent = "No saved farms yet.";
        body.appendChild(empty);
      }
      slots.forEach(function (slot) {
        const card = document.createElement("div");
        card.className = "save-card" + (slot.active ? " active" : "");
        const name = document.createElement("div");
        name.className = "save-name";
        name.textContent = slot.name + (slot.active ? " (active)" : "");
        const meta = document.createElement("div");
        meta.className = "save-meta";
        meta.textContent = "Day " + slot.day + ", " + slot.season + ", year " + slot.year
          + " · " + slot.gold + "G · last played " + (slot.last_played_text || "never");
        const row = document.createElement("div");
        row.className = "save-actions";
        if (!slot.active) {
          const sw = document.createElement("button");
          sw.type = "button";
          sw.className = "btn primary";
          sw.textContent = "Switch";
          sw.addEventListener("click", function () { requestSwitch(slot); });
          row.appendChild(sw);
        }
        const ren = document.createElement("button");
        ren.type = "button";
        ren.className = "btn";
        ren.textContent = "Rename";
        ren.addEventListener("click", function () { beginRename(slot); });
        row.appendChild(ren);
        if (savesRenameId === slot.id) {
          const input = document.createElement("input");
          input.type = "text";
          input.maxLength = 80;
          input.value = slot.name;
          input.setAttribute("aria-label", "New name for " + slot.name);
          const save = document.createElement("button");
          save.type = "button";
          save.className = "btn primary";
          save.textContent = "Save name";
          save.addEventListener("click", function () {
            const next = input.value.trim();
            savesRenameId = null;
            postSaves({action: "rename", slot: slot.id, name: next});
          });
          row.appendChild(input);
          row.appendChild(save);
        }
        card.appendChild(name);
        card.appendChild(meta);
        card.appendChild(row);
        body.appendChild(card);
      });
    }
    function requestSwitch(slot) {
      savesSwitch = slot;
      const box = $("saves-confirm");
      if (!box) return;
      box.hidden = false;
      box.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = "Switch to " + slot.name + "? The current farm is saved first. Both players will play this one.";
      const row = document.createElement("div");
      row.className = "save-actions";
      const ok = document.createElement("button");
      ok.type = "button";
      ok.className = "btn primary";
      ok.textContent = "Switch";
      ok.addEventListener("click", function () {
        const target = savesSwitch;
        savesSwitch = null;
        box.hidden = true;
        box.innerHTML = "";
        if (target) postSaves({action: "load", slot: target.id, confirm: true});
      });
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "btn";
      cancel.textContent = "Cancel";
      cancel.addEventListener("click", function () {
        savesSwitch = null;
        box.hidden = true;
        box.innerHTML = "";
      });
      row.appendChild(ok);
      row.appendChild(cancel);
      box.appendChild(p);
      box.appendChild(row);
    }
    function beginRename(slot) {
      savesRenameId = slot.id;
      if (lastData) renderSaves(lastData);
    }
    function startNewFarm() {
      const input = $("saves-new-name");
      const name = input ? String(input.value || "").trim() : "";
      if (!name) {
        showToast("Name the new farm first.", false);
        return;
      }
      postSaves({action: "new", name: name}).then(function (data) {
        if (data && data.ok && input) input.value = "";
      });
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
    function syncLocationLaunch(data) {
      const shopBtn = $("open-shop");
      const atStore = !!(data && data.at_store);
      if (shopBtn) {
        shopBtn.hidden = !atStore;
        shopBtn.disabled = !atStore;
      }
      if (!atStore && shopOpen) closeShop();
      const chestBtn = $("open-chest");
      const info = (data && data.chest_info) || {};
      const canOpen = !!(data && (data.at_chest || (data.at_chest_site && !info.built)));
      if (chestBtn) {
        chestBtn.hidden = !canOpen;
        chestBtn.disabled = !canOpen;
        chestBtn.textContent = info.built ? "Chest" : "Build chest";
      }
      if (chestOpen && data && !data.at_chest && !data.at_chest_site) closeChest();
    }
    function openShop() {
      if (!lastData || !lastData.at_store) {
        showToast("Walk to the honour store (row 2 col 1) to shop.", true);
        return;
      }
      closeSaves();
      closeJournal();
      closeSettings();
      closeChest();
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
    function openChest() {
      const data = lastData || {};
      const info = data.chest_info || {};
      if (!data.at_chest && !(data.at_chest_site && !info.built)) {
        showToast(info.built
          ? "Walk to the chest inside the cabin to open it."
          : "Walk to the north-wall nook (row 1 col 2) in the cabin to build a chest.", true);
        return;
      }
      closeShop();
      closeJournal();
      closeSaves();
      closeSettings();
      chestOpen = true;
      const modal = $("chest-modal");
      if (modal) modal.hidden = false;
      renderChestWindow(data);
    }
    function closeChest() {
      chestOpen = false;
      const modal = $("chest-modal");
      if (modal) modal.hidden = true;
      cancelChestInteraction();
    }
    function chestOverlaySrc(tier) {
      const pack = packById(artPackId);
      const id = (pack && pack.id) || "storybook";
      const key = (tier && tier !== "wood") ? ("cabin_chest_" + tier) : "cabin_chest";
      const rel = pack && pack.overlays && pack.overlays[key];
      if (rel && typeof rel === "string" && /^[a-z0-9_./-]+$/i.test(rel) && rel.indexOf("..") < 0) {
        return "/static/packs/" + id + "/" + rel;
      }
      return "/static/packs/" + id + "/overlays/" + key + ".png";
    }
    function hideDragGhost() {
      const ghost = $("chest-drag-ghost");
      if (ghost && ghost.parentNode) ghost.parentNode.removeChild(ghost);
    }
    function moveDragGhost(ev) {
      const ghost = $("chest-drag-ghost");
      if (!ghost) return;
      ghost.style.transform = "translate(" + ev.clientX + "px, " + ev.clientY + "px) translate(-50%, -60%)";
    }
    function showDragGhost(slot, ev) {
      hideDragGhost();
      if (!slot || !slot.item) return;
      const ghost = document.createElement("div");
      ghost.id = "chest-drag-ghost";
      ghost.className = "chest-drag-ghost";
      ghost.setAttribute("aria-hidden", "true");
      const img = document.createElement("img");
      img.src = itemIconSrc(slot.item);
      img.alt = "";
      ghost.appendChild(img);
      const badge = document.createElement("span");
      badge.className = "chest-drag-badge";
      badge.textContent = String(slot.count || 1);
      ghost.appendChild(badge);
      document.body.appendChild(ghost);
      moveDragGhost(ev);
    }
    function hideChestItemMenu() {
      const menu = $("chest-item-menu");
      if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
      document.removeEventListener("pointerdown", chestMenuOutside, true);
      const selected = document.querySelectorAll(".chest-cell.is-selected, .pack-cell.is-selected");
      selected.forEach(function (el) { el.classList.remove("is-selected"); });
    }
    function chestMenuOutside(ev) {
      if (ev.target && ev.target.closest && ev.target.closest("#chest-item-menu")) return;
      hideChestItemMenu();
    }
    function showChestItemMenu(cell, data) {
      hideChestItemMenu();
      if (!cell || !cell.dataset.item) return;
      if (!data || !data.your_turn || !data.at_chest) return;
      const store = cell.dataset.store;
      const index = cell.dataset.index;
      const menu = document.createElement("div");
      menu.id = "chest-item-menu";
      menu.className = "chest-item-menu";
      function addBtn(label, cmd) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = label;
        btn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          hideChestItemMenu();
          actCmd(cmd);
        });
        menu.appendChild(btn);
      }
      if (store === "chest") {
        addBtn("Take 1", "take chest " + index + " 1");
        addBtn("Take stack", "take chest " + index + " stack");
      } else {
        addBtn("Put 1", "put pack " + index + " 1");
        addBtn("Put stack", "put pack " + index + " stack");
      }
      cell.classList.add("is-selected");
      document.body.appendChild(menu);
      const box = cell.getBoundingClientRect();
      menu.style.left = Math.max(8, Math.min(box.left, window.innerWidth - 160)) + "px";
      menu.style.top = (box.bottom + 4) + "px";
      setTimeout(function () {
        document.addEventListener("pointerdown", chestMenuOutside, true);
      }, 0);
    }
    function cancelChestInteraction() {
      hideDragGhost();
      hideChestItemMenu();
      chestBusy = false;
      const dragging = document.querySelectorAll(".chest-cell.is-dragging, .pack-cell.is-dragging");
      dragging.forEach(function (el) { el.classList.remove("is-dragging"); });
    }
    function fillChestCell(cell, slot, store, index, data) {
      cell.className = store === "pack" ? "pack-cell" : "chest-cell";
      cell.dataset.store = store;
      cell.dataset.index = String(index);
      const overflow = store === "chest" && data && data.chest_info
        && index > Number(data.chest_info.slots || 0);
      if (overflow) cell.classList.add("is-overflow");
      if (slot && slot.item) {
        cell.dataset.item = slot.item;
        cell.dataset.count = String(slot.count || 1);
        const img = document.createElement("img");
        img.src = itemIconSrc(slot.item);
        img.alt = "";
        cell.appendChild(img);
        const label = document.createElement("span");
        label.textContent = itemName(slot.item, Number(slot.count || 0), data);
        cell.appendChild(label);
      } else {
        cell.classList.add("is-empty");
        cell.textContent = "";
        delete cell.dataset.item;
        delete cell.dataset.count;
      }
    }
    function bindChestDragOnce() {
      const dialog = document.querySelector(".chest-dialog");
      if (!dialog || dialog.dataset.dragReady) return;
      dialog.dataset.dragReady = "1";
      let start = null;
      let dragging = null;
      function slotFromCell(cell) {
        if (!cell || !cell.dataset.item) return null;
        return {
          item: cell.dataset.item,
          count: Number(cell.dataset.count || 1),
          store: cell.dataset.store,
          index: cell.dataset.index
        };
      }
      dialog.addEventListener("pointerdown", function (ev) {
        if (ev.target && ev.target.closest && ev.target.closest("#chest-item-menu, button, input, textarea, a")) return;
        const live = lastData;
        const cell = ev.target.closest && ev.target.closest(".chest-cell, .pack-cell");
        if (!cell || !cell.dataset.item) return;
        if (!live || !live.your_turn || !live.at_chest) return;
        if (ev.button && ev.button !== 0) return;
        start = { cell: cell, x: ev.clientX, y: ev.clientY, pointerId: ev.pointerId, slot: slotFromCell(cell) };
        try { cell.setPointerCapture(ev.pointerId); } catch (err) {}
      });
      dialog.addEventListener("pointermove", function (ev) {
        if (!start) return;
        const dx = ev.clientX - start.x;
        const dy = ev.clientY - start.y;
        if (!dragging && (dx * dx + dy * dy) >= 36) {
          dragging = start.cell;
          chestBusy = true;
          hideChestItemMenu();
          dragging.classList.add("is-dragging");
          showDragGhost(start.slot, ev);
        }
        if (dragging) moveDragGhost(ev);
      });
      function endPointer(ev, cancelled) {
        if (!start) return;
        const src = start.cell;
        const wasDrag = !!dragging;
        start = null;
        dragging = null;
        if (wasDrag) {
          src.classList.remove("is-dragging");
          hideDragGhost();
          if (cancelled) {
            chestBusy = false;
            return;
          }
          const dest = document.elementFromPoint(ev.clientX, ev.clientY);
          const cell = dest && dest.closest && dest.closest(".chest-cell, .pack-cell");
          if (!cell || cell === src) {
            chestBusy = false;
            return;
          }
          const cmd = "transfer " + src.dataset.store + " " + src.dataset.index
            + " " + cell.dataset.store + " " + cell.dataset.index;
          const done = actCmd(cmd);
          if (done && typeof done.finally === "function") {
            done.finally(function () {
              chestBusy = false;
              hideDragGhost();
            });
          } else {
            chestBusy = false;
          }
          return;
        }
        if (!cancelled) showChestItemMenu(src, lastData);
      }
      dialog.addEventListener("pointerup", function (ev) { endPointer(ev, false); });
      dialog.addEventListener("pointercancel", function (ev) { endPointer(ev, true); });
    }
    function renderChestWindow(data) {
      const info = (data && data.chest_info) || {};
      const title = $("chest-title");
      const band = $("chest-band");
      const meta = $("chest-meta");
      const tools = $("chest-toolbar");
      const grid = $("chest-grid");
      const packGrid = $("chest-pack-grid");
      hideChestItemMenu();
      if (title) title.textContent = info.built ? (info.name ? (info.name.charAt(0).toUpperCase() + info.name.slice(1)) : "Chest") : "Build a chest";
      const icon = $("chest-title-icon");
      if (icon) {
        if (info.built) {
          icon.hidden = false;
          icon.src = chestOverlaySrc(info.tier || "wood");
          icon.alt = title ? title.textContent : "Chest";
        } else {
          icon.hidden = true;
          icon.removeAttribute("src");
        }
      }
      if (band) {
        if (info.built && info.band) {
          band.hidden = false;
          band.style.background = info.band;
        } else {
          band.hidden = true;
        }
      }
      if (meta) {
        if (!info.built) {
          meta.textContent = "There is no chest yet. Building one costs 5 wood and is done at this north-wall nook (row 1 col 2). It is the first decoration you can build. A new chest has 12 slots (stacks of 16).";
        } else {
          let line = info.slots + " slots · stacks of " + (info.stack || 16);
          const filled = (info.items || []).filter(function (s) { return s && s.item; }).length;
          line += " · " + filled + " used";
          if (info.overflow) line += " · " + info.overflow + " overflow kept, nothing discarded";
          meta.textContent = line;
        }
      }
      if (tools) {
        tools.innerHTML = "";
        if (!info.built && data.at_chest_site && data.your_turn) {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "btn primary";
          b.textContent = "Build chest (5 wood)";
          b.addEventListener("click", function () { actCmd("build chest"); });
          tools.appendChild(b);
        } else if (info.built && info.next_tier && data.at_chest && data.your_turn) {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "btn";
          const cost = info.upgrade_cost || {};
          const bits = Object.keys(cost).map(function (k) { return cost[k] + " " + k.replace("_", " "); });
          b.textContent = "Upgrade to " + info.next_tier + (bits.length ? " (" + bits.join(", ") + ")" : "");
          b.addEventListener("click", function () { actCmd("upgrade chest"); });
          tools.appendChild(b);
        }
      }
      if (grid) {
        grid.innerHTML = "";
        const cols = Number(info.cols || 12) || 12;
        grid.style.gridTemplateColumns = "repeat(" + cols + ", minmax(0, 1fr))";
        const items = info.built ? (info.items || []) : [];
        const total = Math.max(items.length, Number(info.slots || 0));
        for (let i = 0; i < total; i++) {
          const cell = document.createElement("div");
          fillChestCell(cell, items[i], "chest", i + 1, data);
          grid.appendChild(cell);
        }
      }
      if (packGrid) {
        packGrid.innerHTML = "";
        const pack = packSlotsOf(data);
        packGrid.style.gridTemplateColumns = "repeat(" + Math.max(pack.length || 4, 4) + ", minmax(0, 1fr))";
        for (let i = 0; i < pack.length; i++) {
          const cell = document.createElement("div");
          fillChestCell(cell, pack[i], "pack", i + 1, data);
          packGrid.appendChild(cell);
        }
      }
      bindChestDragOnce();
    }

    function seasonLabel(list) {
      return (list || []).join(", ") || "unknown season";
    }

    function shopEmptyMessage(season) {
      const name = cap(season || "this season");
      return "Nothing in season yet. " + name + " crops arrive in a later update.";
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
      const fruitSprite = "/sprite/" + (info.sprite || (kind + "_mature_dry")) + ".svg";
      if (stock === "bag" || (data.fertilizers && data.fertilizers[kind]) || (data.staples && data.staples[kind]) || (data.recipes && data.recipes[kind])) {
        img.src = itemIconSrc(kind);
      } else if (opts && opts.sell && !opts.buy) {
        img.src = itemIconSrc(kind, fruitSprite);
      } else {
        img.src = itemIconSrc(kind + "_" + (stock || "seed"), fruitSprite);
      }
      img.alt = title;
      card.appendChild(img);
      const body = document.createElement("div");
      let cycle = "";
      if (info.grow_days) {
        cycle = info.regrow_days
          ? (info.grow_days + " days, then every " + info.regrow_days + " days")
          : (info.grow_days + " days");
      }
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
      const isCrop = !!(info.grow_days);
      let seasonBit;
      if (isCrop) {
        seasonBit = "grows " + seasonLabel(info.seasons);
        if (info.shop_uses_override && info.shop_seasons && info.shop_seasons.length) {
          seasonBit += " · sold in " + seasonLabel(info.shop_seasons);
        }
      } else {
        const listed = (info.shop_seasons && info.shop_seasons.length) ? info.shop_seasons : (info.seasons || []);
        seasonBit = (listed.length === 4) ? "year-round" : seasonLabel(listed);
      }
      let windowBit = "";
      if (isCrop && info.for_sale && info.viable_days_left != null) {
        const left = Number(info.viable_days_left);
        if (left > 0) {
          windowBit = left + (left === 1 ? " day left to finish" : " days left to finish");
        }
      }
      const meta = seasonBit +
        (cycle ? " · " + cycle : "") +
        (windowBit ? " · " + windowBit : "") +
        " · " + info.seed_price + "G" +
        (info.sell_price ? " · sell " + info.sell_price + "G" : "") +
        (eat ? " · eat +" + eat + " energy" : "") +
        " · " + shopOwnedCount(kind, info, opts, data);
      card.title = meta;
      body.innerHTML = "<b>" + escapeHtml(title) + "</b>" +
        (desc ? '<p class="desc">' + escapeHtml(desc) + "</p>" : "") +
        '<div class="meta shop-meta">' + escapeHtml(meta) + "</div>";
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
        buy.disabled = gold < info.seed_price || !data.your_turn || !data.at_store;
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
        sell.disabled = fruit < 1 || !data.your_turn || !data.at_stall;
        sell.addEventListener("click", function () { actCmd("sell " + kind + " 1"); });
        row.appendChild(sell);
      }
      body.appendChild(row);
      card.appendChild(body);
      shop.appendChild(card);
    }

    function appendToolCard(shop, data, kind, info) {
      info = info || {};
      const gold = (data.state && data.state.gold) || 0;
      const price = (info.price != null) ? info.price : info.seed_price;
      const title = info.shop_name || info.name || kind;
      const card = document.createElement("div");
      card.className = "shop-card";
      const img = document.createElement("img");
      img.src = itemIconSrc(kind);
      img.alt = title;
      card.appendChild(img);
      const body = document.createElement("div");
      const desc = info.description || "";
      body.innerHTML = "<b>" + escapeHtml(title) + "</b>" +
        (desc ? '<p class="desc">' + escapeHtml(desc) + "</p>" : "") +
        '<div class="meta shop-meta">' + price + "G</div>";
      const row = document.createElement("div");
      row.className = "shop-qty";
      const buy = document.createElement("button");
      buy.type = "button";
      buy.className = "btn primary";
      buy.textContent = "Buy";
      buy.disabled = gold < price || !data.your_turn || !data.at_store;
      buy.addEventListener("click", function () { actCmd("buy " + kind + " 1"); });
      row.appendChild(buy);
      body.appendChild(row);
      card.appendChild(body);
      shop.appendChild(card);
    }

    function packSlotsOf(data) {
      const players = (data && data.players) || (data && data.state && data.state.players) || {};
      if (data && data.pack && data.pack.length) return data.pack;
      return (players[PLAYER] || {}).pack || [];
    }

    function recipeInfo(item, data) {
      const recs = (data && data.recipes) || {};
      if (recs[item]) return recs[item];
      const staples = (data && data.staples) || {};
      return staples[item] || null;
    }
    function isStockItem(item) {
      item = String(item || "");
      return item.endsWith("_seed") || item.endsWith("_seedling") || item.endsWith("_crown") || item.endsWith("_crowns");
    }
    function snackEnergy(item, data) {
      // Recipes and staples first; then forage / item catalog; harvested crop
      // fruit after. Seeds/crowns and cook-only foods (no eat_energy) are not
      // snacks. Shop buy rows never use this.
      const rec = recipeInfo(item, data);
      if (rec && rec.eat_energy) return rec.eat_energy;
      if (isStockItem(item)) return 0;
      const named = data && data.item_names && data.item_names[item];
      if (named && named.eat_energy) return named.eat_energy;
      const forage = (data && data.forage && data.forage[item]) || {};
      if (forage.eat_energy) return forage.eat_energy;
      const info = (data && data.crops && data.crops[item]) || {};
      return info.eat_energy || 0;
    }
    function slotsOfChest(data) {
      const chest = (data && data.chest) || (data && data.state && data.state.chest) || [];
      return Array.isArray(chest) ? chest : [];
    }
    function countItemInSlots(slots, kind) {
      let n = 0;
      (slots || []).forEach(function (slot) {
        if (slot && slot.item === kind) n += Number(slot.count || 0);
      });
      return n;
    }
    const CHEST_OPEN_KEY = "lanternFarm.cabinChestOpen";
    function chestSectionIsOpen() {
      try {
        const raw = localStorage.getItem(CHEST_OPEN_KEY);
        if (raw === null) return true;
        return raw !== "0" && raw !== "false";
      } catch (err) {
        return true;
      }
    }
    function setChestSectionOpen(open) {
      try { localStorage.setItem(CHEST_OPEN_KEY, open ? "1" : "0"); } catch (err) {}
    }
    const LEGAL_OPEN_KEY = "lanternFarm.legalActionsOpen";
    function legalActionsIsOpen() {
      try {
        const raw = localStorage.getItem(LEGAL_OPEN_KEY);
        if (raw === null) return false;
        return raw !== "0" && raw !== "false";
      } catch (err) {
        return false;
      }
    }
    function setLegalActionsOpen(open) {
      try { localStorage.setItem(LEGAL_OPEN_KEY, open ? "1" : "0"); } catch (err) {}
    }
    function enableChestSort(listEl) {
      const cards = function () { return Array.from(listEl.querySelectorAll(".chest-card")); };
      let dragging = null;
      function itemOrder() {
        return cards().map(function (c) { return c.getAttribute("data-item"); }).filter(Boolean);
      }
      listEl.addEventListener("pointerdown", function (ev) {
        const card = ev.target.closest && ev.target.closest(".chest-card");
        if (!card || !listEl.contains(card)) return;
        if (ev.button && ev.button !== 0) return;
        if (ev.target.closest("button, input, a, select, textarea")) return;
        dragging = card;
        dragging._startOrder = itemOrder().join(" ");
        card.classList.add("is-dragging");
        try { card.setPointerCapture(ev.pointerId); } catch (err) {}
        ev.preventDefault();
      });
      listEl.addEventListener("pointermove", function (ev) {
        if (!dragging) return;
        const y = ev.clientY;
        const siblings = cards();
        for (let i = 0; i < siblings.length; i++) {
          const s = siblings[i];
          if (s === dragging) continue;
          const r = s.getBoundingClientRect();
          const mid = r.top + r.height / 2;
          if (y < mid) {
            listEl.insertBefore(dragging, s);
            break;
          }
          if (i === siblings.length - 1 && y > mid) {
            listEl.appendChild(dragging);
          }
        }
      });
      function endDrag() {
        if (!dragging) return;
        const card = dragging;
        card.classList.remove("is-dragging");
        const next = itemOrder().join(" ");
        const prev = card._startOrder || "";
        dragging = null;
        if (next && next !== prev) actCmd("reorder chest " + next);
      }
      listEl.addEventListener("pointerup", endDrag);
      listEl.addEventListener("pointercancel", endDrag);
    }
    function renderChestCards(parent, data, opts) {
      opts = opts || {};
      const chest = slotsOfChest(data);
      if (!chest.length) {
        const empty = document.createElement("p");
        empty.className = "shop-empty";
        empty.textContent = "The chest is empty.";
        parent.appendChild(empty);
        return;
      }
      const canAct = !!(data && data.your_turn && data.at_chest);
      chest.forEach(function (slot) {
        appendItemCard(parent, slot, {
          take: true,
          canAct: canAct,
          yourTurn: !!(data && data.your_turn),
          data: data
        });
        const card = parent.lastElementChild;
        if (card && slot && slot.item) {
          card.classList.add("chest-card");
          card.setAttribute("data-item", slot.item);
        }
      });
      if (opts.sortable && data && data.at_chest && data.your_turn) {
        enableChestSort(parent);
      }
    }
    function appendCabinChestSection(parent, data) {
      if (!data || !data.in_cabin_interior) return;
      const wrap = document.createElement("div");
      wrap.className = "chest-section";
      if (!data.at_chest) {
        const hint = document.createElement("p");
        hint.className = "shop-empty";
        hint.textContent = "Walk to the chest inside the cabin to take or drop items.";
        wrap.appendChild(hint);
      }
      const open = chestSectionIsOpen();
      if (!open) wrap.classList.add("is-collapsed");
      const title = document.createElement("button");
      title.type = "button";
      title.className = "recipe-book-head chest-toggle";
      title.textContent = "CABIN CHEST";
      title.setAttribute("aria-expanded", open ? "true" : "false");
      const body = document.createElement("div");
      body.className = "chest-section-body";
      if (!open) body.hidden = true;
      renderChestCards(body, data, {sortable: true});
      title.addEventListener("click", function () {
        const next = body.hidden;
        body.hidden = !next;
        title.setAttribute("aria-expanded", next ? "true" : "false");
        wrap.classList.toggle("is-collapsed", !next);
        setChestSectionOpen(next);
      });
      wrap.appendChild(title);
      wrap.appendChild(body);
      parent.appendChild(wrap);
    }

    function appendTownStallSection(parent, data) {
      if (!data || !data.at_stall) return;
      const title = document.createElement("div");
      title.className = "shop-section-title";
      title.textContent = "Market stall";
      parent.appendChild(title);
      const slots = (data.stall || []).filter(function (s) { return s && s.item; });
      const note = document.createElement("p");
      note.className = "inv-slots";
      if (!slots.length) note.textContent = "The stall is empty. Put goods here; they sell when the day ends.";
      else note.textContent = "These goods sell when the day ends.";
      parent.appendChild(note);
      slots.forEach(function (slot) {
        appendItemCard(parent, slot, {take: true, canAct: !!data.your_turn, yourTurn: !!data.your_turn, data: data});
      });
      if (slots.length && data.your_turn) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn primary";
        const cost = (data.instant_sell_energy != null) ? data.instant_sell_energy : 50;
        btn.textContent = "Sell now (" + cost + " energy)";
        const me = (data.players || {})[PLAYER] || {};
        const haveE = (me.energy != null) ? me.energy : 0;
        btn.disabled = haveE < cost;
        btn.addEventListener("click", function () { actCmd("sell now"); });
        parent.appendChild(btn);
      }
    }

    function appendItemCard(parent, slot, opts) {
      opts = opts || {};
      if (!slot || !slot.item) return;
      const count = slot.count || 1;
      const row = document.createElement("div");
      row.className = "shop-card";
      const img = document.createElement("img");
      img.src = itemIconSrc(slot.item);
      img.alt = itemName(slot.item, count);
      row.appendChild(img);
      const body = document.createElement("div");
      const title = document.createElement("b");
      title.textContent = itemName(slot.item, count);
      body.appendChild(title);
      const btns = document.createElement("div");
      btns.className = "item-actions";
      const cabinTurn = !!opts.canAct;
      const yourTurn = !!opts.yourTurn;
      const atCabin = !!(opts.data && opts.data.in_cabin && opts.data.your_turn);
      const atStall = !!(opts.data && opts.data.at_stall && opts.data.your_turn);
      const atChest = !!(opts.data && opts.data.at_chest && opts.data.your_turn);
      const atFire = !!(opts.data && opts.data.at_fireplace && opts.data.your_turn);
      function addBtn(label, cmd, enabled) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn";
        btn.textContent = label;
        btn.disabled = !enabled;
        btn.addEventListener("click", function () { actCmd(cmd); });
        btns.appendChild(btn);
      }
      if (opts.take && atChest) {
        if (count <= 1) addBtn("Take", "take " + slot.item + " 1", true);
        else {
          addBtn("Take 1", "take " + slot.item + " 1", true);
          addBtn("Take all", "take " + slot.item + " all", true);
        }
      }
      if (opts.drop && atChest) {
        if (count <= 1) addBtn("Drop", "drop " + slot.item + " 1", true);
        else {
          addBtn("Drop 1", "drop " + slot.item + " 1", true);
          addBtn("Drop all", "drop " + slot.item + " all", true);
        }
      }
      if (opts.drop && yourTurn && !atChest && !atStall) {
        const noun1 = itemName(slot.item, 1);
        const bare = noun1.replace(/^1\s+/, "");
        if (count <= 1) addBtn("Drop " + bare, "drop " + slot.item + " 1", true);
        else {
          addBtn("Drop 1 " + bare, "drop " + slot.item + " 1", true);
          addBtn("Drop all " + itemName(slot.item, count).replace(/^\d+\s+/, ""), "drop " + slot.item + " all", true);
        }
      }
      const rec = recipeInfo(slot.item, opts.data);
      const crops = (opts.data && opts.data.crops) || {};
      const crop = crops[slot.item];
      const named = (opts.data && opts.data.item_names && opts.data.item_names[slot.item]) || {};
      const sellPrice = named.sell_price || (crop && crop.sell_price) || (rec && rec.sellable && rec.sell_price);
      if (opts.drop && atStall) {
        const unitHint = sellPrice ? (" (" + sellPrice + "G later)") : "";
        if (count <= 1) {
          addBtn("Put in stall" + unitHint, "drop " + slot.item + " 1", true);
        } else {
          addBtn("Put 1 in stall" + unitHint, "drop " + slot.item + " 1", true);
          const allHint = sellPrice ? (" (" + (sellPrice * count) + "G later)") : "";
          addBtn("Put all in stall" + allHint, "drop " + slot.item + " all", true);
        }
      }
      if (opts.take && atStall) {
        if (count <= 1) addBtn("Take back", "take " + slot.item + " 1", true);
        else {
          addBtn("Take 1 back", "take " + slot.item + " 1", true);
          addBtn("Take all back", "take " + slot.item + " all", true);
        }
      }
      const energy = snackEnergy(slot.item, opts.data);
      if (energy) {
        const eatCmd = opts.take ? ("eat " + slot.item + " chest") : ("eat " + slot.item);
        const me = (opts.data && opts.data.players && opts.data.players[PLAYER]) || {};
        const haveE = (me.energy != null) ? me.energy : 0;
        const foodCap = (opts.data && opts.data.base_energy != null && opts.data.base_energy > 0)
          ? opts.data.base_energy : 100;
        if (opts.take) {
          if (atChest && haveE < foodCap) addBtn("Eat (+" + energy + ")", eatCmd, true);
        } else if (yourTurn) {
          addBtn("Eat (+" + energy + ")", eatCmd, haveE < foodCap);
        }
      }
      if (slot.item === "herbal_tea") {
        const me = (opts.data && opts.data.players && opts.data.players[PLAYER]) || {};
        const drank = !!me.herbal_tea;
        if (opts.take) {
          if (atChest && !drank) addBtn("Drink (+10 tomorrow)", "drink herbal_tea chest", true);
        } else if (yourTurn) {
          addBtn("Drink (+10 tomorrow)", "drink herbal_tea", !drank);
        }
      }
      // Fuel actions are pack-only and only appear on the matching cabin tile,
      // never as a greyed-out placeholder.
      if (slot.item === "wood" && opts.drop && opts.data && opts.data.your_turn) {
        const viewers = (opts.data.players || {});
        const me = viewers[PLAYER] || {};
        const haveE = (me.energy != null) ? me.energy : 0;
        if (opts.data.at_fireplace) {
          const cost = (opts.data.fuel_fireplace_energy != null) ? opts.data.fuel_fireplace_energy : 5;
          if (!opts.data.fireplace_fueled && haveE >= cost) {
            addBtn("Fuel fireplace (" + cost + " energy)", "fuel fireplace", true);
          }
        } else if (opts.data.at_kitchen) {
          const cost = (opts.data.fuel_stove_energy != null) ? opts.data.fuel_stove_energy : 5;
          if (!opts.data.stove_fueled && haveE >= cost) {
            addBtn("Fuel stove (" + cost + " energy)", "fuel stove", true);
          }
        }
      }
      if (btns.childNodes.length) body.appendChild(btns);
      row.appendChild(body);
      parent.appendChild(row);
    }

    function renderRecipeBook(data) {
      const panel = $("recipe-book");
      const el = $("recipe-book-body");
      if (!el) return;
      const show = !!(data.at_chest || data.at_kitchen);
      if (panel) {
        panel.hidden = !show;
        if (!show) panel.open = false;
      }
      el.innerHTML = "";
      if (!show) return;
      if (data.at_kitchen && !data.stove_fueled) {
        const hint = document.createElement("p");
        hint.className = "shop-empty";
        hint.textContent = "The stove needs wood before you can cook today. Load wood from your backpack.";
        el.appendChild(hint);
        if (data.your_turn) {
          const load = document.createElement("button");
          load.type = "button";
          load.className = "btn";
          load.textContent = "Load wood";
          load.addEventListener("click", function () { actCmd("fuel stove"); });
          el.appendChild(load);
        }
      } else if (data.at_chest && !data.at_kitchen) {
        const hint = document.createElement("p");
        hint.className = "shop-empty";
        hint.textContent = "Walk to the kitchen inside the cabin to cook.";
        el.appendChild(hint);
      }
      const book = data.recipe_book || [];
      if (!book.length) {
        const empty = document.createElement("p");
        empty.className = "shop-empty";
        empty.textContent = "No recipes in the book yet.";
        el.appendChild(empty);
        return;
      }
      book.forEach(function (entry) {
        const row = document.createElement("div");
        row.className = "recipe-entry";
        const head = document.createElement("div");
        head.className = "recipe-entry-head";
        const icon = document.createElement("img");
        icon.src = itemIconSrc(entry.id);
        icon.alt = entry.name || entry.id;
        head.appendChild(icon);
        const title = document.createElement("b");
        title.textContent = entry.name || entry.id;
        head.appendChild(title);
        row.appendChild(head);
        const meta = document.createElement("div");
        meta.className = "recipe-meta";
        const bits = [];
        if (entry.ingredients_text) bits.push(entry.ingredients_text);
        if (entry.sell_price) bits.push("sells for " + entry.sell_price + "G");
        if (entry.eat_energy) bits.push("eat +" + entry.eat_energy + " energy");
        meta.textContent = bits.join(" · ");
        row.appendChild(meta);
        if (entry.missing) {
          const need = document.createElement("div");
          need.className = "recipe-meta";
          need.textContent = "Missing from the backpack — take them from the chest first.";
          row.appendChild(need);
        }
        if (entry.description) {
          const desc = document.createElement("div");
          desc.className = "recipe-meta";
          desc.textContent = entry.description;
          row.appendChild(desc);
        }
        if (data.at_kitchen && data.stove_fueled && entry.craftable && data.your_turn) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn";
          btn.textContent = "Craft";
          btn.addEventListener("click", function () { actCmd("craft " + entry.id); });
          row.appendChild(btn);
        }
        el.appendChild(row);
      });
    }

    function renderBackpack(data) {
      const el = $("inv");
      if (!el) return;
      el.innerHTML = "";
      el.classList.add("inv-panel");
      const title = document.createElement("div");
      title.className = "shop-section-title";
      title.textContent = "Backpack";
      el.appendChild(title);
      const pack = packSlotsOf(data);
      const held = pack.filter(function (s) { return s && s.item; });
      const open = pack.length ? pack.filter(function (s) { return !(s && s.item); }).length : Math.max(0, 4 - held.length);
      const meta = document.createElement("p");
      meta.className = "inv-slots";
      if (!held.length) meta.textContent = "The backpack is empty.";
      else if (open <= 0) meta.textContent = "Backpack is full.";
      else meta.textContent = open + " open slot" + (open === 1 ? "" : "s") + ".";
      if (held.length && !data.at_chest && !data.at_stall) {
        meta.textContent += data.in_cabin
          ? " Walk to the chest nook (row 1 col 2) to store items, or east to the market stall to sell."
          : " Walk to the cabin chest to store items, or east to the market stall to sell.";
      }
      el.appendChild(meta);
      const canAct = !!(data.your_turn && (data.at_chest || data.at_stall));
      held.forEach(function (slot) {
        appendItemCard(el, slot, {drop: true, canAct: canAct, yourTurn: !!data.your_turn, data: data});
      });
      appendTownStallSection(el, data);
    }

    function renderShop(data) {
      const shop = $("shop");
      if (!shop) return;
      shop.innerHTML = "";
      if (!data.at_store) {
        const note = document.createElement("p");
        note.className = "shop-empty";
        note.textContent = "Walk east from the cabin to the market town, then to the honour store (row 2 col 1). Leave coins in the tin to buy. The stall and forge are on this square too.";
        shop.appendChild(note);
      }
      const crops = data.crops || {};
      const season = (data.state && data.state.season) || "";
      const forSale = [];
      for (const [kind, info] of Object.entries(crops)) {
        const shopSeasons = (info.shop_seasons && info.shop_seasons.length) ? info.shop_seasons : (info.seasons || []);
        const flagged = info.for_sale;
        const inSeason = info.available !== false && (
          flagged === true || (flagged == null && shopSeasons.indexOf(season) !== -1)
        );
        if (inSeason) forSale.push([kind, info]);
      }
      if (!forSale.length) {
        const empty = document.createElement("p");
        empty.className = "shop-empty";
        empty.textContent = shopEmptyMessage(season);
        shop.appendChild(empty);
      } else {
        const title = document.createElement("div");
        title.className = "shop-section-title";
        title.textContent = "In season";
        shop.appendChild(title);
        forSale.forEach(function (pair) {
          appendShopCard(shop, data, pair[0], pair[1], {buy: true, sell: false});
        });
      }
      const fertilizers = data.fertilizers || {};
      const fertSale = [];
      for (const [item, info] of Object.entries(fertilizers)) {
        const shopSeasons = info.shop_seasons || [];
        if (shopSeasons.indexOf(season) !== -1) fertSale.push([item, info]);
      }
      if (fertSale.length) {
        const title = document.createElement("div");
        title.className = "shop-section-title";
        title.textContent = "Fertilizer";
        shop.appendChild(title);
        fertSale.forEach(function (pair) {
          appendShopCard(shop, data, pair[0], pair[1], {buy: true, sell: false});
        });
      }
      const staples = data.staples || {};
      const stapleSale = Object.keys(staples);
      if (stapleSale.length) {
        const title = document.createElement("div");
        title.className = "shop-section-title";
        title.textContent = "Staples";
        shop.appendChild(title);
        stapleSale.forEach(function (item) {
          appendShopCard(shop, data, item, staples[item], {buy: true, sell: false});
        });
      }
      const tools = data.tools || {};
      const toolSale = Object.keys(tools);
      if (toolSale.length) {
        const title = document.createElement("div");
        title.className = "shop-section-title";
        title.textContent = "Tools";
        shop.appendChild(title);
        toolSale.forEach(function (item) {
          appendToolCard(shop, data, item, tools[item]);
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
          const doneCmd = String(command || "").toLowerCase();
          if (doneCmd.indexOf("end turn") === 0 || doneCmd === "pass" || doneCmd.indexOf("pass ") === 0) {
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
      if (authStopped || chestBusy) return;
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
          pendingNoteAction = "end";
          if (Object.prototype.hasOwnProperty.call(data, "banner")) {
            showToast(data.banner || "", true);
          }
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

    let pendingNoteAction = "end";

    function noteText() {
      const box = $("end-note");
      let note = box ? box.value : "";
      note = String(note || "").replace(/\s+/g, " ").trim();
      if (note.length > 280) note = note.slice(0, 280).trim();
      return note;
    }

    function endTurnCommand() {
      const note = noteText();
      if (note) return "end turn " + note;
      return "end turn";
    }

    function passTurnCommand() {
      const note = noteText();
      if (note) return "pass turn: " + note;
      return "pass turn";
    }

    function submitEndTurn() {
      if (!needTurn()) return;
      endConfirm = false;
      plantPick = null;
      pendingNoteAction = "end";
      actCmd(endTurnCommand());
    }

    function submitPassTurn() {
      if (!needTurn()) return;
      endConfirm = false;
      plantPick = null;
      pendingNoteAction = "end";
      actCmd(passTurnCommand());
    }

    function submitNoteAction() {
      // Enter in the note field is always End turn — the primary action.
      // Pass is only triggered by the Pass turn button (which includes any note).
      if (!needTurn()) return;
      endConfirm = false;
      plantPick = null;
      pendingNoteAction = "end";
      actCmd(endTurnCommand());
    }

    $("end-turn").addEventListener("click", function () {
      submitEndTurn();
    });
    const passTurnBtn = $("pass-turn");
    if (passTurnBtn) {
      passTurnBtn.addEventListener("click", function () {
        submitPassTurn();
      });
    }
    const walkHomeBtn = $("walk-home");
    if (walkHomeBtn) {
      walkHomeBtn.addEventListener("click", function () {
        if (!needTurn()) return;
        const cmd = walkHomeBtn.getAttribute("data-cmd");
        if (!cmd) return;
        endConfirm = false;
        plantPick = null;
        actCmd(cmd);
      });
    }

    $("end-note").addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        ev.stopPropagation();
        submitNoteAction();
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

    function currentArea(data) {
      data = data || lastData;
      return viewArea(data) || (standingFrom(data) || {}).area || "farm";
    }
    function standingTile(data) {
      data = data || lastData;
      const stand = standingFrom(data);
      if (!stand) return null;
      const area = stand.area || viewArea(data);
      if (area === "farm") {
        const tiles = (data && data.state && data.state.tiles) || [];
        return (tiles[stand.r - 1] || [])[stand.c - 1] || null;
      }
      if (viewArea(data) === area) {
        const tiles = viewTiles(data);
        return (tiles[stand.r - 1] || [])[stand.c - 1] || null;
      }
      return null;
    }
    function standingHasForage(data) {
      const tile = standingTile(data);
      return !!(tile && tile.forage && tile.forage.kind);
    }
    function farmActionToast(verb, data) {
      const area = currentArea(data);
      const where = (area === "hills") ? "in the hills" : (area === "mine") ? "in the mine" : "here";
      showToast("There's nothing to " + verb + " here " + where + ".", false);
    }
    function runFarmKey(verb, send) {
      if (!needTurn() || !needHere()) return;
      if (currentArea(lastData) !== "farm") {
        farmActionToast(verb, lastData);
        return;
      }
      send();
    }
    function renderKeys(data) {
      const el = $("keys");
      if (!el) return;
      const area = currentArea(data);
      const walk = '<kbd>&uarr;</kbd><kbd>&darr;</kbd><kbd>&larr;</kbd><kbd>&rarr;</kbd> walk'
        + ' &middot; <kbd>1</kbd>&ndash;<kbd>9</kbd> walk to that plot';
      const shop = (data && data.at_store)
        ? ' &middot; <kbd>S</kbd> shop'
        : '';
      const common = shop
        + ' &middot; <kbd>J</kbd> journal'
        + ' &middot; <kbd>E</kbd> enter or interact'
        + ' &middot; <kbd>Shift</kbd>+<kbd>E</kbd> then <kbd>Enter</kbd> ends the turn'
        + ' &middot; <kbd>Enter</kbd> in the note box ends the turn (a note is sent too)'
        + ' &middot; <kbd>Esc</kbd> closes the shop, journal, saves, chest, or settings, or cancels unearth';
      let work;
      if (area === "hills") {
        work = ' &middot; <kbd>H</kbd> or <kbd>G</kbd> forage'
          + ' &middot; <kbd>C</kbd> chop'
          + ' &middot; <kbd>U</kbd> unearth'
          + ' &middot; <kbd>E</kbd> enter mine';
      } else if (area === "mine") {
        work = ' &middot; <kbd>E</kbd> climb'
          + ' &middot; <kbd>M</kbd> mine'
          + ' &middot; <kbd>R</kbd> rest'
          + ' &middot; <kbd>K</kbd> strike';
      } else if (area === "cabin") {
        work = ' &middot; <kbd>E</kbd> leave or interact';
      } else if (area === "town") {
        work = '';
      } else {
        work = ' &middot; <kbd>T</kbd> till'
          + ' &middot; <kbd>W</kbd> water'
          + ' &middot; <kbd>P</kbd> plant'
          + ' &middot; <kbd>H</kbd> harvest'
          + ' &middot; <kbd>Q</kbd> pluck a weed'
          + ' &middot; <kbd>U</kbd> unearth'
          + ' &middot; <kbd>F</kbd> fertilize'
          + ' &middot; <kbd>C</kbd> chop'
          + ' &middot; <kbd>G</kbd> forage'
          + ' &middot; <kbd>E</kbd> enter cabin';
      }
      el.innerHTML = walk + work + common;
    }

    function keyTill() {
      runFarmKey("till", function () { actCmd("till"); });
    }

    function keyWater() {
      runFarmKey("water", function () { actCmd("water"); });
    }

    function keyHarvest() {
      if (!needTurn() || !needHere()) return;
      const area = currentArea(lastData);
      if (area === "hills" && standingHasForage(lastData)) {
        actCmd("forage");
        return;
      }
      if (area !== "farm") {
        farmActionToast("harvest", lastData);
        return;
      }
      actCmd("harvest");
    }

    function keyPluck() {
      runFarmKey("pluck", function () { actCmd("pluck"); });
    }

    function standingCropName(data) {
      const stand = standingFrom(data);
      if (!stand || (stand.area && stand.area !== "farm")) return null;
      const tile = standingTile(data);
      const crop = tile && tile.crop;
      if (!crop || !crop.kind) return null;
      const info = cropInfo(crop.kind);
      let name = (info && info.name) || spacedName(crop.kind);
      if (crop.stage === "withered") name = "withered " + name;
      else if (crop.stage === "dormant") name = "dormant " + name;
      return name;
    }
    function standingUnearthName(data) {
      const stand = standingFrom(data);
      if (!stand) return null;
      if (!stand.area || stand.area === "farm") return standingCropName(data);
      if (stand.area === "hills") {
        const tile = standingTile(data);
        const stage = tile && tile.tree && tile.tree.stage;
        if (stage === "stump") return "stump";
        if (stage === "mushroom_log") return "mushroom log";
        return null;
      }
      return null;
    }

    function keyUnearth(immediate) {
      if (!needTurn() || !needHere()) return;
      const area = currentArea(lastData);
      if (area !== "farm" && area !== "hills") {
        unearthConfirm = false;
        farmActionToast("unearth", lastData);
        return;
      }
      const stand = standingFrom(lastData);
      const name = standingUnearthName(lastData);
      if (!name || !stand) {
        unearthConfirm = false;
        if (area === "hills") showToast("There's nothing to unearth here in the hills.", false);
        else showToast("Nothing to unearth here.", false);
        return;
      }
      if (immediate || unearthConfirm) {
        unearthConfirm = false;
        actCmd("unearth");
        return;
      }
      unearthConfirm = true;
      endConfirm = false;
      if (lastData) render(lastData);
      const costHint = area === "hills" ? " (20 energy)" : "";
      showToast("Unearth the " + name + " at r" + stand.r + " c" + stand.c + "?" + costHint + " Press U or Enter to confirm, Esc to cancel.", true);
    }

    function fertilizerKindsInPack(pack) {
      const bags = [];
      const seen = {};
      const map = {
        fertilizer_general: "general",
        fertilizer_yield: "yield",
        fertilizer_growth: "growth"
      };
      (pack || []).forEach(function (slot) {
        if (!slot || !slot.item || !map[slot.item] || seen[slot.item]) return;
        seen[slot.item] = true;
        bags.push(map[slot.item]);
      });
      return bags;
    }

    function keyFertilize() {
      if (!needTurn() || !needHere()) return;
      if (currentArea(lastData) !== "farm") {
        farmActionToast("fertilize", lastData);
        return;
      }
      const pack = (lastData && lastData.pack) || (lastData && lastData.state && lastData.state.players && lastData.viewer && lastData.state.players[lastData.viewer] && lastData.state.players[lastData.viewer].pack) || [];
      const kinds = fertilizerKindsInPack(pack);
      if (!kinds.length) {
        showToast("No fertilizer in the backpack.", false);
        return;
      }
      if (kinds.length === 1) {
        actCmd("fertilize " + kinds[0]);
        return;
      }
      actCmd("fertilize " + kinds[0]);
      showToast("Used " + kinds[0] + " fertilizer. Press F again after buying if you want a different bag.", true);
    }

    function keyPlant() {
      if (!needTurn() || !needHere()) return;
      if (currentArea(lastData) !== "farm") {
        farmActionToast("plant", lastData);
        return;
      }
      const kinds = seedKinds((lastData && lastData.state && lastData.state.inventory) || {});
      if (!kinds.length) {
        plantPick = null;
        render(lastData);
        showToast("No seeds in the backpack.", false);
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

    function focusNoteBox(action) {
      if (!needTurn()) return;
      pendingNoteAction = action || "end";
      const box = $("end-note");
      if (!box) {
        submitNoteAction();
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

    function legalCommands(data) {
      return (data && data.actions) || [];
    }
    function firstLegalCommand(cmds, data) {
      const legal = legalCommands(data || lastData);
      for (let i = 0; i < cmds.length; i++) {
        if (legal.indexOf(cmds[i]) !== -1) return cmds[i];
      }
      return null;
    }
    function fillDebugConsole(data) {
      const list = $("debug-cmd-list");
      const input = $("debug-cmd");
      const send = $("debug-cmd-send");
      const status = $("debug-cmd-status");
      if (!list || !input) return;
      const legal = legalCommands(data);
      list.innerHTML = "";
      legal.forEach(function (act) {
        const opt = document.createElement("option");
        opt.value = act;
        list.appendChild(opt);
      });
      const myTurn = !!(data && data.your_turn);
      input.disabled = !myTurn;
      if (send) send.disabled = !myTurn;
      if (status && status.getAttribute("data-hold") !== "1") {
        if (!myTurn) {
          const who = cap((data && data.current_player) || "the other player");
          status.textContent = "It's " + who + "'s turn right now.";
        } else if (!status.textContent || status.textContent.indexOf("turn right now") !== -1) {
          status.textContent = "";
        }
      }
    }
    function resolveLegalCommand(raw, data) {
      const legal = legalCommands(data);
      if (legal.indexOf(raw) !== -1) return raw;
      const low = raw.toLowerCase();
      const hits = legal.filter(function (act) { return act.toLowerCase() === low; });
      return hits.length === 1 ? hits[0] : null;
    }
    function submitDebugCommand(ev) {
      if (ev) ev.preventDefault();
      const input = $("debug-cmd");
      const status = $("debug-cmd-status");
      function setStatus(text) {
        if (!status) return;
        status.textContent = text || "";
        if (text) status.setAttribute("data-hold", "1");
        else status.removeAttribute("data-hold");
      }
      if (!input) return;
      const raw = (input.value || "").trim();
      const data = lastData;
      if (!data || !data.your_turn) {
        const who = cap((data && data.current_player) || "the other player");
        setStatus("It's " + who + "'s turn right now.");
        return;
      }
      if (!raw) {
        setStatus("Say what to do, like: enter mine");
        return;
      }
      // Send known typo-corrected legal commands when they match, otherwise
      // send what was typed so the server can print a specific refusal
      // (still growing, no axe, pack full) instead of going silent.
      const cmd = resolveLegalCommand(raw, data) || raw;
      setStatus("");
      input.value = "";
      actCmd(cmd);
    }

    function onKey(ev) {
      if (typingInField(ev)) return;
      if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
      const key = ev.key;
      const code = ev.code || "";

      if (key === "Escape") {
        ev.preventDefault();
        if (chestOpen && ($("chest-drag-ghost") || $("chest-item-menu") || chestBusy)) {
          cancelChestInteraction();
          return;
        }
        if (settingsOpen) {
          closeSettings();
          return;
        }
        if (chestOpen) {
          closeChest();
          return;
        }
        if (shopOpen) {
          closeShop();
          return;
        }
        if (journalOpen) {
          closeJournal();
          return;
        }
        if (savesOpen) {
          closeSaves();
          return;
        }
        if (endConfirm || plantPick || unearthConfirm) {
          endConfirm = false;
          unearthConfirm = false;
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
        if (unearthConfirm) {
          ev.preventDefault();
          keyUnearth(true);
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
        if (lastData && lastData.at_store) openShop();
        else showToast("Walk to the honour store (row 2 col 1) to shop.", true);
        return;
      }
      if (letter === "j") {
        ev.preventDefault();
        openJournal();
        return;
      }
      if (shopOpen || journalOpen || savesOpen) return;
      if (letter === "t") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        keyTill();
        return;
      }
      if (letter === "w") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
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
        unearthConfirm = false;
        plantPick = null;
        keyHarvest();
        return;
      }
      if (letter === "q") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        keyPluck();
        return;
      }
      if (letter === "c") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        actCmd("chop");
        return;
      }
      if (letter === "g") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        actCmd("forage");
        return;
      }
      if (letter === "u") {
        ev.preventDefault();
        endConfirm = false;
        plantPick = null;
        keyUnearth(false);
        return;
      }
      if (letter === "f") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        keyFertilize();
        return;
      }
      if (letter === "k") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        if (firstLegalCommand(["strike"])) actCmd("strike");
        else farmActionToast("strike", lastData);
        return;
      }
      if (letter === "m") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        if (firstLegalCommand(["mine"])) actCmd("mine");
        else farmActionToast("mine", lastData);
        return;
      }
      if (letter === "r") {
        ev.preventDefault();
        endConfirm = false;
        unearthConfirm = false;
        plantPick = null;
        if (!needTurn()) return;
        if (firstLegalCommand(["rest"])) actCmd("rest");
        else farmActionToast("rest", lastData);
        return;
      }
      if (letter === "e") {
        ev.preventDefault();
        plantPick = null;
        if (ev.shiftKey) {
          focusNoteBox();
          return;
        }
        const interact = firstLegalCommand([
          "enter cabin",
          "leave cabin",
          "enter mine",
          "climb down",
          "climb up",
          "leave mine",
          "fuel fireplace",
          "fuel stove"
        ]);
        if (interact) {
          unearthConfirm = false;
          endConfirm = false;
          actCmd(interact);
          return;
        }
        const data = lastData || {};
        if (data.at_kitchen) {
          const book = $("recipe-book");
          if (book) { book.hidden = false; book.open = true; }
          if (!data.stove_fueled) {
            showToast("The stove needs wood first. Load wood from your backpack.", true);
          } else {
            showToast("The kitchen. Open the recipe book to cook.", true);
          }
          return;
        }
        if (data.at_chest || data.at_chest_site) {
          openChest();
          return;
        }
        return;
      }
    }

    document.addEventListener("keydown", onKey);
    const debugForm = $("debug-console");
    if (debugForm) debugForm.addEventListener("submit", submitDebugCommand);
    const openBtn = $("open-shop");
    if (openBtn) openBtn.addEventListener("click", function () { openShop(); });
    const closeBtn = $("shop-close");
    if (closeBtn) closeBtn.addEventListener("click", function () { closeShop(); });
    const backdrop = $("shop-backdrop");
    if (backdrop) backdrop.addEventListener("click", function () { closeShop(); });
    const openChestBtn = $("open-chest");
    if (openChestBtn) openChestBtn.addEventListener("click", function () { openChest(); });
    const closeChestBtn = $("chest-close");
    if (closeChestBtn) closeChestBtn.addEventListener("click", function () { closeChest(); });
    const chestBackdrop = $("chest-backdrop");
    if (chestBackdrop) chestBackdrop.addEventListener("click", function () { closeChest(); });
    const openJournalBtn = $("open-journal");
    if (openJournalBtn) openJournalBtn.addEventListener("click", function () { openJournal(); });
    const closeJournalBtn = $("journal-close");
    if (closeJournalBtn) closeJournalBtn.addEventListener("click", function () { closeJournal(); });
    const journalBackdrop = $("journal-backdrop");
    if (journalBackdrop) journalBackdrop.addEventListener("click", function () { closeJournal(); });
    const openSavesBtn = $("open-saves");
    if (openSavesBtn) openSavesBtn.addEventListener("click", function () { openSaves(); });
    const closeSavesBtn = $("saves-close");
    if (closeSavesBtn) closeSavesBtn.addEventListener("click", function () { closeSaves(); });
    const savesBackdrop = $("saves-backdrop");
    if (savesBackdrop) savesBackdrop.addEventListener("click", function () { closeSaves(); });
    const openSettingsBtn = $("open-settings");
    if (openSettingsBtn) openSettingsBtn.addEventListener("click", function () { openSettings(); });
    const closeSettingsBtn = $("settings-close");
    if (closeSettingsBtn) closeSettingsBtn.addEventListener("click", function () { closeSettings(); });
    const settingsBackdrop = $("settings-backdrop");
    if (settingsBackdrop) settingsBackdrop.addEventListener("click", function () { closeSettings(); });
    const autopassBox = $("settings-autopass");
    if (autopassBox) autopassBox.addEventListener("change", function () {
      syncAutopassOptionsEnabled();
      saveSettings();
    });
    const autopassMax = $("settings-autopass-max");
    if (autopassMax) autopassMax.addEventListener("change", function () { saveSettings(); });
    const autopassTimeout = $("settings-autopass-timeout");
    if (autopassTimeout) autopassTimeout.addEventListener("change", function () { saveSettings(); });
    const newSaveBtn = $("saves-new");
    if (newSaveBtn) newSaveBtn.addEventListener("click", function () { startNewFarm(); });
    const newSaveName = $("saves-new-name");
    if (newSaveName) newSaveName.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); startNewFarm(); }
    });
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


def _tool_tiers_payload(state: dict | None) -> dict:
    from mine import FORGE_TOOLS, tool_tier
    if not state:
        return {item: "basic" for item in FORGE_TOOLS}
    return {item: tool_tier(state, item) for item in FORGE_TOOLS}


def _item_name_catalog(crops: dict, rules: dict | None = None, state: dict | None = None) -> dict:
    """Human names (with spaces) for every known item, used by the web UI."""
    from inventory import FERTILIZERS, TOOLS, EQUIPMENT, recipes, item_name
    from engine import stock_key
    from inventory import STAPLES, MATERIALS, FORAGE_ITEMS, item_eat_energy, item_sell_price
    keys = list(TOOLS) + list(EQUIPMENT) + list(FERTILIZERS) + list(STAPLES) + list(MATERIALS) + list(FORAGE_ITEMS) + list(recipes(rules))
    for kind, info in (crops.get("crops") or {}).items():
        keys.append(kind)
        keys.append(stock_key(kind, info))
    out = {}
    for key in keys:
        one = item_name(key, 1, crops, rules, state=state)
        many = item_name(key, 2, crops, rules, state=state)
        # item_name prefixes the count ("1 strawberry jam").
        name = one.split(" ", 1)[-1] if one else key.replace("_", " ")
        name_plural = many.split(" ", 1)[-1] if many else name + "s"
        entry = {"name": name, "name_plural": name_plural}
        energy = item_eat_energy(key, crops, rules)
        if energy:
            entry["eat_energy"] = int(energy)
        sell = item_sell_price(key, crops, rules)
        if sell:
            entry["sell_price"] = int(sell)
        out[key] = entry
    return out


def _recipe_catalog(rules: dict | None = None) -> dict:
    """Crafted foods the UI can sell or eat from a backpack or chest row."""
    from inventory import recipes, recipe_is_sellable
    out = {}
    for item, rec in recipes(rules).items():
        sell = rec.get("sell_price") if recipe_is_sellable(item, rec) else None
        eat = rec.get("eat_energy")
        try:
            sell = int(sell) if sell is not None else None
        except (TypeError, ValueError):
            sell = None
        try:
            eat = int(eat) if eat is not None else None
        except (TypeError, ValueError):
            eat = None
        out[item] = {
            "name": rec.get("name") or item.replace("_", " "),
            "sell_price": sell,
            "eat_energy": eat,
        }
    return out


def _tool_shop_catalog(state: dict, rules: dict | None = None) -> dict:
    """Shop tools and equipment that should appear in the Tools section of the web shop."""
    from mine import pickaxe_unlocked, pickaxe_count, pickaxe_price
    from inventory import (
        TOOL_PICKAXE,
        TOOLS,
        EQUIPMENT,
        SLEEPING_BAG,
        equipment_info,
        sleeping_bag_price,
    )

    out = {}
    gold = int(state.get("gold") or 0)
    bag = equipment_info(SLEEPING_BAG, rules) or EQUIPMENT[SLEEPING_BAG]
    bag_price = sleeping_bag_price(rules)
    out[SLEEPING_BAG] = {
        "name": bag.get("name") or "sleeping bag",
        "name_plural": bag.get("name_plural") or "sleeping bags",
        "shop_name": bag.get("name") or "sleeping bag",
        "stock": "",
        "seed_price": int(bag_price),
        "price": int(bag_price),
        "sell_price": None,
        "available": True,
        "affordable": gold >= int(bag_price),
        "unique": False,
        "description": bag.get("description") or "",
    }
    if not pickaxe_unlocked(state) or pickaxe_count(state, rules) >= 2:
        return out
    price = pickaxe_price(rules)
    info = TOOLS.get(TOOL_PICKAXE) or {}
    out[TOOL_PICKAXE] = {
        "name": info.get("name") or "pickaxe",
        "name_plural": info.get("name_plural") or "pickaxes",
        "shop_name": info.get("name") or "pickaxe",
        "stock": "",
        "seed_price": int(price),
        "price": int(price),
        "sell_price": None,
        "available": True,
        "affordable": gold >= int(price),
        "unique": True,
        "description": (
            "A stout pickaxe for prying open the boarded mine entrance and breaking rock."
        ),
    }
    return out



def _staple_catalog(rules: dict | None = None) -> dict:
    from inventory import staple_shop_items, staple_info, STAPLES
    seasons = ["spring", "summer", "autumn", "winter"]
    out = {}
    for item in staple_shop_items(rules):
        info = staple_info(item, rules) or STAPLES[item]
        out[item] = {
            "name": info.get("name") or item.replace("_", " "),
            "name_plural": info.get("name_plural") or "",
            "shop_name": info.get("name") or item.replace("_", " "),
            "stock": "",
            "seed_price": int(info.get("price") or 0),
            "sell_price": int(info.get("sell_price") or 0),
            "eat_energy": int(info["eat_energy"]) if info.get("eat_energy") is not None else None,
            "available": True,
            "seasons": list(seasons),
            "shop_seasons": list(seasons),
            "description": info.get("description") or "",
        }
    return out


def _recipe_book_payload(state: dict, crops: dict, rules: dict | None, player: str | None) -> list[dict]:
    from inventory import recipes, recipe_is_sellable
    from engine import (
        ensure_discovered_recipes,
        discovered_recipe_ids,
        recipe_is_craftable,
        pack_item_counts,
        recipe_ingredient_rows,
        format_ingredient_have_need,
        is_player_in_cabin,
    )
    ensure_discovered_recipes(state, rules)
    recs = recipes(rules)
    out = []
    from cabin import player_at_cabin_tile
    at_kitchen = bool(player and player_at_cabin_tile(state, player, "kitchen"))
    pack_counts = pack_item_counts(state, player, rules)
    for rec_id in discovered_recipe_ids(state, rules):
        rec = recs.get(rec_id) or {}
        rows = recipe_ingredient_rows(rec, pack_counts, crops, rules)
        sell = rec.get("sell_price") if recipe_is_sellable(rec_id, rec) else None
        eat = rec.get("eat_energy")
        try:
            sell = int(sell) if sell is not None else None
        except (TypeError, ValueError):
            sell = None
        try:
            eat = int(eat) if eat is not None else None
        except (TypeError, ValueError):
            eat = None
        missing = [row for row in rows if int(row["have"]) < int(row["need"])]
        out.append({
            "id": rec_id,
            "name": rec.get("name") or rec_id.replace("_", " "),
            "ingredients_text": format_ingredient_have_need(rows),
            "ingredients": rows,
            "description": rec.get("description") or "",
            "sell_price": sell,
            "eat_energy": eat,
            "missing": bool(missing),
            "craftable": at_kitchen and stove_is_fueled(state) and recipe_is_craftable(state, rec_id, player, rules, crops),
        })
    return out


def _fertilizer_catalog(rules: dict | None = None) -> dict:
    from inventory import FERTILIZERS, FERTILIZER_SHOP_SEASONS, fertilizer_info
    out = {}
    for item in FERTILIZERS:
        info = fertilizer_info(item, rules) or FERTILIZERS[item]
        out[item] = {
            "name": info["name"],
            "shop_name": info["name"],
            "stock": "bag",
            "seed_price": int(info["price"]),
            "sell_price": 0,
            "available": True,
            "seasons": list(FERTILIZER_SHOP_SEASONS),
            "shop_seasons": list(FERTILIZER_SHOP_SEASONS),
            "description": info.get("description") or "",
        }
    return out


def _crop_catalog(crops: dict, state: dict | None = None) -> dict:
    from engine import shop_name, crop_for_sale, crop_viable_days_left, crop_shop_uses_override
    out = {}
    season = (state or {}).get("season")
    day = (state or {}).get("day")
    for kind, info in crops.get("crops", {}).items():
        uses_override = crop_shop_uses_override(info)
        growing = list(info["seasons"])
        out[kind] = {
            "name": info.get("name") or kind,
            "name_plural": info.get("name_plural") or "",
            "shop_name": shop_name(kind, info),
            "stock": info.get("stock") or "seed",
            "seed_price": int(info["seed_price"]),
            "sell_price": int(info["sell_price"]),
            "grow_days": int(info["grow_days"]),
            "regrow_days": int(info.get("regrow_days") or 0),
            "available": info.get("available", True) is not False,
            "seasons": growing,
            # Annual leftover shop_seasons in crops.json are not the sale window.
            "shop_seasons": list(info.get("shop_seasons") or []) if uses_override else growing,
            "shop_uses_override": uses_override,
            "for_sale": crop_for_sale(info, season, day=day, crops=crops),
            "viable_days_left": crop_viable_days_left(info, season, day=day, crops=crops),
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


def _payload_view_tiles(view_tiles, crops: dict, state=None, area: str | None = None, floor: int | None = None):
    """Copy tiles for the client and attach an honest progress phrase to crops.

    The live save tiles are left untouched. Ground stacks are copied onto
    the payload tiles so the This tile panel can list them.
    """
    from describe import crop_progress_phrase
    from engine import crop_info
    from inventory import ground_of

    rows = []
    for r, row in enumerate(view_tiles or [], 1):
        new_row = []
        for c, tile in enumerate(row, 1):
            if not isinstance(tile, dict):
                new_row.append(tile)
                continue
            copied = dict(tile)
            crop = copied.get("crop")
            if isinstance(crop, dict):
                crop = dict(crop)
                info = crop_info(crops, crop.get("kind")) or {}
                crop["progress_phrase"] = crop_progress_phrase(crop, info)
                copied["crop"] = crop
            if state is not None and area:
                copied["ground"] = [
                    {"item": slot["item"], "count": int(slot.get("count") or 0)}
                    for slot in ground_of(state, area, r, c, floor)
                    if slot and slot.get("item")
                ]
            new_row.append(copied)
        rows.append(new_row)
    return rows


def ready_labels_for(state: dict) -> dict:
    """Map player id -> short ready label for the HUD, omitting the current player."""
    from engine import player_ready_line, normalize_player, known_players
    from config import display_name
    current = normalize_player(state.get("current_player"))
    labels = {}
    for name in known_players():
        if name == current:
            continue
        line = player_ready_line(state, name)
        if not line:
            continue
        prefix = display_name(name) + " "
        labels[name] = line[len(prefix):] if line.startswith(prefix) else line
    return labels


def api_payload(
    state: dict,
    crops: dict,
    ok: bool = True,
    message: str = "",
    player: str | None = None,
) -> dict:
    from autopass import public_autopass, format_away_summary, autopass_of

    rules = load_rules()
    migrate_state(state, rules)
    viewer = _web_player(player)
    from config import starting_player
    from engine import recent_notes, year_for_day, discovered_recipe_ids
    current = normalize_player(state.get("current_player")) or starting_player()
    sky = state.get("weather") or "sun"
    from hills import (
        player_area, AREA_HILLS, AREA_FARM, AREA_MINE, AREA_CABIN, AREA_TOWN, hills_tiles, elsewhere_lines,
        area_title, hills_summary, farm_summary, exit_summary, max_hp as hills_max_hp,
        describe_where as describe_area_where, player_hp,
    )
    from mine import player_floor, get_floor, ensure_mine
    from cabin import cabin_tiles, player_at_cabin_tile
    from town import (
        ensure_town, town_tiles, stall_of, is_player_at_stall, is_player_at_store,
        is_player_at_forge, instant_sell_energy,
    )
    ensure_town(state, rules)
    view_area = player_area(state, viewer) if viewer else AREA_FARM
    view_floor = player_floor(state, viewer) if viewer and view_area == AREA_MINE else None
    if view_area == AREA_HILLS and hills_tiles(state):
        view_tiles = hills_tiles(state)
    elif view_area == AREA_MINE and view_floor:
        ensure_mine(state)
        view_tiles = get_floor(state, view_floor)["tiles"]
    elif view_area == AREA_CABIN:
        view_tiles = cabin_tiles(state)
    elif view_area == AREA_TOWN and town_tiles(state):
        view_tiles = town_tiles(state)
    else:
        view_tiles = state["tiles"]
        if view_area not in (AREA_FARM, AREA_HILLS, AREA_MINE, AREA_CABIN, AREA_TOWN):
            view_area = AREA_FARM
    view_tiles = _payload_view_tiles(view_tiles, crops, state=state, area=view_area, floor=view_floor)
    sprites = [
        [sprite_key(tile, sky, r + 1, c + 1, floor=view_floor if view_area == AREA_MINE else None, state=state) for c, tile in enumerate(row)]
        for r, row in enumerate(view_tiles)
    ]
    actions = legal_actions(state, crops, player=viewer, rules=rules)
    places = {}
    hp_map = {}
    for name, slot in (state.get("players") or {}).items():
        prow = int(slot.get("row") or 0)
        pcol = int(slot.get("col") or 0)
        floor = player_floor(state, name)
        places[name] = describe_area_where(player_area(state, name), prow, pcol, floor=floor)
        hp_map[name] = list(player_hp(state, name, rules))
    homesick_map = {}
    for name, slot in (state.get("players") or {}).items():
        try:
            homesick_map[name] = max(0, int((slot or {}).get("homesickness") or 0))
        except (TypeError, ValueError):
            homesick_map[name] = 0
    return {
        "ok": ok,
        "message": message,
        "banner": viewer_status_banner(state, viewer, crops, rules),
        "state": state,
        "sprites": sprites,
        "view_area": view_area,
        "view_floor": view_floor,
        "view_tiles": view_tiles,
        "area_title": area_title(view_area, floor=view_floor),
        "elsewhere": elsewhere_lines(state, viewer, crops),
        "hills_summary": hills_summary(state),
        "farm_summary": farm_summary(state, crops),
        "exit_summary": exit_summary(view_area),
        "places": places,
        "hp": hp_map,
        "homesickness": homesick_map,
        "max_hp": hills_max_hp(rules),
        "actions": actions,
        "action_lines": {
            cmd: format_legal_action(cmd, state, crops, viewer, rules)
            for cmd in actions
        },
        "saves": __import__("saves").public_payload(),
        "look": describe_state(state, crops, viewer=viewer),
        "crops": _crop_catalog(crops, state),
        "viewer": viewer,
        "current_player": current,
        "players": state.get("players") or {},
        "max_energy": player_energy_cap(state, viewer, rules) if viewer else max_energy(rules),
        "base_energy": max_energy(rules),
        "your_turn": viewer == current,
        "forecast": weather_forecast(state, crops, rules),
        "sleep_outlook": sleep_outlook(state, viewer, rules) if viewer else "",
        "in_cabin": is_player_in_cabin(state, viewer) if viewer else False,
        "in_cabin_interior": bool(viewer and player_area(state, viewer) == AREA_CABIN),
        "at_kitchen": bool(viewer and player_at_cabin_tile(state, viewer, "kitchen")),
        "ready_labels": ready_labels_for(state),
        "at_chest": bool(viewer and player_at_cabin_tile(state, viewer, "chest")),
        "at_chest_site": bool(viewer and __import__("chest").player_at_build_tile(state, viewer, rules)),
        "chest_info": __import__("chest").public_chest(state, rules),
        "at_fireplace": bool(viewer and player_at_cabin_tile(state, viewer, "fireplace")),
        "at_stall": bool(viewer and is_player_at_stall(state, viewer)),
        "at_store": bool(viewer and is_player_at_store(state, viewer)),
        "at_forge": bool(viewer and is_player_at_forge(state, viewer)),
        "stall": stall_of(state),
        "instant_sell_energy": instant_sell_energy(rules),
        "fireplace_fueled": bool(state.get("fireplace_fueled")),
        "fuel_fireplace_energy": energy_cost("fuel_fireplace", rules),
        "stove_fueled": bool(state.get("stove_fueled")),
        "fuel_stove_energy": energy_cost("fuel_stove", rules),
        "cabin": [CABIN_ROW, CABIN_COL],
        "pack": (state.get("players") or {}).get(viewer or "", {}).get("pack") or [],
        "chest": (__import__("chest").public_chest(state, rules).get("items") or []),
        "fertilizers": _fertilizer_catalog(rules),
        "item_names": _item_name_catalog(crops, rules, state),
        "tool_tiers": _tool_tiers_payload(state),
        "recipes": _recipe_catalog(rules),
        "staples": _staple_catalog(rules),
        "tools": _tool_shop_catalog(state, rules),
        "recipe_book": _recipe_book_payload(state, crops, rules, viewer),
        "discovered_recipes": discovered_recipe_ids(state, rules),
        "year": year_for_day(int(state.get("day") or 1), crops),
        "recent_notes": recent_notes(state),
        "autopass": public_autopass(state, viewer) if viewer else None,
        "away_summary": (
            format_away_summary(state, viewer)
            if viewer and autopass_of(state, viewer).get("away_pending")
            else ""
        ),
    }


def run_autopass_if_due(path=None, notify: bool = True):
    """End an idle, autopass-enabled turn if its timeout has elapsed.

    Saves only when a turn is actually ended, so a poll or tick does not
    rewrite the farm on every check.
    """
    from autopass import autopass_due, maybe_apply_autopass
    from engine import session

    with session(write=False, path=path) as (state, crops):
        if not autopass_due(state):
            return False, ""
    applied = False
    msg = ""
    ended_for = None
    with session(write=True, path=path) as (state, crops):
        applied, msg, ended_for = maybe_apply_autopass(state, crops)
    if applied and notify:
        maybe_notify_after_end_turn(ended_for, state, True, state_path=path)
    return applied, msg


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
            run_autopass_if_due()
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
        if path not in {"/api/do", "/api/saves", "/api/settings"}:
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
        if path == "/api/settings":
            from autopass import set_autopass_settings, acknowledge_away_summary
            with session(write=True) as (state, crops):
                raw_ap = data.get("autopass") if isinstance(data.get("autopass"), dict) else {}
                # Only the documented fields; never store unexpected keys.
                kwargs = {}
                if "enabled" in raw_ap:
                    kwargs["enabled"] = bool(raw_ap.get("enabled"))
                if "max_turns" in raw_ap:
                    kwargs["max_turns"] = raw_ap.get("max_turns")
                if "timeout_minutes" in raw_ap:
                    kwargs["timeout_minutes"] = raw_ap.get("timeout_minutes")
                if kwargs:
                    set_autopass_settings(state, player, **kwargs)
                if data.get("acknowledge_away"):
                    acknowledge_away_summary(state, player)
                payload = api_payload(state, crops, True, "", player=player)
        elif path == "/api/saves":
            import saves
            saves.maybe_migrate_live()
            action = str(data.get("action") or data.get("command") or "list").strip().lower()
            name = data.get("name")
            slot = data.get("slot")
            confirm = bool(data.get("confirm"))
            if action == "list":
                ok, message = True, ""
            elif action == "new":
                ok, message, _sid = saves.new_slot(str(name or ""))
            elif action == "load":
                if not confirm:
                    ok, message = False, "Switching farms needs confirmation."
                else:
                    ok, message, _sid = saves.load_slot(str(slot or name or ""))
            elif action == "rename":
                ok, message, _sid = saves.rename_slot(str(slot or ""), str(name or ""))
            else:
                ok, message = False, "Unknown saves action. Use list, new, load, or rename."
            with session(write=False) as (state, crops):
                payload = api_payload(state, crops, ok, message, player=player)
        else:
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
    import saves
    saves.maybe_migrate_live()
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
            try:
                run_autopass_if_due()
            except Exception:
                sys.stderr.write("Autopass tick failed\n")
            time.sleep(30)
    except KeyboardInterrupt:
        sys.stdout.write("\nStopping.\n")
        for _host, httpd in servers:
            httpd.shutdown()


if __name__ == "__main__":
    serve()

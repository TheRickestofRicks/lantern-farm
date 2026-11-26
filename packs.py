"""Painted art packs for the web page.

The original procedural SVG tiles stay the default. A pack may supply a
ground tile, a crop overlay, and a weed overlay for a sprite key. If any
layer a key needs is missing, the page falls back to the SVG for that tile.
"""

from __future__ import annotations

import json
from pathlib import Path

from sprites import parse_sprite_key

ROOT = Path(__file__).resolve().parent
PACKS_ROOT = ROOT / "static" / "packs"
ALLOWED_STATIC_SUFFIXES = {".png", ".json"}
CLASSIC_PACK = {
    "id": "classic",
    "name": "Classic",
    "description": "The original procedural SVG tiles.",
}


def _pack_dir(pack_id: str) -> Path | None:
    name = (pack_id or "").strip()
    if not name or name.startswith(".") or "/" in name or "\\" in name or name != Path(name).name:
        return None
    path = (PACKS_ROOT / name).resolve()
    try:
        path.relative_to(PACKS_ROOT.resolve())
    except ValueError:
        return None
    if not path.is_dir():
        return None
    return path


def load_manifest(pack_id: str) -> dict | None:
    folder = _pack_dir(pack_id)
    if folder is None:
        return None
    path = folder / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("id", pack_id)
    data.setdefault("name", pack_id)
    data.setdefault("description", "")
    data.setdefault("grounds", {})
    data.setdefault("overlays", {})
    data.setdefault("items", {})
    if not isinstance(data["grounds"], dict) or not isinstance(data["overlays"], dict):
        return None
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data


def public_packs() -> list[dict]:
    """Pack list injected into the page: Classic first, then any installed packs."""
    packs = [dict(CLASSIC_PACK)]
    if not PACKS_ROOT.is_dir():
        return packs
    seen = {CLASSIC_PACK["id"]}
    for child in sorted(PACKS_ROOT.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name in seen:
            continue
        man = load_manifest(child.name)
        if not man:
            continue
        packs.append({
            "id": man["id"],
            "name": man.get("name") or man["id"],
            "description": man.get("description") or "",
            "grounds": man.get("grounds") or {},
            "overlays": man.get("overlays") or {},
            "cabins": man.get("cabins") or {},
            "items": man.get("items") or {},
        })
        seen.add(man["id"])
    return packs


def ground_key_for(parsed: dict) -> str | None:
    kind = (parsed or {}).get("kind")
    if kind in {None, "cabin", "unknown"}:
        return None
    typ = parsed.get("type") or kind
    if parsed.get("kind") == "cabin_interior":
        return "cabin_floor"
    if parsed.get("mine") or typ in {"mine_floor", "mine_safe"}:
        return typ
    if parsed.get("hills"):
        typ = parsed.get("type") or kind
        if typ == "mine_entrance":
            base = "mine_entrance_closed" if parsed.get("closed") else "mine_entrance"
        elif typ == "hillside":
            base = "hillside"
        else:
            base = "hills_grass"
        if parsed.get("snow"):
            return f"{base}_snow"
        return base
    if kind == "soil":
        if parsed.get("tilled") and parsed.get("watered"):
            base = "soil_watered"
        elif parsed.get("tilled"):
            base = "soil_tilled"
        elif parsed.get("watered"):
            base = "soil_wet"
        else:
            base = "soil"
    elif parsed.get("watered"):
        base = "soil_watered"
    else:
        base = "soil_tilled"
    if parsed.get("snow"):
        return f"{base}_snow"
    return base



def crop_overlay_key(parsed: dict) -> str | None:
    kind = (parsed or {}).get("kind")
    stage = (parsed or {}).get("stage")
    if not kind or kind in {"soil", "cabin", "unknown"} or not stage:
        return None
    return f"{kind}_{stage}"


def weed_overlay_key(parsed: dict) -> str | None:
    if (parsed or {}).get("weedy"):
        return "weedy"
    if (parsed or {}).get("weed"):
        return "weed"
    return None


def _pack_file(manifest: dict, rel: str) -> str | None:
    pack_id = manifest.get("id") or ""
    folder = _pack_dir(pack_id)
    if folder is None or not rel or not isinstance(rel, str):
        return None
    if rel.startswith("/") or ".." in Path(rel).parts:
        return None
    path = (folder / rel).resolve()
    try:
        path.relative_to(folder.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return rel


def layers_for_key(key: str, manifest: dict | None) -> list[dict] | None:
    """Return stacked layers for a sprite key, or None to use the default SVG.

    Each layer is ``{"role": "ground"|"fertilizer"|"crop"|"vine"|"weed", "file": "grounds/soil.png"}``.
    Cabin tiles and any key missing a required layer fall back to the SVG.
    """
    if not manifest or manifest.get("id") in {None, "", "classic"}:
        return None
    parsed = parse_sprite_key(key)
    if parsed.get("kind") == "unknown":
        return None
    if parsed.get("kind") == "cabin":
        cabins = manifest.get("cabins") or {}
        weather = parsed.get("weather") or "sun"
        ckey = "cabin" if weather in {"sun", ""} else f"cabin_{weather}"
        cfile = _pack_file(manifest, cabins.get(ckey) or "") or _pack_file(
            manifest, cabins.get("cabin") or ""
        )
        if not cfile:
            return None
        layers = [{"role": "cabin", "file": cfile}]
        if parsed.get("fire"):
            overlays = manifest.get("overlays") or {}
            sfile = _pack_file(manifest, overlays.get("cabin_smoke") or "")
            if sfile:
                layers.append({"role": "smoke", "file": sfile})
        return layers
    grounds = manifest.get("grounds") or {}
    overlays = manifest.get("overlays") or {}
    layers: list[dict] = []
    gkey = ground_key_for(parsed)
    if not gkey:
        return None
    gfile = _pack_file(manifest, grounds.get(gkey) or "")
    if not gfile and gkey.endswith("_snow"):
        # Missing snowy ground still uses the pack's ordinary soil so crops can layer.
        gfile = _pack_file(manifest, grounds.get(gkey[: -len("_snow")]) or "")
    if not gfile:
        return None
    layers.append({"role": "ground", "file": gfile})
    typ = parsed.get("type") or parsed.get("kind")
    if parsed.get("kind") == "cabin_interior":
        tile = parsed.get("tile") or "floor"
        if tile != "floor":
            if parsed.get("fire") and tile in {"fireplace", "kitchen"}:
                name = f"cabin_{tile}_lit"
            else:
                name = f"cabin_{tile}"
            ffile = _pack_file(manifest, overlays.get(name) or "")
            if not ffile:
                return None
            layers.append({"role": "crop", "file": ffile})
        return layers
    if parsed.get("mine") or typ in {"mine_floor", "mine_safe"}:
        def add_ov(name: str, role: str = "crop") -> bool:
            ffile = _pack_file(manifest, overlays.get(name) or "")
            if not ffile:
                return False
            layers.append({"role": role, "file": ffile})
            return True
        rock = parsed.get("rock")
        if rock:
            if rock == "copper_ore":
                okey = "mine_rock_copper"
            elif rock == "iron_ore":
                okey = "mine_rock_iron"
            elif rock == "gold_ore":
                okey = "mine_rock_gold"
            else:
                okey = "mine_rock"
            if not add_ov(okey):
                return None
        else:
            if parsed.get("ladder") == "open" and not add_ov("mine_ladder"):
                return None
            if parsed.get("ladder_up"):
                if not add_ov("mine_ladder_up"):
                    return None
            elif parsed.get("exit") or parsed.get("shaft"):
                if not add_ov("mine_shaft"):
                    return None
            if parsed.get("lantern") and not add_ov("mine_lantern"):
                return None
            if parsed.get("elevator") and not add_ov("mine_elevator"):
                return None
        return layers
    fert = parsed.get("fertilizer")
    if fert:
        ffile = _pack_file(manifest, overlays.get(f"fertilizer_{fert}") or "")
        if ffile:
            layers.append({"role": "fertilizer", "file": ffile})
    if parsed.get("hills"):
        if typ_tree := parsed.get("tree"):
            tfile = _pack_file(manifest, overlays.get(f"tree_{typ_tree}") or "")
            if not tfile:
                return None
            layers.append({"role": "crop", "file": tfile})
        if typ_forage := parsed.get("forage"):
            ffile = _pack_file(manifest, overlays.get(f"forage_{typ_forage}") or "")
            if not ffile:
                return None
            layers.append({"role": "crop", "file": ffile})
        return layers
    ckey = crop_overlay_key(parsed)
    if ckey:
        cfile = _pack_file(manifest, overlays.get(ckey) or "")
        if not cfile:
            return None
        layers.append({"role": "crop", "file": cfile})
    vine = parsed.get("vine")
    if vine:
        vfile = _pack_file(manifest, overlays.get(f"vine_{vine}") or "")
        if vfile:
            layers.append({"role": "vine", "file": vfile})
    wkey = weed_overlay_key(parsed)
    if wkey:
        wfile = _pack_file(manifest, overlays.get(wkey) or "")
        if not wfile:
            return None
        layers.append({"role": "weed", "file": wfile})
    return layers


def safe_pack_file(url_path: str) -> Path | None:
    """Resolve a ``/static/packs/...`` URL to a file inside PACKS_ROOT, or None."""
    path = (url_path or "").split("?", 1)[0]
    prefix = "/static/packs/"
    if not path.startswith(prefix):
        return None
    rel = path[len(prefix):]
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        return None
    # Windows-style separators and empty parts are not allowed.
    if "\\" in rel or "//" in rel or "\x00" in rel:
        return None
    candidate = (PACKS_ROOT / rel).resolve()
    try:
        candidate.relative_to(PACKS_ROOT.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() not in ALLOWED_STATIC_SUFFIXES:
        return None
    return candidate


def content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "application/octet-stream"

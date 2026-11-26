"""Named farm save slots.

Both players share one active slot. Switching never writes one farm into
another. A new farm never overwrites an existing slot.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

FIRST_FARM_ID = "first-farm"
FIRST_FARM_NAME = "First Farm"
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _engine():
    import engine
    return engine


def data_dir() -> Path:
    return Path(_engine().STATE_PATH).parent


def saves_root() -> Path:
    return data_dir() / "saves"


def active_pointer_path() -> Path:
    return saves_root() / "active.json"


def slot_dir(slot_id: str) -> Path:
    return saves_root() / slot_id


def slot_state_path(slot_id: str) -> Path:
    return slot_dir(slot_id) / "state.json"


def slot_meta_path(slot_id: str) -> Path:
    return slot_dir(slot_id) / "meta.json"


def slot_journal_path(slot_id: str) -> Path:
    return slot_dir(slot_id) / "journal-archive.json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def is_live_tree() -> bool:
    engine = _engine()
    return Path(engine.STATE_PATH).resolve() == (engine.ROOT / "state.json").resolve()


def current_slot_id() -> str | None:
    pointer = active_pointer_path()
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    slot = str(data.get("slot") or "").strip()
    if not slot or not _SLUG_RE.match(slot):
        return None
    return slot


def active_state_path() -> Path:
    """State file for the active slot, or the plain STATE_PATH if slots are unused."""
    engine = _engine()
    slot = current_slot_id()
    if slot:
        return slot_state_path(slot)
    return Path(engine.STATE_PATH)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def set_active_slot(slot_id: str) -> None:
    write_json(active_pointer_path(), {"slot": slot_id})


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text or "farm"


def unique_slot_id(base: str) -> str:
    if not slot_dir(base).exists():
        return base
    n = 2
    while slot_dir(f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"


def meta_from_state(slot_id: str, name: str, state: dict, *, last_played: str | None = None) -> dict:
    return {
        "id": slot_id,
        "name": name,
        "day": int(state.get("day") or 1),
        "season": str(state.get("season") or "spring"),
        "year": int(state.get("year") or 1),
        "gold": int(state.get("gold") or 0),
        "last_played": last_played or now_iso(),
    }


def read_meta(slot_id: str) -> dict | None:
    path = slot_meta_path(slot_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def write_meta(slot_id: str, meta: dict) -> None:
    write_json(slot_meta_path(slot_id), meta)


def touch_meta_for_state_path(path: Path, state: dict) -> None:
    """Refresh metadata when a slot's state.json is written."""
    try:
        path = Path(path).resolve()
        root = saves_root().resolve()
        if root not in path.parents or path.name != "state.json":
            return
        slot_id = path.parent.name
        if not _SLUG_RE.match(slot_id):
            return
        prev = read_meta(slot_id) or {}
        name = str(prev.get("name") or slot_id)
        write_meta(slot_id, meta_from_state(slot_id, name, state))
    except OSError:
        return


def _format_last_played(iso: str) -> str:
    if not iso:
        return "never"
    try:
        stamp = datetime.fromisoformat(iso)
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone()
        return stamp.strftime("%-d %b %Y, %-I:%M %p")
    except ValueError:
        return iso


def list_slots() -> list[dict]:
    root = saves_root()
    if not root.is_dir():
        return []
    active = current_slot_id()
    found: list[dict] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or not _SLUG_RE.match(child.name):
            continue
        if not slot_state_path(child.name).is_file():
            continue
        meta = read_meta(child.name) or {}
        entry = {
            "id": child.name,
            "name": str(meta.get("name") or child.name),
            "day": int(meta.get("day") or 0),
            "season": str(meta.get("season") or ""),
            "year": int(meta.get("year") or 0),
            "gold": int(meta.get("gold") or 0),
            "last_played": str(meta.get("last_played") or ""),
            "last_played_text": _format_last_played(str(meta.get("last_played") or "")),
            "active": child.name == active,
            "protected": child.name == FIRST_FARM_ID,
        }
        if not entry["day"] and slot_state_path(child.name).is_file():
            try:
                state = json.loads(slot_state_path(child.name).read_text(encoding="utf-8"))
                entry["day"] = int(state.get("day") or 0)
                entry["season"] = str(state.get("season") or entry["season"])
                entry["year"] = int(state.get("year") or 0)
                entry["gold"] = int(state.get("gold") or 0)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        found.append(entry)
    found.sort(key=lambda e: (not e["active"], e["id"] != FIRST_FARM_ID, -( _sort_ts(e["last_played"])), e["name"].lower()))
    return found


def _sort_ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return 0.0


def find_slot(token: str) -> str | None:
    """Resolve a slot id or display name (case-insensitive)."""
    token = (token or "").strip()
    if not token:
        return None
    if _SLUG_RE.match(token) and slot_state_path(token).is_file():
        return token
    lowered = token.lower()
    for entry in list_slots():
        if entry["id"] == token or entry["name"].lower() == lowered:
            return entry["id"]
    return None


def display_name_taken(name: str, *, except_id: str | None = None) -> str | None:
    want = (name or "").strip().lower()
    if not want:
        return None
    for entry in list_slots():
        if except_id and entry["id"] == except_id:
            continue
        if entry["name"].strip().lower() == want:
            return entry["id"]
    return None


def format_slot_list(slots: list[dict] | None = None) -> str:
    slots = list_slots() if slots is None else slots
    if not slots:
        return "No saved farms yet.\n"
    lines = ["Saved farms:"]
    for entry in slots:
        mark = "  (active)" if entry["active"] else ""
        lines.append(
            f"  {entry['name']} [{entry['id']}]{mark} — "
            f"day {entry['day']}, {entry['season']}, year {entry['year']}, "
            f"{entry['gold']}G, last played {entry['last_played_text']}"
        )
    return "\n".join(lines) + "\n"


def _copy_journal_into(slot_id: str, source: Path | None = None) -> None:
    engine = _engine()
    src = source or (engine.ROOT / "local" / "journal-archive.json")
    dest = slot_journal_path(slot_id)
    if dest.is_file() or not src.is_file():
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError:
        return


def migrate_legacy_state(*, backup: bool = False) -> str | None:
    """If no active slot exists and STATE_PATH is a farm, copy it into First Farm."""
    engine = _engine()
    if current_slot_id() and slot_state_path(current_slot_id() or "").is_file():
        return current_slot_id()
    src = Path(engine.STATE_PATH)
    if not src.is_file():
        return None
    if backup:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        base = engine.ROOT / "backups" if is_live_tree() else data_dir() / "backups"
        dest = base / f"before-save-slots-{stamp}"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / "state.json")
        except OSError:
            pass
    slot_id = FIRST_FARM_ID
    dest_dir = slot_dir(slot_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_state = slot_state_path(slot_id)
    if not dest_state.is_file():
        shutil.copy2(src, dest_state)
    state = json.loads(dest_state.read_text(encoding="utf-8"))
    write_meta(slot_id, meta_from_state(slot_id, FIRST_FARM_NAME, state))
    _copy_journal_into(slot_id)
    set_active_slot(slot_id)
    return slot_id


def maybe_migrate_live() -> str | None:
    """Copy the live farm into First Farm after a backup. Tests never trigger this."""
    if not is_live_tree():
        return None
    if current_slot_id() and slot_state_path(current_slot_id() or "").is_file():
        return current_slot_id()
    if not Path(_engine().STATE_PATH).is_file():
        return None
    return migrate_legacy_state(backup=True)


def new_slot(name: str, *, crops=None) -> tuple[bool, str, str | None]:
    """Start a fresh farm in a new named slot and switch to it. Never overwrites."""
    engine = _engine()
    name = " ".join((name or "").split())
    if not name:
        return False, 'Usage: python3 cli.py new "Farm name"', None
    taken = display_name_taken(name)
    if taken:
        return False, f"A farm named {name!r} already exists ({taken}). Pick a different name.", None
    slot_id = unique_slot_id(slugify(name))
    dest = slot_state_path(slot_id)
    if dest.exists():
        return False, f"A farm slot {slot_id!r} already exists. Pick a different name.", None
    # Flush metadata for the farm we're leaving, if any.
    current = current_slot_id()
    if current and slot_state_path(current).is_file():
        try:
            prev = json.loads(slot_state_path(current).read_text(encoding="utf-8"))
            prev_meta = read_meta(current) or {}
            write_meta(current, meta_from_state(current, str(prev_meta.get("name") or current), prev))
        except (OSError, json.JSONDecodeError):
            pass
    state = engine.fresh_state(crops)
    dest.parent.mkdir(parents=True, exist_ok=True)
    engine.save_state(state, dest)
    write_meta(slot_id, meta_from_state(slot_id, name, state))
    set_active_slot(slot_id)
    return True, f"Started a new farm, {name}. It is now the active save.", slot_id


def load_slot(token: str) -> tuple[bool, str, str | None]:
    """Save the current slot's metadata, then switch to another farm. Does not copy state."""
    slot_id = find_slot(token)
    if not slot_id:
        return False, f"No saved farm matches {token!r}. Use: python3 cli.py saves", None
    if not slot_state_path(slot_id).is_file():
        return False, f"The farm {token!r} is missing its state file.", None
    current = current_slot_id()
    if current == slot_id:
        meta = read_meta(slot_id) or {}
        return True, f"Already playing {meta.get('name') or slot_id}.", slot_id
    if current and slot_state_path(current).is_file():
        try:
            prev = json.loads(slot_state_path(current).read_text(encoding="utf-8"))
            prev_meta = read_meta(current) or {}
            write_meta(current, meta_from_state(current, str(prev_meta.get("name") or current), prev))
        except (OSError, json.JSONDecodeError):
            pass
    set_active_slot(slot_id)
    meta = read_meta(slot_id) or {}
    # Touch last played now that it's active.
    try:
        state = json.loads(slot_state_path(slot_id).read_text(encoding="utf-8"))
        write_meta(slot_id, meta_from_state(slot_id, str(meta.get("name") or slot_id), state))
        meta = read_meta(slot_id) or meta
    except (OSError, json.JSONDecodeError):
        pass
    return True, f"Switched to {meta.get('name') or slot_id}. Both players share this farm.", slot_id


def rename_slot(token: str, new_name: str) -> tuple[bool, str, str | None]:
    slot_id = find_slot(token)
    if not slot_id:
        return False, f"No saved farm matches {token!r}. Use: python3 cli.py saves", None
    new_name = " ".join((new_name or "").split())
    if not new_name:
        return False, "Usage: python3 cli.py rename <slot> \"New name\"", None
    taken = display_name_taken(new_name, except_id=slot_id)
    if taken:
        return False, f"A farm named {new_name!r} already exists ({taken}). Pick a different name.", None
    meta = read_meta(slot_id) or {"id": slot_id}
    meta["name"] = new_name
    if slot_state_path(slot_id).is_file() and "day" not in meta:
        try:
            state = json.loads(slot_state_path(slot_id).read_text(encoding="utf-8"))
            meta = meta_from_state(slot_id, new_name, state, last_played=str(meta.get("last_played") or now_iso()))
        except (OSError, json.JSONDecodeError):
            meta["name"] = new_name
    write_meta(slot_id, meta)
    return True, f"Renamed the farm to {new_name}.", slot_id


def public_payload() -> dict:
    return {
        "active": current_slot_id(),
        "slots": list_slots(),
    }

"""Opt-in developer commands for testing. Off by default.

Enabled only when the gitignored ``config.local.json`` has
``"dev_commands": true``, or when the environment variable
``LANTERN_FARM_DEV_COMMANDS`` is a truthy value (1, true, yes, on).
A falsey env value (0, false, no, off) overrides the local config and
keeps them off. They never appear in Legal Actions.
"""

from __future__ import annotations

import os
from typing import Mapping

ENV_VAR = "LANTERN_FARM_DEV_COMMANDS"

_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off", ""}

MAX_GIVE = 999


def _truthy(raw: str | None) -> bool | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in _TRUTHY:
        return True
    if text in _FALSEY:
        return False
    return None


def _config_flag(config: dict | None = None) -> bool:
    if config is None:
        from config import load_config

        config = load_config()
    return bool((config or {}).get("dev_commands"))


def dev_commands_enabled(
    environ: Mapping[str, str] | None = None,
    config: dict | None = None,
) -> bool:
    """Return True only when the local flag or env var has opted in."""
    env = environ if environ is not None else os.environ
    flagged = _truthy(env.get(ENV_VAR))
    if flagged is not None:
        return flagged
    return _config_flag(config)


def _off_message() -> str:
    return (
        "Dev commands are off. Set \"dev_commands\": true in the gitignored "
        "config.local.json, or " + ENV_VAR + "=1, to enable them."
    )


def _log(state: dict, player: str, text: str) -> None:
    from engine import log_append

    log_append(state, text, player)


def _usage() -> str:
    return (
        "Dev commands: dev give <item> <n>, dev weather aurora, "
        "dev xp <skill> <n>."
    )


def handle_dev_command(
    state: dict,
    crops: dict,
    player: str,
    args: list[str],
    *,
    raw: str = "",
    rules: dict | None = None,
) -> tuple[bool, str]:
    """Run one ``dev …`` command. Caller has already checked whose turn it is."""
    from engine import display_name

    who = display_name(player)
    typed = (raw or "dev").strip() or "dev"
    if not dev_commands_enabled():
        return False, _off_message()

    if not args:
        msg = f"Dev: {who} tried `{typed}`, but it needs a subcommand. {_usage()}"
        _log(state, player, msg)
        return False, msg

    verb = str(args[0] or "").strip().lower()
    rest = args[1:]
    if verb == "give":
        return _dev_give(state, crops, player, who, rest, typed, rules)
    if verb == "weather":
        return _dev_weather(state, player, who, rest, typed)
    if verb == "xp":
        return _dev_xp(state, player, who, rest, typed, rules)
    msg = f"Dev: {who} tried `{typed}`, but that isn't a dev command. {_usage()}"
    _log(state, player, msg)
    return False, msg


def _dev_give(
    state: dict,
    crops: dict,
    player: str,
    who: str,
    rest: list[str],
    typed: str,
    rules: dict | None,
) -> tuple[bool, str]:
    from inventory import (
        give_or_drop_at_player,
        item_name,
        parse_item_and_count,
    )

    item, count, err = parse_item_and_count(rest)
    if err or not item:
        msg = f"Dev: {who} tried `{typed}`, but {err or 'the item was not recognized.'}"
        _log(state, player, msg)
        return False, msg
    if count == "all":
        msg = f"Dev: {who} tried `{typed}`, but give needs a count, not 'all'."
        _log(state, player, msg)
        return False, msg
    try:
        n = int(count)
    except (TypeError, ValueError):
        msg = f"Dev: {who} tried `{typed}`, but the count was not a number."
        _log(state, player, msg)
        return False, msg
    if n < 1:
        msg = f"Dev: {who} tried `{typed}`, but the count must be at least 1."
        _log(state, player, msg)
        return False, msg
    if n > MAX_GIVE:
        msg = f"Dev: {who} tried `{typed}`, but the count cannot be more than {MAX_GIVE}."
        _log(state, player, msg)
        return False, msg
    packed, dropped, phrase = give_or_drop_at_player(
        state, player, item, n, rules
    )
    noun = item_name(item, n, crops, rules, state=state)
    line = f"Dev: {who} gives themselves {noun}."
    if packed and not dropped:
        line = f"{line} They go into the pack."
    elif packed and dropped:
        # phrase is a clause like "and packs … Your pack is full, so …"
        line = f"{line} {phrase.rstrip('.')}."
    elif dropped and not packed:
        line = f"{line} {phrase}".rstrip()
        if not line.endswith("."):
            line += "."
    _log(state, player, line)
    return True, line


def _dev_weather(
    state: dict,
    player: str,
    who: str,
    rest: list[str],
    typed: str,
) -> tuple[bool, str]:
    from engine import WEATHER_KINDS

    kind = " ".join(rest).strip().lower()
    if not kind:
        msg = (
            f"Dev: {who} tried `{typed}`, but weather needs a kind "
            f"(for example: dev weather aurora)."
        )
        _log(state, player, msg)
        return False, msg
    if kind not in WEATHER_KINDS:
        known = ", ".join(WEATHER_KINDS)
        msg = f"Dev: {who} tried `{typed}`, but {kind!r} is not a known weather. Use one of: {known}."
        _log(state, player, msg)
        return False, msg
    state["weather"] = kind
    if kind == "aurora":
        line = f"Dev: {who} sets the weather to an aurora night."
    else:
        line = f"Dev: {who} sets the weather to {kind}."
    _log(state, player, line)
    return True, line


def _dev_xp(
    state: dict,
    player: str,
    who: str,
    rest: list[str],
    typed: str,
    rules: dict | None,
) -> tuple[bool, str]:
    from xp import SKILLS, grant_xp, player_xp_map

    if len(rest) < 2:
        msg = (
            f"Dev: {who} tried `{typed}`, but xp needs a skill and an amount "
            f"(for example: dev xp mining 2000). Skills: {', '.join(SKILLS)}."
        )
        _log(state, player, msg)
        return False, msg
    # Allow `dev xp mining 2000` or `dev xp 2000 mining`.
    skill_token, amount_token = rest[0], rest[1]
    if skill_token.lstrip("-").isdigit() and not amount_token.lstrip("-").isdigit():
        skill_token, amount_token = amount_token, skill_token
    skill = skill_token.strip().lower()
    if skill not in SKILLS:
        msg = (
            f"Dev: {who} tried `{typed}`, but {skill!r} is not a skill. "
            f"Skills: {', '.join(SKILLS)}."
        )
        _log(state, player, msg)
        return False, msg
    try:
        amount = int(amount_token)
    except (TypeError, ValueError):
        msg = f"Dev: {who} tried `{typed}`, but the amount was not a number."
        _log(state, player, msg)
        return False, msg
    if amount <= 0:
        msg = f"Dev: {who} tried `{typed}`, but the amount must be at least 1."
        _log(state, player, msg)
        return False, msg
    granted = grant_xp(state, player, skill, amount, rules)
    total = int((player_xp_map(state, player) or {}).get(skill) or 0)
    line = f"Dev: {who} grants {granted} {skill} XP (now {total})."
    _log(state, player, line)
    return True, line

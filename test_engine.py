#!/usr/bin/env python3
"""Unit tests for Lantern Farm growth determinism and basic rules."""

from __future__ import annotations

import os

# Tests must never ping Hey or write the live farm.
os.environ["LANTERN_FARM_NO_NOTIFY"] = "1"

import copy
import json
import tempfile
import unittest
from pathlib import Path

import engine

_LIVE_STATE = engine.STATE_PATH.resolve()
_TEST_DIR = Path(tempfile.mkdtemp(prefix="lantern-farm-tests-"))
engine.STATE_PATH = _TEST_DIR / "state.json"
engine.LOCK_PATH = _TEST_DIR / ".state.lock"
engine.JOURNAL_ARCHIVE_PATH = _TEST_DIR / "journal-archive.json"

from config import display_name, player_ids, starting_player as config_starting_player

P1, P2 = player_ids()[0], player_ids()[1]
N1, N2 = display_name(P1), display_name(P2)

from engine import (
    NOTE_MAX,
    RECENT_NOTE_COUNT,
    all_journal_entries,
    archive_journal_if_needed,
    empty_journal,
    migrate_journal,
    normalize_season,
    recent_notes,
    record_journal_note,
    season_journal_entries,
    year_for_day,
    buy,
    crop_info,
    do_action,
    end_turn,
    energy_cost,
    fresh_state,
    harvest,
    legal_actions,
    format_legal_action,
    load_crops,
    load_rules,
    migrate_state,
    parse_end_turn_command,
    plant,
    pluck,
    plot_eligible_for_weed,
    sanitize_note,
    set_player_where,
    player_where,
    is_player_in_cabin,
    sleep_outlook,
    path_cost,
    step_energy,
    eat_energy_for,
    snacks_per_turn,
    pass_out_energy,
    migrate_state,
    CABIN_ROW,
    CABIN_COL,
    season_for_day,
    sell,
    sleep,
    sprout_and_age_weeds,
    till,
    till_hold_left,
    till_hold_phrase,
    water,
    weather_for_day,
    weather_forecast,
    forecast_weather,
    forecast_accuracy,
    find_weather_seed,
    ensure_weather_seed,
    is_wet_weather,
    weed_hash,
    new_weed_count_for_day,
)
from hey_notify import turn_ping_message
from sprites import sprite_key, svg_for_key


def no_weed_rules():
    rules = copy.deepcopy(load_rules())
    rules["weeds"] = {"min_new_per_day": 0, "max_new_per_day": 0, "eligible": "tilled_or_planted"}
    return rules


def stand(state, player, row=1, col=1):
    """Place a player on a tile without charging movement (for isolated action tests)."""
    set_player_where(state, player, row, col)
    return player_where(state, player)


def give_item(state, item, n=1, player=None, where=None):
    """Put items in a pack (if player) or the chest, and refresh the totals view."""
    from inventory import add_to_pack, add_to_chest, sync_inventory_view, migrate_inventory
    from engine import load_crops, load_rules
    migrate_inventory(state, load_crops(), load_rules())
    dest = where or ("pack" if player else "chest")
    if dest == "pack" and player:
        leftover = add_to_pack(state, player, item, n)
        if leftover:
            add_to_chest(state, item, leftover)
    else:
        add_to_chest(state, item, n)
    sync_inventory_view(state)
    from inventory import item_count
    return item_count(state, item)


def give_seeds(state, kind, n=2, player=None):
    """Grant planting stock so tests can still plant later-content crops."""
    from engine import crop_info, load_crops, stock_key
    info = crop_info(load_crops(), kind) or {}
    key = stock_key(kind, info)
    return give_item(state, key, n, player=player)


def kit_out(state, player):
    """Put a hoe and a watering can in the player's pack, taking them from the chest."""
    from inventory import (
        migrate_inventory,
        ensure_starting_tools,
        remove_from_chest,
        add_to_pack,
        pack_has,
        TOOL_HOE,
        TOOL_CAN,
        sync_inventory_view,
    )
    from engine import load_crops, load_rules
    rules = load_rules()
    migrate_inventory(state, load_crops(), rules)
    ensure_starting_tools(state, rules)
    for item in (TOOL_HOE, TOOL_CAN):
        if pack_has(state, player, item, 1, rules):
            continue
        remove_from_chest(state, item, 1, rules)
        add_to_pack(state, player, item, 1, rules)
    sync_inventory_view(state, rules)


def hand_tool(state, item, src, dst):
    """Move a tool from one pack to another (test handoff)."""
    from inventory import remove_from_pack, add_to_pack, sync_inventory_view
    if remove_from_pack(state, src, item, 1):
        add_to_pack(state, dst, item, 1)
    sync_inventory_view(state)


class WeatherDeterminism(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()

    def test_weather_is_a_function_of_seed_and_day(self):
        seed = 42
        for day in range(1, 120):
            a = weather_for_day(day, self.crops, self.rules, seed=seed)
            b = weather_for_day(day, self.crops, self.rules, seed=seed)
            self.assertEqual(a, b)
            self.assertIn(a, {"sun", "cloud", "rain", "storm", "snow"})

    def test_fresh_farm_starts_sunny_on_day_one(self):
        state = fresh_state(self.crops)
        self.assertEqual(state["weather"], "sun")
        self.assertEqual(
            weather_for_day(1, self.crops, self.rules, seed=state["weather_seed"]),
            "sun",
        )

    def test_a_chosen_seed_is_reproducible(self):
        seed = find_weather_seed({1: "sun", 2: "sun", 3: "rain"}, self.rules, self.crops)
        self.assertEqual(weather_for_day(1, self.crops, self.rules, seed=seed), "sun")
        self.assertEqual(weather_for_day(2, self.crops, self.rules, seed=seed), "sun")
        self.assertEqual(weather_for_day(3, self.crops, self.rules, seed=seed), "rain")
        again = find_weather_seed({1: "sun", 2: "sun", 3: "rain"}, self.rules, self.crops)
        self.assertEqual(again, seed)

    def test_winter_can_snow_and_summer_can_storm(self):
        self.assertEqual(season_for_day(46, self.crops), "winter")
        self.assertEqual(season_for_day(16, self.crops), "summer")
        snow_seed = find_weather_seed({46: "snow"}, self.rules, self.crops)
        self.assertEqual(weather_for_day(46, self.crops, self.rules, seed=snow_seed), "snow")
        storm_seed = find_weather_seed({16: "storm"}, self.rules, self.crops)
        self.assertEqual(weather_for_day(16, self.crops, self.rules, seed=storm_seed), "storm")
        self.assertTrue(is_wet_weather("snow"))
        self.assertTrue(is_wet_weather("storm"))
        self.assertTrue(is_wet_weather("rain"))
        self.assertFalse(is_wet_weather("sun"))
        self.assertFalse(is_wet_weather("cloud"))

    def test_season_cycle(self):
        self.assertEqual(season_for_day(1, self.crops), "spring")
        self.assertEqual(season_for_day(15, self.crops), "spring")
        self.assertEqual(season_for_day(16, self.crops), "summer")
        self.assertEqual(season_for_day(31, self.crops), "autumn")
        self.assertEqual(season_for_day(46, self.crops), "winter")
        self.assertEqual(season_for_day(61, self.crops), "spring")


class GrowthRules(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.weather_seed = find_weather_seed(
            {1: "sun", 2: "sun", 3: "rain"}, self.rules, self.crops
        )
        self.state = fresh_state(self.crops, weather_seed=self.weather_seed, rules=self.rules)

    def _plot(self):
        # top-left is free farmland
        return 1, 1

    def _planted(self, kind="kabocha"):
        r, c = self._plot()
        ok, msg = till(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        give_seeds(self.state, kind, 1)
        ok, msg = plant(self.state, self.crops, r, c, kind)
        self.assertTrue(ok, msg)
        return r, c

    def test_watered_crop_grows_one_day_per_sleep(self):
        r, c = self._planted("kabocha")
        info = crop_info(self.crops, "kabocha")
        for expected in range(1, info["grow_days"] + 1):
            ok, msg = water(self.state, self.crops, r, c)
            # Rainy mornings may already have watered the tile.
            self.assertTrue(ok or "already watered" in msg, msg)
            ok, msg = sleep(self.state, self.crops, no_weed_rules())
            self.assertTrue(ok, msg)
            crop = self.state["tiles"][r - 1][c - 1]["crop"]
            self.assertIsNotNone(crop)
            self.assertNotEqual(crop["stage"], "withered")
            self.assertEqual(crop["days_grown"], expected)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")

    def test_unwatered_crop_does_not_grow(self):
        r, c = self._planted("kabocha")
        # Day 1 and 2 are sunny, so one sleep without watering: no growth.
        ok, msg = sleep(self.state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["days_grown"], 0)
        self.assertEqual(crop["dry_days"], 1)
        self.assertEqual(crop["stage"], "seed")

    def test_two_dry_days_do_not_wither(self):
        r, c = self._planted("kabocha")
        self.assertEqual(weather_for_day(1, self.crops, self.rules, seed=self.weather_seed), "sun")
        self.assertEqual(weather_for_day(2, self.crops, self.rules, seed=self.weather_seed), "sun")
        ok, _ = sleep(self.state, self.crops, no_weed_rules())
        self.assertTrue(ok)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["dry_days"], 1)
        self.assertNotEqual(crop["stage"], "withered")
        ok, _ = sleep(self.state, self.crops, no_weed_rules())
        self.assertTrue(ok)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["dry_days"], 2)
        self.assertNotEqual(crop["stage"], "withered")
        self.assertLess(int(crop.get("health") or 100), 100)
        self.assertEqual(crop["days_grown"], 0)

    def test_long_drought_at_low_health_withers(self):
        from engine import _apply_evening_growth, maybe_wither
        r, c = self._planted("kabocha")
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        crop["health"] = 20
        crop["dry_days"] = 5
        crop["growth"] = 40
        self.state["tiles"][r - 1][c - 1]["watered"] = False
        notes = _apply_evening_growth(self.state, self.crops, no_weed_rules())
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "withered")
        self.assertTrue(any("drought" in n or "withered" in n for n in notes))

    def test_rain_waters_everything_and_counts_as_a_growth_day(self):
        r, c = self._planted("kabocha")
        # Sleep from day 1 (sun) without watering, then day 2 (sun), then
        # we need a rain morning before the evening tick.
        # Easier: advance to the day before rain, plant-equivalent already
        # done, water-skip, then land on a rain day and sleep through it.
        # Day 3 is rain. Start on day 1, sleep once (evening of 1, dawn of 2,
        # still sun, crop dry_days=1). Sleep again would be evening of 2
        # (sun, wither if limit is 2) then dawn of 3 (rain) — too late, already withered.
        #
        # So: water on day 1 so it survives, sleep to day 2, do not water,
        # sleep to day 3 (dry_days=1, still alive, morning rain waters),
        # sleep to day 4 — the rain must have counted, days_grown += 1.
        ok, msg = water(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        ok, _ = sleep(self.state, self.crops, no_weed_rules())  # to day 2, grown 1
        self.assertEqual(self.state["day"], 2)
        self.assertEqual(self.state["weather"], "sun")
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["days_grown"], 1)
        ok, _ = sleep(self.state, self.crops, no_weed_rules())  # evening of 2 dry, dawn 3 rain
        self.assertEqual(self.state["day"], 3)
        self.assertEqual(self.state["weather"], "rain")
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["days_grown"], 1)
        self.assertEqual(crop["dry_days"], 1)
        self.assertTrue(self.state["tiles"][r - 1][c - 1]["watered"])
        ok, _ = sleep(self.state, self.crops, no_weed_rules())  # rain counts as water
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["days_grown"], 2)
        self.assertEqual(crop["dry_days"], 0)
        self.assertNotEqual(crop["stage"], "withered")

    def test_same_actions_produce_the_same_state(self):
        def play():
            state = fresh_state(self.crops)
            kit_out(state, P1)
            give_seeds(state, "kabocha", 1, player=P1)
            cmds = [
                "move to 1 1",
                "till 1 1",
                "plant 1 1 kabocha",
                "water 1 1",
                "move to 2 2",
                "till 2 2",
                "go cabin",
                "end turn",
            ]
            for cmd in cmds:
                ok, msg = do_action(state, self.crops, cmd, player=P1)
                self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "end turn", player=P2)
            self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "move to 1 1", player=P1)
            self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "water 1 1", player=P1)
            self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "go cabin", player=P1)
            self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "end turn", player=P1)
            self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "end turn", player=P2)
            self.assertTrue(ok, msg)
            return state

        a = play()
        b = play()
        self.assertEqual(a, b)

    def test_cannot_plant_on_cabin(self):
        ok, msg = till(self.state, self.crops, 1, 3)
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())
        ok, msg = plant(self.state, self.crops, 1, 3, "kabocha")
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())

    def test_cannot_plant_untilled(self):
        ok, msg = plant(self.state, self.crops, 1, 1, "kabocha")
        self.assertFalse(ok)
        self.assertIn("till", msg.lower())

    def test_harvest_mature_adds_inventory(self):
        r, c = self._planted("turnip")  # 9 days
        for _ in range(9):
            # If a morning is already wet, water() may legitimately fail.
            water(self.state, self.crops, r, c)
            ok, msg = sleep(self.state, self.crops, no_weed_rules())
            self.assertTrue(ok, msg)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")
        before = int(self.state["inventory"]["turnip"])
        ok, msg = harvest(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(self.state["inventory"]["turnip"], before + 1)
        self.assertIsNone(self.state["tiles"][r - 1][c - 1]["crop"])

    def test_buy_and_sell(self):
        gold = self.state["gold"]
        ok, msg = buy(self.state, self.crops, "strawberry", 2)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold - 30)
        self.assertEqual(self.state["inventory"]["strawberry_seed"], 4)
        # Later crops stay sellable even when they are not in the shop.
        give_item(self.state, "carrot", 1)
        ok, msg = sell(self.state, self.crops, "carrot", 1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["inventory"]["carrot"], 0)
        self.assertEqual(self.state["gold"], gold - 30 + 32)
        ok, msg = buy(self.state, self.crops, "carrot", 1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["inventory"]["carrot_seed"], 1)
        # Out of season, a spring-and-summer seed is not restocked.
        self.state["season"] = "winter"
        ok, msg = buy(self.state, self.crops, "strawberry", 1)
        self.assertFalse(ok, msg)
        self.assertIn("winter", msg.lower())

    def test_out_of_season_withers_on_season_change(self):
        # Turnips do not grow in summer (day 16).
        state = fresh_state(self.crops)
        # Jump to the last day of spring with a living turnip.
        state["day"] = 15
        state["season"] = season_for_day(15, self.crops)
        state["weather"] = weather_for_day(15, self.crops, self.rules, seed=self.weather_seed)
        self.assertEqual(state["season"], "spring")
        ok, _ = till(state, self.crops, 1, 1)
        self.assertTrue(ok)
        # Give a seed if needed
        give_seeds(state, "turnip", 1)
        ok, msg = plant(state, self.crops, 1, 1, "turnip")
        self.assertTrue(ok, msg)
        water(state, self.crops, 1, 1)
        ok, msg = sleep(state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        self.assertEqual(state["day"], 16)
        self.assertEqual(state["season"], "summer")
        crop = state["tiles"][0][0]["crop"]
        self.assertNotEqual(crop["stage"], "withered")
        self.assertGreaterEqual(int(crop.get("off_season_days") or 0), 1)
        # Three off-season evenings wither an annual.
        from engine import _apply_season_to_crop
        _apply_season_to_crop(state, self.crops, crop, 1, 1)
        _apply_season_to_crop(state, self.crops, crop, 1, 1)
        self.assertEqual(crop["stage"], "withered")

    def test_sprite_key_follows_state(self):
        tile = self.state["tiles"][0][2]
        self.assertEqual(tile["type"], "cabin")
        self.assertEqual(sprite_key(tile), "cabin")
        soil = self.state["tiles"][0][0]
        self.assertEqual(sprite_key(soil), "soil")
        soil["tilled"] = True
        self.assertEqual(sprite_key(soil), "soil_tilled")
        soil["watered"] = True
        self.assertEqual(sprite_key(soil), "soil_watered")
        soil["crop"] = {
            "kind": "kabocha",
            "planted_day": 1,
            "days_grown": 3,
            "stage": "sprouting",
            "dry_days": 0,
        }
        self.assertEqual(sprite_key(soil), "kabocha_sprouting_wet")
        svg = svg_for_key("kabocha_sprouting_wet")
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)

    def test_fresh_state_has_cabin_top_right_and_eight_plots(self):
        soils = 0
        for r, row in enumerate(self.state["tiles"]):
            for c, tile in enumerate(row):
                if r == 0 and c == 2:
                    self.assertEqual(tile["type"], "cabin")
                else:
                    self.assertEqual(tile["type"], "soil")
                    soils += 1
        self.assertEqual(soils, 8)
        self.assertEqual(self.state["day"], 1)
        self.assertEqual(self.state["season"], "spring")


class Persistence(unittest.TestCase):
    def test_round_trip_json(self):
        crops = load_crops()
        state = fresh_state(crops)
        till(state, crops, 3, 3)
        give_seeds(state, "kabocha", 1)
        plant(state, crops, 3, 3, "kabocha")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            engine.save_state(state, path)
            loaded = engine.load_state(crops, path)
            self.assertEqual(loaded, state)


class DeepCopySafety(unittest.TestCase):
    def test_fresh_states_are_independent(self):
        crops = load_crops()
        a = fresh_state(crops)
        b = copy.deepcopy(a)
        till(a, crops, 1, 1)
        self.assertFalse(b["tiles"][0][0]["tilled"])


class TurnsAndEnergy(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops)
        kit_out(self.state, P1)
        # Some tests still plant later-content kabocha from the pack.
        give_seeds(self.state, "kabocha", 2, player=P1)

    def test_costs_come_from_rules_json(self):
        self.assertEqual(energy_cost("till", self.rules), 10)
        self.assertEqual(energy_cost("plant", self.rules), 10)
        self.assertEqual(energy_cost("water", self.rules), 10)
        self.assertEqual(energy_cost("harvest", self.rules), 0)
        self.assertEqual(energy_cost("buy", self.rules), 0)
        self.assertEqual(energy_cost("sell", self.rules), 0)
        self.assertEqual(energy_cost("end_turn", self.rules), 0)
        self.assertEqual(energy_cost("pluck", self.rules), 5)
        self.assertEqual(energy_cost("move", self.rules), 5)
        self.assertEqual(energy_cost("eat", self.rules), 0)
        self.assertEqual(energy_cost("craft", self.rules), 5)
        self.assertEqual(step_energy(self.rules), 5)
        self.assertEqual(snacks_per_turn(self.rules), 2)
        self.assertEqual(pass_out_energy(self.rules), 50)
        custom = copy.deepcopy(self.rules)
        custom["action_energy"]["till"] = 25
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P1, rules=custom)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 75)

    def test_till_plant_water_spend_ten_each(self):
        stand(self.state, P1, 1, 1)
        for cmd in ("till 1 1", "plant 1 1 kabocha", "water 1 1"):
            ok, msg = do_action(self.state, self.crops, cmd, player=P1)
            self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 70)

    def test_blocks_when_energy_is_too_low(self):
        self.state["players"][P1]["energy"] = 5
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("energy", msg.lower())
        self.assertIn("5", msg)
        self.assertFalse(self.state["tiles"][0][0]["tilled"])
        self.assertEqual(self.state["players"][P1]["energy"], 5)

    def test_failed_action_does_not_spend_energy(self):
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "plant 1 1 kabocha", player=P1)
        self.assertFalse(ok)
        self.assertEqual(self.state["players"][P1]["energy"], 100)

    def test_harvest_buy_sell_are_free(self):
        # Grow a turnip with the sleep helper (doesn't spend energy), then harvest.
        ok, _ = till(self.state, self.crops, 1, 1)
        self.assertTrue(ok)
        give_seeds(self.state, "turnip", 1)
        ok, _ = plant(self.state, self.crops, 1, 1, "turnip")
        self.assertTrue(ok)
        for _ in range(9):
            water(self.state, self.crops, 1, 1)
            ok, msg = sleep(self.state, self.crops, no_weed_rules())
            self.assertTrue(ok, msg)
        # sleep() does not reset energy; still 100 because we didn't use do_action.
        self.state["players"][P1]["energy"] = 7
        self.state["current_player"] = P1
        self.state["players"][P1]["ended_turn"] = False
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "harvest 1 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 7)
        gold = self.state["gold"]
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "sell turnip 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 7)
        ok, msg = do_action(self.state, self.crops, "buy strawberry 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 7)
        self.assertEqual(self.state["gold"], gold + 22 - 15)

    def test_wrong_player_is_refused(self):
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P2)
        self.assertFalse(ok)
        self.assertIn(N1, msg)
        self.assertFalse(self.state["tiles"][0][0]["tilled"])

    def test_end_turn_hands_off_with_fresh_energy(self):
        stand(self.state, P1, 1, 1)
        ok, _ = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertTrue(ok)
        self.assertEqual(self.state["players"][P1]["energy"], 90)
        ok, msg = do_action(self.state, self.crops, "end turn", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["current_player"], P2)
        self.assertTrue(self.state["players"][P1]["ended_turn"])
        self.assertEqual(self.state["players"][P2]["energy"], 100)
        self.assertEqual(self.state["day"], 1)
        # The other player spends some, then...
        hand_tool(self.state, "hoe", P1, P2)
        stand(self.state, P2, 2, 2)
        ok, _ = do_action(self.state, self.crops, "till 2 2", player=P2)
        self.assertTrue(ok)
        self.assertEqual(self.state["players"][P2]["energy"], 90)

    def test_both_end_turns_advance_the_day_back_to_the_starting_player(self):
        stand(self.state, P1, 1, 1)
        ok, _ = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "plant 1 1 kabocha", player=P1)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "water 1 1", player=P1)
        self.assertTrue(ok)
        # Sleep in the cabin so the new day starts at full energy.
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, _ = do_action(self.state, self.crops, "end turn", player=P1)
        self.assertTrue(ok)
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["day"], 2)
        self.assertEqual(self.state["current_player"], config_starting_player())
        # Both slept in the cabin, so together rest raises the wake to 105.
        self.assertEqual(self.state["players"][P1]["energy"], 105)
        self.assertEqual(self.state["players"][P2]["energy"], 105)
        self.assertFalse(self.state["players"][P1]["ended_turn"])
        self.assertFalse(self.state["players"][P2]["ended_turn"])
        crop = self.state["tiles"][0][0]["crop"]
        self.assertEqual(crop["days_grown"], 1)
        self.assertIn("Day 2 dawns", msg)

    def test_log_names_the_player(self):
        stand(self.state, P1, 1, 1)
        ok, _ = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertTrue(ok)
        last = self.state["log"][-1]
        self.assertEqual(last["player"], P1)
        self.assertIn(f"{N1} tills", last["text"])

    
    def test_fresh_state_starts_on_the_starting_players_turn(self):
        self.assertEqual(self.state["current_player"], config_starting_player())
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 100)
        self.assertFalse(self.state["players"][P1]["ended_turn"])

    def test_parse_end_turn_with_optional_note(self):
        self.assertEqual(parse_end_turn_command("end turn"), (True, ""))
        self.assertEqual(parse_end_turn_command("end turn: hi there"), (True, "hi there"))
        self.assertEqual(parse_end_turn_command("end turn water the kabocha"), (True, "water the kabocha"))
        self.assertEqual(parse_end_turn_command("end-turn: wait"), (True, "wait"))
        self.assertEqual(parse_end_turn_command("end turnip"), (False, ""))
        self.assertEqual(parse_end_turn_command("till 1 1"), (False, ""))

    def test_note_is_capped_at_280(self):
        self.assertEqual(NOTE_MAX, 280)
        self.assertEqual(len(sanitize_note("a" * 400)), 280)
        self.assertEqual(sanitize_note("  hello   \n world  "), "hello world")

    def test_end_turn_logs_and_stores_a_note(self):
        ok, msg = do_action(self.state, self.crops, "end turn see you in the morning", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["current_player"], P2)
        note = self.state["last_note"]
        self.assertEqual(note["from"], P1)
        self.assertEqual(note["text"], "see you in the morning")
        texts = [e["text"] for e in self.state["log"]]
        self.assertTrue(any(f"{N1} leaves a note: see you in the morning" in t for t in texts))
        spring = self.state["journal"]["seasons"]["spring"]
        self.assertEqual(len(spring), 1)
        self.assertEqual(spring[0]["from"], P1)
        self.assertEqual(spring[0]["text"], "see you in the morning")
        self.assertEqual(spring[0]["day"], 1)
        self.assertEqual(spring[0]["season"], "spring")
        self.assertEqual(spring[0]["year"], 1)

    def test_note_clears_when_the_recipient_ends_their_turn(self):
        ok, _ = do_action(self.state, self.crops, "end turn: water tomorrow", player=P1)
        self.assertTrue(ok)
        self.assertEqual(self.state["last_note"]["from"], P1)
        # The other player ends without a note — the first note has been read and is cleared.
        ok, _ = do_action(self.state, self.crops, "end turn", player=P2)
        self.assertTrue(ok)
        self.assertFalse(self.state.get("last_note"))
        # Day advanced, starting player's turn. The other player leaves a note.
        ok, _ = do_action(self.state, self.crops, "end turn: I watered already", player=P1)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "end turn: look at the kabocha", player=P2)
        self.assertTrue(ok)
        note = self.state["last_note"]
        self.assertEqual(note["from"], P2)
        self.assertEqual(note["text"], "look at the kabocha")
        self.assertEqual(self.state["current_player"], P1)
        # The handoff note cleared earlier, but every end-turn note stays in the journal.
        texts = [e["text"] for e in all_journal_entries(self.state)]
        self.assertEqual(
            texts,
            ["water tomorrow", "I watered already", "look at the kabocha"],
        )

    def test_hey_ping_message_includes_the_note(self):
        self.assertEqual(
            turn_ping_message(4),
            "🌱 Lantern Farm: your turn (Day 4)",
        )
        bare = turn_ping_message(4)
        self.assertIn("Day 4", bare)
        noted = turn_ping_message(4, "water the kabocha")
        self.assertIn("Day 4", noted)
        self.assertIn("water the kabocha", noted)
        self.assertNotEqual(bare, noted)



class GentleWeeds(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops)
        give_seeds(self.state, "kabocha", 2)

    def _tilled_farm(self):
        # Till every soil plot so all 8 can sprout weeds.
        for r in range(1, 4):
            for c in range(1, 4):
                if r == 1 and c == 3:
                    continue
                ok, msg = till(self.state, self.crops, r, c)
                self.assertTrue(ok, msg)

    def test_weed_hash_is_deterministic(self):
        self.assertEqual(weed_hash(5, 2, 1), weed_hash(5, 2, 1))
        self.assertNotEqual(weed_hash(5, 2, 1), weed_hash(6, 2, 1))
        self.assertNotEqual(weed_hash(5, 2, 1), weed_hash(5, 3, 1))

    def test_one_to_two_new_weeds_a_day(self):
        for day in range(1, 57):
            n = new_weed_count_for_day(day, self.rules)
            self.assertIn(n, (1, 2), f"day {day} counted {n}")

    def test_sprout_is_reproducible_and_skips_cabin_and_untilled(self):
        self._tilled_farm()
        self.state["day"] = 5
        notes_a = sprout_and_age_weeds(self.state, self.rules)
        spots_a = [
            (r, c)
            for r, c, tile in (
                (r, c, self.state["tiles"][r - 1][c - 1])
                for r in range(1, 4)
                for c in range(1, 4)
            )
            if tile.get("weed")
        ]
        self.assertTrue(1 <= len(spots_a) <= 2)
        self.assertTrue(any("A small weed has crept in" in n for n in notes_a))
        self.assertIsNone(self.state["tiles"][0][2].get("weed"))  # cabin
        # Replay on a fresh tilled farm should pick the same plots.
        other = fresh_state(self.crops)
        for r, c in ((r, c) for r in range(1, 4) for c in range(1, 4) if not (r == 1 and c == 3)):
            till(other, self.crops, r, c)
        other["day"] = 5
        sprout_and_age_weeds(other, self.rules)
        spots_b = [
            (r, c)
            for r in range(1, 4)
            for c in range(1, 4)
            if other["tiles"][r - 1][c - 1].get("weed")
        ]
        self.assertEqual(spots_a, spots_b)
        # Untilled empty soil is not eligible.
        bare = fresh_state(self.crops)
        bare["day"] = 5
        sprout_and_age_weeds(bare, self.rules)
        for r in range(1, 4):
            for c in range(1, 4):
                self.assertFalse(bare["tiles"][r - 1][c - 1].get("weed"))

    def test_unplucked_weed_becomes_weedy_the_next_day_turn(self):
        ok, _ = till(self.state, self.crops, 1, 1)
        self.assertTrue(ok)
        ok, _ = plant(self.state, self.crops, 1, 1, "kabocha")
        self.assertTrue(ok)
        self.state["tiles"][0][0]["weed"] = {"appeared_day": 1}
        self.state["day"] = 2
        notes = sprout_and_age_weeds(self.state, no_weed_rules())
        self.assertTrue(self.state["tiles"][0][0]["weedy"])
        self.assertTrue(any("grown weedy" in n for n in notes))
        # Same-day weed does not become weedy yet.
        fresh = fresh_state(self.crops)
        till(fresh, self.crops, 1, 1)
        fresh["tiles"][0][0]["weed"] = {"appeared_day": 1}
        fresh["day"] = 1
        sprout_and_age_weeds(fresh, no_weed_rules())
        self.assertFalse(fresh["tiles"][0][0]["weedy"])

    def test_weedy_plot_skips_every_other_watered_growth(self):
        ok, _ = till(self.state, self.crops, 1, 1)
        self.assertTrue(ok)
        ok, _ = plant(self.state, self.crops, 1, 1, "kabocha")
        self.assertTrue(ok)
        tile = self.state["tiles"][0][0]
        tile["weed"] = {"appeared_day": 1}
        tile["weedy"] = True
        tile["weedy_ticks"] = 0
        grown = []
        for _ in range(4):
            water(self.state, self.crops, 1, 1)
            ok, msg = sleep(self.state, self.crops, no_weed_rules())
            self.assertTrue(ok, msg)
            grown.append(self.state["tiles"][0][0]["crop"]["days_grown"])
        # Grow, skip, grow, skip — 50%.
        self.assertEqual(grown, [1, 1, 2, 2])
        self.assertNotEqual(self.state["tiles"][0][0]["crop"]["stage"], "withered")

    def test_pluck_clears_weed_and_weedy_and_costs_five(self):
        till(self.state, self.crops, 1, 1)
        plant(self.state, self.crops, 1, 1, "kabocha")
        tile = self.state["tiles"][0][0]
        tile["weed"] = {"appeared_day": 1}
        tile["weedy"] = True
        tile["weedy_ticks"] = 3
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "pluck 1 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertIn("plucks the weed", msg)
        self.assertIsNone(self.state["tiles"][0][0]["weed"])
        self.assertFalse(self.state["tiles"][0][0]["weedy"])
        self.assertEqual(self.state["tiles"][0][0]["weedy_ticks"], 0)
        self.assertEqual(self.state["players"][P1]["energy"], 95)
        # After plucking, growth is full speed again.
        water(self.state, self.crops, 1, 1)
        sleep(self.state, self.crops, no_weed_rules())
        water(self.state, self.crops, 1, 1)
        sleep(self.state, self.crops, no_weed_rules())
        self.assertEqual(self.state["tiles"][0][0]["crop"]["days_grown"], 2)

    def test_pluck_fails_without_a_weed_and_spends_nothing(self):
        till(self.state, self.crops, 1, 1)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "pluck 1 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("no weed", msg.lower())
        self.assertEqual(self.state["players"][P1]["energy"], 100)

    def test_weeds_never_kill_crops(self):
        till(self.state, self.crops, 1, 1)
        plant(self.state, self.crops, 1, 1, "kabocha")
        tile = self.state["tiles"][0][0]
        tile["weed"] = {"appeared_day": 1}
        tile["weedy"] = True
        # Stay watered so dryness cannot be blamed.
        for _ in range(8):
            water(self.state, self.crops, 1, 1)
            sleep(self.state, self.crops, no_weed_rules())
        crop = self.state["tiles"][0][0]["crop"]
        self.assertIsNotNone(crop)
        self.assertNotEqual(crop["stage"], "withered")
        self.assertGreaterEqual(crop["days_grown"], 4)  # 50% of 8

    def test_sprite_key_marks_weeds(self):
        from sprites import sprite_key, svg_for_key, parse_sprite_key
        tile = self.state["tiles"][0][0]
        tile["tilled"] = True
        tile["weed"] = {"appeared_day": 1}
        self.assertTrue(sprite_key(tile).endswith("_weed"))
        tile["weedy"] = True
        self.assertTrue(sprite_key(tile).endswith("_weedy"))
        info = parse_sprite_key(sprite_key(tile))
        self.assertTrue(info.get("weedy"))
        svg = svg_for_key(sprite_key(tile))
        self.assertIn("<svg", svg)




class SeasonalWeatherAndForecast(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()

    def test_snow_waters_plots_like_rain(self):
        # Day 46 is the first day of winter, when snow is possible.
        seed = find_weather_seed({45: "sun", 46: "snow"}, self.rules, self.crops)
        state = fresh_state(self.crops, weather_seed=seed, rules=self.rules)
        state["day"] = 45
        state["season"] = "autumn"
        state["weather"] = "sun"
        r, c = 1, 1
        till(state, self.crops, r, c)
        give_seeds(state, "carrot", 1)
        ok, msg = plant(state, self.crops, r, c, "carrot")
        self.assertTrue(ok, msg)
        # Jumping the calendar must not keep a wet flag from day 1.
        state["tiles"][0][0]["watered"] = False
        # No watering. Sleep to a snowy winter dawn.
        ok, msg = sleep(state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        self.assertEqual(state["day"], 46)
        self.assertEqual(state["season"], "winter")
        self.assertEqual(state["weather"], "snow")
        self.assertTrue(state["tiles"][0][0]["watered"])
        self.assertIn("snow", msg.lower())
        crop = state["tiles"][0][0]["crop"]
        self.assertNotEqual(crop["stage"], "withered")
        # The snow morning counts as water into the next evening.
        ok, msg = sleep(state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        crop = state["tiles"][0][0]["crop"]
        self.assertEqual(crop["days_grown"], 1)
        self.assertNotEqual(crop["stage"], "withered")

    def test_migrate_keeps_todays_weather(self):
        state = fresh_state(self.crops)
        state["day"] = 13
        state["season"] = "spring"
        state["weather"] = "sun"
        state.pop("weather_seed", None)
        changed = migrate_state(state, self.rules)
        self.assertTrue(changed)
        self.assertEqual(state["weather"], "sun")
        self.assertEqual(state["day"], 13)
        self.assertIn("weather_seed", state)
        self.assertEqual(
            weather_for_day(13, self.crops, self.rules, seed=state["weather_seed"]),
            "sun",
        )
        # A second migrate must not change the seed or the weather.
        seed = state["weather_seed"]
        self.assertFalse(ensure_weather_seed(state, self.rules, self.crops))
        self.assertEqual(state["weather_seed"], seed)
        self.assertEqual(state["weather"], "sun")

    def test_forecast_is_deterministic_and_sharpens_as_the_day_approaches(self):
        seed = 7
        made = 10
        first = [forecast_weather(made + k, made, seed, self.crops, self.rules) for k in range(1, 8)]
        again = [forecast_weather(made + k, made, seed, self.crops, self.rules) for k in range(1, 8)]
        self.assertEqual(first, again)
        self.assertEqual(round(forecast_accuracy(1, self.rules), 2), 0.90)
        self.assertEqual(round(forecast_accuracy(7, self.rules), 2), 0.50)
        # Over many seeds, day+1 is right more often than day+7.
        near = far = 0
        samples = 800
        for s in range(samples):
            actual1 = weather_for_day(made + 1, self.crops, self.rules, seed=s)
            actual7 = weather_for_day(made + 7, self.crops, self.rules, seed=s)
            if forecast_weather(made + 1, made, s, self.crops, self.rules) == actual1:
                near += 1
            if forecast_weather(made + 7, made, s, self.crops, self.rules) == actual7:
                far += 1
        self.assertGreater(near / samples, 0.80)
        self.assertLess(near / samples, 0.98)
        self.assertGreater(far / samples, 0.38)
        self.assertLess(far / samples, 0.62)
        self.assertGreater(near, far)

    def test_forecast_for_a_day_can_change_when_remade_later(self):
        # Find a case where the prediction for a target day changes as we approach it.
        changed = False
        target = 20
        for seed in range(4000):
            early = forecast_weather(target, target - 7, seed, self.crops, self.rules)
            late = forecast_weather(target, target - 1, seed, self.crops, self.rules)
            if early != late:
                changed = True
                break
        self.assertTrue(changed)

    def test_weather_forecast_helper_has_seven_days(self):
        state = fresh_state(self.crops)
        days = weather_forecast(state, self.crops, self.rules)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]["day"], state["day"] + 1)
        self.assertEqual(days[-1]["day"], state["day"] + 7)
        self.assertEqual(days[0]["lead"], 1)

    def test_cabin_sprite_keys_follow_the_weather(self):
        from sprites import sprite_key, svg_for_key, parse_sprite_key
        tile = {"type": "cabin"}
        self.assertEqual(sprite_key(tile), "cabin")
        self.assertEqual(sprite_key(tile, "sun"), "cabin")
        self.assertEqual(sprite_key(tile, "rain"), "cabin_rain")
        self.assertEqual(sprite_key(tile, "snow"), "cabin_snow")
        self.assertEqual(sprite_key(tile, "storm"), "cabin_storm")
        self.assertEqual(sprite_key(tile, "cloud"), "cabin_cloud")
        rain = svg_for_key("cabin_rain")
        snow = svg_for_key("cabin_snow")
        clear = svg_for_key("cabin")
        self.assertIn("<line", rain)
        self.assertIn("<circle", snow)
        self.assertNotEqual(rain, clear)
        self.assertNotEqual(snow, clear)
        self.assertEqual(parse_sprite_key("cabin_rain")["weather"], "rain")
        self.assertEqual(parse_sprite_key("cabin_snow")["weather"], "snow")
        self.assertEqual(parse_sprite_key("cabin_rain_fire")["weather"], "rain")
        self.assertTrue(parse_sprite_key("cabin_rain_fire")["fire"])
        self.assertEqual(parse_sprite_key("cabin_snow_fire")["weather"], "snow")
        self.assertTrue(parse_sprite_key("cabin_fire")["fire"])
        self.assertEqual(parse_sprite_key("cabin_fire")["weather"], "sun")


    def test_sprite_key_marks_snow_on_the_ground(self):
        from sprites import sprite_key, svg_for_key, parse_sprite_key, is_safe_key
        soil = {"type": "plot", "tilled": False, "watered": False}
        self.assertEqual(sprite_key(soil), "soil")
        self.assertEqual(sprite_key(soil, "rain"), "soil")
        self.assertEqual(sprite_key(soil, "snow"), "soil_snow")
        tilled = {"type": "plot", "tilled": True, "watered": False}
        self.assertEqual(sprite_key(tilled, "snow"), "soil_tilled_snow")
        watered = {"type": "plot", "tilled": True, "watered": True}
        self.assertEqual(sprite_key(watered, "snow"), "soil_watered_snow")
        wet = {"type": "plot", "tilled": False, "watered": True}
        self.assertEqual(sprite_key(wet, "snow"), "soil_wet_snow")
        crop = {
            "type": "plot", "tilled": True, "watered": True,
            "crop": {"kind": "strawberry", "stage": "mature"},
        }
        self.assertEqual(sprite_key(crop, "snow"), "strawberry_mature_wet_snow")
        weedy = {"type": "plot", "tilled": True, "watered": False, "weedy": True}
        self.assertEqual(sprite_key(weedy, "snow"), "soil_tilled_snow_weedy")
        info = parse_sprite_key("strawberry_mature_wet_snow_weedy")
        self.assertTrue(info["snow"])
        self.assertTrue(info["weedy"])
        self.assertEqual(info["kind"], "strawberry")
        self.assertEqual(info["stage"], "mature")
        snow_svg = svg_for_key("soil_snow")
        plain = svg_for_key("soil")
        self.assertIn("#f2efe8", snow_svg)
        self.assertNotEqual(snow_svg, plain)
        crop_svg = svg_for_key("strawberry_mature_wet_snow")
        self.assertIn("#f2efe8", crop_svg)
        self.assertTrue(is_safe_key("strawberry_mature_wet_snow_weedy"))
        self.assertTrue(is_safe_key("soil_watered_snow"))


class ConfigAndMCP(unittest.TestCase):
    def test_example_config_is_generic(self):
        from pathlib import Path
        import json
        example = json.loads((Path(__file__).resolve().parent / "config.example.json").read_text())
        blob = json.dumps(example)
        self.assertIsNone(example.get("notify"))
        names = [p.get("name") for p in example.get("players") or []]
        self.assertEqual(names, ["Player 1", "Player 2"])
        self.assertNotIn("Hey", blob)
        self.assertIsNone(example.get("notify"))
        # No host-specific bind addresses or env-file paths.
        self.assertNotIn("100.", blob)
        self.assertNotIn("~/.config/", blob)
        bind = example.get("bind") or {}
        self.assertIn("127.0.0.1", bind.get("allowed_hosts") or [])
        self.assertIn("localhost", bind.get("allowed_hosts") or [])
        tokens = example.get("web_tokens") or {}
        self.assertEqual(set(tokens), {"player1", "player2"})
        self.assertFalse(any(str(v or "").strip() for v in tokens.values()))

    def test_local_overlay_keeps_configured_display_names(self):
        from config import display_name, load_config, notify_config, player_ids, starting_player
        # On a machine with config.local.json this is the personal overlay;
        # without it, the example names are used. Either way ids are consistent.
        ids = player_ids()
        self.assertGreaterEqual(len(ids), 2)
        self.assertEqual(self.state_ids_are_strings(ids), True)
        self.assertTrue(starting_player() in ids)
        for pid in ids:
            self.assertTrue(display_name(pid))
        cfg = load_config()
        self.assertIn("theme", cfg)
        # Notify may be present only in the local overlay; never required.
        notify = notify_config()
        if notify:
            self.assertIn("from", notify)
            self.assertIn("to", notify)
            blob = json.dumps(notify)
            # Credentials themselves never live in the farm config, only key names and a path.
            self.assertNotIn("http://", blob)
            self.assertNotIn("https://", blob)

    def state_ids_are_strings(self, ids):
        return all(isinstance(i, str) and i for i in ids)

    def _tmp_farm(self):
        import tempfile
        from engine import fresh_state, load_crops, save_state
        folder = Path(tempfile.mkdtemp(prefix="lantern-farm-mcp-"))
        path = folder / "state.json"
        save_state(fresh_state(load_crops()), path)
        return path

    def test_mcp_tools_share_turn_rules_on_a_temp_save(self):
        from config import display_name, player_ids, starting_player
        import mcp_server
        path = self._tmp_farm()
        mcp_server._STATE_PATH = path
        self.addCleanup(lambda: setattr(mcp_server, "_STATE_PATH", None))
        p1, p2 = player_ids()[0], player_ids()[1]
        self.assertEqual(p1, starting_player())
        look = mcp_server.farm_look(p1)
        self.assertIn(display_name(p1), look)
        self.assertIn("Day 1", look)
        rules = json.loads(mcp_server.farm_rules())
        self.assertEqual(rules["action_energy"]["pluck"], 5)
        self.assertEqual(rules["action_energy"]["till"], 10)
        self.assertEqual(rules["action_energy"]["move"], 5)
        self.assertEqual(rules["snacks_per_turn"], 2)
        self.assertEqual(rules["pass_out_energy"], 50)
        self.assertEqual(rules["max_energy"], 100)
        ok, msg = mcp_server.farm_do(p2, "till 1 1")
        self.assertFalse(ok)
        self.assertIn(display_name(p1), msg)
        ok, msg = mcp_server.farm_do(p1, "take hoe")
        self.assertTrue(ok, msg)
        ok, msg = mcp_server.farm_do(p1, "take watering_can")
        self.assertTrue(ok, msg)
        ok, msg = mcp_server.farm_do(p1, "move to 1 1")
        self.assertTrue(ok, msg)
        ok, msg = mcp_server.farm_do(p1, "till 1 1")
        self.assertTrue(ok, msg)
        # Second look as p1 should show the tilled plot.
        look = mcp_server.farm_look(p1, path=path)
        self.assertIn("tilled", look.lower())
        ok, msg = mcp_server.farm_end_turn(p1, "see you")
        self.assertTrue(ok, msg)
        self.assertIn("ends the turn", msg.lower())
        look = mcp_server.farm_look(p2, path=path)
        self.assertIn("see you", look)
        self.assertIn(f"Note from {display_name(p1)} (player text):", look)
        # It is now the other player's turn on the temp save, not the live one.
        ok, msg = mcp_server.farm_do(p1, "water 1 1")
        self.assertFalse(ok)
        ok, msg = mcp_server.farm_do(p2, "take watering_can")
        self.assertTrue(ok, msg)
        ok, msg = mcp_server.farm_do(p2, "move to 1 1")
        self.assertTrue(ok, msg)
        ok, msg = mcp_server.farm_do(p2, "water 1 1")
        self.assertTrue(ok, msg)

    def test_mcp_jsonrpc_initialize_and_tools(self):
        import mcp_server
        from config import player_ids, starting_player
        path = self._tmp_farm()
        mcp_server._STATE_PATH = path
        self.addCleanup(lambda: setattr(mcp_server, "_STATE_PATH", None))
        init = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "lantern-farm")
        self.assertIn("tools", init["result"]["capabilities"])
        listed = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listed["result"]["tools"]]
        self.assertEqual(
            names,
            ["farm_look", "farm_do", "farm_end_turn", "farm_forecast", "farm_journal", "farm_recipes", "farm_saves", "farm_rules"],
        )
        p1 = starting_player()
        called = mcp_server.handle_rpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "farm_look", "arguments": {"player": p1}},
        })
        text = called["result"]["content"][0]["text"]
        self.assertIn("Day 1", text)
        self.assertIn("Forecast", text)
        self.assertFalse(called["result"]["isError"])
        forecast = mcp_server.handle_rpc({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "farm_forecast", "arguments": {}},
        })
        ftext = forecast["result"]["content"][0]["text"]
        self.assertIn("Forecast", ftext)
        self.assertFalse(forecast["result"]["isError"])
        # notifications have no response
        self.assertIsNone(mcp_server.handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_mcp_bearer_compare_is_constant_time_shape(self):
        import mcp_server
        self.assertTrue(mcp_server._tokens_match("secret-token", "secret-token"))
        self.assertFalse(mcp_server._tokens_match("secret-token", "other-token"))
        self.assertFalse(mcp_server._tokens_match("", "secret-token"))
        self.assertFalse(mcp_server._tokens_match("secret-token", ""))

    def test_notify_disabled_under_test_flag(self):
        from hey_notify import maybe_notify_after_end_turn, notify_disabled, send_turn_ping
        self.assertTrue(notify_disabled())
        self.assertFalse(send_turn_ping(1, "should not send"))
        # Even a handoff-shaped state must not notify under the flag.
        called = {"n": 0}
        import hey_notify
        def boom(*_a, **_k):
            called["n"] += 1
            raise AssertionError("send_turn_ping must not be called from tests")
        original = hey_notify.send_turn_ping
        hey_notify.send_turn_ping = boom
        try:
            state = {
                "day": 1,
                "current_player": P2,
                "last_note": {"from": P1, "text": "see you", "day": 1},
            }
            maybe_notify_after_end_turn(P1, state, True)
            maybe_notify_after_end_turn(P1, state, True, state_path=self._tmp_farm())
        finally:
            hey_notify.send_turn_ping = original
        self.assertEqual(called["n"], 0)

    def test_tests_do_not_point_at_the_live_save(self):
        self.assertNotEqual(engine.STATE_PATH.resolve(), _LIVE_STATE)
        self.assertFalse(engine.STATE_PATH.resolve().exists() and engine.STATE_PATH.resolve() == _LIVE_STATE)
        self.assertTrue(_LIVE_STATE.name == "state.json")

    def test_notify_skips_non_live_save_even_if_flag_off(self):
        import hey_notify
        path = self._tmp_farm()
        self.assertFalse(hey_notify.is_live_save(path))
        self.assertTrue(hey_notify.is_live_save(None))
        self.assertTrue(hey_notify.is_live_save(_LIVE_STATE))
        called = {"n": 0}
        def boom(*_a, **_k):
            called["n"] += 1
            raise AssertionError("must not send a ping for a temp save")
        original = hey_notify.send_turn_ping
        previous = os.environ.get("LANTERN_FARM_NO_NOTIFY")
        hey_notify.send_turn_ping = boom
        try:
            os.environ.pop("LANTERN_FARM_NO_NOTIFY", None)
            state = {
                "day": 1,
                "current_player": P2,
                "last_note": {"from": P1, "text": "see you", "day": 1},
            }
            hey_notify.maybe_notify_after_end_turn(P1, state, True, state_path=path)
        finally:
            hey_notify.send_turn_ping = original
            if previous is not None:
                os.environ["LANTERN_FARM_NO_NOTIFY"] = previous
        self.assertEqual(called["n"], 0)


    def test_mcp_stdio_is_newline_delimited_json(self):
        import subprocess
        import sys
        script = Path(__file__).resolve().parent / "mcp_server.py"
        init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        listed = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        env = os.environ.copy()
        env["LANTERN_FARM_NO_NOTIFY"] = "1"
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=(init + "\n" + listed + "\n").encode("utf-8"),
            capture_output=True,
            timeout=10,
            env=env,
            cwd=str(script.parent),
        )
        self.assertNotIn(b"Content-Length", proc.stdout)
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 2, proc.stderr.decode("utf-8", "replace"))
        messages = [json.loads(ln) for ln in lines]
        by_id = {m["id"]: m for m in messages}
        self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "lantern-farm")
        names = [tool["name"] for tool in by_id[2]["result"]["tools"]]
        self.assertEqual(
            names,
            ["farm_look", "farm_do", "farm_end_turn", "farm_forecast", "farm_journal", "farm_recipes", "farm_saves", "farm_rules"],
        )
        self.assertEqual(proc.returncode, 0)


class PlayerNotesAreUntrusted(unittest.TestCase):
    def test_look_labels_notes_as_player_text_and_strips_controls(self):
        from describe import describe_state, format_player_note
        crops = load_crops()
        state = fresh_state(crops)
        state["last_note"] = {"from": P1, "text": "hello\x07 there", "day": 1}
        labeled = format_player_note(state["last_note"])
        self.assertEqual(labeled, f"Note from {N1} (player text): hello there")
        text = describe_state(state, crops, viewer=P2)
        self.assertIn(labeled, text)
        self.assertNotIn("\x07", text)
        self.assertNotIn(f"{N1}'s note:", text)


class WebCsrfAndTokens(unittest.TestCase):
    def setUp(self):
        import threading
        import web
        self.web = web
        save_state = __import__("engine", fromlist=["save_state"]).save_state
        st = fresh_state(load_crops())
        kit_out(st, P1)
        save_state(st, engine.STATE_PATH)
        web._TEST_WEB_TOKENS = {P1: "test-token-one", P2: "test-token-two"}
        self.server = web.try_bind("127.0.0.1", 0)
        self.assertIsNotNone(self.server)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        self.web._TEST_WEB_TOKENS = None
        self.web._LISTEN_PORTS.discard(self.port)

    def _request(self, method, path, body=None, headers=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data
        finally:
            conn.close()

    def test_text_plain_post_is_rejected(self):
        status, _, _ = self._request(
            "POST",
            "/api/do?key=test-token-one",
            body=b'{"command": "look"}',
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 415)

    def test_bad_origin_is_forbidden(self):
        status, _, _ = self._request(
            "POST",
            "/api/do?key=test-token-one",
            body=b'{"command": "look"}',
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)

    def test_bad_host_is_forbidden_on_get_and_post(self):
        status, _, _ = self._request(
            "GET",
            "/api/state?key=test-token-one",
            headers={"Host": "evil.example"},
        )
        self.assertEqual(status, 403)
        status, _, _ = self._request(
            "POST",
            "/api/do?key=test-token-one",
            body=b'{"command": "look"}',
            headers={"Content-Type": "application/json", "Host": "evil.example"},
        )
        self.assertEqual(status, 403)

    def test_missing_or_wrong_token_is_unauthorized(self):
        status, _, _ = self._request("GET", "/")
        self.assertIn(status, (401, 403))
        status, _, _ = self._request("GET", "/api/state")
        self.assertIn(status, (401, 403))
        status, _, _ = self._request(
            "POST",
            "/api/do",
            body=b'{"command": "look"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertIn(status, (401, 403))
        status, _, _ = self._request("GET", "/api/state?key=wrong-token")
        self.assertIn(status, (401, 403))
        status, _, _ = self._request(
            "POST",
            "/api/do?key=wrong-token",
            body=b'{"command": "look"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertIn(status, (401, 403))

    def test_right_token_works_and_sets_cookie(self):
        status, headers, body = self._request("GET", "/api/state?key=test-token-one")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload.get("viewer"), P1)
        status, headers, _ = self._request("GET", f"/?player={P1}&key=test-token-one")
        self.assertEqual(status, 302)
        cookie = headers.get("set-cookie") or ""
        self.assertTrue(cookie.startswith(self.web.COOKIE_NAME + "="))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        # Cookie alone is enough after the first visit.
        status, _, body = self._request(
            "GET",
            "/api/state",
            headers={"Cookie": f"{self.web.COOKIE_NAME}=test-token-one"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("viewer"), P1)

    def test_body_player_cannot_override_the_token(self):
        # Token for the second player, body claims the first: still not their turn.
        status, _, body = self._request(
            "POST",
            "/api/do?key=test-token-two",
            body=json.dumps({"command": "till 1 1", "player": P1}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("viewer"), P2)
        # Token for the first player, body claims the second: the action is still theirs.
        status, _, body = self._request(
            "POST",
            "/api/do?key=test-token-one",
            body=json.dumps({"command": "move to 1 1", "player": P2}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body).get("ok"), json.loads(body).get("message"))
        status, _, body = self._request(
            "POST",
            "/api/do?key=test-token-one",
            body=json.dumps({"command": "till 1 1", "player": P2}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload.get("ok"), payload.get("message"))
        self.assertEqual(payload.get("viewer"), P1)
        tile = payload["state"]["tiles"][0][0]
        self.assertTrue(tile.get("tilled"))


class AvatarsSleepAndSnacks(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops)
        kit_out(self.state, P1)

    def test_fresh_and_migrated_players_start_in_the_cabin(self):
        self.assertTrue(is_player_in_cabin(self.state, P1))
        self.assertTrue(is_player_in_cabin(self.state, P2))
        self.assertEqual(player_where(self.state, P1), (CABIN_ROW, CABIN_COL))
        orphan = fresh_state(self.crops)
        for slot in orphan["players"].values():
            slot.pop("row", None)
            slot.pop("col", None)
            slot.pop("snacks_eaten", None)
        energy = orphan["players"][P1]["energy"]
        migrate_state(orphan, self.rules)
        self.assertEqual(player_where(orphan, P1), (CABIN_ROW, CABIN_COL))
        self.assertEqual(orphan["players"][P1]["energy"], energy)
        self.assertEqual(orphan["players"][P1]["snacks_eaten"], 0)

    def test_must_stand_on_a_tile_to_work_it(self):
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("Walk there", msg)
        self.assertFalse(self.state["tiles"][0][0]["tilled"])
        ok, msg = do_action(self.state, self.crops, "move to 1 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(player_where(self.state, P1), (1, 1))
        # cabin (1,3) to (1,1) is two steps.
        self.assertEqual(self.state["players"][P1]["energy"], 90)
        ok, msg = do_action(self.state, self.crops, "till", player=P1)
        self.assertTrue(ok, msg)
        self.assertTrue(self.state["tiles"][0][0]["tilled"])

    def test_diagonal_step_costs_the_same_as_cardinal(self):
        # Cabin 1,3 to center 2,2 is one diagonal step.
        self.assertEqual(path_cost((1, 3), (2, 2), self.rules), 5)
        self.assertEqual(path_cost((1, 3), (1, 1), self.rules), 10)
        ok, msg = do_action(self.state, self.crops, "move to 2 2", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(player_where(self.state, P1), (2, 2))
        self.assertEqual(self.state["players"][P1]["energy"], 95)
        before = self.state["players"][P1]["energy"]
        ok, msg = do_action(self.state, self.crops, "move down", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], before - 5)
        # Not enough energy: no partial move.
        self.state["players"][P1]["energy"] = 5
        here = player_where(self.state, P1)
        ok, msg = do_action(self.state, self.crops, "move to 1 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("energy", msg.lower())
        self.assertEqual(player_where(self.state, P1), here)

    def test_go_cabin_and_already_there(self):
        ok, msg = do_action(self.state, self.crops, "go cabin", player=P1)
        self.assertTrue(ok, msg)
        self.assertIn("already", msg.lower())
        ok, msg = do_action(self.state, self.crops, "move to 3 3", player=P1)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "go cabin", player=P1)
        self.assertTrue(ok, msg)
        self.assertTrue(is_player_in_cabin(self.state, P1))

    def test_walk_messages_name_the_place_cleanly(self):
        from engine import describe_place, describe_where, steps_phrase
        # Cabin is already where a fresh farm starts.
        self.assertEqual(describe_place(1, 3), "the cabin")
        self.assertEqual(describe_where(1, 3), "in the cabin")
        self.assertEqual(describe_place(2, 3), "mid-right, row 2 col 3")
        self.assertEqual(describe_where(2, 3), "at mid-right, row 2 col 3")
        self.assertEqual(steps_phrase(1), "1 step")
        self.assertEqual(steps_phrase(2), "2 steps")
        ok, msg = do_action(self.state, self.crops, "move to 2 3", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, f"{N1} walks to mid-right, row 2 col 3 (1 step, 5 energy).")
        self.assertNotIn("walks to at ", msg)
        self.assertNotIn("step(s)", msg)
        ok, msg = do_action(self.state, self.crops, "move to 2 3", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, f"{N1} is already at mid-right, row 2 col 3.")
        ok, msg = do_action(self.state, self.crops, "go cabin", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, f"{N1} walks to the cabin (1 step, 5 energy).")
        self.assertNotIn("walks to in the cabin", msg)
        ok, msg = do_action(self.state, self.crops, "move down", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, f"{N1} walks down to mid-right, row 2 col 3 (5 energy).")
        self.assertNotIn("to at ", msg)
        self.state["players"][P1]["energy"] = 5
        ok, msg = do_action(self.state, self.crops, "move to 3 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("Walking to bottom-left, row 3 col 1 is 2 steps (10 energy)", msg)
        self.assertNotIn("step(s)", msg)

    def test_sleep_in_cabin_and_pass_out_in_the_field(self):
        self.assertIn("sleep", sleep_outlook(self.state, P1).lower())
        self.assertIn("105", sleep_outlook(self.state, P1))
        self.assertIn("sleeping close tonight", sleep_outlook(self.state, P1))
        stand(self.state, P1, 3, 1)
        self.assertIn("pass out", sleep_outlook(self.state, P1).lower())
        self.assertIn("50", sleep_outlook(self.state, P1))
        ok, msg = do_action(self.state, self.crops, "end turn", player=P1)
        self.assertTrue(ok, msg)
        self.assertIn("pass out", msg.lower())
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["day"], 2)
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertEqual(player_where(self.state, P1), (3, 1))
        self.assertEqual(self.state["players"][P2]["energy"], 100)
        self.assertTrue(is_player_in_cabin(self.state, P2))
        header = "\n".join(__import__("describe").turn_header_lines(self.state, self.crops, viewer=P1))
        self.assertIn(f"{N1} is at bottom-left, row 3 col 1", header)
        self.assertIn(f"{N2} is in the cabin", header)
        self.assertIn("You'll pass out in the field", header)

    def test_eat_restores_energy_and_is_capped_at_two_snacks(self):
        self.assertEqual(eat_energy_for(self.crops, "carrot"), 10)
        self.assertEqual(eat_energy_for(self.crops, "turnip"), 12)
        self.assertEqual(eat_energy_for(self.crops, "strawberry"), 30)
        self.assertEqual(eat_energy_for(self.crops, "everbearing"), 20)
        self.assertEqual(eat_energy_for(self.crops, "kabocha"), 25)
        give_item(self.state, "carrot", 3, player=P1)
        self.state["players"][P1]["energy"] = 20
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 30)
        self.assertEqual(self.state["inventory"]["carrot"], 2)
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["inventory"]["carrot"], 1)
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1)
        self.assertFalse(ok)
        self.assertEqual(self.state["inventory"]["carrot"], 1)
        # Seeds are not snacks; leftover crop can still be sold.
        ok, msg = do_action(self.state, self.crops, "eat carrot_seed", player=P1)
        self.assertFalse(ok)
        gold = self.state["gold"]
        ok, msg = do_action(self.state, self.crops, "sell carrot 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold + 32)
        self.assertEqual(self.state["inventory"]["carrot"], 0)

    def test_eat_will_not_exceed_max_energy(self):
        give_item(self.state, "kabocha", 1, player=P1)
        self.state["players"][P1]["energy"] = 90
        ok, msg = do_action(self.state, self.crops, "eat kabocha", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["inventory"]["kabocha"], 0)
        give_item(self.state, "kabocha", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "eat kabocha", player=P1)
        self.assertFalse(ok)
        self.assertEqual(self.state["inventory"]["kabocha"], 1)


class SpringCropsAndShop(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)

    def test_new_farm_starts_with_strawberry_seeds(self):
        inv = self.state["inventory"]
        self.assertEqual(inv["strawberry_seed"], 2)
        self.assertEqual(inv["strawberry"], 0)
        self.assertEqual(inv.get("everbearing_seedling", 0), 0)
        self.assertEqual(inv.get("everbearing", 0), 0)
        self.assertEqual(inv.get("kabocha_seed", 0), 0)
        self.assertEqual(inv.get("turnip_seed", 0), 0)
        self.assertEqual(inv.get("carrot_seed", 0), 0)

    def test_shop_sells_strawberry_not_later_crops(self):
        from engine import shop_kinds, crop_in_shop, legal_actions
        spring = shop_kinds(self.crops, "spring")
        self.assertEqual(shop_kinds(self.crops), spring)
        for kind in (
            "strawberry", "everbearing", "turnip", "radish", "lettuce", "spinach",
            "pea", "carrot", "beet", "potato", "bush_bean", "cucumber", "zucchini",
            "tomato", "kabocha", "pumpkin", "corn", "onion", "rhubarb", "asparagus",
        ):
            self.assertIn(kind, spring, kind)
            self.assertTrue(crop_in_shop(self.crops["crops"][kind]), kind)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("buy strawberry 1", actions)
        self.assertIn("buy everbearing 1", actions)
        self.assertIn("buy turnip 1", actions)
        self.assertIn("buy kabocha 1", actions)
        self.assertIn("buy carrot 1", actions)
        self.assertIn("buy rhubarb 1", actions)
        self.assertIn("buy asparagus 1", actions)

    def test_seed_names_are_always_crop_specific(self):
        from inventory import item_name, add_to_pack, add_to_chest
        from describe import describe_state
        from engine import stock_label
        for kind in ("kabocha", "turnip", "carrot", "radish", "tomato"):
            one = item_name(f"{kind}_seed", 1, self.crops, self.rules)
            many = item_name(f"{kind}_seed", 2, self.crops, self.rules)
            self.assertEqual(one, f"1 {kind} seed")
            self.assertEqual(many, f"2 {kind} seeds")
            self.assertEqual(stock_label(kind, crop_info(self.crops, kind), 1), f"{kind} seed")
            self.assertEqual(stock_label(kind, crop_info(self.crops, kind), 2), f"{kind} seeds")
        self.assertEqual(
            item_name("strawberry_seed", 1, self.crops, self.rules),
            "1 June-bearing strawberry seed",
        )
        self.assertEqual(
            item_name("strawberry_seed", 2, self.crops, self.rules),
            "2 June-bearing strawberry seeds",
        )
        self.assertEqual(
            stock_label("strawberry", crop_info(self.crops, "strawberry"), 1),
            "June-bearing strawberry seed",
        )
        self.assertEqual(item_name("bush_bean_seed", 2, self.crops, self.rules), "2 bush bean seeds")
        self.assertEqual(item_name("pea_seed", 1, self.crops, self.rules), "1 pea seed")
        self.assertEqual(item_name("potato_seed", 1, self.crops, self.rules), "1 potato seed")
        self.assertEqual(item_name("rhubarb_crown", 1, self.crops, self.rules), "1 rhubarb crown")
        self.assertEqual(item_name("rhubarb_crown", 2, self.crops, self.rules), "2 rhubarb crowns")
        self.assertEqual(item_name("asparagus_crown", 2, self.crops, self.rules), "2 asparagus crowns")
        self.assertEqual(
            item_name("everbearing_seedling", 1, self.crops, self.rules),
            "1 everbearing strawberry seed",
        )
        self.assertEqual(
            item_name("everbearing_seedling", 2, self.crops, self.rules),
            "2 everbearing strawberry seeds",
        )
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["gold"] = 500
        ok, msg = buy(self.state, self.crops, "strawberry", 2, player=P1)
        self.assertTrue(ok, msg)
        self.assertIn("June-bearing strawberry seeds", msg)
        self.assertNotIn("2 seeds", msg)
        add_to_pack(self.state, P1, "turnip_seed", 2, self.rules)
        add_to_chest(self.state, "carrot_seed", 3, self.rules)
        text_view = describe_state(self.state, self.crops, viewer=P1)
        self.assertIn("2 turnip seeds", text_view)
        self.assertIn("3 carrot seeds", text_view)
        # A bare "N seeds" (no crop name) should not appear in look text.
        import re
        bare = re.findall(r"(?<![A-Za-z])(\d+ seeds)(?![A-Za-z])", text_view)
        self.assertEqual(bare, [])


    def test_no_seed_or_crown_display_name_is_bare(self):
        from inventory import item_label, item_name
        from engine import action_item_phrase, shop_name, stock_key, stock_label
        bare = {"seed", "seeds", "crown", "crowns", "seedling", "seedlings"}
        for kind, info in self.crops["crops"].items():
            label = stock_label(kind, info)
            shop = shop_name(kind, info)
            key = stock_key(kind, info)
            listed = item_label(key, self.crops, self.rules)
            phrase = action_item_phrase(key, self.crops, self.rules)
            for text, where in (
                (label, "stock_label"),
                (shop, "shop_name"),
                (listed, "item_label"),
                (phrase, "action_item_phrase"),
            ):
                words = text.strip()
                self.assertTrue(words, f"{where} empty for {kind}")
                self.assertNotIn(words.lower(), bare, f"{where} bare for {kind}: {words!r}")
                last = words.split()[-1].lower()
                if (info.get("stock") or "seed") == "crown":
                    self.assertIn(last, {"crown", "crowns"}, f"{where} for {kind}: {words!r}")
                else:
                    self.assertIn(last, {"seed", "seeds"}, f"{where} for {kind}: {words!r}")
                self.assertGreaterEqual(len(words.split()), 2, f"{where} for {kind} has no crop name: {words!r}")
        self.assertEqual(item_label("strawberry_seed", self.crops, self.rules), "June-bearing strawberry seed")
        self.assertEqual(item_label("everbearing_seedling", self.crops, self.rules), "everbearing strawberry seed")
        self.assertEqual(item_label("lettuce_seed", self.crops, self.rules), "lettuce seed")
        self.assertEqual(item_label("rhubarb_crown", self.crops, self.rules), "rhubarb crown")
        self.assertEqual(item_label("asparagus_crown", self.crops, self.rules), "asparagus crown")
        self.assertEqual(item_name("turnip_seed", 1, self.crops, self.rules), "1 turnip seed")
        self.assertNotIn("1 turnip seeds", item_name("turnip_seed", 1, self.crops, self.rules))


    def test_every_harvest_crop_except_rhubarb_is_edible(self):
        from engine import eat_energy_for, do_action
        from inventory import item_eat_energy
        for kind, info in self.crops["crops"].items():
            energy = eat_energy_for(self.crops, kind)
            if kind == "rhubarb":
                self.assertIsNone(energy, "rhubarb should be cook-only")
                self.assertIsNone(item_eat_energy(kind, self.crops, self.rules))
            else:
                self.assertIsNotNone(energy, f"{kind} should be edible raw")
                self.assertGreater(int(energy), 0, kind)
                self.assertIsNone(eat_energy_for(self.crops, f"{kind}_seed"))
        give_item(self.state, "radish", 1, player=P1)
        self.state["players"][P1]["energy"] = 20
        restore = eat_energy_for(self.crops, "radish")
        ok, msg = do_action(self.state, self.crops, "eat radish", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 20 + restore)
        give_item(self.state, "rhubarb", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "eat rhubarb", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertIn("edible raw", msg.lower())

    def test_mini_map_crop_labels_fit_without_truncation(self):
        from describe import MAP_LABEL_WIDTH, _ascii_cell, ascii_map, map_crop_label
        from engine import crop_name, crop_info, get_tile

        for kind, info in self.crops["crops"].items():
            label = map_crop_label(kind, info)
            name = crop_name(kind, info)
            self.assertTrue(label, kind)
            self.assertLessEqual(
                len(label),
                MAP_LABEL_WIDTH,
                f"{kind} map label {label!r} exceeds {MAP_LABEL_WIDTH} chars",
            )
            self.assertNotIn("_", label, f"{kind} map label still has underscores: {label!r}")
            # A proper short form is allowed; a raw mid-word slice is not
            # (e.g. 'strawbe' from 'strawberry', 'asparag' from 'asparagus').
            if name.startswith(label) and len(label) < len(name) and not label.endswith("."):
                self.fail(f"{kind} map label {label!r} looks like a truncated {name!r}")
            tile = {"type": "soil", "tilled": True, "crop": {"kind": kind, "stage": "mature"}}
            top, _bot = _ascii_cell(tile)
            self.assertEqual(top, label)
            self.assertEqual(top, top.strip())

        self.assertEqual(map_crop_label("strawberry", crop_info(self.crops, "strawberry")), "strawberry")
        self.assertEqual(map_crop_label("asparagus", crop_info(self.crops, "asparagus")), "asparagus")
        self.assertEqual(map_crop_label("bush_bean", crop_info(self.crops, "bush_bean")), "bush bean")
        self.assertEqual(map_crop_label("kabocha", crop_info(self.crops, "kabocha")), "kabocha")
        self.assertEqual(map_crop_label("everbearing", crop_info(self.crops, "everbearing")), "e.berry")

        # Place the long names on the field and confirm each full label appears.
        kinds = ("strawberry", "asparagus", "everbearing", "bush_bean", "kabocha")
        tiles = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)]
        for (r, c), kind in zip(tiles, kinds):
            tile = get_tile(self.state, r, c)
            tile["type"] = "soil"
            tile["tilled"] = True
            tile["crop"] = {"kind": kind, "stage": "mature"}
            tile["watered"] = False
        text_map = ascii_map(self.state)
        for kind in kinds:
            label = map_crop_label(kind, crop_info(self.crops, kind))
            self.assertIn(label, text_map, f"mini map missing {label!r}\n{text_map}")
        # The old 7-char mid-word cut must not appear as its own cell label.
        for bad in ("strawbe", "asparag", "bush_be", "everbea"):
            self.assertNotRegex(
                text_map,
                rf"(?<![A-Za-z.]){bad}(?![A-Za-z.])",
                f"mini map still truncates to {bad!r}\n{text_map}",
            )

    def test_listed_legal_actions_parse_and_execute(self):
        """Every look-line legal action must be directly executable, including display names."""
        import copy
        from engine import (
            described_legal_actions,
            do_action,
            legal_actions,
            strip_action_descriptor,
            till,
        )
        from inventory import item_count, normalize_item

        def check(state, label):
            listed = described_legal_actions(state, self.crops, P1, self.rules)
            raw_actions = legal_actions(state, self.crops, player=P1, rules=self.rules)
            self.assertEqual(len(listed), len(raw_actions), label)
            for shown, raw in zip(listed, raw_actions):
                cmd = strip_action_descriptor(shown)
                scratch = copy.deepcopy(state)
                ok, msg = do_action(scratch, self.crops, cmd, player=P1, rules=self.rules)
                self.assertTrue(ok, f"{label}: {shown!r} -> {cmd!r} failed: {msg}")
                scratch2 = copy.deepcopy(state)
                ok2, msg2 = do_action(scratch2, self.crops, raw, player=P1, rules=self.rules)
                self.assertTrue(ok2, f"{label}: canonical {raw!r} failed: {msg2}")

        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        check(self.state, "starting cabin")

        ok, msg = do_action(self.state, self.crops, "buy radish seed 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(item_count(self.state, "radish_seed"), 1)
        gold = self.state["gold"]
        ok, msg = do_action(self.state, self.crops, "buy radish seeds 2", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold - 12)

        ok, msg = do_action(
            self.state, self.crops, "take June-bearing strawberry seeds all",
            player=P1, rules=self.rules,
        )
        self.assertTrue(ok, msg)
        self.assertEqual(item_count(self.state, "strawberry_seed"), 2)
        ok, msg = do_action(self.state, self.crops, "drop June-bearing strawberry seeds all", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "take strawberry all", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(item_count(self.state, "strawberry_seed"), 2)
        self.assertEqual(normalize_item("June-bearing strawberry seed"), "strawberry_seed")
        self.assertEqual(normalize_item("radish seeds"), "radish_seed")

        # Make pack room: tools plus turnip seeds need three of the four slots.
        ok, msg = do_action(self.state, self.crops, "drop radish seeds all", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "drop June-bearing strawberry seeds all", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        kit_out(self.state, P1)
        give_seeds(self.state, "turnip", 2, player=P1)
        from inventory import pack_has
        self.assertTrue(pack_has(self.state, P1, "turnip_seed", 2, self.rules))
        stand(self.state, P1, 1, 1)
        ok, msg = till(self.state, self.crops, 1, 1, P1)
        self.assertTrue(ok, msg)
        check(self.state, "tilled plot with turnip seed in pack")
        ok, msg = do_action(self.state, self.crops, "plant 1 1 turnip seed", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)

        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        give_item(self.state, "strawberry", 3, player=P1)
        check(self.state, "cabin with produce and tools")

    def test_later_crops_remain_plantable_sellable_and_edible_from_the_pack(self):
        kit_out(self.state, P1)
        give_seeds(self.state, "turnip", 1, player=P1)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "plant 1 1 turnip", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        give_item(self.state, "kabocha", 1)  # chest; sell() without a player uses the chest
        gold = self.state["gold"]
        ok, msg = sell(self.state, self.crops, "kabocha", 1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold + 50)
        give_item(self.state, "carrot", 1, player=P1)
        self.state["players"][P1]["energy"] = 80
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 90)

    def _grow_days(self, r, c, n):
        for _ in range(n):
            self.state["weather"] = "sun"
            water(self.state, self.crops, r, c)
            ok, msg = sleep(self.state, self.crops, self.rules)
            self.assertTrue(ok, msg)

    def test_strawberry_does_not_fruit_in_its_first_season(self):
        r, c = 1, 1
        till(self.state, self.crops, r, c)
        ok, msg = plant(self.state, self.crops, r, c, "strawberry")
        self.assertTrue(ok, msg)
        self._grow_days(r, c, 14)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertIsNotNone(crop)
        self.assertNotEqual(crop["stage"], "mature")
        self.assertNotEqual(crop["stage"], "withered")
        self.assertFalse(crop.get("overwintered"))

    def test_strawberry_goes_dormant_in_autumn_and_fruits_the_next_spring(self):
        r, c = 1, 1
        till(self.state, self.crops, r, c)
        ok, msg = plant(self.state, self.crops, r, c, "strawberry")
        self.assertTrue(ok, msg)
        self._grow_days(r, c, 3)
        # Last day of summer into autumn.
        self.state["day"] = 30
        self.state["season"] = "summer"
        water(self.state, self.crops, r, c)
        ok, msg = sleep(self.state, self.crops, self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["season"], "autumn")
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "dormant")
        self.assertTrue(crop.get("overwintered"))
        self.assertIn("dormant", msg.lower())
        # Watering is refused; tilling is blocked.
        ok, msg = water(self.state, self.crops, r, c)
        self.assertFalse(ok)
        self.assertIn("dormant", msg.lower())
        ok, msg = till(self.state, self.crops, r, c)
        self.assertFalse(ok)
        # Through winter, still dormant, then it wakes in spring and can fruit.
        self.state["day"] = 60
        self.state["season"] = "winter"
        ok, msg = sleep(self.state, self.crops, self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["season"], "spring")
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertNotEqual(crop["stage"], "dormant")
        self.assertNotEqual(crop["stage"], "withered")
        self.assertIn("woken", msg.lower())
        self._grow_days(r, c, 7)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")
        ok, msg = harvest(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(self.state["inventory"]["strawberry"], 1)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "regrowing")
        self._grow_days(r, c, 7)
        self.assertEqual(self.state["tiles"][r - 1][c - 1]["crop"]["stage"], "mature")

    def test_strawberry_dies_after_eight_seasons(self):
        r, c = 1, 1
        till(self.state, self.crops, r, c)
        plant(self.state, self.crops, r, c, "strawberry")
        # Planted on day 1 (season 0). The 9th season starts on day 121.
        self.state["day"] = 120
        self.state["season"] = "winter"
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        crop["overwintered"] = True
        crop["stage"] = "dormant"
        ok, msg = sleep(self.state, self.crops, self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["day"], 121)
        self.assertEqual(self.state["season"], "spring")
        self.assertEqual(self.state["tiles"][r - 1][c - 1]["crop"]["stage"], "withered")
        self.assertIn("two years", msg.lower())

    def test_strawberry_runner_is_capped_at_one_per_season(self):
        from engine import _apply_runners
        r, c = 2, 2
        till(self.state, self.crops, r, c)
        plant(self.state, self.crops, r, c, "strawberry")
        till(self.state, self.crops, 1, 2)
        till(self.state, self.crops, 2, 1)
        till(self.state, self.crops, 2, 3)
        till(self.state, self.crops, 3, 2)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        info = dict(self.crops["crops"]["strawberry"])
        info["runner_chance"] = 1.0
        # Force the roll by temporarily setting chance on the live info used by crop_info.
        self.crops["crops"]["strawberry"]["runner_chance"] = 1.0
        notes = _apply_runners(self.state, self.crops)
        self.assertTrue(any("runner" in n.lower() for n in notes), notes)
        children = [
            (rr, cc)
            for rr in range(1, 4)
            for cc in range(1, 4)
            if (rr, cc) != (r, c)
            and (self.state["tiles"][rr - 1][cc - 1].get("crop") or {}).get("kind") == "strawberry"
        ]
        self.assertEqual(len(children), 1)
        rr, cc = children[0]
        child = self.state["tiles"][rr - 1][cc - 1]["crop"]
        self.assertEqual(child.get("runner_from"), [r, c])
        notes2 = _apply_runners(self.state, self.crops)
        self.assertFalse(any("runner" in n.lower() for n in notes2))
        children2 = [
            (rr, cc)
            for rr in range(1, 4)
            for cc in range(1, 4)
            if (rr, cc) != (r, c)
            and (self.state["tiles"][rr - 1][cc - 1].get("crop") or {}).get("kind") == "strawberry"
        ]
        self.assertEqual(len(children2), 1)
        self.crops["crops"]["strawberry"]["runner_chance"] = 0.10

    def test_shop_sells_strawberry_in_summer_but_not_autumn(self):
        from engine import shop_kinds, legal_actions, buy
        # Season-only (no day) is treated as day 1 of that season.
        summer_open = shop_kinds(self.crops, "summer")
        self.assertIn("strawberry", summer_open)
        self.assertIn("everbearing", summer_open)
        self.assertIn("kabocha", summer_open)  # 30d, summer day 1 exactly
        self.assertNotIn("pumpkin", summer_open)  # 33d
        self.assertNotIn("turnip", summer_open)
        # State is summer day 2, so kabocha no longer fits.
        self.state["day"] = 17
        self.state["season"] = "summer"
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("buy strawberry 1", actions)
        self.assertIn("buy everbearing 1", actions)
        self.assertNotIn("buy kabocha 1", actions)
        ok, msg = buy(self.state, self.crops, "strawberry", 1)
        self.assertTrue(ok, msg)
        self.state["day"] = 31
        self.state["season"] = "autumn"
        autumn = shop_kinds(self.crops, "autumn")
        self.assertIn("turnip", autumn)
        self.assertIn("carrot", autumn)
        self.assertNotIn("strawberry", autumn)
        self.assertNotIn("everbearing", autumn)
        self.assertNotIn("kabocha", autumn)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn("buy strawberry 1", actions)
        self.assertNotIn("buy everbearing 1", actions)
        self.assertIn("buy turnip 1", actions)
        ok, msg = buy(self.state, self.crops, "strawberry", 1)
        self.assertFalse(ok, msg)
        self.assertIn("autumn", msg.lower())
        ok, msg = buy(self.state, self.crops, "everbearing", 1)
        self.assertFalse(ok, msg)
        self.assertIn("autumn", msg.lower())

    def test_calendar_migrate_remaps_day_and_keeps_remaining_growth(self):
        from engine import migrate_calendar, remap_calendar_day
        self.assertEqual(remap_calendar_day(16, 14, 15), 17)
        self.assertEqual(remap_calendar_day(14, 14, 15), 14)
        self.assertEqual(remap_calendar_day(15, 14, 15), 16)
        self.assertEqual(remap_calendar_day(28, 14, 15), 29)
        state = fresh_state(self.crops, rules=self.rules)
        # Simulate a 14-day-calendar save: summer day 2, kabocha watered once (6 days left).
        state["days_per_season"] = 14
        state["day"] = 16
        state["season"] = "summer"
        state["gold"] = 162
        till(state, self.crops, 1, 2)
        give_seeds(state, "kabocha", 1)
        plant(state, self.crops, 1, 2, "kabocha")
        crop = state["tiles"][0][1]["crop"]
        crop["planted_day"] = 15
        crop["days_grown"] = 1
        crop["stage"] = "seed"
        weather = state["weather"]
        changed = migrate_calendar(state, self.crops)
        self.assertTrue(changed)
        self.assertEqual(state["day"], 17)
        self.assertEqual(state["season"], "summer")
        self.assertEqual(state["days_per_season"], 15)
        self.assertEqual(state["weather"], weather)
        self.assertEqual(state["gold"], 162)
        crop = state["tiles"][0][1]["crop"]
        self.assertEqual(crop["planted_day"], 16)
        # Legacy kabocha grew in 7 days; remaining 6 days are preserved
        # against the current grow_days.
        from engine import grow_days, crop_info
        new_g = grow_days(crop_info(self.crops, "kabocha"))
        self.assertEqual(crop["days_grown"], new_g - 6)
        self.assertNotEqual(crop["stage"], "withered")
        # Idempotent.
        self.assertFalse(migrate_calendar(state, self.crops))

    def test_shop_sells_everbearing_seedlings_and_they_fruit_this_year(self):
        from engine import shop_kinds, buy, sell
        self.assertIn("everbearing", shop_kinds(self.crops, "summer"))
        gold = self.state["gold"]
        ok, msg = buy(self.state, self.crops, "everbearing", 1)
        self.assertTrue(ok, msg)
        self.assertIn("everbearing strawberry seed", msg.lower())
        self.assertEqual(self.state["gold"], gold - 40)
        self.assertEqual(self.state["inventory"]["everbearing_seedling"], 1)
        r, c = 1, 1
        till(self.state, self.crops, r, c)
        ok, msg = plant(self.state, self.crops, r, c, "everbearing")
        self.assertTrue(ok, msg)
        self.assertIn("everbearing strawberry seed", msg.lower())
        self.assertEqual(self.state["inventory"]["everbearing_seedling"], 0)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "seedling")
        self.assertFalse(crop.get("overwintered"))
        self._grow_days(r, c, 4)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")
        ok, msg = harvest(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(self.state["inventory"]["everbearing"], 1)
        self.assertEqual(self.state["inventory"].get("strawberry", 0), 0)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "regrowing")
        self._grow_days(r, c, 7)
        self.assertEqual(self.state["tiles"][r - 1][c - 1]["crop"]["stage"], "mature")
        gold = self.state["gold"]
        ok, msg = sell(self.state, self.crops, "everbearing", 1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold + 18)

    def test_everbearing_fruits_late_summer_and_early_autumn_then_rests_in_winter(self):
        from engine import in_fruiting_window
        info = self.crops["crops"]["everbearing"]
        r, c = 1, 1
        give_seeds(self.state, "everbearing", 1)
        till(self.state, self.crops, r, c)
        # Mid-summer, past the June-bearing cutoff, an everbearing seedling can still fruit.
        self.state["day"] = 25  # summer day 10
        self.state["season"] = "summer"
        ok, msg = plant(self.state, self.crops, r, c, "everbearing")
        self.assertTrue(ok, msg)
        self.assertTrue(in_fruiting_window(self.state, info, self.crops))
        june = self.crops["crops"]["strawberry"]
        self.assertFalse(in_fruiting_window(self.state, june, self.crops))
        self._grow_days(r, c, 4)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")
        ok, msg = harvest(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        # First 5 days of autumn are still in the fruiting window; day 6 is not.
        self.state["day"] = 35  # autumn day 5
        self.state["season"] = "autumn"
        self.assertTrue(in_fruiting_window(self.state, info, self.crops))
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        crop["days_grown"] = 6
        crop["stage"] = "regrowing"
        crop["harvests"] = 1
        self._grow_days(r, c, 1)
        self.assertEqual(self.state["day"], 36)
        self.assertEqual(self.state["tiles"][r - 1][c - 1]["crop"]["stage"], "mature")
        harvest(self.state, self.crops, r, c)
        self.state["day"] = 36  # autumn day 6
        self.state["season"] = "autumn"
        self.assertFalse(in_fruiting_window(self.state, info, self.crops))
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        crop["days_grown"] = 6
        crop["stage"] = "regrowing"
        crop["harvests"] = 2
        self._grow_days(r, c, 1)
        self.assertEqual(self.state["day"], 37)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertNotEqual(crop["stage"], "mature")
        self.assertNotEqual(crop["stage"], "withered")
        self.assertNotEqual(crop["stage"], "dormant")
        # Winter dormancy.
        self.state["day"] = 45
        self.state["season"] = "autumn"
        ok, msg = sleep(self.state, self.crops, self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["season"], "winter")
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "dormant")
        self.assertTrue(crop.get("overwintered"))
        ok, msg = water(self.state, self.crops, r, c)
        self.assertFalse(ok)
        self.assertIn("dormant", msg.lower())

    def test_everbearing_snack_and_migrate_keys(self):
        from engine import migrate_state
        give_item(self.state, "everbearing", 1, player=P1)
        self.state["players"][P1]["energy"] = 50
        ok, msg = do_action(self.state, self.crops, "eat everbearing", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 70)
        self.assertEqual(self.state["inventory"]["everbearing"], 0)
        state = fresh_state(self.crops)
        gold = state["gold"]
        # Removing keys from the totals view must not drop real chest counts;
        # migrate fills missing crop keys as 0.
        state["inventory"].pop("everbearing_seedling", None)
        state["inventory"].pop("everbearing", None)
        migrate_state(state, self.rules)
        self.assertEqual(state["inventory"].get("everbearing_seedling", 0), 0)
        self.assertEqual(state["inventory"].get("everbearing", 0), 0)
        self.assertEqual(state["gold"], gold)

    def test_strawberry_sprites_cover_each_stage(self):
        from sprites import svg_for_key
        for stage in ("seed", "sprouting", "growing", "mature", "regrowing", "dormant", "withered"):
            svg = svg_for_key(f"strawberry_{stage}_dry")
            self.assertIn("<svg", svg)
            self.assertNotIn("unknown", svg.lower())
        ripe = svg_for_key("strawberry_mature_dry")
        self.assertIn("#c43c3c", ripe)
        for stage in ("seedling", "growing", "mature", "regrowing", "dormant", "withered"):
            svg = svg_for_key(f"everbearing_{stage}_dry")
            self.assertIn("<svg", svg)
            self.assertNotIn("unknown", svg.lower())
        ev = svg_for_key("everbearing_mature_dry")
        self.assertIn("#c43c3c", ev)

    def test_migrate_adds_strawberry_keys_without_touching_tiles_or_counts(self):
        from engine import migrate_state, ensure_inventory_keys
        # A legacy-shaped save: no chest yet, shared count map, missing strawberry keys.
        state = fresh_state(self.crops)
        # Pour starting seeds out so this looks like an older farm mid-game.
        from inventory import chest_of, remove_from_chest, add_to_chest, sync_inventory_view
        for slot in list(chest_of(state)):
            if slot and str(slot.get("item") or "").endswith("_seed") or (slot and str(slot.get("item") or "").endswith("_seedling")):
                remove_from_chest(state, slot["item"], int(slot.get("count") or 0))
        # Keep tools; add 3 kabocha as existing produce.
        add_to_chest(state, "kabocha", 3)
        sync_inventory_view(state)
        state["gold"] = 182
        till(state, self.crops, 2, 2)
        give_seeds(state, "kabocha", 1)
        plant(state, self.crops, 2, 2, "kabocha")
        crop_before = dict(state["tiles"][1][1]["crop"])
        # After planting, chest still holds the 3 kabocha fruit (seed was used).
        migrate_state(state, self.rules)
        self.assertEqual(state["inventory"].get("strawberry_seed", 0), 0)
        self.assertEqual(state["inventory"].get("strawberry", 0), 0)
        self.assertEqual(state["inventory"]["kabocha"], 3)
        self.assertEqual(state["gold"], 182)
        self.assertEqual(state["tiles"][1][1]["crop"], crop_before)

class FarmJournal(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, weather_seed=0, rules=self.rules)
        archive = engine.JOURNAL_ARCHIVE_PATH
        if archive.exists():
            archive.unlink()

    def test_year_and_season_helpers(self):
        self.assertEqual(year_for_day(1, self.crops), 1)
        self.assertEqual(year_for_day(15, self.crops), 1)
        self.assertEqual(year_for_day(16, self.crops), 1)
        self.assertEqual(year_for_day(60, self.crops), 1)
        self.assertEqual(year_for_day(61, self.crops), 2)
        self.assertEqual(normalize_season("Fall"), "autumn")
        self.assertEqual(normalize_season("autumn"), "autumn")
        self.assertIsNone(normalize_season("monsoon"))
        self.assertEqual(RECENT_NOTE_COUNT, 15)

    def test_duplicate_notes_are_stored_once(self):
        self.assertTrue(record_journal_note(self.state, P1, "same text", day=3, crops=self.crops))
        self.assertFalse(record_journal_note(self.state, P1, "same text", day=3, crops=self.crops))
        self.assertTrue(record_journal_note(self.state, P1, "same text", day=4, crops=self.crops))
        self.assertEqual(len(all_journal_entries(self.state)), 2)

    def test_migrate_imports_log_and_last_note_without_doubling(self):
        state = fresh_state(self.crops, weather_seed=0, rules=self.rules)
        state.pop("journal", None)
        state.pop("year", None)
        state["log"] = [
            {"day": 2, "player": P1, "text": f"{N1} leaves a note: watered the berries"},
            {"day": 2, "player": P2, "text": f"{N2} leaves a note: I'll take morning water"},
            {"day": 2, "player": P1, "text": f"{N1} ends the turn in the cabin."},
        ]
        state["last_note"] = {"from": P2, "text": "I'll take morning water", "day": 2}
        self.assertTrue(migrate_state(state, self.rules))
        entries = all_journal_entries(state)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["from"], P1)
        self.assertEqual(entries[0]["text"], "watered the berries")
        self.assertEqual(entries[1]["from"], P2)
        self.assertEqual(entries[1]["text"], "I'll take morning water")
        self.assertEqual(state["year"], 1)
        self.assertEqual(state["journal"]["year"], 1)
        # Running migrate again must not duplicate them.
        self.assertFalse(migrate_journal(state, self.crops))
        self.assertEqual(len(all_journal_entries(state)), 2)

    def test_look_shows_last_fifteen_notes_most_recent_first_without_duplicates(self):
        from describe import describe_state, format_player_note, format_journal_line
        for i in range(1, 21):
            who = P1 if i % 2 else P2
            record_journal_note(self.state, who, f"note {i}", day=i, crops=self.crops)
        entries = recent_notes(self.state)
        self.assertEqual(len(entries), 15)
        self.assertEqual(entries[0]["text"], "note 20")
        self.assertEqual(entries[-1]["text"], "note 6")
        self.assertEqual(len({(e["day"], e["from"], e["text"]) for e in entries}), 15)
        look = describe_state(self.state, self.crops, viewer=P1)
        self.assertIn("Recent notes (last 15, most recent first):", look)
        self.assertIn(format_journal_line(entries[0]), look)
        self.assertIn(format_player_note(entries[0]), look)
        self.assertNotIn(format_journal_line({"day": 5, "from": P1, "text": "note 5"}), look)
        self.assertNotIn(format_journal_line({"day": 1, "from": P1, "text": "note 1"}), look)
        # The same labelled line must appear only once.
        labeled = format_journal_line(entries[0])
        self.assertEqual(look.count(labeled), 1)

    def test_year_rollover_archives_old_notes(self):
        from describe import describe_state, format_season_journal
        record_journal_note(self.state, P1, "last winter thought", day=60, crops=self.crops)
        self.state["day"] = 60
        self.state["season"] = "winter"
        self.state["year"] = 1
        self.state["journal"]["year"] = 1
        ok, _ = engine.advance_day(self.state, self.crops, self.rules)
        self.assertTrue(ok)
        self.assertEqual(self.state["day"], 61)
        self.assertEqual(self.state["season"], "spring")
        self.assertEqual(self.state["year"], 2)
        self.assertEqual(self.state["journal"]["year"], 2)
        self.assertEqual(all_journal_entries(self.state), [])
        look = describe_state(self.state, self.crops, viewer=P1)
        self.assertNotIn("last winter thought", look)
        journal_text = format_season_journal(self.state)
        self.assertIn("Year 2", journal_text)
        self.assertNotIn("last winter thought", journal_text)
        archived = json.loads(engine.JOURNAL_ARCHIVE_PATH.read_text(encoding="utf-8"))
        winter = archived["years"]["1"]["winter"]
        self.assertEqual(len(winter), 1)
        self.assertEqual(winter[0]["text"], "last winter thought")
        self.assertEqual(winter[0]["from"], P1)

    def test_calendar_remap_moves_journal_days(self):
        # A 28-day summer note (day 36 is summer day 8) remaps onto a 15-day calendar.
        self.state["days_per_season"] = 28
        self.state["day"] = 36
        self.state["season"] = "summer"
        self.state["journal"]["seasons"]["summer"] = [{
            "day": 36,
            "year": 1,
            "season": "summer",
            "from": P1,
            "text": "long summer",
        }]
        self.assertTrue(engine.migrate_calendar(self.state, self.crops))
        entries = all_journal_entries(self.state)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "long summer")
        self.assertEqual(entries[0]["day"], 23)  # summer day 8 on a 15-day season
        self.assertEqual(entries[0]["season"], "summer")
        self.assertEqual(entries[0]["year"], 1)

    def test_mcp_and_format_read_a_season_including_fall_alias(self):
        from describe import format_season_journal
        import mcp_server
        record_journal_note(self.state, P1, "spring rain", day=3, crops=self.crops)
        self.state["day"] = 16
        self.state["season"] = "summer"
        record_journal_note(self.state, P2, "summer sun", day=16, crops=self.crops)
        spring = format_season_journal(self.state, "spring")
        self.assertIn("Year 1, Spring", spring)
        self.assertIn("spring rain", spring)
        self.assertIn(f"Note from {N1} (player text):", spring)
        self.assertNotIn("summer sun", spring)
        autumn = format_season_journal(self.state, "fall")
        self.assertIn("Year 1, Autumn", autumn)
        self.assertIn("No notes in this season yet", autumn)
        bad = format_season_journal(self.state, "monsoon")
        self.assertIn("spring, summer, autumn (or fall), and winter", bad)
        path = engine.STATE_PATH
        engine.save_state(self.state, path)
        mcp_server._STATE_PATH = path
        self.addCleanup(lambda: setattr(mcp_server, "_STATE_PATH", None))
        text = mcp_server.farm_journal("summer", path=path)
        self.assertIn("summer sun", text)
        self.assertIn(f"Note from {N2} (player text):", text)
        self.assertNotIn("spring rain", text)
        whole = mcp_server.farm_journal(path=path)
        self.assertIn("spring rain", whole)
        self.assertIn("summer sun", whole)
        called = mcp_server.handle_rpc({
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "farm_journal", "arguments": {"season": "fall"}},
        })
        self.assertFalse(called["result"]["isError"])
        self.assertIn("Autumn", called["result"]["content"][0]["text"])

    def test_web_page_has_a_journal_modal(self):
        import web
        html = web.PAGE
        self.assertIn('id="open-journal"', html)
        self.assertIn('id="journal-modal"', html)
        self.assertIn('id="recent-notes"', html)
        self.assertIn("Journal <kbd>J</kbd>", html)




class ArtPackAndPage(unittest.TestCase):
    def _png_info(self, path: Path):
        import struct
        import zlib

        data = path.read_bytes()
        self.assertGreaterEqual(data[:8], b"")  # keep assert style on the signature
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        pos = 8
        idats = []
        width = height = color = None
        while pos + 8 <= len(data):
            length, typ = struct.unpack(">I4s", data[pos:pos + 8])
            chunk = data[pos + 8:pos + 8 + length]
            if typ == b"IHDR":
                width, height, _bit, color = struct.unpack(">IIBB", chunk[:10])
            elif typ == b"IDAT":
                idats.append(chunk)
            elif typ == b"IEND":
                break
            pos += 12 + length
        raw = zlib.decompress(b"".join(idats))
        return width, height, color, raw

    def _paeth(self, a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    def _unfilter_rows(self, width, height, bpp, raw):
        row = width * bpp
        prev = bytes(row)
        out = []
        pos = 0
        for _ in range(height):
            ftype = raw[pos]
            pos += 1
            cur = bytearray(row)
            for i in range(row):
                left = cur[i - bpp] if i >= bpp else 0
                up = prev[i]
                ul = prev[i - bpp] if i >= bpp else 0
                x = raw[pos + i]
                if ftype == 0:
                    cur[i] = x
                elif ftype == 1:
                    cur[i] = (x + left) & 255
                elif ftype == 2:
                    cur[i] = (x + up) & 255
                elif ftype == 3:
                    cur[i] = (x + ((left + up) // 2)) & 255
                elif ftype == 4:
                    cur[i] = (x + self._paeth(left, up, ul)) & 255
                else:
                    self.fail(f"unknown PNG filter {ftype}")
            pos += row
            prev = bytes(cur)
            out.append(prev)
        return out

    def _alpha_extrema(self, width, height, color, raw):
        # color 2 = RGB, 6 = RGBA
        if color == 2:
            return 255, 255
        self.assertEqual(color, 6)
        rows = self._unfilter_rows(width, height, 4, raw)
        alphas = [row[i + 3] for row in rows for i in range(0, width * 4, 4)]
        return min(alphas), max(alphas)

    def test_storybook_pack_tiles_are_square_and_keyed(self):
        from packs import PACKS_ROOT, load_manifest

        man = load_manifest("storybook")
        self.assertIsNotNone(man)
        self.assertEqual(man["id"], "storybook")
        self.assertEqual(int(man["size"]), 512)
        self.assertIn("soil", man["grounds"])
        self.assertIn("strawberry_mature", man["overlays"])
        self.assertIn("everbearing_seedling", man["overlays"])
        self.assertIn("weed", man["overlays"])
        for rel in list(man["grounds"].values()) + list(man["overlays"].values()):
            path = PACKS_ROOT / "storybook" / rel
            self.assertTrue(path.is_file(), rel)
            width, height, color, raw = self._png_info(path)
            self.assertEqual((width, height), (512, 512), rel)
            lo, hi = self._alpha_extrema(width, height, color, raw)
            if rel.startswith("grounds/"):
                self.assertEqual((lo, hi), (255, 255), rel)
            else:
                self.assertEqual(color, 6, rel)
                self.assertEqual(lo, 0, rel)
                self.assertGreater(hi, 0, rel)

    def test_pack_layers_fall_back_when_a_sprite_is_missing(self):
        from packs import layers_for_key, load_manifest

        man = load_manifest("storybook")
        soil = layers_for_key("soil", man)
        self.assertEqual([layer["role"] for layer in soil], ["ground"])
        self.assertTrue(soil[0]["file"].endswith("soil.png"))
        crop = layers_for_key("strawberry_mature_wet", man)
        self.assertEqual([layer["role"] for layer in crop], ["ground", "crop"])
        self.assertIn("soil_watered", crop[0]["file"])
        self.assertIn("strawberry_mature", crop[1]["file"])
        weedy = layers_for_key("soil_tilled_weedy", man)
        self.assertEqual([layer["role"] for layer in weedy], ["ground", "weed"])
        self.assertIn("weedy", weedy[1]["file"])
        stacked = layers_for_key("strawberry_sprouting_dry_weed", man)
        self.assertEqual([layer["role"] for layer in stacked], ["ground", "crop", "weed"])
        fert = layers_for_key("soil_tilled_fert_general", man)
        self.assertEqual([layer["role"] for layer in fert], ["ground", "fertilizer"])
        self.assertIn("fertilizer_general", fert[1]["file"])
        vine = layers_for_key("strawberry_sprouting_wet_vine_west", man)
        self.assertEqual([layer["role"] for layer in vine], ["ground", "crop", "vine"])
        self.assertIn("vine_west", vine[2]["file"])
        both = layers_for_key("strawberry_sprouting_wet_weed_fert_general_vine_west", man)
        self.assertEqual([layer["role"] for layer in both], ["ground", "fertilizer", "crop", "vine", "weed"])
        cabin = layers_for_key("cabin", man)
        self.assertEqual([layer["role"] for layer in cabin], ["cabin"])
        self.assertTrue(cabin[0]["file"].endswith("cabin.png"))
        rain = layers_for_key("cabin_rain", man)
        self.assertTrue(rain[0]["file"].endswith("cabin_rain.png"))
        self.assertEqual([layer["role"] for layer in rain], ["cabin"])
        lit_rain = layers_for_key("cabin_rain_fire", man)
        self.assertEqual([layer["role"] for layer in lit_rain], ["cabin", "smoke"])
        self.assertTrue(lit_rain[0]["file"].endswith("cabin_rain.png"), lit_rain)
        self.assertTrue(lit_rain[1]["file"].endswith("cabin_smoke.png"), lit_rain)
        lit_snow = layers_for_key("cabin_snow_fire", man)
        self.assertTrue(lit_snow[0]["file"].endswith("cabin_snow.png"), lit_snow)
        self.assertTrue(lit_snow[1]["file"].endswith("cabin_smoke.png"), lit_snow)
        lit_clear = layers_for_key("cabin_fire", man)
        self.assertTrue(lit_clear[0]["file"].endswith("cabin.png"), lit_clear)
        self.assertNotEqual(lit_rain[0]["file"], lit_clear[0]["file"])
        snowy = layers_for_key("strawberry_mature_wet_snow", man)
        self.assertEqual([layer["role"] for layer in snowy], ["ground", "crop"])
        self.assertIn("soil_watered_snow", snowy[0]["file"])
        self.assertIn("strawberry_mature", snowy[1]["file"])
        self.assertTrue(layers_for_key("soil_snow", man)[0]["file"].endswith("soil_snow.png"))
        self.assertTrue(layers_for_key("soil_tilled_snow", man)[0]["file"].endswith("soil_tilled_snow.png"))
        hills = layers_for_key("hills_grass_tree_grown", man)
        self.assertEqual([layer["role"] for layer in hills], ["ground", "crop"])
        self.assertIn("hills_grass", hills[0]["file"])
        self.assertIn("tree_grown", hills[1]["file"])
        entrance = layers_for_key("mine_entrance_closed_snow", man)
        self.assertTrue(entrance[0]["file"].endswith("mine_entrance_closed_snow.png"))
        forage = layers_for_key("hills_grass_forage_wild_onion", man)
        self.assertIn("forage_wild_onion", forage[1]["file"])
        # Spring-shop crops now have Storybook overlays, same layering as strawberry.
        kabocha = layers_for_key("kabocha_sprouting_wet", man)
        self.assertEqual([layer["role"] for layer in kabocha], ["ground", "crop"])
        self.assertIn("soil_watered", kabocha[0]["file"])
        self.assertIn("kabocha_sprouting", kabocha[1]["file"])
        self.assertIsNone(layers_for_key("soil", None))
        # If a snowy ground is missing, the pack still layers crops on ordinary soil.
        thin = {
            "id": man["id"],
            "grounds": {"soil_tilled": "grounds/soil_tilled.png", "soil_watered": "grounds/soil_watered.png"},
            "overlays": dict(man["overlays"]),
            "cabins": {},
        }
        fallback = layers_for_key("strawberry_sprouting_dry_snow", thin)
        self.assertEqual(fallback[0]["file"], "grounds/soil_tilled.png")
        self.assertIn("strawberry_sprouting", fallback[1]["file"])
        self.assertIsNone(layers_for_key("cabin_storm", thin))

    def test_safe_pack_file_rejects_path_traversal(self):
        from packs import safe_pack_file

        soil = safe_pack_file("/static/packs/storybook/grounds/soil.png")
        self.assertIsNotNone(soil)
        self.assertEqual(soil.name, "soil.png")
        self.assertIsNotNone(safe_pack_file("/static/packs/storybook/manifest.json"))
        self.assertIsNone(safe_pack_file("/static/packs/storybook/sources/prompts.md"))
        self.assertIsNone(safe_pack_file("/static/packs/storybook/sources/originals/soil.jpg"))
        self.assertIsNone(safe_pack_file("/static/packs/../../state.json"))
        self.assertIsNone(safe_pack_file("/static/packs/storybook/../../../etc/passwd"))
        self.assertIsNone(safe_pack_file("/static/packs/storybook/grounds/../../config.local.json"))
        self.assertIsNone(safe_pack_file("/static/packs/storybook/grounds/../../../config.local.json"))
        self.assertIsNone(safe_pack_file("/etc/passwd"))
        self.assertIsNone(safe_pack_file("/sprite/soil.svg"))

    def test_web_page_has_art_pack_toggle_and_folded_notes(self):
        import web

        html = web.PAGE
        self.assertIn('id="art-pack"', html)
        self.assertIn("lantern-farm-art-pack", html)
        self.assertIn('<details class="recent-notes"', html)
        self.assertIn('id="recent-notes"', html)
        self.assertIn("lantern-farm-recent-notes-open", html)
        self.assertNotIn('<details class="recent-notes" id="recent-notes" open', html)
        self.assertNotIn("<details class='recent-notes' id='recent-notes' open", html)
        end_at = html.find('id="end-turn"')
        note_at = html.find('id="end-note"')
        outlook_at = html.find('id="sleep-outlook"')
        recent_at = html.find('id="recent-notes"')
        self.assertTrue(0 < end_at < recent_at)
        self.assertTrue(0 < note_at < recent_at)
        self.assertTrue(0 < outlook_at < recent_at)
        self.assertIn('id="journal-modal"', html)
        self.assertIn('id="journal-modal" class="shop-modal" hidden', html)
        # The journal is opened by the button or the J key, not on page load.
        boot = html.split("function openJournal()", 1)[0]
        self.assertNotIn("openJournal();", boot)
        from packs import public_packs
        ids = [p["id"] for p in public_packs()]
        self.assertEqual(ids[0], "classic")
        self.assertIn("storybook", ids)
        page = web.render_page(viewer=P1)
        self.assertIn('"id": "storybook"', page)
        self.assertIn('"id": "classic"', page)

    def test_storybook_weeds_sit_in_the_corners(self):
        from packs import PACKS_ROOT

        def alpha_map(name):
            path = PACKS_ROOT / "storybook" / "overlays" / name
            width, height, color, raw = self._png_info(path)
            self.assertEqual((width, height, color), (512, 512, 6), name)
            rows = self._unfilter_rows(width, height, 4, raw)
            return rows, width, height

        def coverage(rows, width, box):
            x0, y0, x1, y1 = box
            n = visible = 0
            for y in range(y0, y1):
                row = rows[y]
                for x in range(x0, x1):
                    n += 1
                    if row[x * 4 + 3] > 16:
                        visible += 1
            return visible / n if n else 0

        for name, expect_right in (("weed.png", False), ("weedy.png", True)):
            rows, width, height = alpha_map(name)
            mid = coverage(rows, width, (176, 176, 336, 336))
            bl = coverage(rows, width, (0, 320, 160, 512))
            br = coverage(rows, width, (352, 320, 512, 512))
            self.assertLess(mid, 0.005, f"{name} should leave the crop centre clear")
            self.assertGreater(bl, 0.02, f"{name} should be visible in the lower-left")
            if expect_right:
                self.assertGreater(br, 0.01, f"{name} should also appear in the lower-right")
            else:
                self.assertLess(br, 0.005, f"{name} is a single clump in the lower-left")



    def test_storybook_root_crops_sit_above_the_tile_label(self):
        """Mature/withered roots must clear the bottom tile caption (~100px)."""
        from packs import PACKS_ROOT

        # The web tile label sits at the bottom with padding that covers
        # roughly the lower fifth of a 512px overlay. Keep the root shoulder
        # above that band so it stays visible.
        max_bottom = 410
        names = [
            "carrot_mature.png", "carrot_withered.png",
            "beet_mature.png", "beet_withered.png",
            "turnip_mature.png", "turnip_withered.png",
            "radish_mature.png", "radish_withered.png",
            "onion_mature.png", "onion_withered.png",
        ]
        for name in names:
            path = PACKS_ROOT / "storybook" / "overlays" / name
            width, height, color, raw = self._png_info(path)
            self.assertEqual((width, height, color), (512, 512, 6), name)
            rows = self._unfilter_rows(width, height, 4, raw)
            bottom = 0
            for y, row in enumerate(rows):
                if any(row[i + 3] > 20 for i in range(0, width * 4, 4)):
                    bottom = y + 1
            self.assertLessEqual(
                bottom, max_bottom,
                f"{name} content ends at y={bottom}, under the tile label",
            )
            for x, y in ((0, 0), (511, 0), (0, 511), (511, 511)):
                self.assertLessEqual(rows[y][x * 4 + 3], 16, f"{name} corner {x},{y}")



    def test_storybook_stump_is_smaller_and_log_overlays_are_grounded(self):
        from packs import PACKS_ROOT
        from PIL import Image

        stump_old_width = 249
        for name, max_width, max_bottom in (
            ("tree_stump.png", 180, 410),
            ("tree_mushroom_log.png", 240, 410),
            ("forage_oyster_mushroom.png", 180, 410),
        ):
            path = PACKS_ROOT / "storybook" / "overlays" / name
            im = Image.open(path)
            self.assertEqual(im.size, (512, 512), name)
            self.assertEqual(im.mode, "RGBA", name)
            bbox = im.split()[-1].point(lambda v: 255 if v > 16 else 0).getbbox()
            self.assertIsNotNone(bbox, name)
            width = bbox[2] - bbox[0]
            self.assertLessEqual(bbox[3], max_bottom, f"{name} bottom {bbox[3]}")
            self.assertLessEqual(width, max_width, f"{name} width {width}")
            if name == "tree_stump.png":
                self.assertLess(width, stump_old_width, "stump should be smaller than the old 249px sprite")
            for x, y in ((0, 0), (511, 0), (0, 511), (511, 511)):
                self.assertLessEqual(im.getpixel((x, y))[3], 16, f"{name} corner {x},{y}")

    def test_storybook_item_icons_are_square_and_transparent(self):
        from packs import PACKS_ROOT, load_manifest, public_packs, safe_pack_file

        man = load_manifest("storybook")
        items = man.get("items") or {}
        expected = {
            "hoe", "shovel", "watering_can",
            "fertilizer_general", "fertilizer_yield", "fertilizer_growth",
            "bread", "bread_half", "butter", "milk",
            "strawberry_jam", "kabocha_soup", "root_stew",
            "bread_and_butter", "jam_toast", "strawberry_milk",
            "buttered_kabocha", "kabocha_cream_soup",
            "kabocha", "turnip", "carrot", "strawberry", "everbearing",
            "strawberry_seed", "kabocha_seed", "turnip_seed", "carrot_seed",
            "everbearing_seedling",
            "radish", "lettuce", "spinach", "pea", "beet", "potato",
            "bush_bean", "cucumber", "zucchini", "tomato", "pumpkin",
            "corn", "onion", "rhubarb", "asparagus",
            "radish_seed", "lettuce_seed", "spinach_seed", "pea_seed",
            "beet_seed", "potato_seed", "bush_bean_seed", "cucumber_seed",
            "zucchini_seed", "tomato_seed", "pumpkin_seed", "corn_seed",
            "onion_seed", "rhubarb_crown", "asparagus_crown",
            "rhubarb_strawberry_jam", "garden_salad", "roasted_potatoes",
            "pumpkin_soup",
            "axe", "wood", "wild_onion", "wild_berry", "wild_mushroom",
            "wild_berry_jam", "wild_onion_soup", "mushroom_soup",
            "oyster_mushroom", "pickaxe",
            "stone", "copper_ore", "iron_ore", "gold_ore",
            "sugar",
            "herbal_tea",
            "hoe_copper", "hoe_iron", "hoe_gold",
            "watering_can_copper", "watering_can_iron", "watering_can_gold",
            "axe_copper", "axe_iron", "axe_gold",
            "pickaxe_copper", "pickaxe_iron", "pickaxe_gold",
        }
        self.assertEqual(set(items), expected)
        for key, rel in items.items():
            path = PACKS_ROOT / "storybook" / rel
            self.assertTrue(path.is_file(), key)
            width, height, color, raw = self._png_info(path)
            self.assertEqual((width, height), (512, 512), key)
            self.assertEqual(color, 6, key)  # RGBA
            rows = self._unfilter_rows(width, height, 4, raw)
            # Corners should be transparent so the icon sits on the panel.
            for x, y in ((0, 0), (511, 0), (0, 511), (511, 511)):
                self.assertLessEqual(rows[y][x * 4 + 3], 16, f"{key} corner {x},{y}")
            self.assertIsNotNone(safe_pack_file(f"/static/packs/storybook/{rel}"))
        self.assertIsNone(
            safe_pack_file("/static/packs/storybook/sources/originals/item_hoe.jpg")
        )
        packs = {p["id"]: p for p in public_packs()}
        self.assertEqual(packs["storybook"]["items"]["hoe"], "items/hoe.png")
        self.assertNotIn("items", packs["classic"])


class TillHold(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        self.state["weather"] = "sun"
        # Clear any morning watering from a wet day-1 seed.
        for _r, _c, tile in (
            (r, c, self.state["tiles"][r][c])
            for r in range(3)
            for c in range(3)
        ):
            tile["watered"] = False

    def _dry_evening(self):
        from engine import _apply_evening_growth
        notes = _apply_evening_growth(self.state, self.crops, self.rules)
        self.state["day"] = int(self.state["day"]) + 1
        self.state["weather"] = "sun"
        return notes

    def test_empty_tilled_bed_reverts_after_five_dry_days(self):
        ok, msg = till(self.state, self.crops, 1, 1)
        self.assertTrue(ok, msg)
        tile = self.state["tiles"][0][0]
        self.assertTrue(tile["tilled"])
        self.assertEqual(till_hold_left(tile), 5)
        self.assertIn("5 days left", till_hold_phrase(tile))
        for night in range(1, 5):
            notes = self._dry_evening()
            tile = self.state["tiles"][0][0]
            self.assertTrue(tile["tilled"], f"still tilled after night {night}: {notes}")
            self.assertEqual(till_hold_left(tile), 5 - night)
        notes = self._dry_evening()
        tile = self.state["tiles"][0][0]
        self.assertFalse(tile["tilled"])
        self.assertIsNone(till_hold_left(tile))
        self.assertTrue(any("gone untilled" in n for n in notes))

    def test_watering_resets_the_countdown(self):
        till(self.state, self.crops, 1, 1)
        self._dry_evening()
        self._dry_evening()
        tile = self.state["tiles"][0][0]
        self.assertEqual(till_hold_left(tile), 3)
        ok, msg = water(self.state, self.crops, 1, 1)
        self.assertTrue(ok, msg)
        self.assertEqual(till_hold_left(tile), 5)
        self._dry_evening()
        self.assertTrue(self.state["tiles"][0][0]["tilled"])
        self.assertEqual(till_hold_left(self.state["tiles"][0][0]), 5)

    def test_a_wet_dawn_resets_the_countdown(self):
        from engine import dawn_water
        till(self.state, self.crops, 1, 1)
        self._dry_evening()
        self.assertEqual(till_hold_left(self.state["tiles"][0][0]), 4)
        self.state["weather"] = "rain"
        dawn_water(self.state, self.rules)
        tile = self.state["tiles"][0][0]
        self.assertTrue(tile["watered"])
        self.assertEqual(till_hold_left(tile), 5)

    def test_a_planted_bed_does_not_revert(self):
        till(self.state, self.crops, 1, 1)
        give_seeds(self.state, "carrot", 1)
        ok, msg = plant(self.state, self.crops, 1, 1, "carrot")
        self.assertTrue(ok, msg)
        self.assertIsNone(till_hold_left(self.state["tiles"][0][0]))
        for _ in range(5):
            self.state["tiles"][0][0]["watered"] = False
            water(self.state, self.crops, 1, 1)
            self._dry_evening()
        tile = self.state["tiles"][0][0]
        self.assertTrue(tile["tilled"])
        self.assertIsNotNone(tile.get("crop"))
        self.assertIsNone(till_hold_left(tile))

    def test_look_text_names_the_days_left(self):
        from describe import describe_tile
        till(self.state, self.crops, 1, 1)
        line = describe_tile(self.state, self.crops, 1, 1)
        self.assertIn("5 days left until it reverts if left unwatered", line)


class PackChestAndCraft(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)

    def test_tools_start_in_the_chest_and_packs_start_empty(self):
        from inventory import item_count, pack_of, chest_of, stack_count, TOOL_HOE, TOOL_CAN, TOOL_SHOVEL
        self.assertEqual(item_count(self.state, TOOL_HOE), 1)
        self.assertEqual(item_count(self.state, TOOL_CAN), 2)
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 1)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_HOE), 1)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_CAN), 2)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_SHOVEL), 1)
        self.assertEqual(item_count(self.state, "strawberry_seed"), 2)
        for player in (P1, P2):
            self.assertTrue(all(slot is None for slot in pack_of(self.state, player)))

    def test_till_requires_a_hoe_in_the_pack(self):
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "till", player=P1)
        self.assertFalse(ok)
        self.assertIn("hoe", msg.lower())
        self.assertFalse(self.state["tiles"][0][0]["tilled"])
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take hoe", player=P1)
        self.assertTrue(ok, msg)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "till", player=P1)
        self.assertTrue(ok, msg)

    def test_water_requires_a_can_in_the_pack(self):
        till(self.state, self.crops, 1, 1)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "water", player=P1)
        self.assertFalse(ok)
        self.assertIn("watering can", msg.lower())
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take watering_can", player=P1)
        self.assertTrue(ok, msg)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "water", player=P1)
        self.assertTrue(ok, msg)

    def test_harvest_goes_to_the_pack_and_refuses_when_full(self):
        from inventory import add_to_pack, pack_of, pack_has
        kit_out(self.state, P1)
        # Fill the two remaining pack slots (hoe + can already occupy two).
        add_to_pack(self.state, P1, "carrot", 1)
        add_to_pack(self.state, P1, "kabocha", 1)
        self.assertTrue(all(s is not None for s in pack_of(self.state, P1)))
        till(self.state, self.crops, 1, 1)
        give_seeds(self.state, "turnip", 1)
        plant(self.state, self.crops, 1, 1, "turnip")
        tile = self.state["tiles"][0][0]
        tile["crop"]["stage"] = "mature"
        tile["crop"]["days_grown"] = 9
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "harvest", player=P1)
        self.assertFalse(ok)
        self.assertIn("backpack is full", msg.lower())
        self.assertEqual(tile["crop"]["stage"], "mature")
        # Make room and harvest.
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "drop carrot", player=P1)
        self.assertTrue(ok, msg)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "harvest", player=P1)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "turnip", 1))

    def test_buy_sell_take_drop_and_craft_are_cabin_only(self):
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "take hoe", player=P1)
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())
        ok, msg = do_action(self.state, self.crops, "buy strawberry 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take hoe", player=P1)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "drop hoe", player=P1)
        self.assertTrue(ok, msg)
        give_item(self.state, "strawberry", 3, player=P1)
        give_item(self.state, "sugar", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft strawberry_jam", player=P1)
        self.assertTrue(ok, msg)
        from inventory import pack_has
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1))
        give_item(self.state, "kabocha", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft kabocha_soup", player=P1)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "kabocha_soup", 1))
        # Soup restores energy from the pack, even away from the cabin.
        stand(self.state, P1, 1, 1)
        self.state["players"][P1]["energy"] = 20
        ok, msg = do_action(self.state, self.crops, "eat kabocha_soup", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 75)
        self.assertIn("kabocha soup", msg)
        self.assertNotIn("kabocha_soup", msg)

    def test_packs_survive_a_day_turn(self):
        from inventory import pack_has
        kit_out(self.state, P1)
        give_item(self.state, "strawberry", 2, player=P1)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, _ = do_action(self.state, self.crops, "end turn", player=P1)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "end turn", player=P2)
        self.assertTrue(ok)
        self.assertEqual(self.state["day"], 2)
        self.assertTrue(pack_has(self.state, P1, "hoe", 1))
        self.assertTrue(pack_has(self.state, P1, "strawberry", 2))

    def test_legacy_inventory_moves_to_the_chest(self):
        from inventory import item_count, chest_of, stack_count, pack_of, TOOL_HOE, TOOL_CAN
        from engine import migrate_state, save_state, load_state
        import tempfile
        folder = Path(tempfile.mkdtemp(prefix="lantern-farm-legacy-"))
        path = folder / "state.json"
        # Minimal pre-pack save: shared inventory, no chest, no packs.
        legacy = fresh_state(self.crops, rules=self.rules)
        # Strip pack/chest and restore a shared inventory map.
        legacy.pop("chest", None)
        legacy.pop("_inventory_is_view", None)
        for slot in (legacy.get("players") or {}).values():
            slot.pop("pack", None)
        legacy["inventory"] = {"kabocha": 1, "strawberry_seed": 3}
        save_state(legacy, path)
        loaded = load_state(self.crops, path)
        self.assertEqual(item_count(loaded, "kabocha"), 1)
        self.assertEqual(item_count(loaded, "strawberry_seed"), 3)
        self.assertEqual(stack_count(chest_of(loaded), "kabocha"), 1)
        self.assertEqual(item_count(loaded, TOOL_HOE), 1)
        self.assertEqual(item_count(loaded, TOOL_CAN), 2)
        for player in (P1, P2):
            if player in (loaded.get("players") or {}):
                self.assertTrue(all(s is None for s in pack_of(loaded, player)))



class GrowthHealthAndYield(unittest.TestCase):
    def test_yield_roll_is_at_least_one_and_favors_high_quality(self):
        from engine import yield_roll
        lows = highs = 0
        for i in range(40):
            lows += yield_roll("strawberry", 70, 50, 1, 1, 1, i)
            highs += yield_roll("strawberry", 100, 100, 1, 1, 1, i)
        self.assertGreater(highs, lows)
        self.assertGreaterEqual(yield_roll("kabocha", 60, 40, 3, 1, 1, 0), 1)
        self.assertIn(yield_roll("kabocha", 100, 100, 3, 1, 1, 0), (1, 2))

    def test_early_harvest_is_refused_below_the_threshold(self):
        crops = load_crops()
        state = fresh_state(crops, rules=no_weed_rules())
        till(state, crops, 1, 1)
        give_seeds(state, "kabocha", 1)
        plant(state, crops, 1, 1, "kabocha")
        crop = state["tiles"][0][0]["crop"]
        crop["growth"] = 40
        crop["health"] = 100
        crop["stage"] = "growing"
        ok, msg = harvest(state, crops, 1, 1)
        self.assertFalse(ok)
        self.assertIn("filling out", msg.lower())
        self.assertNotIn("%", msg)
        crop["growth"] = 60
        ok, msg = harvest(state, crops, 1, 1)
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(state["inventory"]["kabocha"], 1)

    def test_hints_contain_no_percentages(self):
        from engine import crop_hint
        from describe import describe_tile
        crops = load_crops()
        state = fresh_state(crops, rules=no_weed_rules())
        till(state, crops, 1, 1)
        give_seeds(state, "carrot", 1)
        plant(state, crops, 1, 1, "carrot")
        crop = state["tiles"][0][0]["crop"]
        crop["growth"] = 80
        crop["health"] = 90
        crop["stage"] = "growing"
        hint = crop_hint(crop, state["tiles"][0][0], state, crop_info(crops, "carrot"))
        self.assertTrue(hint)
        self.assertNotIn("%", hint)
        self.assertNotRegex(hint, r"health|growth",)
        line = describe_tile(state, crops, 1, 1)
        self.assertNotIn("%", line)
        self.assertNotIn("80", line)

    def test_migration_sets_growth_from_days_grown_and_health_to_100(self):
        from engine import migrate_crop_vitals
        crops = load_crops()
        state = fresh_state(crops, rules=no_weed_rules())
        till(state, crops, 1, 1)
        give_seeds(state, "kabocha", 1)
        plant(state, crops, 1, 1, "kabocha")
        crop = state["tiles"][0][0]["crop"]
        crop["days_grown"] = 17
        crop["stage"] = "mature"
        crop.pop("growth", None)
        crop.pop("health", None)
        self.assertTrue(migrate_crop_vitals(state, crops))
        self.assertEqual(crop["growth"], 100)
        self.assertEqual(crop["health"], 100)



class Fertilizer(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)

    def test_shop_sells_fertilizer_in_spring_and_summer_only(self):
        from engine import buy, shop_listing
        self.assertEqual(self.state["season"], "spring")
        ok, msg = buy(self.state, self.crops, "fertilizer_general", 1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], int(fresh_state(self.crops, rules=self.rules)["gold"]) - 15)
        self.assertIn("fertilizer_general", shop_listing(self.crops, "summer"))
        self.state["season"] = "autumn"
        ok, msg = buy(self.state, self.crops, "fertilizer_yield", 1)
        self.assertFalse(ok)
        self.assertIn("autumn", msg.lower())

    def test_one_bag_per_plot_per_season_and_effects(self):
        from engine import fertilize, fertilizer_on_tile, fertilizer_bonus, growth_step_for, crop_info
        from engine import _apply_evening_growth, advance_day
        till(self.state, self.crops, 1, 1)
        give_item(self.state, "fertilizer_general", 1)
        give_item(self.state, "fertilizer_yield", 1)
        give_seeds(self.state, "turnip", 1)
        plant(self.state, self.crops, 1, 1, "turnip")
        crop = self.state["tiles"][0][0]["crop"]
        crop["health"] = 80
        ok, msg = fertilize(self.state, self.crops, 1, 1, "general")
        self.assertTrue(ok, msg)
        self.assertEqual(crop["health"], 90)
        self.assertEqual(fertilizer_on_tile(self.state["tiles"][0][0], self.state, self.crops)["kind"], "general")
        self.assertAlmostEqual(fertilizer_bonus(self.state["tiles"][0][0]), 0.10)
        ok, msg = fertilize(self.state, self.crops, 1, 1, "yield")
        self.assertFalse(ok)
        self.assertIn("already fertilized", msg.lower())
        # Season change clears the bag so a new one can be applied.
        self.state["day"] = 15
        self.state["season"] = "spring"
        self.state["tiles"][0][0]["watered"] = True
        ok, msg = sleep(self.state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["season"], "summer")
        self.assertIsNone(fertilizer_on_tile(self.state["tiles"][0][0], self.state, self.crops))
        ok, msg = fertilize(self.state, self.crops, 1, 1, "yield")
        self.assertTrue(ok, msg)
        self.assertAlmostEqual(fertilizer_bonus(self.state["tiles"][0][0]), 0.25)

    def test_growth_boost_speeds_a_watered_day(self):
        from engine import fertilize, growth_step_for, crop_info
        till(self.state, self.crops, 1, 1)
        give_seeds(self.state, "turnip", 1)
        plant(self.state, self.crops, 1, 1, "turnip")
        give_item(self.state, "fertilizer_growth", 1)
        ok, msg = fertilize(self.state, self.crops, 1, 1, "growth")
        self.assertTrue(ok, msg)
        info = crop_info(self.crops, "turnip")
        crop = self.state["tiles"][0][0]["crop"]
        bare = growth_step_for(info, crop, weedy=False, tile={"fertilizer": None})
        boosted = growth_step_for(info, crop, weedy=False, tile=self.state["tiles"][0][0])
        self.assertAlmostEqual(boosted, bare * 1.5)

    def test_look_names_the_kind_and_sprite_key_includes_it(self):
        from engine import fertilize, fertilizer_phrase
        from describe import describe_tile
        from sprites import sprite_key, parse_sprite_key, svg_for_key
        till(self.state, self.crops, 1, 1)
        give_item(self.state, "fertilizer_yield", 1)
        fertilize(self.state, self.crops, 1, 1, "yield")
        line = describe_tile(self.state, self.crops, 1, 1)
        self.assertIn("yield-boost fertilizer", line)
        self.assertNotIn("%", line)
        key = sprite_key(self.state["tiles"][0][0], "sun")
        self.assertIn("_fert_yield", key)
        parsed = parse_sprite_key(key)
        self.assertEqual(parsed.get("fertilizer"), "yield")
        svg = svg_for_key(key)
        # Granules are painted before a crop layer would be (empty bed here).
        self.assertIn("ellipse", svg)
        # Crop-on-fertilizer: granules appear in the SVG before the plant stem/leaf.
        give_seeds(self.state, "turnip", 1)
        plant(self.state, self.crops, 1, 1, "turnip")
        key = sprite_key(self.state["tiles"][0][0], "sun")
        svg = svg_for_key(key)
        self.assertLess(svg.find('fill="#2a6b2a"'), _crop_marker(svg))

    def test_player_must_carry_the_bag_in_the_pack(self):
        from engine import fertilize
        kit_out(self.state, P1)
        till(self.state, self.crops, 1, 1)
        give_item(self.state, "fertilizer_general", 1)  # chest
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "fertilize general", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("pack", msg.lower())
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take fertilizer_general", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "fertilize", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["tiles"][0][0]["fertilizer"]["kind"], "general")


def _crop_marker(svg: str) -> int:
    # Turnip seed is a pale mound/seed fill in the classic sprite.
    for token in ('fill="#d8c070"', 'fill="#8a7030"', 'fill="#3d6b3a"'):
        i = svg.find(token)
        if i >= 0:
            return i
    return len(svg)



class TakeDropStacks(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)

    def test_legal_actions_offer_drop_one_and_drop_all_for_a_stack(self):
        give_item(self.state, "everbearing", 3, player=P1)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("drop everbearing 1", actions)
        self.assertIn("drop everbearing all", actions)
        self.assertNotIn("drop everbearing", actions)
        # A single item only offers the count-1 form.
        give_item(self.state, "carrot", 1, player=P1)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("drop carrot 1", actions)
        self.assertNotIn("drop carrot all", actions)
        self.assertNotIn("drop carrot", actions)

    def test_drop_all_moves_the_whole_stack_drop_one_moves_one(self):
        from inventory import pack_has, stack_count, pack_of, chest_of
        give_item(self.state, "everbearing", 3, player=P1)
        ok, msg = do_action(self.state, self.crops, "drop everbearing 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "everbearing", 2, self.rules))
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "everbearing"), 1)
        ok, msg = do_action(self.state, self.crops, "drop everbearing all", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertFalse(pack_has(self.state, P1, "everbearing", 1, self.rules))
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "everbearing"), 3)
        self.assertIn("2 everbearing", msg)

    def test_bare_drop_still_moves_one_for_compatibility(self):
        from inventory import pack_has, stack_count, chest_of
        give_item(self.state, "everbearing", 3, player=P1)
        ok, msg = do_action(self.state, self.crops, "drop everbearing", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "everbearing", 2, self.rules))
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "everbearing"), 1)

    def test_take_one_and_take_all_from_the_chest(self):
        from inventory import pack_has, stack_count, chest_of, pack_of
        give_item(self.state, "everbearing", 3)  # chest
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("take everbearing 1", actions)
        self.assertIn("take everbearing all", actions)
        self.assertNotIn("take everbearing", actions)
        ok, msg = do_action(self.state, self.crops, "take everbearing 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "everbearing", 1, self.rules))
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "everbearing"), 2)
        ok, msg = do_action(self.state, self.crops, "take everbearing all", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "everbearing", 3, self.rules))
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "everbearing"), 0)

    def test_look_text_says_backpack(self):
        from describe import describe_state
        look = describe_state(self.state, self.crops, viewer=P1)
        self.assertIn("Backpack:", look)
        self.assertNotIn("\nPack:", look)



class CraftPricesAndNames(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)

    def test_craft_costs_five_energy(self):
        give_item(self.state, "strawberry", 3, player=P1)
        give_item(self.state, "sugar", 1, player=P1)
        energy = self.state["players"][P1]["energy"]
        ok, msg = do_action(self.state, self.crops, "craft strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], energy - 5)
        from inventory import pack_has
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))

    def test_crafted_foods_sell_for_more_than_their_ingredients(self):
        from inventory import item_sell_price
        from engine import crop_info
        from inventory import recipes, ingredient_cost
        jam = item_sell_price("strawberry_jam", self.crops, self.rules)
        soup = item_sell_price("kabocha_soup", self.crops, self.rules)
        stew = item_sell_price("root_stew", self.crops, self.rules)
        berry = int(crop_info(self.crops, "strawberry")["sell_price"])
        kabocha = int(crop_info(self.crops, "kabocha")["sell_price"])
        carrot = int(crop_info(self.crops, "carrot")["sell_price"])
        turnip = int(crop_info(self.crops, "turnip")["sell_price"])
        self.assertGreater(jam, ingredient_cost(recipes(self.rules)["strawberry_jam"], self.crops, self.rules))
        self.assertGreater(jam, 3 * berry)  # still beats the fruit alone too
        self.assertGreater(soup, kabocha)
        self.assertGreater(stew, carrot + turnip)

    def test_human_names_use_spaces_and_commands_accept_them(self):
        from inventory import item_name, normalize_item
        self.assertEqual(normalize_item("watering can"), "watering_can")
        self.assertEqual(normalize_item("strawberry jam"), "strawberry_jam")
        self.assertEqual(normalize_item("strawberry seed"), "strawberry_seed")
        self.assertNotIn("_", item_name("watering_can", 1, self.crops, self.rules))
        self.assertNotIn("_", item_name("strawberry_jam", 2, self.crops, self.rules))
        self.assertNotIn("_", item_name("strawberry_seed", 1, self.crops, self.rules))
        self.assertIn("watering can", item_name("watering_can", 1, self.crops, self.rules))
        give_item(self.state, "watering_can", 1)  # chest already has cans; extra is fine
        # Take using the spaced name.
        before = self.state["players"][P1]["energy"]
        ok, msg = do_action(self.state, self.crops, "take watering can 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("watering can", msg)
        self.assertNotIn("watering_can", msg)
        ok, msg = do_action(self.state, self.crops, "drop watering can", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)




class CraftedFoodSellAndEat(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)

    def test_jam_is_a_modest_snack_and_soups_restore_more(self):
        from inventory import item_eat_energy
        jam = item_eat_energy("strawberry_jam", self.crops, self.rules)
        soup = item_eat_energy("kabocha_soup", self.crops, self.rules)
        stew = item_eat_energy("root_stew", self.crops, self.rules)
        berry = int((self.crops["crops"]["strawberry"]).get("eat_energy") or 0)
        kabocha = int((self.crops["crops"]["kabocha"]).get("eat_energy") or 0)
        self.assertGreater(jam, berry)
        self.assertGreater(soup, jam)
        self.assertGreater(stew, jam)
        self.assertGreater(soup, kabocha)

    def test_eat_and_sell_accept_spaced_names_and_use_them_in_messages(self):
        from inventory import pack_has, add_to_pack
        give_item(self.state, "strawberry_jam", 2, player=P1)
        self.state["players"][P1]["energy"] = 20
        gold = int(self.state["gold"])
        ok, msg = do_action(self.state, self.crops, "eat strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("strawberry jam", msg)
        self.assertNotIn("strawberry_jam", msg)
        self.assertEqual(self.state["players"][P1]["energy"], 60)
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))
        ok, msg = do_action(self.state, self.crops, "sell strawberry jam 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("strawberry jam", msg)
        self.assertNotIn("strawberry_jam", msg)
        self.assertEqual(int(self.state["gold"]), gold + 90)
        self.assertFalse(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))

    def test_eat_from_the_chest_at_the_cabin_consumes_one(self):
        from inventory import add_to_chest, add_to_pack, pack_has, stack_count, chest_of
        add_to_chest(self.state, "strawberry_jam", 2, self.rules)
        add_to_pack(self.state, P1, "strawberry_jam", 1, self.rules)
        self.state["players"][P1]["energy"] = 20
        ok, msg = do_action(self.state, self.crops, "eat strawberry jam chest", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "strawberry_jam"), 1)
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 60)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "eat strawberry jam chest", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())
        # Eating from the pack still works in the field.
        ok, msg = do_action(self.state, self.crops, "eat strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertFalse(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))

    def test_legal_actions_offer_eat_and_sell_for_crafted_food(self):
        from inventory import add_to_chest
        give_item(self.state, "strawberry_jam", 1, player=P1)
        add_to_chest(self.state, "kabocha_soup", 1, self.rules)
        self.state["players"][P1]["energy"] = 20
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("eat strawberry_jam", actions)
        self.assertIn("sell strawberry_jam 1", actions)
        self.assertIn("eat kabocha_soup chest", actions)
        self.assertIn("sell kabocha_soup 1", actions)

    def test_eat_from_the_shop_is_rejected(self):
        from inventory import add_to_pack, pack_has, staple_info
        # Shop stock is not something you can eat; you must buy it first.
        self.state["players"][P1]["energy"] = 20
        self.assertFalse(pack_has(self.state, P1, "bread", 1, self.rules))
        ok, msg = do_action(self.state, self.crops, "eat bread shop", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("shop", msg.lower())
        self.assertIn("backpack", msg.lower())
        self.assertFalse(pack_has(self.state, P1, "bread", 1, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 20)
        ok, msg = do_action(self.state, self.crops, "eat bread from shop", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("shop", msg.lower())
        # Even with bread in the pack, "eat … shop" is refused and the loaf stays.
        add_to_pack(self.state, P1, "bread", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat bread shop", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("shop", msg.lower())
        self.assertTrue(pack_has(self.state, P1, "bread", 1, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 20)
        # Eating from the pack still works.
        ok, msg = do_action(self.state, self.crops, "eat bread", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertFalse(pack_has(self.state, P1, "bread", 1, self.rules))
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertFalse(any(a.startswith("eat ") and a.endswith(" shop") for a in actions))
        # staple_info is only here to make sure bread is a real shop snack.
        self.assertIsNotNone(staple_info("bread", self.rules))




class RunnerVines(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)

    def _runner_tile(self, stage="sprouting", parent=(1, 1), row=1, col=2):
        return {
            "type": "soil",
            "tilled": True,
            "watered": True,
            "crop": {
                "kind": "strawberry",
                "stage": stage,
                "runner_from": list(parent),
                "planted_day": 26,
                "days_grown": 0,
                "growth": 0,
                "health": 100,
            },
        }

    def test_establishing_runner_uses_a_direction_aware_vine(self):
        from sprites import sprite_key, parse_sprite_key, svg_for_key, runner_vine_direction
        from describe import describe_tile
        tile = self._runner_tile("sprouting")
        self.state["tiles"][0][1] = tile
        key = sprite_key(tile, "sun", 1, 2)
        self.assertTrue(key.endswith("_vine_west"), key)
        parsed = parse_sprite_key(key)
        self.assertEqual(parsed.get("vine"), "west")
        self.assertEqual(parsed.get("stage"), "sprouting")
        self.assertEqual(runner_vine_direction(tile["crop"], 1, 2), "west")
        svg = svg_for_key(key)
        self.assertIn('id="vine-west"', svg)
        # Crop marks (sprout ellipses) are painted before the vine group.
        vine_at = svg.find('id="vine-west"')
        self.assertGreater(vine_at, 0)
        self.assertLess(svg.find("<ellipse"), vine_at)
        # Look text names the parent and the vine.
        line = describe_tile(self.state, self.crops, 1, 2)
        self.assertIn("a runner from", line.lower())
        self.assertIn("still joined by its vine", line.lower())
        self.assertIn("row 1 col 1", line)
        self.assertIn("_vine_west", line)

    def test_vine_disappears_once_the_runner_grows_past_sprouting(self):
        from sprites import sprite_key, svg_for_key
        from describe import describe_tile
        tile = self._runner_tile("growing")
        self.state["tiles"][0][1] = tile
        key = sprite_key(tile, "sun", 1, 2)
        self.assertNotIn("_vine_", key)
        self.assertEqual(tile["crop"].get("runner_from"), [1, 1])
        svg = svg_for_key(key)
        self.assertNotIn('id="vine-', svg)
        line = describe_tile(self.state, self.crops, 1, 2)
        self.assertNotIn("still joined by its vine", line.lower())

    def test_diagonal_and_cardinal_parent_directions(self):
        from sprites import runner_vine_direction
        crop = {"kind": "strawberry", "stage": "seed", "runner_from": [2, 2]}
        self.assertEqual(runner_vine_direction(crop, 2, 3), "west")
        self.assertEqual(runner_vine_direction(crop, 2, 1), "east")
        self.assertEqual(runner_vine_direction(crop, 3, 2), "north")
        self.assertEqual(runner_vine_direction(crop, 1, 2), "south")
        self.assertEqual(runner_vine_direction(crop, 3, 3), "northwest")
        self.assertEqual(runner_vine_direction(crop, 1, 1), "southeast")

    def test_everbearing_seedling_runners_also_show_a_vine(self):
        from sprites import sprite_key
        tile = {
            "type": "soil",
            "tilled": True,
            "watered": False,
            "crop": {"kind": "everbearing", "stage": "seedling", "runner_from": [3, 2]},
        }
        key = sprite_key(tile, "sun", 3, 3)
        self.assertTrue(key.endswith("_vine_west"), key)

    def test_migrate_records_the_existing_runner_from_the_parent_to_the_left(self):
        from engine import migrate_runner_from
        # Child at 1,2, parent at 1,1 already sent a runner this season.
        self.state["tiles"][0][0]["crop"] = {
            "kind": "strawberry",
            "stage": "growing",
            "runner_season": 1,
        }
        self.state["tiles"][0][1]["crop"] = {
            "kind": "strawberry",
            "stage": "growing",
            "planted_day": 26,
        }
        self.state.pop("migrated_runner_from", None)
        self.assertTrue(migrate_runner_from(self.state))
        self.assertEqual(self.state["tiles"][0][1]["crop"].get("runner_from"), [1, 1])
        self.assertTrue(self.state.get("migrated_runner_from"))
        # Idempotent.
        self.assertFalse(migrate_runner_from(self.state))
        self.assertEqual(self.state["tiles"][0][1]["crop"].get("runner_from"), [1, 1])




class StaplesAndRecipeBook(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)

    def test_shop_sells_bread_butter_and_milk_year_round(self):
        from engine import shop_listing, buy
        from inventory import pack_has
        for season in ("spring", "summer", "autumn", "winter"):
            listing = shop_listing(self.crops, season, self.rules)
            self.assertIn("bread", listing)
            self.assertIn("butter", listing)
            self.assertIn("milk", listing)
            self.assertIn("sugar", listing)
            self.assertIn("herbal_tea", listing)
        self.state["season"] = "winter"
        gold = int(self.state["gold"])
        ok, msg = do_action(self.state, self.crops, "buy bread 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("bread", msg)
        self.assertNotIn("_", msg)
        self.assertEqual(int(self.state["gold"]), gold - 8)
        self.assertTrue(pack_has(self.state, P1, "bread", 1, self.rules))

        gold = int(self.state["gold"])
        ok, msg = do_action(self.state, self.crops, "buy sugar 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["gold"]), gold - 5)
        self.assertTrue(pack_has(self.state, P1, "sugar", 1, self.rules))

        gold = int(self.state["gold"])
        ok, msg = do_action(self.state, self.crops, "buy herbal tea 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["gold"]), gold - 15)
        self.assertTrue(pack_has(self.state, P1, "herbal_tea", 1, self.rules))
        self.assertIn("herbal tea", msg.lower())
        self.assertNotIn("_", msg)

    def test_jam_cannot_be_crafted_without_sugar(self):
        from inventory import pack_has, recipes, ingredient_cost, item_sell_price
        from engine import crop_info

        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 100
        give_item(self.state, "strawberry", 3, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft strawberry jam", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("sugar", msg.lower())
        self.assertFalse(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))

        give_item(self.state, "sugar", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))

        berry = int(crop_info(self.crops, "strawberry")["sell_price"])
        rhubarb = int(crop_info(self.crops, "rhubarb")["sell_price"])
        jam = recipes(self.rules)["strawberry_jam"]
        wild = recipes(self.rules)["wild_berry_jam"]
        rhub = recipes(self.rules)["rhubarb_strawberry_jam"]
        # Old input costs (no sugar): 75 / 0 / 81. New costs include 5G sugar.
        self.assertEqual(ingredient_cost(jam, self.crops, self.rules), 3 * berry + 5)
        self.assertEqual(ingredient_cost(wild, self.crops, self.rules), 5)
        self.assertEqual(ingredient_cost(rhub, self.crops, self.rules), 2 * rhubarb + berry + 5)
        self.assertEqual(item_sell_price("strawberry_jam", self.crops, self.rules), 90)
        self.assertEqual(item_sell_price("wild_berry_jam", self.crops, self.rules), 55)
        self.assertEqual(item_sell_price("rhubarb_strawberry_jam", self.crops, self.rules), 95)

    def test_staples_are_edible_snacks(self):
        from inventory import add_to_pack, pack_has, item_eat_energy
        add_to_pack(self.state, P1, "bread", 1, self.rules)
        self.state["players"][P1]["energy"] = 20
        ok, msg = do_action(self.state, self.crops, "eat bread", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 25)
        self.assertIn("bread", msg)
        self.assertFalse(pack_has(self.state, P1, "bread", 1, self.rules))
        self.assertTrue(pack_has(self.state, P1, "bread_half", 1, self.rules))
        self.assertEqual(item_eat_energy("bread", self.crops, self.rules), 5)
        self.assertEqual(item_eat_energy("bread_half", self.crops, self.rules), 5)
        self.assertEqual(item_eat_energy("butter", self.crops, self.rules), 6)
        self.assertEqual(item_eat_energy("milk", self.crops, self.rules), 8)
        self.assertFalse(item_eat_energy("sugar", self.crops, self.rules))

    def test_starting_book_has_jam_and_soup_but_not_later_recipes(self):
        from engine import discovered_recipe_ids, format_recipe_book, legal_actions
        found = discovered_recipe_ids(self.state, self.rules)
        self.assertIn("strawberry_jam", found)
        self.assertIn("kabocha_soup", found)
        self.assertNotIn("jam_toast", found)
        self.assertNotIn("bread_and_butter", found)
        book = format_recipe_book(self.state, self.crops, self.rules, player=P1)
        self.assertIn("strawberry jam", book)
        self.assertIn("3 berries (strawberries or wild berries)", book)
        self.assertIn("1 sugar", book)
        self.assertIn("kabocha soup", book)
        self.assertNotIn("jam toast", book)
        self.assertNotIn("bread and butter", book)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertFalse(any(a.startswith("craft ") for a in actions))

    def test_having_ingredients_at_the_cabin_discovers_a_recipe(self):
        from inventory import add_to_chest, add_to_pack, pack_has
        from engine import discovered_recipe_ids, format_recipe_book
        add_to_pack(self.state, P1, "bread", 1, self.rules)
        add_to_chest(self.state, "butter", 1, self.rules)
        # Trigger discovery by asking for the book / legal actions at the cabin.
        ok, book = do_action(self.state, self.crops, "recipes", player=P1, rules=self.rules)
        self.assertTrue(ok, book)
        self.assertIn("bread_and_butter", discovered_recipe_ids(self.state, self.rules))
        self.assertIn("bread and butter", book)
        self.assertIn("1 bread", book)
        self.assertIn("1 butter", book)
        self.assertIn("Ready to cook", book)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("craft bread_and_butter", actions)
        self.assertNotIn("craft jam_toast", actions)
        # Cooking spends ingredients, costs 5 energy, and the food sells above cost.
        energy = int(self.state["players"][P1]["energy"])
        ok, msg = do_action(self.state, self.crops, "craft bread and butter", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("bread and butter", msg)
        self.assertEqual(self.state["players"][P1]["energy"], energy - 5)
        self.assertTrue(pack_has(self.state, P1, "bread_and_butter", 1, self.rules))
        gold = int(self.state["gold"])
        ok, msg = do_action(self.state, self.crops, "sell bread and butter 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["gold"]), gold + 28)

    def test_undiscovered_recipes_cannot_be_cooked_and_do_not_spoil_the_book(self):
        from inventory import add_to_pack
        ok, msg = do_action(self.state, self.crops, "craft jam toast", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertTrue("haven't found" in msg.lower() or "unknown recipe" in msg.lower(), msg)
        # Even with ingredients in the field, discovery waits until the cabin.
        stand(self.state, P1, 1, 1)
        add_to_pack(self.state, P1, "bread", 1, self.rules)
        add_to_pack(self.state, P1, "strawberry_jam", 1, self.rules)
        ok, book = do_action(self.state, self.crops, "recipes", player=P1, rules=self.rules)
        self.assertTrue(ok, book)
        self.assertNotIn("jam toast", book)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, book = do_action(self.state, self.crops, "recipes", player=P1, rules=self.rules)
        self.assertTrue(ok, book)
        self.assertIn("jam toast", book)

    def test_new_crafted_foods_sell_and_restore_more_than_their_ingredients(self):
        from inventory import (
            recipes,
            ingredient_cost,
            ingredient_eat_total,
            item_sell_price,
            item_eat_energy,
        )
        recs = recipes(self.rules)
        for key in (
            "bread_and_butter",
            "jam_toast",
            "strawberry_milk",
            "buttered_kabocha",
            "kabocha_cream_soup",
            "strawberry_jam",
            "kabocha_soup",
            "root_stew",
            "rhubarb_strawberry_jam",
            "garden_salad",
            "roasted_potatoes",
            "pumpkin_soup",
        ):
            rec = recs[key]
            self.assertGreater(
                item_sell_price(key, self.crops, self.rules),
                ingredient_cost(rec, self.crops, self.rules),
                key,
            )
            # Jam is a modest snack by design (less than eating three berries raw).
            if key != "strawberry_jam":
                self.assertGreater(
                    item_eat_energy(key, self.crops, self.rules),
                    ingredient_eat_total(rec, self.crops, self.rules),
                    key,
                )

    def test_migrate_seeds_jam_and_soup_in_the_recipe_book(self):
        from engine import migrate_state, discovered_recipe_ids
        self.state.pop("discovered_recipes", None)
        self.assertTrue(migrate_state(self.state, self.rules))
        found = discovered_recipe_ids(self.state, self.rules)
        self.assertEqual(found[:2], ["strawberry_jam", "kabocha_soup"])
        self.assertIn("strawberry_jam", self.state["discovered_recipes"])
        self.assertIn("kabocha_soup", self.state["discovered_recipes"])

    def test_mcp_and_cli_recipe_book_agree(self):
        import tempfile
        from pathlib import Path
        import mcp_server
        from engine import save_state
        folder = Path(tempfile.mkdtemp(prefix="lantern-farm-recipes-"))
        path = folder / "state.json"
        save_state(self.state, path)
        mcp_server._STATE_PATH = path
        self.addCleanup(lambda: setattr(mcp_server, "_STATE_PATH", None))
        text = mcp_server.farm_recipes(P1)
        self.assertIn("strawberry jam", text)
        self.assertIn("kabocha soup", text)
        self.assertNotIn("jam toast", text)
        names = [spec["name"] for spec in mcp_server.TOOL_SPECS]
        self.assertIn("farm_recipes", names)





class ActionDescriptorsUnearthAndShovel(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)

    def test_fresh_farm_has_exactly_one_shovel_in_the_chest(self):
        from inventory import item_count, pack_of, chest_of, stack_count, TOOL_SHOVEL, pack_has
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 1)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_SHOVEL), 1)
        self.assertFalse(pack_has(self.state, P1, TOOL_SHOVEL, 1))
        self.assertTrue(all(slot is None or slot.get("item") != TOOL_SHOVEL for slot in pack_of(self.state, P1)))

    def test_older_save_gains_a_shovel_in_the_chest_on_migrate(self):
        from inventory import (
            chest_of, stack_count, item_count, TOOL_SHOVEL, remove_from_chest, migrate_inventory,
        )
        from engine import migrate_state
        # Simulate a pre-shovel farm: no shovel in the world.
        have = item_count(self.state, TOOL_SHOVEL)
        if have:
            remove_from_chest(self.state, TOOL_SHOVEL, have)
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 0)
        self.assertTrue(migrate_inventory(self.state, self.crops, self.rules))
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 1)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_SHOVEL), 1)
        # Idempotent: do not mint a second shovel.
        self.assertFalse(migrate_inventory(self.state, self.crops, self.rules))
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 1)
        migrate_state(self.state, self.rules)
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 1)

    def test_unearth_requires_a_shovel_not_a_hoe_and_clears_the_plot(self):
        from inventory import add_to_pack, pack_has, TOOL_HOE, TOOL_SHOVEL, item_count
        from engine import get_tile, legal_actions, format_legal_action, energy_cost
        # Plant a strawberry at 1,1 with a weed, fertilizer, and a runner child.
        stand(self.state, P1, 1, 1)
        tile = get_tile(self.state, 1, 1)
        tile["type"] = "soil"
        tile["tilled"] = True
        tile["watered"] = True
        tile["weed"] = True
        tile["weedy"] = True
        tile["weedy_ticks"] = 2
        tile["fertilizer"] = {"kind": "yield", "season": "spring", "year": 1}
        tile["crop"] = {"kind": "strawberry", "stage": "growing", "days_grown": 4}
        child = get_tile(self.state, 1, 2)
        child["type"] = "soil"
        child["tilled"] = True
        child["crop"] = {"kind": "strawberry", "stage": "sprouting", "runner_from": [1, 1]}
        energy = int(self.state["players"][P1]["energy"])
        # Hoe in the pack is not enough; take it from the chest, leave the shovel there.
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take hoe 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        stand(self.state, P1, 1, 1)
        ok, msg = do_action(self.state, self.crops, "unearth", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("shovel", msg.lower())
        self.assertNotIn("hoe", msg.lower())
        self.assertEqual(get_tile(self.state, 1, 1)["crop"]["kind"], "strawberry")
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn("unearth 1 1", actions)
        # Shovel in the pack makes it legal and performs the work.
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take shovel 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        stand(self.state, P1, 1, 1)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("unearth 1 1", actions)
        line = format_legal_action("unearth 1 1", self.state, self.crops, P1, self.rules)
        self.assertEqual(line, "unearth (removes strawberry, untills, 5 energy)")
        ok, msg = do_action(
            self.state, self.crops,
            "unearth (removes strawberry, untills, 5 energy)",
            player=P1, rules=self.rules,
        )
        self.assertTrue(ok, msg)
        self.assertIn("strawberry", msg)
        self.assertIn("plain soil", msg)
        self.assertEqual(self.state["players"][P1]["energy"], energy - energy_cost("unearth", self.rules))
        cleared = get_tile(self.state, 1, 1)
        self.assertIsNone(cleared.get("crop"))
        self.assertFalse(cleared.get("tilled"))
        self.assertFalse(cleared.get("weed"))
        self.assertFalse(cleared.get("weedy"))
        self.assertFalse(cleared.get("fertilizer"))
        # Child plant remains, but the runner link is gone.
        leftover = get_tile(self.state, 1, 2)["crop"]
        self.assertEqual(leftover["kind"], "strawberry")
        self.assertNotIn("runner_from", leftover)
        # Still exactly one shovel in the world.
        self.assertEqual(item_count(self.state, TOOL_SHOVEL), 1)
        self.assertTrue(pack_has(self.state, P1, TOOL_SHOVEL, 1, self.rules))

    def test_look_actions_include_deterministic_descriptors_and_crop_seed_names(self):
        from inventory import add_to_pack, add_to_chest, TOOL_SHOVEL
        from describe import describe_state
        from engine import format_legal_action, legal_actions, strip_action_descriptor
        # Starting cabin: move down goes to r2 c3; move to 3 2 is two steps.
        self.assertEqual(
            format_legal_action("move down", self.state, self.crops, P1, self.rules),
            "move down (to r2 c3, 5 energy)",
        )
        self.assertEqual(
            format_legal_action("move to 3 2", self.state, self.crops, P1, self.rules),
            "move to 3 2 (2 steps, 10 energy)",
        )
        gold = int(self.state["gold"])
        self.assertEqual(
            format_legal_action("buy strawberry 1", self.state, self.crops, P1, self.rules),
            f"buy June-bearing strawberry seed 1 (\u2212{15}G, leaves {gold - 15}G)",
        )
        # Chest starts with 2 strawberry seeds and 1 hoe.
        self.assertEqual(
            format_legal_action("take strawberry_seed 1", self.state, self.crops, P1, self.rules),
            "take June-bearing strawberry seed 1 (leaves 1 in chest)",
        )
        self.assertEqual(
            format_legal_action("take strawberry_seed all", self.state, self.crops, P1, self.rules),
            "take June-bearing strawberry seeds all (takes 2)",
        )
        self.assertEqual(
            format_legal_action("take hoe 1", self.state, self.crops, P1, self.rules),
            "take hoe 1 (leaves 0)",
        )
        self.assertEqual(
            format_legal_action("end turn", self.state, self.crops, P1, self.rules),
            "end turn (sleep in cabin, 105 energy tomorrow, sleeping close tonight)",
        )
        add_to_pack(self.state, P1, "bread", 1, self.rules)
        self.assertEqual(
            format_legal_action("sell bread 1", self.state, self.crops, P1, self.rules),
            "sell bread 1 (+4G)",
        )
        self.assertEqual(
            format_legal_action("drop bread 1", self.state, self.crops, P1, self.rules),
            "drop bread 1 (chest will have 1)",
        )
        self.state["players"][P1]["energy"] = 80
        self.assertEqual(
            format_legal_action("eat bread", self.state, self.crops, P1, self.rules),
            "eat bread (+5 energy)",
        )
        add_to_pack(self.state, P1, "strawberry", 3, self.rules)
        add_to_pack(self.state, P1, "sugar", 1, self.rules)
        line = format_legal_action("craft strawberry_jam", self.state, self.crops, P1, self.rules)
        self.assertEqual(line, "craft strawberry jam (5 energy, uses 3 strawberries, 1 sugar)")
        # legal_actions stay bare commands; look shows the human names + descriptors.
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("buy strawberry 1", actions)
        self.assertIn("take strawberry_seed 1", actions)
        self.assertIn("take hoe 1", actions)
        self.assertIn("end turn", actions)
        look = describe_state(self.state, self.crops, viewer=P1)
        self.assertIn("move down (to r2 c3, 5 energy)", look)
        self.assertIn("buy June-bearing strawberry seed 1", look)
        self.assertIn("take June-bearing strawberry seed 1 (leaves 1 in chest)", look)
        self.assertIn("end turn (sleep in cabin, 105 energy tomorrow, sleeping close tonight)", look)
        self.assertNotIn("take strawberry_seed", look)
        self.assertNotIn(" 2 seeds", look)
        # Pasting a look line still works.
        self.assertEqual(strip_action_descriptor("eat bread (+5 energy)"), "eat bread")
        stand(self.state, P1, 2, 3)
        self.assertEqual(
            format_legal_action("end turn", self.state, self.crops, P1, self.rules),
            "end turn (pass out, 50 energy)",
        )

    def test_eat_from_shop_descriptor_is_not_a_legal_action(self):
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertFalse(any("shop" in a for a in actions if a.startswith("eat ")))
        ok, msg = do_action(self.state, self.crops, "eat bread shop", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("shop", msg.lower())


class SaveSlots(unittest.TestCase):
    def setUp(self):
        import shutil
        self._old_state = engine.STATE_PATH
        self._old_lock = engine.LOCK_PATH
        self._old_journal = engine.JOURNAL_ARCHIVE_PATH
        self.tmp = Path(tempfile.mkdtemp(prefix="lantern-farm-saves-"))
        engine.STATE_PATH = self.tmp / "state.json"
        engine.LOCK_PATH = self.tmp / ".state.lock"
        engine.JOURNAL_ARCHIVE_PATH = self.tmp / "journal-archive.json"
        self.addCleanup(self._restore)

    def _restore(self):
        import shutil
        engine.STATE_PATH = self._old_state
        engine.LOCK_PATH = self._old_lock
        engine.JOURNAL_ARCHIVE_PATH = self._old_journal
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _legacy_farm(self, gold=80, day=3):
        from engine import fresh_state, save_state, load_crops
        state = fresh_state(load_crops())
        state["gold"] = gold
        state["day"] = day
        save_state(state, engine.STATE_PATH)
        return state

    def test_without_slots_load_and_save_use_state_path(self):
        import saves
        from engine import default_state_path, load_state, save_state, load_crops
        self.assertIsNone(saves.current_slot_id())
        self.assertEqual(default_state_path(), engine.STATE_PATH)
        state = self._legacy_farm(gold=91, day=2)
        loaded = load_state(load_crops())
        self.assertEqual(loaded["gold"], 91)
        self.assertFalse((self.tmp / "saves" / "active.json").exists())

    def test_migrate_copies_legacy_into_permanent_first_farm_and_keeps_the_snapshot(self):
        import saves
        from engine import default_state_path, load_state, load_crops
        self._legacy_farm(gold=123, day=4)
        slot = saves.migrate_legacy_state(backup=True)
        self.assertEqual(slot, saves.FIRST_FARM_ID)
        self.assertEqual(saves.current_slot_id(), saves.FIRST_FARM_ID)
        self.assertEqual(default_state_path(), saves.slot_state_path(saves.FIRST_FARM_ID))
        loaded = load_state(load_crops())
        self.assertEqual(loaded["gold"], 123)
        self.assertEqual(loaded["day"], 4)
        # Root snapshot is left in place.
        snap = json.loads(engine.STATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(snap["gold"], 123)
        entries = saves.list_slots()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "First Farm")
        self.assertTrue(entries[0]["active"])
        self.assertTrue(entries[0]["protected"])
        backups = list((self.tmp / "backups").glob("before-save-slots-*"))
        self.assertTrue(backups, "migrate should copy the farm into a local backup first")
        backed = json.loads((backups[-1] / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(backed["gold"], 123)
        self.assertEqual(saves.migrate_legacy_state(backup=False), saves.FIRST_FARM_ID)
        # A later change to the leftover snapshot must not overwrite First Farm.
        snap["gold"] = 1
        engine.STATE_PATH.write_text(json.dumps(snap), encoding="utf-8")
        self.assertEqual(saves.migrate_legacy_state(backup=False), saves.FIRST_FARM_ID)
        again = json.loads(saves.slot_state_path(saves.FIRST_FARM_ID).read_text(encoding="utf-8"))
        self.assertEqual(again["gold"], 123)

    def test_maybe_migrate_live_is_a_noop_in_tests(self):
        import saves
        self._legacy_farm()
        self.assertFalse(saves.is_live_tree())
        self.assertIsNone(saves.maybe_migrate_live())
        self.assertIsNone(saves.current_slot_id())

    def test_new_load_rename_never_overwrite_another_slot(self):
        import saves
        from engine import load_state, save_state, load_crops, do_action
        self._legacy_farm(gold=200, day=5)
        saves.migrate_legacy_state(backup=False)
        ok, msg, sid = saves.new_slot("")
        self.assertFalse(ok)
        self.assertIsNone(sid)
        ok, msg, sid = saves.new_slot("Orchard")
        self.assertTrue(ok, msg)
        self.assertEqual(sid, "orchard")
        fresh = load_state(load_crops())
        self.assertEqual(fresh["gold"], 80)
        self.assertEqual(fresh["day"], 1)
        # First Farm is unchanged.
        first = json.loads(saves.slot_state_path(saves.FIRST_FARM_ID).read_text(encoding="utf-8"))
        self.assertEqual(first["gold"], 200)
        self.assertEqual(first["day"], 5)
        # Play in the new slot, then switch back; progress is kept in each.
        fresh["gold"] = 50
        save_state(fresh)
        refused, message, _ = saves.new_slot("orchard")
        self.assertFalse(refused)
        self.assertIn("already exists", message)
        refused, message, _ = saves.new_slot("First Farm")
        self.assertFalse(refused)
        ok, message, sid = saves.load_slot("First Farm")
        self.assertTrue(ok, message)
        self.assertEqual(sid, saves.FIRST_FARM_ID)
        loaded = load_state(load_crops())
        self.assertEqual(loaded["gold"], 200)
        orchard = json.loads(saves.slot_state_path("orchard").read_text(encoding="utf-8"))
        self.assertEqual(orchard["gold"], 50)
        ok, message, sid = saves.rename_slot("first-farm", "Home Place")
        self.assertTrue(ok, message)
        self.assertEqual(sid, saves.FIRST_FARM_ID)
        meta = saves.read_meta(saves.FIRST_FARM_ID)
        self.assertEqual(meta["name"], "Home Place")
        refused, message, _ = saves.rename_slot("orchard", "home place")
        self.assertFalse(refused)
        listed = saves.format_slot_list()
        self.assertIn("Home Place", listed)
        self.assertIn("(active)", listed)
        self.assertIn("Orchard", listed)
        missing, message, _ = saves.load_slot("no-such-farm")
        self.assertFalse(missing)
        # Colliding slugs get a suffix; the first slot is left alone.
        ok, message, sid = saves.new_slot("Orchard Lane")
        self.assertTrue(ok, message)
        # "Orchard Lane" slugs to orchard-lane, not orchard. Force a collision:
        ok, message, sid = saves.new_slot("ORCHARD")
        self.assertFalse(ok)
        # A different name that slugs to orchard should unique-ify.
        # "Orchard!" slugs to orchard and the display name differs.
        ok, message, sid = saves.new_slot("The Orchard!")
        self.assertTrue(ok, message)
        self.assertEqual(sid, "the-orchard")
        # Direct slug collision: create "Meadow", then a name that slugs to meadow.
        ok, message, sid = saves.new_slot("Meadow")
        self.assertTrue(ok, message)
        self.assertEqual(sid, "meadow")
        ok, message, sid = saves.new_slot("Meadow!!")
        self.assertTrue(ok, message)
        self.assertEqual(sid, "meadow-2")
        meadow = json.loads(saves.slot_state_path("meadow").read_text(encoding="utf-8"))
        self.assertEqual(meadow["day"], 1)

    def test_cli_new_without_a_name_does_not_wipe_the_farm(self):
        import io
        import contextlib
        import cli
        import saves
        from engine import load_state, load_crops
        self._legacy_farm(gold=222, day=6)
        saves.migrate_legacy_state(backup=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(["new"])
        self.assertEqual(code, 2)
        self.assertIn("Farm name", err.getvalue())
        state = load_state(load_crops())
        self.assertEqual(state["gold"], 222)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["saves"])
        self.assertEqual(code, 0)
        self.assertIn("First Farm", out.getvalue())
        self.assertIn("(active)", out.getvalue())

    def test_cli_and_mcp_can_list_and_switch(self):
        import io
        import contextlib
        import cli
        import saves
        import mcp_server
        from engine import load_state, load_crops, save_state
        self._legacy_farm(gold=140, day=2)
        saves.migrate_legacy_state(backup=False)
        text, is_error = mcp_server.farm_saves("list")
        self.assertFalse(is_error)
        self.assertIn("First Farm", text)
        ok_text, is_error = mcp_server.farm_saves("new", name="River Bank")
        self.assertFalse(is_error)
        self.assertIn("River Bank", ok_text)
        state = load_state(load_crops())
        self.assertEqual(state["day"], 1)
        text, is_error = mcp_server.farm_saves("load", slot="First Farm")
        self.assertFalse(is_error)
        self.assertEqual(load_state(load_crops())["gold"], 140)
        text, is_error = mcp_server.farm_saves("rename", name="The First Farm", slot="first-farm")
        self.assertFalse(is_error)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["load", "river-bank"]), 0)
        self.assertIn("River Bank", out.getvalue())
        self.assertEqual(load_state(load_crops())["day"], 1)

    def test_journal_archive_follows_the_active_slot_when_not_redirected(self):
        import saves
        from engine import journal_archive_path
        self._legacy_farm()
        saves.migrate_legacy_state(backup=False)
        # Tests redirect the archive path; honor that.
        self.assertEqual(journal_archive_path(), engine.JOURNAL_ARCHIVE_PATH)
        # When the path is the engine default, use the slot file.
        engine.JOURNAL_ARCHIVE_PATH = engine.ROOT / "local" / "journal-archive.json"
        self.assertEqual(journal_archive_path(), saves.slot_journal_path(saves.FIRST_FARM_ID))

    def test_reset_state_writes_the_legacy_path_not_the_active_slot(self):
        import saves
        from engine import reset_state, load_crops
        self._legacy_farm(gold=77, day=8)
        saves.migrate_legacy_state(backup=False)
        reset_state(load_crops())
        first = json.loads(saves.slot_state_path(saves.FIRST_FARM_ID).read_text(encoding="utf-8"))
        self.assertEqual(first["gold"], 77)
        snap = json.loads(engine.STATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(snap["day"], 1)
        self.assertEqual(snap["gold"], 80)


class SpringPlantedCrops(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)
        self.state["weather"] = "sun"

    def _grow(self, r, c, n):
        for _ in range(n):
            self.state["weather"] = "sun"
            water(self.state, self.crops, r, c)
            ok, msg = sleep(self.state, self.crops, self.rules)
            self.assertTrue(ok, msg)

    def test_summer_shop_follows_the_remaining_grow_window(self):
        from engine import shop_kinds, legal_actions, buy, crop_for_sale, crop_info
        # Summer day 1: corn (28d) and kabocha (30d) fit; pumpkin (33d) does not.
        self.state["day"] = 16
        self.state["season"] = "summer"
        summer = shop_kinds(self.crops, "summer", day=16)
        self.assertIn("strawberry", summer)
        self.assertIn("everbearing", summer)
        self.assertIn("carrot", summer)
        self.assertIn("lettuce", summer)
        self.assertIn("kabocha", summer)
        self.assertIn("corn", summer)
        self.assertNotIn("pumpkin", summer)
        self.assertNotIn("turnip", summer)
        self.assertNotIn("rhubarb", summer)  # crown, shop_seasons spring only
        self.assertTrue(crop_for_sale(crop_info(self.crops, "corn"), "summer", day=16, crops=self.crops))
        self.assertFalse(crop_for_sale(crop_info(self.crops, "corn"), "summer", day=19, crops=self.crops))
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("buy strawberry 1", actions)
        self.assertIn("buy kabocha 1", actions)
        self.assertIn("buy carrot 1", actions)
        self.assertNotIn("buy turnip 1", actions)
        self.assertNotIn("buy pumpkin 1", actions)
        ok, msg = buy(self.state, self.crops, "turnip", 1)
        self.assertFalse(ok)
        self.assertIn("summer", msg.lower())
        # Summer day 4: corn no longer fits.
        self.state["day"] = 19
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn("buy corn 1", actions)
        self.assertNotIn("buy kabocha 1", actions)

    def test_quick_and_regrow_crops_harvest_in_their_window(self):
        from engine import grow_days, regrow_days, crop_info, yield_range_for
        from inventory import item_count
        for kind in ("radish", "pea", "tomato"):
            state = fresh_state(self.crops, rules=self.rules)
            state["weather"] = "sun"
            self.state = state
            info = crop_info(self.crops, kind)
            r, c = 1, 1
            till(state, self.crops, r, c)
            give_seeds(state, kind, 1)
            ok, msg = plant(state, self.crops, r, c, kind)
            self.assertTrue(ok, msg)
            self._grow(r, c, grow_days(info))
            crop = state["tiles"][r - 1][c - 1]["crop"]
            self.assertEqual(crop["stage"], "mature", (kind, crop))
            before = item_count(state, kind)
            ok, msg = harvest(state, self.crops, r, c)
            self.assertTrue(ok, msg)
            got = item_count(state, kind) - before
            lo, hi = yield_range_for(kind, self.crops)
            self.assertGreaterEqual(got, lo)
            self.assertLessEqual(got, hi)
            if regrow_days(info) > 0:
                crop = state["tiles"][r - 1][c - 1]["crop"]
                self.assertEqual(crop["stage"], "regrowing", kind)
                self._grow(r, c, regrow_days(info))
                self.assertEqual(state["tiles"][r - 1][c - 1]["crop"]["stage"], "mature", kind)

    def test_kabocha_planted_in_spring_ripens_in_early_autumn(self):
        from engine import grow_days, crop_info, season_for_day
        info = crop_info(self.crops, "kabocha")
        self.assertEqual(grow_days(info), 30)
        r, c = 1, 1
        till(self.state, self.crops, r, c)
        give_seeds(self.state, "kabocha", 1)
        ok, msg = plant(self.state, self.crops, r, c, "kabocha")
        self.assertTrue(ok, msg)
        self._grow(r, c, 30)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")
        self.assertEqual(self.state["season"], "autumn")
        self.assertEqual(season_for_day(int(self.state["day"]), self.crops), "autumn")
        ok, msg = harvest(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(self.state["inventory"]["kabocha"], 1)

    def test_rhubarb_and_asparagus_wait_until_the_next_spring(self):
        from inventory import item_count
        for kind in ("rhubarb", "asparagus"):
            state = fresh_state(self.crops, rules=self.rules)
            state["weather"] = "sun"
            r, c = 1, 1
            till(state, self.crops, r, c)
            from engine import stock_key, crop_info
            info = crop_info(self.crops, kind)
            give_item(state, stock_key(kind, info), 1)
            ok, msg = plant(state, self.crops, r, c, kind)
            self.assertTrue(ok, msg)
            crop = state["tiles"][r - 1][c - 1]["crop"]
            self.assertIn(crop["stage"], {"crown", "seed"})
            # Grow through the first spring; it must not be harvestable yet.
            self.state = state
            self._grow(r, c, 14)
            crop = state["tiles"][r - 1][c - 1]["crop"]
            self.assertIsNotNone(crop)
            self.assertFalse(crop.get("overwintered"))
            ok, msg = harvest(state, self.crops, r, c)
            self.assertFalse(ok, kind)
            # Skip to the end of summer so the next sleep enters autumn (dormant).
            state["day"] = 30
            state["season"] = "summer"
            water(state, self.crops, r, c)
            ok, msg = sleep(state, self.crops, self.rules)
            self.assertTrue(ok, msg)
            self.assertEqual(state["season"], "autumn")
            crop = state["tiles"][r - 1][c - 1]["crop"]
            self.assertEqual(crop["stage"], "dormant", kind)
            self.assertTrue(crop.get("overwintered"))
            # Wake in spring and grow to a harvest.
            state["day"] = 60
            state["season"] = "winter"
            ok, msg = sleep(state, self.crops, self.rules)
            self.assertTrue(ok, msg)
            self.assertEqual(state["season"], "spring")
            crop = state["tiles"][r - 1][c - 1]["crop"]
            self.assertNotEqual(crop["stage"], "dormant", kind)
            from engine import grow_days
            self._grow(r, c, grow_days(info))
            crop = state["tiles"][r - 1][c - 1]["crop"]
            self.assertEqual(crop["stage"], "mature", (kind, crop))
            before = item_count(state, kind)
            ok, msg = harvest(state, self.crops, r, c)
            self.assertTrue(ok, msg)
            self.assertGreater(item_count(state, kind), before)
            self.assertEqual(state["tiles"][r - 1][c - 1]["crop"]["stage"], "regrowing", kind)

    def test_potato_yields_two_or_three(self):
        from engine import yield_roll, yield_range_for
        self.assertEqual(yield_range_for("potato", self.crops), (2, 3))
        seen = set()
        for day in range(1, 80):
            n = yield_roll("potato", 100, 100, day, 1, 1, harvest_index=0)
            seen.add(n)
            self.assertIn(n, (2, 3))
        self.assertTrue(seen & {2, 3})

    def test_new_spring_recipes_craft_sell_and_eat(self):
        from inventory import add_to_chest, pack_has, item_sell_price, item_eat_energy, recipes
        from engine import do_action
        recs = recipes(self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 100
        add_to_chest(self.state, "rhubarb", 2, self.rules)
        add_to_chest(self.state, "strawberry", 1, self.rules)
        add_to_chest(self.state, "sugar", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "craft rhubarb strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "rhubarb_strawberry_jam", 1))
        gold = self.state["gold"]
        ok, msg = do_action(self.state, self.crops, "sell rhubarb_strawberry_jam 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold + item_sell_price("rhubarb_strawberry_jam", self.crops, self.rules))
        add_to_chest(self.state, "lettuce", 1, self.rules)
        add_to_chest(self.state, "tomato", 1, self.rules)
        add_to_chest(self.state, "cucumber", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "craft garden salad", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.state["players"][P1]["energy"] = 50
        energy = self.state["players"][P1]["energy"]
        ok, msg = do_action(self.state, self.crops, "eat garden_salad", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], energy + item_eat_energy("garden_salad", self.crops, self.rules))
        add_to_chest(self.state, "potato", 2, self.rules)
        add_to_chest(self.state, "butter", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "craft roasted potatoes", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        add_to_chest(self.state, "pumpkin", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "craft pumpkin soup", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "pumpkin_soup", 1))
        for key in ("rhubarb_strawberry_jam", "garden_salad", "roasted_potatoes", "pumpkin_soup"):
            self.assertIn(key, recs)

    def test_give_seeds_accepts_crowns_and_bush_beans(self):
        from engine import stock_key, crop_info, normalize_kind
        self.assertEqual(normalize_kind("peas"), "pea")
        self.assertEqual(normalize_kind("bush beans"), "bush_bean")
        self.assertEqual(stock_key("rhubarb", crop_info(self.crops, "rhubarb")), "rhubarb_crown")
        give_seeds(self.state, "bush_bean", 2, player=P1)
        from inventory import pack_has
        self.assertTrue(pack_has(self.state, P1, "bush_bean_seed", 2))




class HillsPhaseOne(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)

    def _axe(self, player=None):
        player = player or P1
        from inventory import TOOL_AXE, pack_has, remove_from_chest, add_to_pack, sync_inventory_view
        stand(self.state, player, CABIN_ROW, CABIN_COL)
        if not pack_has(self.state, player, TOOL_AXE, 1, self.rules):
            remove_from_chest(self.state, TOOL_AXE, 1, self.rules)
            add_to_pack(self.state, player, TOOL_AXE, 1, self.rules)
            sync_inventory_view(self.state, self.rules)

    def test_fresh_farm_has_hills_and_full_hp(self):
        from hills import hills_tiles, AREA_FARM, player_area, player_hp, MINE_ENTRANCE, get_hills_tile
        from inventory import item_count, TOOL_AXE
        self.assertTrue(hills_tiles(self.state))
        self.assertEqual(player_area(self.state, P1), AREA_FARM)
        hp, cap = player_hp(self.state, P1, self.rules)
        self.assertEqual((hp, cap), (100, 100))
        self.assertGreaterEqual(item_count(self.state, TOOL_AXE, self.rules), 1)
        entrance = get_hills_tile(self.state, *MINE_ENTRANCE)
        self.assertEqual(entrance.get("type"), "mine_entrance")
        self.assertTrue(entrance.get("closed"))
        self.assertFalse(self.state.get("mine_entrance_found"))

    def test_migrate_keeps_farm_and_turn(self):
        from hills import player_area, AREA_FARM
        from inventory import item_count, TOOL_AXE
        state = fresh_state(self.crops, weather_seed=7, rules=self.rules)
        state["day"] = 5
        state["season"] = "spring"
        state["gold"] = 2
        state["current_player"] = P1
        state["players"][P1]["energy"] = 0
        state["players"][P1]["ended_turn"] = False
        state["players"][P1]["row"] = 3
        state["players"][P1]["col"] = 1
        farm = copy.deepcopy(state["tiles"])
        pack = copy.deepcopy(state["players"][P1]["pack"])
        state.pop("hills", None)
        state.pop("mine_entrance_found", None)
        for slot in state["players"].values():
            slot.pop("area", None)
            slot.pop("hp", None)
            slot.pop("hp_max", None)
        changed = migrate_state(state, self.rules)
        self.assertTrue(changed)
        self.assertEqual(state["tiles"], farm)
        self.assertEqual(state["gold"], 2)
        self.assertEqual(state["current_player"], P1)
        self.assertEqual(state["players"][P1]["energy"], 0)
        self.assertEqual(state["players"][P1]["ended_turn"], False)
        self.assertEqual((state["players"][P1]["row"], state["players"][P1]["col"]), (3, 1))
        self.assertEqual(state["players"][P1]["pack"], pack)
        self.assertEqual(player_area(state, P1), AREA_FARM)
        self.assertEqual(state["players"][P1]["hp"], 100)
        self.assertTrue(state.get("hills", {}).get("tiles"))
        self.assertGreaterEqual(item_count(state, TOOL_AXE, self.rules), 1)

    def test_hills_13_is_not_the_cabin(self):
        from hills import set_player_place, AREA_HILLS, is_cabin_place
        from engine import is_player_in_cabin
        set_player_place(self.state, P1, AREA_HILLS, 1, 3)
        self.assertFalse(is_cabin_place(AREA_HILLS, 1, 3))
        self.assertFalse(is_player_in_cabin(self.state, P1))
        self.assertIn("pass out", sleep_outlook(self.state, P1, self.rules).lower())

    def test_pass_out_outlook_names_the_current_area(self):
        from hills import set_player_place, AREA_HILLS, AREA_FARM, HILLS_GATE
        from describe import describe_state
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.assertIn("You'll sleep in the cabin", sleep_outlook(self.state, P1, self.rules))
        stand(self.state, P1, 3, 1)
        field = sleep_outlook(self.state, P1, self.rules)
        self.assertEqual(field, "You'll pass out in the field — 50 energy tomorrow")
        self.assertIn(field, describe_state(self.state, self.crops, viewer=P1))
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        hills = sleep_outlook(self.state, P1, self.rules)
        self.assertEqual(hills, "You'll pass out in the hills — 50 energy tomorrow")
        self.assertNotIn("in the field", hills)
        look = describe_state(self.state, self.crops, viewer=P1)
        self.assertIn("You'll pass out in the hills", look)
        self.assertNotIn("You'll pass out in the field", look)
        # Mine isn't a playable area yet; the warning should still name it
        # once a player is marked as being there.
        self.state["players"][P1]["area"] = "mine"
        mine = sleep_outlook(self.state, P1, self.rules)
        self.assertEqual(mine, "You'll pass out in the mine — 50 energy tomorrow")
        set_player_place(self.state, P1, AREA_FARM, 3, 1)

    def test_cabin_north_enters_hills_bottom_right(self):
        from hills import player_area, AREA_HILLS, HILLS_GATE, AREA_FARM
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "go north", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(player_where(self.state, P1), HILLS_GATE)
        self.assertIn("hills", msg.lower())
        ok, msg = do_action(self.state, self.crops, "go south", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(player_area(self.state, P1), AREA_FARM)
        self.assertEqual(player_where(self.state, P1), (CABIN_ROW, CABIN_COL))

    def test_north_from_other_top_row_is_refused(self):
        from hills import player_area, AREA_FARM
        stand(self.state, P1, 1, 1)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "move up", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())
        self.assertEqual(player_area(self.state, P1), AREA_FARM)
        self.assertEqual(player_where(self.state, P1), (1, 1))

    def test_go_cabin_from_hills_charges_the_path(self):
        from hills import set_player_place, AREA_HILLS, AREA_FARM, player_area
        set_player_place(self.state, P1, AREA_HILLS, 1, 1)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "go cabin", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(player_where(self.state, P1), (CABIN_ROW, CABIN_COL))
        self.assertEqual(player_area(self.state, P1), AREA_FARM)
        self.assertEqual(self.state["players"][P1]["energy"], 85)
        self.assertIn("3 steps", msg)

    def test_trees_grow_chop_and_stump_resprouts(self):
        from hills import (
            set_player_place, AREA_HILLS, make_tree, get_hills_tile,
            tick_hills, tree_days_for,
        )
        from inventory import pack_has
        tile = get_hills_tile(self.state, 3, 2)
        tile["tree"] = make_tree("sapling", planted_day=1, days_grown=0)
        tile["forage"] = None
        days = tree_days_for("sapling", self.rules) + tree_days_for("young", self.rules)
        for _ in range(days):
            tick_hills(self.state, self.rules)
        self.assertEqual(get_hills_tile(self.state, 3, 2)["tree"]["stage"], "grown")
        self._axe(P1)
        set_player_place(self.state, P1, AREA_HILLS, 3, 2)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "chop", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("packs 2 wood", msg)
        self.assertNotIn("and pack 2", msg)
        self.assertEqual(get_hills_tile(self.state, 3, 2)["tree"]["stage"], "stump")
        self.assertTrue(pack_has(self.state, P1, "wood", 2, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 90)
        from inventory import remove_from_pack, add_to_chest, sync_inventory_view
        tile2 = get_hills_tile(self.state, 2, 2)
        tile2["tree"] = make_tree("grown", planted_day=1)
        tile2["forage"] = None
        set_player_place(self.state, P1, AREA_HILLS, 2, 2)
        remove_from_pack(self.state, P1, "axe", 1, self.rules)
        add_to_chest(self.state, "axe", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        ok, msg = do_action(self.state, self.crops, "chop", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("axe", msg.lower())
        stump = get_hills_tile(self.state, 3, 2)
        stump["tree"] = make_tree("stump", planted_day=1, days_grown=0)
        from hills import stump_becomes_log
        seed = int(self.state.get("weather_seed") or 1)
        while stump_becomes_log(self.state, 3, 2):
            seed += 1
            self.state["weather_seed"] = seed
        for _ in range(tree_days_for("stump", self.rules)):
            tick_hills(self.state, self.rules)
        self.assertEqual(get_hills_tile(self.state, 3, 2)["tree"]["stage"], "sapling")

    def test_stump_becomes_a_mushroom_log_or_a_sapling_never_both(self):
        from hills import (
            make_tree, get_hills_tile, tick_hills, tree_days_for, stump_becomes_log,
        )
        saw_log = saw_sapling = False
        for seed in range(1, 40):
            for r, c in ((1, 1), (2, 1), (2, 2), (3, 1), (3, 2), (3, 3)):
                tile = get_hills_tile(self.state, r, c)
                if tile.get("type") == "mine_entrance":
                    continue
                self.state["weather_seed"] = seed
                self.state["day"] = 8
                if stump_becomes_log(self.state, r, c):
                    saw_log = True
                else:
                    saw_sapling = True
        self.assertTrue(saw_log and saw_sapling, "the exclusive roll should hit both outcomes")
        tile = get_hills_tile(self.state, 3, 2)
        tile["tree"] = make_tree("stump", planted_day=1, days_grown=0)
        tile["forage"] = None
        seed = 1
        self.state["weather_seed"] = seed
        self.state["day"] = 8
        while not stump_becomes_log(self.state, 3, 2):
            seed += 1
            self.state["weather_seed"] = seed
        for _ in range(tree_days_for("stump", self.rules)):
            tick_hills(self.state, self.rules)
        self.assertEqual(get_hills_tile(self.state, 3, 2)["tree"]["stage"], "mushroom_log")

    def test_mushroom_log_forages_oysters_past_the_wild_cap_and_in_winter(self):
        from hills import (
            make_tree, make_forage, get_hills_tile, tick_hills, log_forage_days,
            forage_count, iter_hills_tiles, is_mine_entrance_tile,
        )
        for r, c, tile in iter_hills_tiles(self.state):
            if is_mine_entrance_tile(r, c):
                continue
            tile["forage"] = make_forage("wild_onion", 1)
            tile["tree"] = None
        log_tile = get_hills_tile(self.state, 3, 2)
        log_tile["tree"] = make_tree("mushroom_log", planted_day=1, days_grown=0)
        log_tile["forage"] = None
        self.state["day"] = 46
        self.state["season"] = "winter"
        cap_before = forage_count(self.state)
        self.assertGreaterEqual(cap_before, 2)
        for _ in range(log_forage_days(self.rules)):
            tick_hills(self.state, self.rules)
        log_tile = get_hills_tile(self.state, 3, 2)
        self.assertEqual((log_tile.get("forage") or {}).get("kind"), "oyster_mushroom")
        self.assertEqual(forage_count(self.state), cap_before + 1)

    def test_unearth_hills_stump_needs_a_shovel_costs_20_and_clears_to_grass(self):
        from hills import set_player_place, AREA_HILLS, make_tree, get_hills_tile
        from inventory import add_to_pack, TOOL_SHOVEL, pack_has
        from engine import legal_actions, format_legal_action, energy_cost, unearth_energy_cost
        tile = get_hills_tile(self.state, 3, 2)
        tile["tree"] = make_tree("stump", planted_day=1, days_grown=0)
        tile["forage"] = None
        set_player_place(self.state, P1, AREA_HILLS, 3, 2)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "unearth", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertIn("shovel", msg.lower())
        self.assertEqual(get_hills_tile(self.state, 3, 2)["tree"]["stage"], "stump")
        add_to_pack(self.state, P1, TOOL_SHOVEL, 1, self.rules)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("unearth 3 2", actions)
        line = format_legal_action("unearth 3 2", self.state, self.crops, P1, self.rules)
        self.assertEqual(line, "unearth (removes the stump, 20 energy)")
        self.assertEqual(unearth_energy_cost(self.state, P1, self.rules, 3, 2), 20)
        self.assertEqual(energy_cost("unearth", self.rules), 5)
        ok, msg = do_action(
            self.state, self.crops,
            "unearth (removes the stump, 20 energy)",
            player=P1, rules=self.rules,
        )
        self.assertTrue(ok, msg)
        self.assertIn("stump", msg)
        self.assertIn("plain grass", msg)
        self.assertIsNone(get_hills_tile(self.state, 3, 2).get("tree"))
        self.assertIsNone(get_hills_tile(self.state, 3, 2).get("forage"))
        self.assertEqual(self.state["players"][P1]["energy"], 80)
        self.assertTrue(pack_has(self.state, P1, TOOL_SHOVEL, 1, self.rules))
        ok, msg = do_action(self.state, self.crops, "unearth", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertEqual(msg, "There's nothing to unearth here in the hills.")

    def test_unearth_hills_mushroom_log_clears_oysters_too(self):
        from hills import set_player_place, AREA_HILLS, make_tree, make_forage, get_hills_tile
        from inventory import add_to_pack, TOOL_SHOVEL
        tile = get_hills_tile(self.state, 2, 2)
        tile["tree"] = make_tree("mushroom_log", planted_day=1, days_grown=0)
        tile["forage"] = make_forage("oyster_mushroom", 1)
        set_player_place(self.state, P1, AREA_HILLS, 2, 2)
        self.state["players"][P1]["energy"] = 40
        add_to_pack(self.state, P1, TOOL_SHOVEL, 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "unearth 2 2", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("mushroom log", msg)
        self.assertIn("oyster mushroom", msg)
        self.assertIn("plain grass", msg)
        self.assertIsNone(get_hills_tile(self.state, 2, 2).get("tree"))
        self.assertIsNone(get_hills_tile(self.state, 2, 2).get("forage"))
        self.assertEqual(self.state["players"][P1]["energy"], 20)

    def test_take_axe_1_from_the_chest(self):
        from inventory import pack_has, TOOL_AXE
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        ok, msg = do_action(self.state, self.crops, "take axe 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, TOOL_AXE, 1, self.rules))

    def test_forage_is_deterministic_and_seasonal(self):
        from hills import _spawn_forage, forage_kind_for_season, iter_hills_tiles, set_player_place, AREA_HILLS
        from inventory import pack_has
        self.assertEqual(forage_kind_for_season("spring"), "wild_onion")
        self.assertEqual(forage_kind_for_season("summer"), "wild_berry")
        self.assertEqual(forage_kind_for_season("winter"), None)
        for _r, _c, tile in iter_hills_tiles(self.state):
            tile["forage"] = None
        a = copy.deepcopy(self.state)
        b = copy.deepcopy(self.state)
        _spawn_forage(a, self.rules, log=False)
        _spawn_forage(b, self.rules, log=False)
        spots_a = [(r, c, t["forage"]) for r, c, t in iter_hills_tiles(a) if t.get("forage")]
        spots_b = [(r, c, t["forage"]) for r, c, t in iter_hills_tiles(b) if t.get("forage")]
        self.assertEqual(spots_a, spots_b)
        if not spots_a:
            from hills import make_forage, get_hills_tile
            get_hills_tile(self.state, 3, 1)["tree"] = None
            get_hills_tile(self.state, 3, 1)["forage"] = make_forage("wild_onion", 1)
            r, c, kind = 3, 1, "wild_onion"
        else:
            r, c, fod = spots_a[0]
            kind = fod["kind"]
            self.state = a
        set_player_place(self.state, P1, AREA_HILLS, r, c)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "forage", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, kind, 1, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 95)

    def test_look_names_the_area_and_the_other_player(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        from describe import describe_state
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        text = describe_state(self.state, self.crops, viewer=P1)
        self.assertIn("Mini map — the hills", text)
        self.assertIn("Elsewhere:", text)
        self.assertIn("The farm:", text)
        self.assertIn("Walk south from the bottom-right hill", text)
        self.assertIn(N2, text)
        self.assertIn("in the cabin", text)
        farm_text = describe_state(self.state, self.crops, viewer=P2)
        self.assertIn("Mini map — the farm", farm_text)
        self.assertIn("The hills:", farm_text)
        self.assertIn("Walk north from the cabin", farm_text)
        self.assertIn("in the hills", farm_text)

    def test_mini_map_hills_labels_fit(self):
        from hills import map_cell_lines, iter_hills_tiles
        from describe import MAP_LABEL_WIDTH
        for _r, _c, tile in iter_hills_tiles(self.state):
            a, b = map_cell_lines(tile)
            self.assertLessEqual(len(a), MAP_LABEL_WIDTH, a)
            self.assertLessEqual(len(b), MAP_LABEL_WIDTH, b)

    def test_snacks_heal_hp_and_sleep_fills_hp(self):
        from hills import player_hp, set_player_place, AREA_HILLS, player_area
        from inventory import add_to_pack, sync_inventory_view
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["hp"] = 80
        self.state["players"][P1]["energy"] = 100
        add_to_pack(self.state, P1, "bread", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat bread", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        hp, cap = player_hp(self.state, P1, self.rules)
        self.assertEqual(hp, 85)
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertIn("HP", msg)
        self.state["players"][P1]["hp"] = 40
        self.state["players"][P1]["snacks_eaten"] = 0
        ok, msg = do_action(self.state, self.crops, "end turn", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        hp, cap = player_hp(self.state, P1, self.rules)
        self.assertEqual(hp, 100)
        set_player_place(self.state, P1, AREA_HILLS, 3, 3)
        self.state["players"][P1]["hp"] = 40
        self.state["current_player"] = P1
        self.state["players"][P1]["ended_turn"] = False
        self.state["players"][P2]["ended_turn"] = False
        ok, _ = do_action(self.state, self.crops, "end turn", player=P1, rules=self.rules)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok)
        hp, cap = player_hp(self.state, P1, self.rules)
        self.assertEqual(hp, 40)
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(self.state["players"][P1]["energy"], 50)

    def test_zero_hp_wakes_at_the_mine_entrance(self):
        from hills import faint_from_hp, player_area, AREA_HILLS, MINE_ENTRANCE, player_hp
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["hp"] = 0
        self.state["players"][P1]["energy"] = 80
        msg = faint_from_hp(self.state, P1, self.rules)
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(player_where(self.state, P1), MINE_ENTRANCE)
        self.assertEqual(self.state["players"][P1]["energy"], 25)
        self.assertEqual(player_hp(self.state, P1, self.rules)[0], 100)
        self.assertIn("mine entrance", msg.lower())
        self.assertTrue(self.state.get("mine_entrance_found"))

    def test_listed_hills_actions_execute(self):
        from hills import set_player_place, AREA_HILLS, make_tree, make_forage, get_hills_tile
        from engine import described_legal_actions, legal_actions, strip_action_descriptor
        self._axe(P1)
        tile = get_hills_tile(self.state, 3, 3)
        tile["tree"] = make_tree("grown")
        tile["forage"] = make_forage("wild_onion", 1)
        set_player_place(self.state, P1, AREA_HILLS, 3, 3)
        self.state["players"][P1]["energy"] = 100
        listed = described_legal_actions(self.state, self.crops, P1, self.rules)
        raw = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("go south", raw)
        self.assertIn("chop", raw)
        self.assertIn("forage", raw)
        self.assertIn("go cabin", raw)
        for shown, cmd in zip(listed, raw):
            scratch = copy.deepcopy(self.state)
            ok, msg = do_action(scratch, self.crops, strip_action_descriptor(shown), player=P1, rules=self.rules)
            self.assertTrue(ok, f"{shown!r} -> failed: {msg}")
            scratch2 = copy.deepcopy(self.state)
            ok2, msg2 = do_action(scratch2, self.crops, cmd, player=P1, rules=self.rules)
            self.assertTrue(ok2, f"{cmd!r} failed: {msg2}")

    def test_hills_sprite_keys_round_trip(self):
        from sprites import sprite_key, parse_sprite_key, svg_for_key, is_safe_key
        tiles = [
            {"type": "grass", "tree": {"stage": "sapling"}, "forage": None},
            {"type": "grass", "tree": {"stage": "grown"}, "forage": {"kind": "wild_onion"}},
            {"type": "hillside", "tree": {"stage": "stump"}, "forage": None},
            {"type": "grass", "tree": {"stage": "mushroom_log"}, "forage": {"kind": "oyster_mushroom"}},
            {"type": "mine_entrance", "closed": True, "tree": None, "forage": None},
        ]
        for tile in tiles:
            for weather in ("sun", "snow"):
                key = sprite_key(tile, weather)
                self.assertTrue(is_safe_key(key), key)
                info = parse_sprite_key(key)
                self.assertTrue(info.get("hills"), key)
                self.assertEqual(info.get("type"), tile["type"])
                if tile.get("tree"):
                    self.assertEqual(info.get("tree"), tile["tree"]["stage"])
                if tile.get("forage"):
                    self.assertEqual(info.get("forage"), tile["forage"]["kind"])
                if weather == "snow":
                    self.assertTrue(info.get("snow"))
                svg = svg_for_key(key)
                self.assertIn("<svg", svg)

    def test_web_payload_has_elsewhere_and_view_area(self):
        import web
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertEqual(payload["view_area"], "hills")
        self.assertEqual(len(payload["view_tiles"]), 3)
        self.assertIn("hills", payload["area_title"])
        joined = "\n".join(payload["elsewhere"])
        self.assertIn("Elsewhere:", joined)
        self.assertIn("The farm:", joined)
        self.assertIn(N2, joined)
        self.assertIn("100", str(payload["hp"][P1]))
        html = web.PAGE
        self.assertIn('id="area-head"', html)
        self.assertNotIn('id="elsewhere"', html)
        self.assertIn("<kbd>C</kbd>", html)
        self.assertIn("<kbd>G</kbd>", html)


class ForageFood(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 40
        self.state["players"][P1]["hp"] = 80
        self.state["players"][P1]["snacks_eaten"] = 0

    def test_forage_eat_values_and_mushroom_is_cook_only(self):
        from inventory import item_eat_energy, item_sell_price, pack_has
        from hills import player_hp

        self.assertEqual(item_eat_energy("wild_onion", self.crops, self.rules), 6)
        self.assertEqual(item_eat_energy("wild_berry", self.crops, self.rules), 8)
        self.assertIsNone(item_eat_energy("wild_mushroom", self.crops, self.rules))
        for item in ("wild_onion", "wild_berry", "wild_mushroom"):
            self.assertIsNone(item_sell_price(item, self.crops, self.rules))

        give_item(self.state, "wild_onion", 1, player=P1)
        give_item(self.state, "wild_berry", 1, player=P1)
        give_item(self.state, "wild_mushroom", 1, player=P1)

        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("eat wild_onion", actions)
        self.assertIn("eat wild_berry", actions)
        self.assertNotIn("eat wild_mushroom", actions)
        self.assertFalse(any(a.startswith("sell wild") for a in actions))

        ok, msg = do_action(self.state, self.crops, "eat wild onion", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 46)
        hp, cap = player_hp(self.state, P1, self.rules)
        self.assertEqual(hp, 86)
        self.assertFalse(pack_has(self.state, P1, "wild_onion", 1, self.rules))

        ok, msg = do_action(self.state, self.crops, "eat wild berry", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 54)
        hp, cap = player_hp(self.state, P1, self.rules)
        self.assertEqual(hp, 94)
        self.assertFalse(pack_has(self.state, P1, "wild_berry", 1, self.rules))

        ok, msg = do_action(self.state, self.crops, "eat wild mushroom", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertIn("isn't edible raw", msg)
        self.assertTrue(pack_has(self.state, P1, "wild_mushroom", 1, self.rules))

        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn("eat wild_mushroom", actions)
        self.assertFalse(any(a.startswith("sell wild") for a in actions))

    def test_shop_does_not_buy_foraged_goods(self):
        from inventory import pack_has

        give_item(self.state, "wild_onion", 1, player=P1)
        gold = int(self.state["gold"])
        ok, msg = do_action(self.state, self.crops, "sell wild onion", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertEqual(msg, "The shop doesn't buy foraged goods.")
        self.assertEqual(self.state["gold"], gold)
        self.assertTrue(pack_has(self.state, P1, "wild_onion", 1, self.rules))

        for cmd in ("sell wild berry", "sell wild mushroom", "sell oyster mushroom", "sell wild_onion 1"):
            ok, msg = do_action(self.state, self.crops, cmd, player=P1, rules=self.rules)
            self.assertFalse(ok, msg)
            self.assertEqual(msg, "The shop doesn't buy foraged goods.", cmd)

    def test_forage_recipes_craft_and_wild_berries_count_toward_jam(self):
        from inventory import (
            pack_has,
            recipes,
            ingredient_cost,
            ingredient_eat_total,
            item_sell_price,
            item_eat_energy,
        )

        for key in ("wild_onion_soup", "wild_berry_jam", "mushroom_soup"):
            rec = recipes(self.rules)[key]
            self.assertGreater(
                item_sell_price(key, self.crops, self.rules),
                ingredient_cost(rec, self.crops, self.rules),
                key,
            )
            self.assertGreater(
                item_eat_energy(key, self.crops, self.rules),
                ingredient_eat_total(rec, self.crops, self.rules),
                key,
            )

        give_item(self.state, "wild_onion", 1, player=P1)
        give_item(self.state, "milk", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft wild onion soup", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "wild_onion_soup", 1, self.rules) or pack_has(self.state, P1, "wild_onion_soup", 1))
        self.assertFalse(pack_has(self.state, P1, "wild_onion", 1, self.rules))

        give_item(self.state, "wild_berry", 3, player=P1)
        give_item(self.state, "sugar", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft wild berry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "wild_berry_jam", 1, self.rules))

        give_item(self.state, "wild_mushroom", 1, player=P1)
        give_item(self.state, "milk", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft mushroom soup", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "mushroom_soup", 1, self.rules))

        # Wild berries fill strawberry jam's berry pool.
        give_item(self.state, "strawberry", 1, player=P1)
        give_item(self.state, "wild_berry", 2, player=P1)
        give_item(self.state, "sugar", 1, player=P1)
        ok, msg = do_action(self.state, self.crops, "craft strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))
        self.assertFalse(pack_has(self.state, P1, "strawberry", 1, self.rules))
        self.assertFalse(pack_has(self.state, P1, "wild_berry", 1, self.rules))

    def test_oyster_mushroom_is_cook_only_unsellable_and_cooks_soup(self):
        from inventory import add_to_pack, pack_has, item_eat_energy, item_sell_price
        from engine import legal_actions
        self.assertIsNone(item_eat_energy("oyster_mushroom", self.crops, self.rules))
        self.assertIsNone(item_sell_price("oyster_mushroom", self.crops, self.rules))
        add_to_pack(self.state, P1, "oyster_mushroom", 1, self.rules)
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn("eat oyster_mushroom", actions)
        ok, msg = do_action(self.state, self.crops, "eat oyster mushroom", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertIn("isn't edible raw", msg)
        ok, msg = do_action(self.state, self.crops, "sell oyster mushroom 1", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertIn("foraged", msg.lower())
        self.assertTrue(pack_has(self.state, P1, "oyster_mushroom", 1, self.rules))
        add_to_pack(self.state, P1, "milk", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "craft mushroom soup", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "mushroom_soup", 1, self.rules))
        self.assertFalse(pack_has(self.state, P1, "oyster_mushroom", 1, self.rules))


class BreadHalvesAndChopGrammar(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 40
        self.state["players"][P1]["snacks_eaten"] = 0

    def test_eating_bread_leaves_a_half_loaf_and_the_two_halves_sum_to_ten(self):
        from inventory import add_to_pack, pack_has, item_sell_price, item_eat_energy, staple_shop_items

        self.assertEqual(item_eat_energy("bread", self.crops, self.rules), 5)
        self.assertEqual(item_eat_energy("bread_half", self.crops, self.rules), 5)
        self.assertEqual(item_sell_price("bread", self.crops, self.rules), 4)
        self.assertEqual(item_sell_price("bread_half", self.crops, self.rules), 2)
        self.assertNotIn("bread_half", staple_shop_items(self.rules))

        add_to_pack(self.state, P1, "bread", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat bread", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 45)
        self.assertFalse(pack_has(self.state, P1, "bread", 1, self.rules))
        self.assertTrue(pack_has(self.state, P1, "bread_half", 1, self.rules))
        self.assertIn("half loaf", msg)

        ok, msg = do_action(self.state, self.crops, "eat half loaf", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertFalse(pack_has(self.state, P1, "bread_half", 1, self.rules))

    def test_a_half_loaf_can_be_left_in_the_chest_for_a_companion(self):
        from inventory import add_to_pack, pack_has, stack_count, chest_of
        from engine import eat

        add_to_pack(self.state, P1, "bread", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat bread", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        ok, msg = do_action(self.state, self.crops, "drop bread_half 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertFalse(pack_has(self.state, P1, "bread_half", 1, self.rules))
        self.assertGreaterEqual(stack_count(chest_of(self.state, self.rules), "bread_half"), 1)

        self.state["players"][P2]["energy"] = 40
        self.state["players"][P2]["snacks_eaten"] = 0
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        ok, msg = eat(self.state, self.crops, "half loaf", P2, self.rules, from_chest=True)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P2]["energy"], 45)
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "bread_half"), 0)

    def test_shop_does_not_sell_half_loaves(self):
        self.state["gold"] = 100
        ok, msg = do_action(self.state, self.crops, "buy half loaf 1", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)
        self.assertIn("isn't selling", msg.lower())

    def test_chop_log_says_packs_wood(self):
        from hills import set_player_place, AREA_HILLS, make_tree, get_hills_tile
        from inventory import TOOL_AXE, pack_has, remove_from_chest, add_to_pack, sync_inventory_view
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        if not pack_has(self.state, P1, TOOL_AXE, 1, self.rules):
            remove_from_chest(self.state, TOOL_AXE, 1, self.rules)
            add_to_pack(self.state, P1, TOOL_AXE, 1, self.rules)
            sync_inventory_view(self.state, self.rules)
        tile = get_hills_tile(self.state, 2, 3)
        tile["tree"] = make_tree("grown", planted_day=1)
        tile["forage"] = None
        set_player_place(self.state, P1, AREA_HILLS, 2, 3)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "chop", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("packs 2 wood", msg)
        self.assertNotIn("and pack 2", msg)


class PerennialProgressLabels(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        self.state["weather"] = "sun"

    def _plant(self, kind, r=1, c=1):
        from engine import stock_key, crop_info, till, plant
        till(self.state, self.crops, r, c)
        info = crop_info(self.crops, kind)
        give_item(self.state, stock_key(kind, info), 1)
        ok, msg = plant(self.state, self.crops, r, c, kind)
        self.assertTrue(ok, msg)
        return self.state["tiles"][r - 1][c - 1]["crop"]

    def _grow(self, r, c, n):
        from engine import water, sleep
        for _ in range(n):
            water(self.state, self.crops, r, c)
            sleep(self.state, self.crops, self.rules)

    def test_june_bearing_strawberry_is_establishing_not_day_zero_of_seven(self):
        from describe import describe_tile, crop_progress_phrase
        from engine import crop_info
        import web

        crop = self._plant("strawberry")
        info = crop_info(self.crops, "strawberry")
        phrase = crop_progress_phrase(crop, info)
        self.assertEqual(phrase, "establishing, day 0 of the first year; fruits next spring")
        self.assertNotIn("day 0 of 7", phrase)
        line = describe_tile(self.state, self.crops, 1, 1)
        self.assertIn("establishing, day 0 of the first year; fruits next spring", line)
        self.assertNotIn("day 0 of 7", line)

        self._grow(1, 1, 5)
        crop = self.state["tiles"][0][0]["crop"]
        self.assertEqual(int(crop.get("days_established") or 0), 5)
        self.assertEqual(int(crop.get("days_grown") or 0), 0)
        phrase = crop_progress_phrase(crop, info)
        self.assertEqual(phrase, "establishing, day 5 of the first year; fruits next spring")
        self.assertNotIn("of 7", phrase)
        line = describe_tile(self.state, self.crops, 1, 1)
        self.assertIn("establishing, day 5 of the first year; fruits next spring", line)
        self.assertNotIn("day 0 of 7", line)
        self.assertNotIn("day 5 of 7", line)

        payload = web.api_payload(self.state, self.crops, player=P1)
        view_crop = payload["view_tiles"][0][0]["crop"]
        self.assertEqual(
            view_crop["progress_phrase"],
            "establishing, day 5 of the first year; fruits next spring",
        )
        # The live save must not be annotated for the client.
        self.assertNotIn("progress_phrase", self.state["tiles"][0][0]["crop"])

    def test_everbearing_uses_settling_day_n_of_four(self):
        from describe import describe_tile, crop_progress_phrase
        from engine import crop_info

        crop = self._plant("everbearing")
        info = crop_info(self.crops, "everbearing")
        phrase = crop_progress_phrase(crop, info)
        self.assertEqual(phrase, "settling, day 0 of 4")
        self.assertNotIn("day 0 of 7", phrase)
        line = describe_tile(self.state, self.crops, 1, 1)
        self.assertIn("settling, day 0 of 4", line)
        self.assertNotIn("day 0 of 7", line)

        self._grow(1, 1, 2)
        crop = self.state["tiles"][0][0]["crop"]
        phrase = crop_progress_phrase(crop, info)
        self.assertEqual(phrase, "settling, day 2 of 4")
        line = describe_tile(self.state, self.crops, 1, 1)
        self.assertIn("settling, day 2 of 4", line)

    def test_rhubarb_and_asparagus_crowns_are_establishing(self):
        from describe import describe_tile, crop_progress_phrase
        from engine import crop_info

        for kind, col in (("rhubarb", 1), ("asparagus", 2)):
            state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
            state["weather"] = "sun"
            self.state = state
            crop = self._plant(kind, 1, col)
            info = crop_info(self.crops, kind)
            phrase = crop_progress_phrase(crop, info)
            self.assertTrue(phrase.startswith("establishing, day 0 of the first year"), kind)
            self.assertIn("fruits next spring", phrase)
            self.assertNotIn("day 0 of 10", phrase)
            self.assertNotIn("day 0 of 7", phrase)
            line = describe_tile(self.state, self.crops, 1, col)
            self.assertIn("establishing, day 0 of the first year; fruits next spring", line)
            self.assertNotIn("day 0 of 10", line)
            self._grow(1, col, 3)
            crop = self.state["tiles"][0][col - 1]["crop"]
            self.assertEqual(int(crop.get("days_established") or 0), 3, kind)
            phrase = crop_progress_phrase(crop, info)
            self.assertEqual(
                phrase,
                "establishing, day 3 of the first year; fruits next spring",
                kind,
            )



class HillsJsdomUi(unittest.TestCase):
    def test_jsdom_renders_hills_grid_and_elsewhere(self):
        import shutil
        import subprocess
        import tempfile
        import web
        from hills import set_player_place, AREA_HILLS, HILLS_GATE, make_tree, get_hills_tile

        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        get_hills_tile(state, 3, 3)["tree"] = make_tree("grown")
        set_player_place(state, P1, AREA_HILLS, *HILLS_GATE)
        payload = web.api_payload(state, crops, player=P1)
        html = web.render_page(viewer=P1)
        runner = Path(__file__).resolve().parent / "tests" / "hills-ui.test.js"
        self.assertTrue(runner.is_file(), str(runner))
        with tempfile.TemporaryDirectory(prefix="lantern-hills-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            if not (jsdom_root / "node_modules" / "jsdom").exists():
                jsdom_root.mkdir(parents=True, exist_ok=True)
                inst = subprocess.run(
                    ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund", "jsdom@24"],
                    cwd=jsdom_root,
                    capture_output=True,
                    text=True,
                )
                if inst.returncode != 0:
                    self.skipTest("jsdom install failed: " + (inst.stderr or inst.stdout)[-400:])
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            proc = subprocess.run(
                [node, str(runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertIn("hills", data["head"].lower())
            self.assertFalse(data.get("elsewherePresent"))
            self.assertEqual((data.get("elsewhere") or "").strip(), "")
            self.assertEqual(data["tileCount"], 9)
            self.assertEqual(
                data["labels"],
                ["r1 c1", "r1 c2", "r1 c3", "r2 c1", "r2 c2", "r2 c3", "r3 c1", "r3 c2", "r3 c3"],
            )
            self.assertIn("hills", (data["aria"] or "").lower())
            srcs = " ".join(data.get("imgSrcs") or [])
            self.assertIn("hills_grass.png", srcs)
            self.assertIn("tree_grown.png", srcs)
            self.assertIn("mine_entrance_closed.png", srcs)


class MinePhaseTwo(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)

    def _give_pickaxe(self, player=None):
        player = player or P1
        give_item(self.state, "pickaxe", 1, player=player, where="pack")

    def _at_entrance(self, player=None, found=True, energy=100, gold=80):
        from hills import set_player_place, AREA_HILLS, MINE_ENTRANCE
        player = player or P1
        if found:
            self.state["mine_entrance_found"] = True
        set_player_place(self.state, player, AREA_HILLS, *MINE_ENTRANCE)
        self.state["players"][player]["energy"] = energy
        self.state["gold"] = gold
        self.state["current_player"] = player

    def _enter(self, player=None):
        player = player or P1
        self._give_pickaxe(player)
        self._at_entrance(player)
        ok, msg = do_action(self.state, self.crops, "enter mine", player=player, rules=self.rules)
        self.assertTrue(ok, msg)
        return msg

    def test_entrance_stays_boarded_until_pickaxe_is_used(self):
        from hills import get_hills_tile, MINE_ENTRANCE, set_player_place, AREA_HILLS
        from mine import is_entrance_open
        tile = get_hills_tile(self.state, *MINE_ENTRANCE)
        self.assertTrue(tile.get("closed"))
        self.assertFalse(is_entrance_open(self.state))
        self.assertNotIn("pickaxe", " ".join(engine.shop_listing(self.crops, self.state["season"], self.rules, state=self.state)))
        # Finding the entrance unlocks the shop, but boards stay up until a pickaxe pries them.
        self._at_entrance(found=True)
        self.assertFalse(is_entrance_open(self.state))
        listing = engine.shop_listing(self.crops, self.state["season"], self.rules, state=self.state)
        self.assertIn("pickaxe", listing)
        ok, msg = do_action(self.state, self.crops, "enter mine", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("pickaxe", msg.lower())
        self.assertFalse(is_entrance_open(self.state))

    def test_shop_sells_one_pickaxe_after_the_entrance_is_found(self):
        from inventory import pack_has, TOOL_PICKAXE
        from hills import set_player_place, AREA_FARM
        set_player_place(self.state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        self.state["gold"] = 80
        self.state["current_player"] = P1
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "buy pickaxe 1", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("entrance", msg.lower())
        self.state["mine_entrance_found"] = True
        set_player_place(self.state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 100
        self.state["current_player"] = P1
        self.assertIn("buy pickaxe 1", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "buy pickaxe 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], 40)
        self.assertTrue(pack_has(self.state, P1, TOOL_PICKAXE, 1, self.rules))
        ok, msg = do_action(self.state, self.crops, "buy pickaxe 1", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("already", msg.lower())

    def test_shop_payload_lists_the_pickaxe_once_the_entrance_is_found(self):
        import web
        from hills import set_player_place, AREA_FARM
        from engine import format_legal_action

        set_player_place(self.state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        self.state["current_player"] = P1
        self.state["players"][P1]["energy"] = 100

        # Hidden until the entrance is found.
        self.state["mine_entrance_found"] = False
        self.state["gold"] = 51
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertFalse(payload.get("tools") or {})
        self.assertNotIn("buy pickaxe 1", legal_actions(self.state, self.crops, P1, self.rules))

        # Listed (and priced) even when gold is short of 40G.
        self.state["mine_entrance_found"] = True
        self.state["gold"] = 9
        payload = web.api_payload(self.state, self.crops, player=P1)
        tools = payload.get("tools") or {}
        self.assertIn("pickaxe", tools)
        self.assertEqual(int(tools["pickaxe"]["price"]), 40)
        self.assertEqual(int(tools["pickaxe"]["seed_price"]), 40)
        self.assertFalse(tools["pickaxe"]["affordable"])
        self.assertIn("buy pickaxe 1", legal_actions(self.state, self.crops, P1, self.rules))
        line = format_legal_action("buy pickaxe 1", self.state, self.crops, P1, self.rules)
        self.assertIn("40", line)
        self.assertIn("9", line)
        self.assertIn("pickaxe", line.lower())
        ok, msg = do_action(self.state, self.crops, "buy pickaxe 1", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("40", msg)
        self.assertIn("9", msg)

        # Affordable at 51G: still in the payload, Buy is offered, descriptor shows the change.
        self.state["gold"] = 51
        payload = web.api_payload(self.state, self.crops, player=P1)
        tools = payload.get("tools") or {}
        self.assertIn("pickaxe", tools)
        self.assertTrue(tools["pickaxe"]["affordable"])
        self.assertEqual(int(tools["pickaxe"]["price"]), 40)
        line = format_legal_action("buy pickaxe 1", self.state, self.crops, P1, self.rules)
        self.assertIn("40", line)
        self.assertIn("11", line)

        # Gone from the shop once one is already on the farm.
        from inventory import add_to_pack, TOOL_PICKAXE, sync_inventory_view
        add_to_pack(self.state, P1, TOOL_PICKAXE, 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertNotIn("pickaxe", payload.get("tools") or {})
        self.assertNotIn("buy pickaxe 1", legal_actions(self.state, self.crops, P1, self.rules))

    def test_enter_mine_opens_boards_and_arrives_on_a_clear_tile(self):
        from hills import get_hills_tile, MINE_ENTRANCE, player_area, AREA_MINE
        from mine import is_entrance_open, get_mine_tile, player_floor, arrival_tile
        msg = self._enter()
        self.assertTrue(is_entrance_open(self.state))
        self.assertFalse(get_hills_tile(self.state, *MINE_ENTRANCE).get("closed"))
        self.assertEqual(player_area(self.state, P1), AREA_MINE)
        self.assertEqual(player_floor(self.state, P1), 1)
        r, c = player_where(self.state, P1)
        self.assertEqual((r, c), arrival_tile(self.state, 1, self.rules))
        tile = get_mine_tile(self.state, 1, r, c, self.rules)
        self.assertFalse(tile.get("rock"))
        self.assertTrue(tile.get("exit"))
        self.assertEqual(self.state["players"][P1]["energy"], 95)
        self.assertIn("floor 1", msg.lower())

    def test_layouts_are_deterministic_and_reroll_with_the_season(self):
        from mine import get_floor, ensure_mine
        a = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        b = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        ensure_mine(a, self.rules)
        ensure_mine(b, self.rules)
        self.assertEqual(get_floor(a, 3, self.rules)["tiles"], get_floor(b, 3, self.rules)["tiles"])
        first = copy.deepcopy(get_floor(a, 3, self.rules)["tiles"])
        ensure_mine(a, self.rules)
        self.assertEqual(first, get_floor(a, 3, self.rules)["tiles"])
        a["season"] = "summer"
        a["day"] = 29
        ensure_mine(a, self.rules)
        self.assertNotEqual(first, get_floor(a, 3, self.rules)["tiles"])

    def test_ladder_is_hidden_under_a_non_centre_rock_and_is_revealed_by_mining(self):
        from hills import set_player_place, AREA_MINE
        from mine import get_floor, iter_mine_tiles, CENTER
        from inventory import pack_has, TOOL_PICKAXE
        self._enter()
        hidden = [
            (r, c, tile)
            for r, c, tile in iter_mine_tiles(self.state, 1, self.rules)
            if tile.get("ladder") == "hidden"
        ]
        self.assertEqual(len(hidden), 1)
        r, c, tile = hidden[0]
        self.assertNotEqual((r, c), CENTER)
        self.assertTrue(tile.get("rock"))
        self.assertNotEqual((r, c), player_where(self.state, P1))
        set_player_place(self.state, P1, AREA_MINE, r, c, floor=1)
        self.state["players"][P1]["energy"] = 100
        self.assertTrue(pack_has(self.state, P1, TOOL_PICKAXE, 1, self.rules))
        ok, msg = do_action(self.state, self.crops, "mine", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        from mine import get_mine_tile
        cleared = get_mine_tile(self.state, 1, r, c, self.rules)
        self.assertFalse(cleared.get("rock"))
        self.assertEqual(cleared.get("ladder"), "open")
        self.assertIn("ladder", msg.lower())
        self.assertIn("stone", msg.lower())
        self.assertTrue(pack_has(self.state, P1, "stone", 1, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 90)
        self.assertIn("climb down", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "climb down", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        from mine import player_floor
        self.assertEqual(player_floor(self.state, P1), 2)
        self.assertEqual(self.state["players"][P1]["energy"], 80)
        self.assertIn("floor 2", msg.lower())

    def test_ores_follow_depth_bands_and_safe_floors_have_rest_and_elevator(self):
        from mine import get_floor, iter_mine_tiles, ore_chances, is_safe_floor
        self._enter()
        for floor in range(1, 5):
            copper, iron, gold = ore_chances(floor)
            self.assertGreater(copper, 0)
            self.assertEqual(iron, 0)
            self.assertEqual(gold, 0)
            kinds = {tile.get("rock") for _r, _c, tile in iter_mine_tiles(self.state, floor, self.rules) if tile.get("rock")}
            self.assertTrue(kinds <= {"stone", "copper_ore"})
        copper, iron, gold = ore_chances(12)
        self.assertGreater(iron, copper)
        self.assertGreater(gold, 0)
        copper, iron, gold = ore_chances(22)
        self.assertEqual(copper, 0)
        self.assertGreater(gold, 0)
        floor5 = get_floor(self.state, 5, self.rules)
        rocks = [tile for _r, _c, tile in iter_mine_tiles(self.state, 5, self.rules) if tile.get("rock")]
        self.assertFalse(rocks)
        self.assertTrue(is_safe_floor(5, self.rules))
        features = {(bool(t.get("lantern")), bool(t.get("elevator")), t.get("ladder"), bool(t.get("exit")))
                    for _r, _c, t in iter_mine_tiles(self.state, 5, self.rules)}
        self.assertTrue(any(t.get("lantern") for _r, _c, t in iter_mine_tiles(self.state, 5, self.rules)))
        self.assertTrue(any(t.get("elevator") for _r, _c, t in iter_mine_tiles(self.state, 5, self.rules)))
        self.assertTrue(any(t.get("ladder") == "open" for _r, _c, t in iter_mine_tiles(self.state, 5, self.rules)))
        self.assertFalse(any(t.get("ladder") == "open" for _r, _c, t in iter_mine_tiles(self.state, 25, self.rules)))

    def test_lantern_rest_is_once_per_day_and_elevator_reaches_checkpoints(self):
        from hills import set_player_place, AREA_MINE, player_area, AREA_HILLS, MINE_ENTRANCE
        from mine import iter_mine_tiles, player_floor, get_floor
        self._enter()
        get_floor(self.state, 5, self.rules)
        lantern = next(( (r, c) for r, c, t in iter_mine_tiles(self.state, 5, self.rules) if t.get("lantern") ))
        lift = next(( (r, c) for r, c, t in iter_mine_tiles(self.state, 5, self.rules) if t.get("elevator") ))
        set_player_place(self.state, P1, AREA_MINE, *lantern, floor=5)
        self.state["players"][P1]["energy"] = 20
        ok, msg = do_action(self.state, self.crops, "rest", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 45)
        ok, msg = do_action(self.state, self.crops, "rest", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("already rested", msg.lower())
        set_player_place(self.state, P1, AREA_MINE, *lift, floor=5)
        self.state["players"][P1]["energy"] = 50
        actions = legal_actions(self.state, self.crops, P1, self.rules)
        self.assertIn("elevator entrance", actions)
        self.assertIn("elevator", actions)
        ok, msg = do_action(self.state, self.crops, "elevator entrance", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(player_where(self.state, P1), MINE_ENTRANCE)
        self.assertEqual(self.state["players"][P1]["energy"], 45)

    def test_pass_out_in_the_mine_wakes_at_the_last_elevator_or_entrance(self):
        from hills import set_player_place, AREA_MINE, player_area, AREA_HILLS, MINE_ENTRANCE
        from mine import iter_mine_tiles, player_floor, get_floor, mark_checkpoint
        from engine import days_per_season
        self._enter()
        get_floor(self.state, 5, self.rules)
        mark_checkpoint(self.state, 5)
        lift = next(( (r, c) for r, c, t in iter_mine_tiles(self.state, 5, self.rules) if t.get("elevator") ))
        set_player_place(self.state, P1, AREA_MINE, *lift, floor=5)
        self.assertIn("You'll pass out in the mine — 50 energy tomorrow", sleep_outlook(self.state, P1, self.rules))
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        self.state["current_player"] = P2
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.state["current_player"] = P1
        ok, msg = do_action(self.state, self.crops, "end turn", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(player_area(self.state, P1), AREA_MINE)
        self.assertEqual(player_floor(self.state, P1), 5)
        self.assertEqual(player_where(self.state, P1), lift)
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertIn("passed out in the mine", msg.lower())

        # Season change at dawn sends them to the hills entrance instead.
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        self._enter()
        get_floor(self.state, 5, self.rules)
        mark_checkpoint(self.state, 5)
        lift = next(( (r, c) for r, c, t in iter_mine_tiles(self.state, 5, self.rules) if t.get("elevator") ))
        set_player_place(self.state, P1, AREA_MINE, *lift, floor=5)
        self.state["day"] = days_per_season(self.crops)
        self.state["season"] = "spring"
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        self.state["current_player"] = P2
        ok, _msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, _msg)
        self.state["current_player"] = P1
        ok, msg = do_action(self.state, self.crops, "end turn", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["season"], "summer")
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(player_where(self.state, P1), MINE_ENTRANCE)
        self.assertIsNone(self.state["players"][P1].get("floor"))
        self.assertEqual(self.state["players"][P1]["energy"], 50)

    def test_zero_hp_still_wakes_at_the_hills_entrance_with_25_energy(self):
        from hills import faint_from_hp, player_area, AREA_HILLS, MINE_ENTRANCE, set_player_place, AREA_MINE
        from mine import player_floor
        self._enter()
        set_player_place(self.state, P1, AREA_MINE, 2, 2, floor=8)
        self.state["players"][P1]["hp"] = 0
        self.state["players"][P1]["energy"] = 40
        msg = faint_from_hp(self.state, P1, self.rules)
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(player_where(self.state, P1), MINE_ENTRANCE)
        self.assertIsNone(self.state["players"][P1].get("floor"))
        self.assertEqual(self.state["players"][P1]["energy"], 25)
        self.assertEqual(self.state["players"][P1]["hp"], 100)
        self.assertIn("entrance", msg.lower())

    def test_forge_upgrades_reduce_tool_energy(self):
        from inventory import TOOL_HOE, add_to_pack, sync_inventory_view
        from mine import tool_action_cost, tool_tier, set_tool_tier
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 100
        self.state["current_player"] = P1
        # Hoe starts in the chest on a fresh farm; take it and add ore.
        give_item(self.state, "copper_ore", 5, player=P1, where="pack")
        if not any((s or {}).get("item") == TOOL_HOE for s in self.state["players"][P1]["pack"]):
            give_item(self.state, TOOL_HOE, 1, player=P1, where="pack")
        self.assertIn("forge hoe", legal_actions(self.state, self.crops, P1, self.rules))
        before = tool_action_cost(self.state, P1, "till", self.rules)
        self.assertEqual(before, 10)
        ok, msg = do_action(self.state, self.crops, "forge hoe", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(tool_tier(self.state, TOOL_HOE), "copper")
        self.assertEqual(tool_action_cost(self.state, P1, "till", self.rules), 5)
        self.assertEqual(self.state["players"][P1]["energy"], 95)
        # Iron axe yields an extra wood.
        from hills import set_player_place, AREA_HILLS, make_tree, get_hills_tile
        from inventory import TOOL_AXE, pack_has
        give_item(self.state, TOOL_AXE, 1, player=P1, where="pack")
        set_tool_tier(self.state, TOOL_AXE, "iron")
        tile = get_hills_tile(self.state, 2, 2)
        tile["tree"] = make_tree("grown", planted_day=1)
        tile["forage"] = None
        set_player_place(self.state, P1, AREA_HILLS, 2, 2)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "chop", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("3 wood", msg)
        self.assertTrue(pack_has(self.state, P1, "wood", 3, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 95)

    def test_legal_actions_and_short_names_work_and_go_cabin_is_refused(self):
        from hills import set_player_place, AREA_MINE, player_area
        from mine import iter_mine_tiles, get_floor, player_floor
        self._enter()
        actions = legal_actions(self.state, self.crops, P1, self.rules)
        self.assertIn("climb up", actions)
        self.assertIn("leave mine", actions)
        self.assertNotIn("go cabin", actions)
        ok, msg = do_action(self.state, self.crops, "go cabin", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("leave", msg.lower() + "climb" + msg.lower())
        self.assertIn("mine", msg.lower())
        ok, msg = do_action(self.state, self.crops, "leave mine", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        from hills import AREA_HILLS, MINE_ENTRANCE
        self.assertEqual(player_area(self.state, P1), AREA_HILLS)
        self.assertEqual(player_where(self.state, P1), MINE_ENTRANCE)

    def test_go_mine_does_not_double_charge(self):
        self._give_pickaxe(P1)
        self._at_entrance()
        ok, msg = do_action(self.state, self.crops, "go mine", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 95)

    def test_migration_leaves_farm_gold_packs_and_turn_alone(self):
        from hills import player_area, AREA_FARM
        state = fresh_state(self.crops, weather_seed=9, rules=self.rules)
        state["day"] = 10
        state["season"] = "spring"
        state["gold"] = 50
        state["current_player"] = P1
        state["players"][P1]["energy"] = 7
        state["players"][P1]["ended_turn"] = False
        farm = copy.deepcopy(state["tiles"])
        pack = copy.deepcopy(state["players"][P1]["pack"])
        chest = copy.deepcopy(state.get("chest") or state.get("cabin_chest"))
        state.pop("mine", None)
        state.pop("tool_tiers", None)
        changed = migrate_state(state, self.rules)
        self.assertTrue(changed)
        self.assertEqual(state["tiles"], farm)
        self.assertEqual(state["gold"], 50)
        self.assertEqual(state["current_player"], P1)
        self.assertEqual(state["players"][P1]["energy"], 7)
        self.assertEqual(state["players"][P1]["pack"], pack)
        self.assertEqual(state.get("chest") or state.get("cabin_chest"), chest)
        self.assertEqual(player_area(state, P1), AREA_FARM)
        self.assertIn("mine", state)

    def test_web_payload_serves_the_viewers_mine_floor_without_elsewhere_dom(self):
        from hills import AREA_MINE
        import web
        self._enter()
        payload = web.api_payload(self.state, self.crops, True, "entered", player=P1)
        self.assertEqual(payload["view_area"], AREA_MINE)
        self.assertEqual(payload["view_floor"], 1)
        self.assertEqual(len(payload["view_tiles"]), 3)
        self.assertIn("floor", payload["area_title"])
        self.assertTrue(payload.get("elsewhere"))  # CLI/payload hint stays
        self.assertNotIn('id="elsewhere"', web.PAGE)
        # Copies, not the live floor object.
        payload["view_tiles"][0][0]["progress_phrase"] = "mutated"
        from mine import get_floor
        live = get_floor(self.state, 1, self.rules)["tiles"]
        self.assertNotIn("progress_phrase", live[0][0])

    def test_bare_gold_is_not_an_ore_alias(self):
        from inventory import normalize_item
        self.assertEqual(normalize_item("gold ore"), "gold_ore")
        self.assertNotEqual(normalize_item("gold"), "gold_ore")

    def test_plain_rock_yields_sellable_stone_and_respects_pack_space(self):
        from hills import set_player_place, AREA_MINE, AREA_FARM
        from mine import get_mine_tile, iter_mine_tiles
        from inventory import pack_has, add_to_pack, item_sell_price
        from sprites import sprite_key, parse_sprite_key
        from packs import layers_for_key, load_manifest

        exit_tile = {"type": "mine_floor", "exit": True}
        self.assertEqual(sprite_key(exit_tile, floor=1), "mine_floor_shaft")
        self.assertEqual(sprite_key(exit_tile), "mine_floor_shaft")
        self.assertEqual(sprite_key(exit_tile, floor=2), "mine_floor_ladder_up")
        up = parse_sprite_key("mine_floor_ladder_up")
        self.assertTrue(up.get("ladder_up"))
        self.assertTrue(up.get("mine"))
        door = parse_sprite_key("mine_floor_shaft")
        self.assertTrue(door.get("exit") or door.get("shaft"))
        self.assertFalse(door.get("ladder_up"))

        man = load_manifest("storybook")
        rock_layers = layers_for_key("mine_floor_rock", man)
        self.assertEqual([layer["role"] for layer in rock_layers], ["ground", "crop"])
        self.assertIn("mine_floor", rock_layers[0]["file"])
        self.assertIn("mine_rock.png", rock_layers[1]["file"])
        up_layers = layers_for_key("mine_safe_ladder_up", man)
        self.assertIn("mine_safe", up_layers[0]["file"])
        self.assertIn("mine_ladder_up", up_layers[1]["file"])
        self.assertIn("mine_shaft", layers_for_key("mine_floor_shaft", man)[1]["file"])
        self.assertIn("mine_rock_copper", layers_for_key("mine_floor_rock_copper", man)[1]["file"])
        self.assertEqual(item_sell_price("stone", self.crops, self.rules), 1)

        self._enter()
        found = next(
            ((r, c) for r, c, tile in iter_mine_tiles(self.state, 1, self.rules) if tile.get("rock") == "stone"),
            None,
        )
        self.assertIsNotNone(found)
        r, c = found
        set_player_place(self.state, P1, AREA_MINE, r, c, floor=1)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "mine", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("stone", msg.lower())
        self.assertTrue(pack_has(self.state, P1, "stone", 1, self.rules))
        self.assertEqual(self.state["players"][P1]["energy"], 90)
        self.assertFalse(get_mine_tile(self.state, 1, r, c, self.rules).get("rock"))

        # Fill the stone stack to its cap too, or a second piece would still fit.
        add_to_pack(self.state, P1, "stone", 7, self.rules)
        while add_to_pack(self.state, P1, "wood", 8, self.rules) == 0:
            pass
        found2 = next(
            (
                (rr, cc)
                for rr, cc, tile in iter_mine_tiles(self.state, 1, self.rules)
                if tile.get("rock") == "stone" and (rr, cc) != found
            ),
            None,
        )
        self.assertIsNotNone(found2)
        r, c = found2
        set_player_place(self.state, P1, AREA_MINE, r, c, floor=1)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "mine", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("room", msg.lower())
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertTrue(get_mine_tile(self.state, 1, r, c, self.rules).get("rock"))

        set_player_place(self.state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        gold = int(self.state["gold"] or 0)
        ok, msg = do_action(self.state, self.crops, "sell stone 1", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["gold"]), gold + 1)

    def test_iron_pickaxe_yields_extra_stone_and_gold_splashes_a_neighbour(self):
        from hills import set_player_place, AREA_MINE
        from mine import get_mine_tile, iter_mine_tiles, set_tool_tier
        from inventory import pack_has, TOOL_PICKAXE

        self._enter()
        set_tool_tier(self.state, TOOL_PICKAXE, "iron")
        target = neigh = None
        for r, c, tile in iter_mine_tiles(self.state, 1, self.rules):
            if tile.get("exit") or tile.get("elevator") or tile.get("lantern"):
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if not (1 <= rr <= 3 and 1 <= cc <= 3):
                    continue
                other = get_mine_tile(self.state, 1, rr, cc, self.rules)
                if other.get("exit") or other.get("elevator") or other.get("lantern"):
                    continue
                target, neigh = (r, c), (rr, cc)
                break
            if target:
                break
        self.assertIsNotNone(target)
        tr, tc = target
        nr, nc = neigh
        # Clear other adjacent rocks so a later gold splash has only this neighbour.
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = tr + dr, tc + dc
            if not (1 <= rr <= 3 and 1 <= cc <= 3):
                continue
            other = get_mine_tile(self.state, 1, rr, cc, self.rules)
            if (rr, cc) == (nr, nc):
                continue
            if other.get("rock"):
                other["rock"] = None
        get_mine_tile(self.state, 1, tr, tc, self.rules).update({"rock": "stone", "ladder": None})
        get_mine_tile(self.state, 1, nr, nc, self.rules).update({"rock": "stone", "ladder": None})
        set_player_place(self.state, P1, AREA_MINE, tr, tc, floor=1)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "mine", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "stone", 2, self.rules), msg)
        self.assertTrue(get_mine_tile(self.state, 1, nr, nc, self.rules).get("rock"))
        self.assertEqual(self.state["players"][P1]["energy"], 95)

        set_tool_tier(self.state, TOOL_PICKAXE, "gold")
        get_mine_tile(self.state, 1, tr, tc, self.rules).update({"rock": "gold_ore", "ladder": None})
        get_mine_tile(self.state, 1, nr, nc, self.rules).update({"rock": "stone", "ladder": None})
        set_player_place(self.state, P1, AREA_MINE, tr, tc, floor=1)
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "mine", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(pack_has(self.state, P1, "gold_ore", 2, self.rules), msg)
        self.assertTrue(pack_has(self.state, P1, "stone", 4, self.rules), msg)
        self.assertFalse(get_mine_tile(self.state, 1, nr, nc, self.rules).get("rock"))
        self.assertIn("stone", msg.lower())
        self.assertEqual(self.state["players"][P1]["energy"], 95)

    def test_web_mine_payload_uses_shaft_on_floor_one_and_ladder_up_deeper(self):
        import web
        from hills import set_player_place, AREA_MINE
        from mine import arrival_tile, get_mine_tile, ensure_mine

        self._enter()
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertEqual(payload.get("view_floor"), 1)
        r, c = arrival_tile(self.state, 1, self.rules)
        self.assertTrue(get_mine_tile(self.state, 1, r, c, self.rules).get("exit"))
        self.assertEqual(payload["sprites"][r - 1][c - 1], "mine_floor_shaft")

        ensure_mine(self.state, self.rules)
        set_player_place(self.state, P1, AREA_MINE, *arrival_tile(self.state, 2, self.rules), floor=2)
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertEqual(payload.get("view_floor"), 2)
        r, c = arrival_tile(self.state, 2, self.rules)
        self.assertEqual(payload["sprites"][r - 1][c - 1], "mine_floor_ladder_up")


class WebHudAndOverview(unittest.TestCase):
    def test_overview_sits_above_this_tile_and_status_has_icons(self):
        import web
        page = web.PAGE
        self.assertIn('<h2>Overview</h2>', page)
        self.assertIn('id="overview-desc"', page)
        self.assertLess(page.find('<h2>Overview</h2>'), page.find('<h2>This tile</h2>'))
        self.assertIn("overview-desc", page)
        self.assertIn("overflow-wrap: anywhere", page)
        self.assertIn("function energyIcon", page)
        self.assertIn("function hpIcon", page)
        self.assertIn("function forecastIcon", page)
        self.assertIn("title='Energy'", page)
        self.assertIn("title='HP'", page)
        self.assertIn("aria-label='Energy", page)
        self.assertIn("aria-label='HP", page)
        self.assertIn("Weather:", page)
        self.assertNotIn("escapeHtml(placeBits)", page)
        # Location line is written to the overview, not the header.
        render = page[page.find("function render(data)"): page.find("function energyIcon") if False else page.find("$(\"status\").innerHTML")]
        # status assignment should not include placeBits
        status = page[page.find('$("status").innerHTML'): page.find('$("status").innerHTML') + 1200]
        self.assertNotIn("placeBits", status)
        self.assertIn('overview-desc', page)
        self.assertIn("overview.textContent = placeBits", page)




class ShopChestWebUi(unittest.TestCase):
    def _run_jsdom(self, payload, html):
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        runner = Path(__file__).resolve().parent / "tests" / "shop-ui.test.js"
        self.assertTrue(runner.is_file(), str(runner))
        with tempfile.TemporaryDirectory(prefix="lantern-shop-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            if not (jsdom_root / "node_modules" / "jsdom").exists():
                jsdom_root.mkdir(parents=True, exist_ok=True)
                inst = subprocess.run(
                    ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund", "jsdom@24"],
                    cwd=jsdom_root,
                    capture_output=True,
                    text=True,
                )
                if inst.returncode != 0:
                    self.skipTest("jsdom install failed: " + (inst.stderr or inst.stdout)[-400:])
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            proc = subprocess.run(
                [node, str(runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_item_catalog_exposes_forage_eat_energy(self):
        import web
        catalog = web._item_name_catalog(load_crops(), load_rules())
        self.assertEqual(catalog["wild_onion"].get("eat_energy"), 6)
        self.assertEqual(catalog["wild_berry"].get("eat_energy"), 8)
        self.assertNotIn("eat_energy", catalog["wild_mushroom"])
        self.assertEqual(catalog["stone"].get("sell_price"), 1)
        self.assertEqual(catalog["wood"].get("sell_price"), 4)
        self.assertEqual(catalog["copper_ore"].get("sell_price"), 8)
        self.assertEqual(catalog["sugar"].get("sell_price"), 2)

    def test_web_chest_lists_produce_and_eat_forage_not_under_backpack(self):
        import web
        from hills import set_player_place, AREA_FARM
        from inventory import add_to_chest, add_to_pack, TOOL_CAN, sync_inventory_view

        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        state["players"][P1]["energy"] = 50
        # Pack holds only a watering can; produce and forage live in the chest,
        # matching the live cabin-chest mix that the shop used to mislabel.
        state["players"][P1]["pack"] = [None, None, None, None]
        add_to_pack(state, P1, TOOL_CAN, 1, rules)
        for item, n in (("spinach", 1), ("turnip", 1), ("wild_onion", 6), ("wood", 8)):
            add_to_chest(state, item, n, rules)
        sync_inventory_view(state, rules)
        self.assertTrue(is_player_in_cabin(state, P1))
        actions = legal_actions(state, crops, P1, rules)
        self.assertIn("take spinach 1", actions)
        self.assertIn("take turnip 1", actions)
        self.assertIn("take wild_onion 1", actions)
        self.assertIn("eat wild_onion chest", actions)
        self.assertIn("eat spinach chest", actions)

        payload = web.api_payload(state, crops, player=P1)
        self.assertTrue(payload["in_cabin"])
        self.assertTrue(payload["your_turn"])
        chest_items = [s.get("item") for s in (payload.get("chest") or []) if s]
        self.assertIn("spinach", chest_items)
        self.assertIn("turnip", chest_items)
        self.assertIn("wild_onion", chest_items)
        pack_items = [s.get("item") for s in (payload.get("pack") or []) if s]
        self.assertEqual(pack_items, [TOOL_CAN])
        self.assertEqual((payload.get("item_names") or {}).get("wild_onion", {}).get("eat_energy"), 6)

        html = web.render_page(viewer=P1)
        data = self._run_jsdom(payload, html)
        self.assertTrue(data["invChestPresent"])
        self.assertRegex(data["invChestText"].lower(), r"spinach")
        self.assertRegex(data["invChestText"].lower(), r"turnip")
        self.assertRegex(data["invChestText"].lower(), r"wild onion")
        self.assertTrue(any(t.lower().startswith("take") for t in data["invChestButtons"]))
        self.assertTrue(any(t.lower().startswith("eat") for t in data["invChestButtons"]))
        self.assertRegex(data["invPackText"].lower(), r"watering can")
        self.assertNotRegex(data["invPackText"].lower(), r"spinach|turnip|wild onion")
        # Combined inventory totals must not be sold as "from the backpack".
        self.assertFalse(
            data["shopBackpackPresent"],
            "chest produce was listed under From the backpack: " + (data.get("shopBackpackText") or ""),
        )
        self.assertFalse(data["shopChestPresent"], "cabin chest should not appear in the shop panel")
        self.assertFalse(data.get("shopBackpackDropPresent"), "backpack drop should not appear in the shop panel")
        self.assertFalse(data.get("shopKitchenPresent"), "kitchen should not appear in the shop panel")
        self.assertTrue(any(t.lower().startswith("eat") for t in data.get("eatButtons") or []))
        self.assertTrue(
            any("sell" in t.lower() and "4" in t for t in data["invChestButtons"]),
            "wood in the chest should still be sellable from the cabin chest panel: "
            + repr(data.get("invChestButtons")),
        )


    def test_side_panel_hides_the_chest_when_not_in_the_cabin(self):
        import web
        from hills import set_player_place, AREA_HILLS

        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        set_player_place(state, P1, AREA_HILLS, 3, 3)
        payload = web.api_payload(state, crops, player=P1)
        self.assertFalse(payload["in_cabin"])
        html = web.render_page(viewer=P1)
        data = self._run_jsdom(payload, html)
        self.assertFalse(data["invChestPresent"])
        self.assertFalse(data.get("chestTogglePresent"))
        self.assertNotRegex(data.get("invText") or "", r"Cabin chest")

    def test_side_panel_chest_is_collapsible_and_remembers_its_state(self):
        import web
        from hills import set_player_place, AREA_FARM
        from inventory import add_to_chest, sync_inventory_view

        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        add_to_chest(state, "spinach", 1, rules)
        sync_inventory_view(state, rules)
        payload = web.api_payload(state, crops, player=P1)
        self.assertTrue(payload["in_cabin"])
        html = web.render_page(viewer=P1)
        data = self._run_jsdom(payload, html)
        self.assertTrue(data["invChestPresent"])
        self.assertTrue(data.get("chestTogglePresent"))
        self.assertTrue(data.get("chestOpen"))
        self.assertTrue(data.get("chestHiddenAfterClick"))
        self.assertFalse(data.get("chestOpenAfterClick"))
        self.assertEqual(data.get("chestStorageAfterClick"), "0")
        self.assertEqual((data.get("invChestHeading") or "").strip(), "CABIN CHEST")
        self.assertIn("recipe-book-head", data.get("invChestHeadingClass") or "")
        css = html
        self.assertIn("font-family: \"Iowan Old Style\", Palatino", css)
        # The chest button must not inherit typography from the inventory panel.
        self.assertNotRegex(
            css,
            r"button\.recipe-book-head\.chest-toggle\s*\{[^}]*font:\s*inherit",
        )
        self.assertRegex(
            css,
            r"button\.recipe-book-head\.chest-toggle\s*\{[^}]*text-transform:\s*uppercase",
        )
        self.assertRegex(
            css,
            r"button\.recipe-book-head\.chest-toggle\s*\{[^}]*letter-spacing:\s*0\.06em",
        )
        self.assertRegex(
            css,
            r"\.recipe-book-head\s*\{[^}]*text-transform:\s*uppercase",
        )


    def test_web_hud_shows_bonus_energy_over_the_base_max(self):
        import web
        from hills import set_player_place, AREA_FARM

        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        state["players"][P1]["energy"] = 110
        state["players"][P1]["energy_max"] = 110
        payload = web.api_payload(state, crops, player=P1)
        self.assertEqual(payload["base_energy"], 100)
        self.assertEqual(payload["max_energy"], 110)
        html = web.render_page(viewer=P1)
        data = self._run_jsdom(payload, html)
        self.assertRegex(data.get("energyHud") or "", r"110/100")
        self.assertIn("over-max", data.get("energyHudClass") or "")
        self.assertRegex(data.get("energyHudLabel") or "", r"110 of 100")

        state["players"][P1]["energy"] = 100
        state["players"][P1]["energy_max"] = 100
        payload = web.api_payload(state, crops, player=P1)
        self.assertEqual(payload["base_energy"], 100)
        data = self._run_jsdom(payload, html)
        self.assertRegex(data.get("energyHud") or "", r"100/100")
        self.assertNotIn("over-max", data.get("energyHudClass") or "")

    def test_shop_panel_is_buy_only_and_recipe_book_still_crafts(self):
        import web
        from hills import set_player_place, AREA_FARM

        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        payload = web.api_payload(state, crops, player=P1)
        book = list(payload.get("recipe_book") or [])
        book.append({
            "id": "strawberry_jam",
            "name": "strawberry jam",
            "craftable": True,
            "ingredients_text": "3 berries, 1 sugar",
        })
        payload["recipe_book"] = book
        html = web.render_page(viewer=P1)
        data = self._run_jsdom(payload, html)
        self.assertFalse(data.get("shopChestPresent"))
        self.assertFalse(data.get("shopBackpackPresent"))
        self.assertFalse(data.get("shopBackpackDropPresent"))
        self.assertFalse(data.get("shopKitchenPresent"))
        self.assertRegex((data.get("shopText") or "").lower(), r"sugar")
        self.assertTrue(
            any((t or "").strip().lower() == "craft" for t in (data.get("recipeCraftButtons") or [])),
            "recipe book should still offer Craft: " + repr(data.get("recipeCraftButtons")),
        )

    def test_shop_cards_show_growing_seasons_and_days_left_in_late_summer(self):
        import web
        from hills import set_player_place, AREA_FARM
        from engine import crop_viable_days_left, crop_info

        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        state["day"] = 30
        state["season"] = "summer"
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        payload = web.api_payload(state, crops, player=P1)
        carrot = payload["crops"]["carrot"]
        self.assertTrue(carrot["for_sale"])
        self.assertIn("summer", carrot["seasons"])
        self.assertIn("autumn", carrot["seasons"])
        self.assertIn("winter", carrot["seasons"])
        self.assertNotEqual(list(carrot["seasons"]), ["spring"])
        left = crop_viable_days_left(crop_info(crops, "carrot"), "summer", day=30, crops=crops)
        self.assertEqual(carrot["viable_days_left"], left)
        self.assertGreaterEqual(left, 12)

        html = web.render_page(viewer=P1)
        data = self._run_jsdom(payload, html)
        names = data.get("shopCardNames") or []
        metas = data.get("shopMetas") or []
        titles = data.get("shopTitles") or []
        self.assertTrue(names, "shop should list seeds on summer day 30")
        # Pair each In-season crop card with its meta line.
        by_name = {}
        for name, meta, title in zip(names, metas, titles):
            by_name[name] = (meta, title)
        # Carrot must not look like a spring-only seed.
        carrot_meta = None
        for name, (meta, title) in by_name.items():
            if "carrot" in name.lower():
                carrot_meta = meta
                self.assertRegex(meta, r"grows spring, summer, autumn, winter")
                self.assertRegex(meta, r"12 days")
                self.assertRegex(meta, rf"{left} days left to finish")
                self.assertEqual(title, meta)
                self.assertFalse(meta.strip().lower().startswith("spring ·"))
                break
        self.assertIsNotNone(carrot_meta, "carrot seed card missing: " + repr(names))
        lettuce_hit = False
        for name, (meta, _title) in by_name.items():
            if "lettuce" in name.lower():
                lettuce_hit = True
                self.assertRegex(meta, r"grows spring, summer, autumn")
                self.assertNotRegex(meta, r"^spring ·")
                break
        self.assertTrue(lettuce_hit, "lettuce seed card missing: " + repr(names))
        for name, (meta, _title) in by_name.items():
            if "everbearing" in name.lower():
                self.assertIn("sold in spring, summer", meta)
        # No seed card should be labeled only "spring" when it also grows later.
        for name, (meta, _title) in by_name.items():
            if "crown" in name.lower() or "rhubarb" in name.lower() or "asparagus" in name.lower():
                continue
            self.assertNotRegex(
                meta.strip(),
                r"^spring ·",
                f"{name} still looks spring-only: {meta}",
            )


class CabinChestOrder(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)

    def test_reorder_chest_persists_in_the_save_and_new_items_append(self):
        from inventory import add_to_chest, chest_of, sync_inventory_view
        add_to_chest(self.state, "wood", 1, self.rules)
        add_to_chest(self.state, "spinach", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        before = [s["item"] for s in chest_of(self.state, self.rules) if s]
        self.assertIn("wood", before)
        self.assertIn("spinach", before)
        # Put spinach first; leftover stacks stay after.
        ok, msg = do_action(
            self.state, self.crops,
            "reorder chest spinach wood",
            player=P1, rules=self.rules,
        )
        self.assertTrue(ok, msg)
        items = [s["item"] for s in chest_of(self.state, self.rules) if s]
        self.assertTrue(items.index("spinach") < items.index("wood"), items)
        # A newly added item lands at the end.
        add_to_chest(self.state, "turnip", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        items = [s["item"] for s in chest_of(self.state, self.rules) if s]
        self.assertEqual(items[-1], "turnip")

    def test_reorder_chest_is_refused_away_from_the_cabin(self):
        from hills import set_player_place, AREA_HILLS
        from inventory import add_to_chest, sync_inventory_view
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        set_player_place(self.state, P1, AREA_HILLS, 3, 3)
        ok, msg = do_action(
            self.state, self.crops,
            "reorder chest wood",
            player=P1, rules=self.rules,
        )
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())



class FarmPlotActionsArea(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)

    def _farm_strawberry_at(self, row, col):
        tile = engine.get_tile(self.state, row, col)
        tile["type"] = "soil"
        tile["tilled"] = True
        tile["crop"] = {
            "kind": "strawberry",
            "stage": "sprouting",
            "days_grown": 1,
            "planted_day": 1,
            "growth": 20,
            "health": 100,
        }

    def test_farm_plot_actions_refuse_in_the_hills_and_do_not_touch_the_farm_tile(self):
        from hills import set_player_place, AREA_HILLS, AREA_FARM, HILLS_GATE
        from hills import get_hills_tile
        self._farm_strawberry_at(*HILLS_GATE)
        crop = copy.deepcopy(engine.get_tile(self.state, *HILLS_GATE)["crop"])
        hills_tile = get_hills_tile(self.state, *HILLS_GATE)
        hills_tile["tree"] = None
        hills_tile["forage"] = None
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["current_player"] = P1
        self.state["players"][P1]["energy"] = 100
        commands = [
            "harvest",
            "harvest 3 3",
            "water",
            "till",
            "plant spinach",
            "pluck",
            "unearth",
            "fertilize",
        ]
        for cmd in commands:
            ok, msg = do_action(self.state, self.crops, cmd, player=P1, rules=self.rules)
            self.assertFalse(ok, cmd)
            self.assertIn("hills", msg.lower(), cmd)
            self.assertIn("nothing to", msg.lower(), cmd)
            self.assertNotIn("filling out", msg.lower(), cmd)
            self.assertNotIn("strawberry", msg.lower(), cmd)
        self.assertEqual(engine.get_tile(self.state, *HILLS_GATE)["crop"], crop)
        set_player_place(self.state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)

    def test_farm_plot_actions_refuse_in_the_mine(self):
        from hills import set_player_place, AREA_MINE
        set_player_place(self.state, P1, AREA_MINE, 2, 2, floor=1)
        self.state["current_player"] = P1
        self.state["players"][P1]["energy"] = 100
        ok, msg = do_action(self.state, self.crops, "harvest", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("mine", msg.lower())
        self.assertIn("nothing to harvest", msg.lower())
        self.assertNotIn("filling out", msg.lower())

    def test_eat_half_loaf_is_a_snack_and_marks_ate_today(self):
        from inventory import add_to_pack, pack_has, item_eat_energy
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["current_player"] = P1
        self.state["players"][P1]["energy"] = 50
        add_to_pack(self.state, P1, "bread_half", 1, self.rules)
        self.assertEqual(item_eat_energy("bread_half", self.crops, self.rules), 5)
        self.assertIn("eat bread_half", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "eat half loaf", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("5", msg)
        self.assertEqual(self.state["players"][P1]["energy"], 55)
        self.assertEqual(self.state["players"][P1]["snacks_eaten"], 1)
        self.assertTrue(self.state["players"][P1].get("ate_today"))
        self.assertFalse(pack_has(self.state, P1, "bread_half", 1, self.rules))


class HillsHotkeysWeb(unittest.TestCase):
    def _run(self, payload, html):
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        runner = Path(__file__).resolve().parent / "tests" / "hills-hotkeys.test.js"
        self.assertTrue(runner.is_file(), str(runner))
        with tempfile.TemporaryDirectory(prefix="lantern-hotkeys-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            if not (jsdom_root / "node_modules" / "jsdom").exists():
                jsdom_root.mkdir(parents=True, exist_ok=True)
                inst = subprocess.run(
                    ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund", "jsdom@24"],
                    cwd=jsdom_root,
                    capture_output=True,
                    text=True,
                )
                if inst.returncode != 0:
                    self.skipTest("jsdom install failed: " + (inst.stderr or inst.stdout)[-400:])
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            proc = subprocess.run(
                [node, str(runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_h_forages_in_the_hills_and_farm_keys_are_hidden(self):
        import web
        from hills import set_player_place, AREA_HILLS, HILLS_GATE, get_hills_tile
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        state["players"][P1]["energy"] = 80
        set_player_place(state, P1, AREA_HILLS, *HILLS_GATE)
        tile = get_hills_tile(state, *HILLS_GATE)
        tile["forage"] = {"kind": "wild_onion"}
        tile["tree"] = None
        payload = web.api_payload(state, crops, player=P1)
        html = web.render_page(viewer=P1)
        data = self._run(payload, html)
        keys = data["keysText"].lower()
        self.assertIn("forage", keys)
        self.assertIn("chop", keys)
        self.assertRegex(keys, r"h or g forage")
        self.assertNotRegex(keys, r"\btill\b")
        self.assertNotRegex(keys, r"\bwater\b")
        self.assertNotRegex(keys, r"\bplant\b")
        self.assertRegex(keys, r"\bu\b unearth")
        self.assertNotRegex(keys, r"\bfertilize\b")
        self.assertNotRegex(keys, r"\bharvest\b")
        self.assertIn("forage", data["commands"])
        self.assertNotIn("harvest", data["commands"])
        self.assertNotIn("till", data["commands"])
        self.assertIn("chop", data["commands"])

    def test_web_u_unearths_a_hills_stump(self):
        import web
        from hills import set_player_place, AREA_HILLS, make_tree, get_hills_tile
        from inventory import add_to_pack, TOOL_SHOVEL
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        state["players"][P1]["energy"] = 80
        add_to_pack(state, P1, TOOL_SHOVEL, 1, rules)
        set_player_place(state, P1, AREA_HILLS, 3, 2)
        tile = get_hills_tile(state, 3, 2)
        tile["tree"] = make_tree("stump", planted_day=1, days_grown=0)
        tile["forage"] = None
        payload = web.api_payload(state, crops, player=P1)
        html = web.render_page(viewer=P1)
        runner = Path(__file__).resolve().parent / "tests" / "hills-unearth.test.js"
        self.assertTrue(runner.is_file(), str(runner))
        import shutil, subprocess, tempfile, os
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory(prefix="lantern-unearth-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            proc = subprocess.run(
                [node, str(runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp, capture_output=True, text=True, env=env, timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        keys = (data.get("keysText") or "").lower()
        self.assertRegex(keys, r"\bu\b unearth")
        self.assertTrue(any(str(c).startswith("unearth") for c in data.get("commands") or []), data)
        self.assertIn("20 energy", (data.get("toast") or "").lower())

    def test_web_shows_eat_for_a_half_loaf_in_the_pack(self):
        import web
        from hills import set_player_place, AREA_FARM
        from inventory import add_to_pack
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        state["players"][P1]["energy"] = 50
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        state["players"][P1]["pack"] = [None, None, None, None]
        add_to_pack(state, P1, "bread_half", 1, rules)
        payload = web.api_payload(state, crops, player=P1)
        self.assertEqual((payload.get("item_names") or {}).get("bread_half", {}).get("eat_energy"), 5)
        self.assertIn("eat bread_half", legal_actions(state, crops, P1, rules))
        html = web.render_page(viewer=P1)
        # Reuse the shop UI runner, which inspects Eat buttons on item cards.
        shop_runner = Path(__file__).resolve().parent / "tests" / "shop-ui.test.js"
        self.assertTrue(shop_runner.is_file())
        import shutil, subprocess, tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory(prefix="lantern-half-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            proc = subprocess.run(
                [node, str(shop_runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp, capture_output=True, text=True, env=env, timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertRegex((data.get("invPackText") or "").lower(), r"half loaf")
        self.assertTrue(any("eat" in t.lower() and "5" in t for t in data.get("invChestButtons") and [] or data.get("eatButtons") or []))
        eats = [t for t in (data.get("eatButtons") or []) if "eat" in t.lower()]
        self.assertTrue(eats, data)




class MineActionsWeb(unittest.TestCase):
    def _run(self, payload, html, mode="entrance"):
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        runner = Path(__file__).resolve().parent / "tests" / "mine-ui.test.js"
        self.assertTrue(runner.is_file(), str(runner))
        with tempfile.TemporaryDirectory(prefix="lantern-mine-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            if not (jsdom_root / "node_modules" / "jsdom").exists():
                jsdom_root.mkdir(parents=True, exist_ok=True)
                inst = subprocess.run(
                    ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund", "jsdom@24"],
                    cwd=jsdom_root,
                    capture_output=True,
                    text=True,
                )
                if inst.returncode != 0:
                    self.skipTest("jsdom install failed: " + (inst.stderr or inst.stdout)[-400:])
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            env["MINE_UI_MODE"] = mode
            proc = subprocess.run(
                [node, str(runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            return json.loads(proc.stdout.strip().splitlines()[-1])

    def _entrance_state(self, energy=80, your_turn=True):
        import web
        from hills import set_player_place, AREA_HILLS, MINE_ENTRANCE
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["mine_entrance_found"] = True
        give_item(state, "pickaxe", 1, player=P1, where="pack")
        set_player_place(state, P1, AREA_HILLS, *MINE_ENTRANCE)
        state["players"][P1]["energy"] = energy
        if your_turn:
            state["current_player"] = P1
        else:
            state["current_player"] = P2
        return state, crops, rules, web

    def test_web_shows_enter_mine_and_debug_console_stays_legal(self):
        state, crops, rules, web = self._entrance_state()
        legal = legal_actions(state, crops, P1, rules)
        self.assertIn("enter mine", legal)
        payload = web.api_payload(state, crops, player=P1)
        self.assertIn("enter mine", payload.get("actions") or [])
        html = web.render_page(viewer=P1)
        self.assertIn("debug-cmd", html)
        data = self._run(payload, html, mode="entrance")
        joined = " ".join(data["tileButtons"]).lower()
        self.assertRegex(joined, r"enter mine")
        self.assertIn("E", " ".join(data["tileButtons"]))
        self.assertRegex(data["keysText"], r"enter mine")
        self.assertTrue(data["hasDebug"])
        self.assertTrue(data["debugOptionsIncludeEnter"])
        self.assertTrue(data["clickedEnter"])
        self.assertIn("enter mine", data["commandsAfterClick"])
        self.assertIn("legal action", data["rejectedStatus"].lower())
        self.assertEqual(data["commandsAfterReject"], data["commandsAfterClick"])
        self.assertIn("enter mine", data["commandsAfterDebug"])
        self.assertGreater(data["commandsAfterDebug"].count("enter mine"), data["commandsAfterClick"].count("enter mine"))
        self.assertEqual(data["debugInputAfterSend"], "")
        self.assertIn("enter mine", data["commandsAfterE"])

    def test_debug_console_does_not_send_on_the_other_players_turn(self):
        state, crops, rules, web = self._entrance_state(your_turn=False)
        payload = web.api_payload(state, crops, player=P1)
        self.assertFalse(payload.get("your_turn"))
        html = web.render_page(viewer=P1)
        data = self._run(payload, html, mode="noturn")
        self.assertTrue(data["debugDisabled"])
        self.assertIn("turn", data["noturnStatus"].lower())
        self.assertEqual(data["commandsAfterNoturn"], [])

    def test_web_shows_in_mine_actions(self):
        import web
        from hills import set_player_place, AREA_MINE
        from engine import player_where
        from mine import get_mine_tile, player_floor, ensure_mine
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        give_item(state, "pickaxe", 1, player=P1, where="pack")
        state["mine_entrance_found"] = True
        state["mine_entrance_open"] = True
        set_player_place(state, P1, AREA_MINE, 2, 2, floor=1)
        state["players"][P1]["energy"] = 80
        ensure_mine(state, rules)
        r, c = player_where(state, P1)
        floor = player_floor(state, P1)
        tile = get_mine_tile(state, floor, r, c, rules)
        tile["rock"] = "copper_ore"
        tile["ladder"] = "open"
        tile["exit"] = True
        tile["lantern"] = True
        tile["elevator"] = True
        legal = legal_actions(state, crops, P1, rules)
        for act in ("mine", "climb down", "climb up", "leave mine", "rest", "elevator", "elevator entrance"):
            self.assertIn(act, legal, act)
        payload = web.api_payload(state, crops, player=P1)
        html = web.render_page(viewer=P1)
        data = self._run(payload, html, mode="inside")
        joined = " ".join(data["tileButtons"]).lower()
        self.assertIn("mine", joined)
        self.assertIn("climb down", joined)
        self.assertIn("climb up", joined)
        self.assertIn("leave mine", joined)
        self.assertIn("rest", joined)
        self.assertIn("elevator", joined)
        self.assertRegex(data["keysText"], r"\bM\b")
        self.assertRegex(data["keysText"], r"\bR\b")



class EatButtonsWeb(unittest.TestCase):
    """Web eat buttons must use the engine edible list, not crops.json alone."""

    def _run(self, payload, html):
        import shutil
        import subprocess
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        runner = Path(__file__).resolve().parent / "tests" / "eat-buttons.test.js"
        self.assertTrue(runner.is_file(), str(runner))
        with tempfile.TemporaryDirectory(prefix="lantern-eat-jsdom-") as tmp:
            tmp = Path(tmp)
            (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
            (tmp / "page.html").write_text(html, encoding="utf-8")
            jsdom_root = Path(tempfile.gettempdir()) / "lantern-farm-jsdom"
            if not (jsdom_root / "node_modules" / "jsdom").exists():
                jsdom_root.mkdir(parents=True, exist_ok=True)
                inst = subprocess.run(
                    ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund", "jsdom@24"],
                    cwd=jsdom_root,
                    capture_output=True,
                    text=True,
                )
                if inst.returncode != 0:
                    self.skipTest("jsdom install failed: " + (inst.stderr or inst.stdout)[-400:])
            env = dict(os.environ)
            env["NODE_PATH"] = str(jsdom_root / "node_modules")
            proc = subprocess.run(
                [node, str(runner), str(tmp / "payload.json"), str(tmp / "page.html")],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
            return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_catalog_includes_non_crop_eat_energy(self):
        import web
        catalog = web._item_name_catalog(load_crops(), load_rules())
        self.assertEqual(catalog["bread_half"].get("eat_energy"), 5)
        self.assertEqual(catalog["wild_onion"].get("eat_energy"), 6)
        self.assertEqual(catalog["wild_berry"].get("eat_energy"), 8)
        self.assertNotIn("eat_energy", catalog["wild_mushroom"])
        self.assertIn("named.eat_energy", web.PAGE)

    def test_web_eat_buttons_show_for_half_loaf_and_wild_onion_at_partial_energy(self):
        import web
        from hills import set_player_place, AREA_FARM
        from inventory import add_to_pack, add_to_chest
        crops = load_crops()
        rules = load_rules()
        state = fresh_state(crops, weather_seed=1, rules=rules)
        state["current_player"] = P1
        # Below full, matching the live report (eat works in the CLI at 85/100).
        state["players"][P1]["energy"] = 85
        set_player_place(state, P1, AREA_FARM, CABIN_ROW, CABIN_COL)
        state["players"][P1]["pack"] = [None, None, None, None]
        add_to_pack(state, P1, "bread_half", 1, rules)
        add_to_chest(state, "wild_onion", 2, rules)
        actions = legal_actions(state, crops, P1, rules)
        self.assertIn("eat bread_half", actions)
        self.assertIn("eat wild_onion chest", actions)
        payload = web.api_payload(state, crops, player=P1)
        self.assertEqual(payload["item_names"]["bread_half"].get("eat_energy"), 5)
        self.assertEqual(payload["item_names"]["wild_onion"].get("eat_energy"), 6)
        html = web.render_page(viewer=P1)
        data = self._run(payload, html)
        self.assertTrue(data["packHalf"]["present"], data.get("invText"))
        self.assertTrue(
            any(t.lower().startswith("eat") and "5" in t for t in data["packHalf"]["buttons"]),
            data["packHalf"],
        )
        self.assertFalse(
            data["shopOnion"]["present"],
            "wild onion should not be listed in the shop: " + (data.get("shopText") or ""),
        )
        self.assertTrue(data["chestOnion"]["present"], data.get("invText"))
        self.assertTrue(
            any(t.lower().startswith("eat") and "6" in t for t in data["chestOnion"]["buttons"]),
            data["chestOnion"],
        )




class CabinComfort(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        # Keep P2 at the threshold so existing fire/fed/tea cases stay isolated
        # from together rest (which needs more than 10 energy, or a carry).
        self.state["players"][P2]["energy"] = 10

    def _end_both(self):
        first = self.state["current_player"]
        second = P2 if first == P1 else P1
        ok, msg1 = do_action(self.state, self.crops, "end turn", player=first, rules=self.rules)
        self.assertTrue(ok, msg1)
        ok, msg2 = do_action(self.state, self.crops, "end turn", player=second, rules=self.rules)
        self.assertTrue(ok, msg2)
        return msg1, msg2

    def test_plain_cabin_sleep_is_still_100(self):
        from inventory import stack_count, chest_of
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 0)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 100 energy tomorrow")
        self.assertIn(
            "end turn (sleep in cabin, 100 energy tomorrow)",
            __import__("engine").format_legal_action("end turn", self.state, self.crops, P1, self.rules),
        )
        _msg1, msg2 = self._end_both()
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P1]["energy_max"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 100)
        self.assertNotIn("fire crackled", msg2)
        self.assertNotIn("full belly", msg2)
        self.assertIn("wakes with 100 energy", msg2)

    def test_wood_in_the_chest_does_not_auto_burn(self):
        from inventory import add_to_chest, stack_count, chest_of, sync_inventory_view
        add_to_chest(self.state, "wood", 3, self.rules)
        sync_inventory_view(self.state, self.rules)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 100 energy tomorrow")
        self.assertIn("fuel fireplace", legal_actions(self.state, self.crops, P1, self.rules))
        _msg1, msg2 = self._end_both()
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 3)
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 100)
        self.assertNotIn("fire crackled", msg2)
        self.assertFalse(self.state.get("fireplace_fueled"))

    def _fuel(self, player=None):
        player = player or P1
        self.state["current_player"] = player
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=player, rules=self.rules)
        self.assertTrue(ok, msg)
        return msg

    def test_fuel_fireplace_spends_wood_and_energy_and_raises_outlook(self):
        from inventory import add_to_chest, stack_count, chest_of, sync_inventory_view
        from engine import format_legal_action, energy_cost
        add_to_chest(self.state, "wood", 2, self.rules)
        sync_inventory_view(self.state, self.rules)
        self.state["players"][P1]["energy"] = 100
        line = format_legal_action("fuel fireplace", self.state, self.crops, P1, self.rules)
        self.assertIn("5 energy", line)
        self.assertIn("1 wood", line)
        msg = self._fuel(P1)
        self.assertIn("fireplace", msg.lower())
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 1)
        self.assertEqual(self.state["players"][P1]["energy"], 100 - energy_cost("fuel_fireplace", self.rules))
        self.assertTrue(self.state.get("fireplace_fueled"))
        self.assertTrue(self.state["tiles"][CABIN_ROW - 1][CABIN_COL - 1].get("fire"))
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 110 energy tomorrow")
        self.assertEqual(sleep_outlook(self.state, P2, self.rules), "You'll sleep in the cabin — 110 energy tomorrow")
        self.assertNotIn("fuel fireplace", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("already", msg.lower())
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 1)

    def test_fuel_uses_pack_wood_before_chest(self):
        from inventory import add_to_chest, add_to_pack, stack_count, chest_of, pack_of, sync_inventory_view
        add_to_chest(self.state, "wood", 2, self.rules)
        add_to_pack(self.state, P1, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        self.assertEqual(stack_count(pack_of(self.state, P1, self.rules), "wood"), 0)
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 2)

    def test_fuel_requires_cabin_energy_and_wood(self):
        from inventory import add_to_chest, sync_inventory_view
        from hills import set_player_place, AREA_FARM
        # No wood.
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("wood", msg.lower())
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        # Exhausted.
        self.state["players"][P1]["energy"] = 3
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("energy", msg.lower())
        self.assertIn("5", msg)
        self.assertFalse(self.state.get("fireplace_fueled"))
        # Not in the cabin.
        self.state["players"][P1]["energy"] = 20
        set_player_place(self.state, P1, AREA_FARM, 3, 1)
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("cabin", msg.lower())

    def test_fueled_fire_warms_everyone_who_sleeps_in_the_cabin(self):
        from inventory import add_to_chest, stack_count, chest_of, sync_inventory_view
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        _msg1, msg2 = self._end_both()
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 0)
        self.assertEqual(self.state["players"][P1]["energy"], 110)
        self.assertEqual(self.state["players"][P1]["energy_max"], 110)
        self.assertEqual(self.state["players"][P2]["energy"], 110)
        self.assertIn("The fire crackled all night", msg2)
        self.assertIn("wakes with 110 energy", msg2)
        self.assertNotIn("+10", msg2)
        self.assertFalse(self.state.get("fireplace_fueled"))
        # Next day the fire has to be laid again. Both woke with 110, so
        # together rest still applies for tonight.
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 105 energy tomorrow, sleeping close tonight",
        )

    def test_one_small_snack_is_not_enough_for_a_full_belly(self):
        from inventory import add_to_pack, add_to_chest, sync_inventory_view
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 50
        add_to_pack(self.state, P1, "bread_half", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat half loaf", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(self.state["players"][P1].get("ate_today"))
        self.assertEqual(self.state["players"][P1].get("ate_energy_today"), 5)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 100 energy tomorrow")
        add_to_pack(self.state, P1, "bread_half", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat half loaf", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1].get("ate_energy_today"), 10)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 110 energy tomorrow")
        self.assertEqual(sleep_outlook(self.state, P2, self.rules), "You'll sleep in the cabin — 100 energy tomorrow")
        _msg1, msg2 = self._end_both()
        self.assertEqual(self.state["players"][P1]["energy"], 110)
        self.assertEqual(self.state["players"][P1]["energy_max"], 110)
        self.assertEqual(self.state["players"][P2]["energy"], 100)
        self.assertIn("a full belly", msg2)
        self.assertIn(f"{N1} slept in the cabin and wakes with 110 energy, a full belly", msg2)
        self.assertNotIn("fire crackled", msg2)
        self.assertFalse(self.state["players"][P1].get("ate_today"))
        self.assertFalse(self.state["players"][P1].get("ate_energy_today"))

    def test_one_hearty_snack_earns_the_fed_bonus(self):
        from inventory import add_to_pack
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 40
        add_to_pack(self.state, P1, "carrot", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1].get("ate_energy_today"), 10)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 110 energy tomorrow")

    def test_fire_and_food_together_reach_120(self):
        from inventory import add_to_chest, add_to_pack, stack_count, chest_of, sync_inventory_view
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        self.state["players"][P1]["energy"] = 40
        add_to_pack(self.state, P1, "carrot", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 120 energy tomorrow")
        _msg1, msg2 = self._end_both()
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 0)
        self.assertEqual(self.state["players"][P1]["energy"], 120)
        self.assertEqual(self.state["players"][P1]["energy_max"], 120)
        self.assertEqual(self.state["players"][P2]["energy"], 110)
        self.assertIn("The fire crackled all night, and a full belly helped", msg2)
        self.assertIn("wakes with 120 energy", msg2)
        self.assertIn("wakes with 110 energy", msg2)
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 110
        add_to_pack(self.state, P1, "bread_half", 1, self.rules)
        self.assertIn("eat bread_half", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "eat half loaf", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 115)
        self.assertIn("115/120", msg)

    def test_passing_out_skips_comfort_even_if_fed_and_the_fire_is_fueled(self):
        from inventory import add_to_chest, add_to_pack, stack_count, chest_of, sync_inventory_view
        from hills import set_player_place, AREA_FARM
        add_to_chest(self.state, "wood", 2, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        self.state["players"][P1]["energy"] = 40
        add_to_pack(self.state, P1, "carrot", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        set_player_place(self.state, P1, AREA_FARM, 3, 1)
        self.assertIn("pass out", sleep_outlook(self.state, P1, self.rules).lower())
        self.assertIn("50", sleep_outlook(self.state, P1, self.rules))
        # P2 is still in the cabin, so the laid fire warms them.
        _msg1, msg2 = self._end_both()
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertEqual(self.state["players"][P1].get("energy_max"), 100)
        self.assertEqual(self.state["players"][P2]["energy"], 110)
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 1)
        self.assertIn("passed out", msg2)
        self.assertNotIn(f"{N1} slept in the cabin", msg2)
        self.assertIn("The fire crackled all night", msg2)
        self.assertNotIn(f"{N1} slept in the cabin and wakes with 50 energy, a full belly", msg2)

    def test_no_cabin_sleeper_gets_no_fire_bonus_after_fueling(self):
        from inventory import add_to_chest, stack_count, chest_of, sync_inventory_view
        from hills import set_player_place, AREA_FARM, AREA_HILLS
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        set_player_place(self.state, P1, AREA_FARM, 3, 1)
        set_player_place(self.state, P2, AREA_HILLS, 3, 3)
        _msg1, msg2 = self._end_both()
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "wood"), 0)
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertEqual(self.state["players"][P2]["energy"], 50)
        self.assertNotIn("fire crackled", msg2)
        self.assertIn("passed out", msg2)
        self.assertFalse(self.state.get("fireplace_fueled"))

    def test_cabin_narration_and_sprite_show_the_fire(self):
        from inventory import add_to_chest, sync_inventory_view
        from sprites import sprite_key
        from describe import describe_tile
        import web
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        tile = self.state["tiles"][CABIN_ROW - 1][CABIN_COL - 1]
        self.assertTrue(tile.get("fire"))
        key = sprite_key(tile, self.state.get("weather"), CABIN_ROW, CABIN_COL)
        self.assertTrue(key.endswith("_fire") or key == "cabin_fire", key)
        self.assertEqual(sprite_key(tile, "rain", CABIN_ROW, CABIN_COL), "cabin_rain_fire")
        self.assertEqual(sprite_key(tile, "snow", CABIN_ROW, CABIN_COL), "cabin_snow_fire")
        self.assertEqual(sprite_key(tile, "storm", CABIN_ROW, CABIN_COL), "cabin_storm_fire")
        self.assertEqual(sprite_key(tile, "cloud", CABIN_ROW, CABIN_COL), "cabin_cloud_fire")
        from packs import layers_for_key, load_manifest
        man = load_manifest("storybook")
        rain_layers = layers_for_key("cabin_rain_fire", man)
        self.assertTrue(rain_layers[0]["file"].endswith("cabin_rain.png"))
        self.assertTrue(any(layer["file"].endswith("cabin_smoke.png") for layer in rain_layers))
        text = describe_tile(self.state, self.crops, CABIN_ROW, CABIN_COL)
        self.assertIn("fire is laid", text.lower())
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertTrue(payload.get("fireplace_fueled"))
        self.assertEqual(payload.get("fuel_fireplace_energy"), 5)

    def test_herbal_tea_banks_10_energy_and_stacks_to_130(self):
        from inventory import add_to_pack, add_to_chest, pack_has, stack_count, chest_of, sync_inventory_view
        add_to_pack(self.state, P1, "herbal_tea", 2, self.rules)
        self.assertIn("drink herbal_tea", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "drink herbal tea", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(self.state["players"][P1].get("herbal_tea"))
        self.assertTrue(pack_has(self.state, P1, "herbal_tea", 1, self.rules))
        self.assertFalse(pack_has(self.state, P1, "herbal_tea", 2, self.rules))
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 110 energy tomorrow")
        self.assertEqual(sleep_outlook(self.state, P2, self.rules), "You'll sleep in the cabin — 100 energy tomorrow")
        ok, msg = do_action(self.state, self.crops, "drink herbal tea", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("already", msg.lower())
        self.assertTrue(pack_has(self.state, P1, "herbal_tea", 1, self.rules))
        ok, msg = do_action(self.state, self.crops, "eat herbal tea", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("drink", msg.lower())
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self._fuel(P1)
        self.state["players"][P1]["energy"] = 40
        add_to_pack(self.state, P1, "carrot", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "eat carrot", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 130 energy tomorrow")
        self.assertIn(
            "end turn (sleep in cabin, 130 energy tomorrow)",
            __import__("engine").format_legal_action("end turn", self.state, self.crops, P1, self.rules),
        )
        _msg1, msg2 = self._end_both()
        self.assertEqual(self.state["players"][P1]["energy"], 130)
        self.assertEqual(self.state["players"][P1]["energy_max"], 130)
        self.assertEqual(self.state["players"][P2]["energy"], 110)
        self.assertIn("wakes with 130 energy", msg2)
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        self.assertFalse(self.state["players"][P1].get("herbal_tea"))
        self.assertIn("drink herbal_tea", legal_actions(self.state, self.crops, P1, self.rules))

    def test_herbal_tea_does_not_help_if_you_pass_out(self):
        from inventory import add_to_pack
        from hills import set_player_place, AREA_FARM
        add_to_pack(self.state, P1, "herbal_tea", 1, self.rules)
        ok, msg = do_action(self.state, self.crops, "drink herbal tea", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        set_player_place(self.state, P1, AREA_FARM, 3, 1)
        self.assertIn("pass out", sleep_outlook(self.state, P1, self.rules).lower())
        self.assertIn("50", sleep_outlook(self.state, P1, self.rules))
        self.assertNotIn("110", sleep_outlook(self.state, P1, self.rules))
        _msg1, msg2 = self._end_both()
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertEqual(self.state["players"][P1].get("energy_max"), 100)

    def test_herbal_tea_from_the_chest_at_the_cabin(self):
        from inventory import add_to_chest, pack_has, stack_count, chest_of, sync_inventory_view
        add_to_chest(self.state, "herbal_tea", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        self.assertIn("drink herbal_tea chest", legal_actions(self.state, self.crops, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "drink herbal tea chest", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(stack_count(chest_of(self.state, self.rules), "herbal_tea"), 0)
        self.assertFalse(pack_has(self.state, P1, "herbal_tea", 1, self.rules))
        self.assertEqual(sleep_outlook(self.state, P1, self.rules), "You'll sleep in the cabin — 110 energy tomorrow")


class SeedShopWindow(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)

    def test_turnip_closes_mid_spring_and_reopens_in_autumn(self):
        from engine import crop_for_sale, crop_info, shop_kinds
        info = crop_info(self.crops, "turnip")
        self.assertTrue(crop_for_sale(info, "spring", day=7, crops=self.crops))
        self.assertFalse(crop_for_sale(info, "spring", day=8, crops=self.crops))
        self.assertTrue(crop_for_sale(info, "autumn", day=31, crops=self.crops))
        self.assertFalse(crop_for_sale(info, "autumn", day=38, crops=self.crops))
        self.assertNotIn("turnip", shop_kinds(self.crops, "summer"))

    def test_lettuce_stays_on_sale_through_late_spring(self):
        from engine import crop_for_sale, crop_info
        info = crop_info(self.crops, "lettuce")
        self.assertIn("summer", info["seasons"])
        self.assertTrue(crop_for_sale(info, "spring", day=15, crops=self.crops))

    def test_kabocha_and_pumpkin_and_corn_windows(self):
        from engine import crop_for_sale, crop_info
        kabocha = crop_info(self.crops, "kabocha")
        pumpkin = crop_info(self.crops, "pumpkin")
        corn = crop_info(self.crops, "corn")
        self.assertTrue(crop_for_sale(kabocha, "summer", day=16, crops=self.crops))
        self.assertFalse(crop_for_sale(kabocha, "summer", day=17, crops=self.crops))
        self.assertFalse(crop_for_sale(pumpkin, "summer", day=16, crops=self.crops))
        self.assertTrue(crop_for_sale(pumpkin, "spring", day=13, crops=self.crops))
        self.assertFalse(crop_for_sale(pumpkin, "spring", day=14, crops=self.crops))
        self.assertTrue(crop_for_sale(corn, "summer", day=16, crops=self.crops))
        self.assertTrue(crop_for_sale(corn, "summer", day=18, crops=self.crops))
        self.assertFalse(crop_for_sale(corn, "summer", day=19, crops=self.crops))

    def test_crowns_use_shop_seasons_and_carrot_sells_in_winter(self):
        from engine import crop_for_sale, crop_info, shop_kinds
        self.assertTrue(crop_for_sale(crop_info(self.crops, "rhubarb"), "spring", day=1, crops=self.crops))
        self.assertFalse(crop_for_sale(crop_info(self.crops, "rhubarb"), "summer", day=16, crops=self.crops))
        self.assertFalse(crop_for_sale(crop_info(self.crops, "asparagus"), "summer", day=16, crops=self.crops))
        self.assertIn("carrot", shop_kinds(self.crops, "winter"))
        self.assertTrue(crop_for_sale(crop_info(self.crops, "carrot"), "winter", day=46, crops=self.crops))

    def test_season_name_alone_is_day_one_and_mismatched_day_does_not_refuse(self):
        from engine import crop_for_sale, crop_info, shop_kinds, shop_day_in_season
        self.assertEqual(shop_kinds(self.crops, "summer"), shop_kinds(self.crops, "summer", day=16))
        self.assertEqual(shop_day_in_season("autumn", None, self.crops), 1)
        self.assertEqual(shop_day_in_season("autumn", 1, self.crops), 1)
        info = crop_info(self.crops, "turnip")
        self.assertTrue(crop_for_sale(info, "autumn", day=1, crops=self.crops))

    def test_web_payload_marks_for_sale_from_the_current_day(self):
        import web
        self.state["day"] = 17
        self.state["season"] = "summer"
        payload = web.api_payload(self.state, self.crops, player=P1)
        crops = payload["crops"]
        self.assertTrue(crops["strawberry"]["for_sale"])
        self.assertTrue(crops["carrot"]["for_sale"])
        self.assertFalse(crops["kabocha"]["for_sale"])
        self.assertFalse(crops["pumpkin"]["for_sale"])
        self.assertFalse(crops["turnip"]["for_sale"])
        self.assertFalse(crops["rhubarb"]["for_sale"])
        # Leftover spring-only shop_seasons on annuals must not be sent as the window.
        self.assertIn("summer", crops["carrot"]["seasons"])
        self.assertIn("summer", crops["carrot"]["shop_seasons"])
        self.assertFalse(crops["carrot"]["shop_uses_override"])
        self.assertEqual(crops["carrot"]["grow_days"], 12)
        self.assertGreaterEqual(crops["carrot"]["viable_days_left"], 12)
        self.assertTrue(crops["rhubarb"]["shop_uses_override"])
        self.assertEqual(crops["rhubarb"]["shop_seasons"], ["spring"])
        self.assertIn("summer", crops["rhubarb"]["seasons"])


class ForgedToolDisplay(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = no_weed_rules()
        self.state = fresh_state(self.crops, rules=self.rules)

    def test_forged_tools_use_tiered_names_and_payload_icons(self):
        from inventory import item_name, item_label, indefinite, add_to_pack, TOOL_PICKAXE, TOOL_HOE, TOOL_AXE, TOOL_CAN
        from mine import set_tool_tier
        import web
        from sprites import svg_for_item
        self.assertEqual(item_label(TOOL_PICKAXE, state=self.state), "pickaxe")
        self.assertEqual(indefinite(item_label(TOOL_AXE, state=self.state)), "an axe")
        set_tool_tier(self.state, TOOL_PICKAXE, "copper")
        set_tool_tier(self.state, TOOL_HOE, "iron")
        set_tool_tier(self.state, TOOL_AXE, "gold")
        set_tool_tier(self.state, TOOL_CAN, "copper")
        self.assertEqual(item_label(TOOL_PICKAXE, state=self.state), "copper pickaxe")
        self.assertEqual(item_name(TOOL_HOE, 1, state=self.state), "1 iron hoe")
        self.assertEqual(item_label(TOOL_CAN, state=self.state), "copper watering can")
        self.assertEqual(indefinite(item_label(TOOL_AXE, state=self.state)), "a gold axe")
        self.assertEqual(indefinite(item_label(TOOL_HOE, state=self.state)), "an iron hoe")
        add_to_pack(self.state, P1, TOOL_PICKAXE, 1, self.rules)
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertEqual(payload["tool_tiers"]["pickaxe"], "copper")
        self.assertEqual(payload["tool_tiers"]["hoe"], "iron")
        self.assertEqual(payload["item_names"]["pickaxe"]["name"], "copper pickaxe")
        self.assertEqual(payload["item_names"]["hoe"]["name"], "iron hoe")
        self.assertIn("#8a4a1a", svg_for_item("pickaxe_copper"))
        self.assertIn("PICK", svg_for_item("pickaxe_copper"))
        self.assertIn("TEA", svg_for_item("herbal_tea"))

    def test_need_messages_use_the_forged_article(self):
        from inventory import TOOL_HOE, TOOL_AXE, TOOL_PICKAXE
        from mine import set_tool_tier
        from engine import till
        from hills import chop, set_player_place, AREA_HILLS, ensure_hills, get_hills_tile, make_tree
        set_tool_tier(self.state, TOOL_HOE, "iron")
        set_tool_tier(self.state, TOOL_AXE, "copper")
        set_tool_tier(self.state, TOOL_PICKAXE, "gold")
        stand(self.state, P1, 2, 2)
        self.state["players"][P1]["pack"] = []
        ok, msg = till(self.state, self.crops, 2, 2, player=P1)
        self.assertFalse(ok)
        self.assertIn("an iron hoe", msg)
        self.assertNotIn("a iron hoe", msg)
        ensure_hills(self.state, self.rules)
        tile = get_hills_tile(self.state, 2, 2)
        tile["tree"] = make_tree("grown", planted_day=1, days_grown=0)
        set_player_place(self.state, P1, AREA_HILLS, 2, 2)
        ok, msg = chop(self.state, P1, self.rules)
        self.assertFalse(ok)
        self.assertIn("a copper axe", msg)
        self.assertNotIn("an copper axe", msg)





class PassTurnAndWalkHome(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        stand(self.state, P2, CABIN_ROW, CABIN_COL)

    def test_pass_turn_is_legal_any_time_and_hands_off_like_end_turn(self):
        from hills import set_player_place, AREA_FARM
        set_player_place(self.state, P1, AREA_FARM, 2, 1)
        self.state["players"][P1]["energy"] = 0
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("pass turn", actions)
        self.assertIn("pass turn home", actions)
        self.assertIn("end turn", actions)
        line = format_legal_action("pass turn", self.state, self.crops, P1, self.rules)
        self.assertIn("end your turn", line)
        self.assertIn("pass out", line)
        ok, msg = do_action(self.state, self.crops, "pass turn", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(self.state["players"][P1]["ended_turn"])
        self.assertFalse(self.state["players"][P1].get("carry_home"))
        self.assertEqual(self.state["current_player"], P2)
        self.assertIn("passes the turn", msg)
        self.assertEqual(int(self.state["day"]), 1)

    def test_pass_turn_home_then_walk_home_costs_double_and_sleeps_in_the_cabin(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE, player_area, AREA_FARM
        from inventory import add_to_chest, sync_inventory_view
        # P1 is in the hills at the gate; P2 stays in the cabin with plenty of energy.
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 0
        self.state["players"][P2]["energy"] = 100
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P1, rules=self.rules)
        self.assertFalse(ok, msg)  # P1 is not at the cabin
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        self.state["current_player"] = P2
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.state["current_player"] = P1
        ok, msg = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(self.state["players"][P1].get("carry_home"))
        self.assertIn("waits to be carried home", msg)
        self.assertEqual(self.state["current_player"], P2)
        # P2 is still in the cabin, so walk home is not listed until they stand on P1.
        actions = legal_actions(self.state, self.crops, player=P2, rules=self.rules)
        self.assertNotIn(f"walk {N1} home", actions)
        set_player_place(self.state, P2, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P2]["energy"] = 100
        actions = legal_actions(self.state, self.crops, player=P2, rules=self.rules)
        self.assertIn(f"walk {N1} home", actions)
        line = format_legal_action(f"walk {N1} home", self.state, self.crops, P2, self.rules)
        self.assertIn("double movement", line)
        self.assertIn("10 energy", line)  # 1 step from the gate, doubled from 5
        ok, msg = do_action(self.state, self.crops, f"walk {N1} home", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("home to the cabin", msg)
        self.assertIn("10 energy", msg)
        self.assertEqual(self.state["players"][P2]["energy"], 90)
        self.assertTrue(is_player_in_cabin(self.state, P1))
        self.assertTrue(is_player_in_cabin(self.state, P2))
        self.assertFalse(self.state["players"][P1].get("carry_home"))
        self.assertTrue(self.state["players"][P1].get("carried_home"))
        self.assertEqual(player_area(self.state, P1), AREA_FARM)
        # Day has not turned; P2 can end. P1 was carried home (0 energy) and
        # P2 is in the cabin above 10, so together rest also applies.
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 115 energy tomorrow, sleeping close tonight",
        )
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("slept in the cabin", msg)
        self.assertIn("wakes with 115 energy", msg)
        self.assertIn("Sleeping close tonight", msg)
        self.assertEqual(int(self.state["day"]), 2)
        self.assertEqual(self.state["players"][P1]["energy"], 115)
        self.assertEqual(self.state["players"][P1]["energy_max"], 115)
        self.assertTrue(is_player_in_cabin(self.state, P1))

    def test_walk_home_refuses_without_enough_energy_and_nobody_moves(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        set_player_place(self.state, P2, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 0
        self.state["players"][P2]["energy"] = 5  # normal walk would be 5; double is 10
        ok, _ = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok)
        self.state["current_player"] = P2
        here1 = player_where(self.state, P1)
        here2 = player_where(self.state, P2)
        ok, msg = do_action(self.state, self.crops, f"walk {N1} home", player=P2, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("Not enough energy", msg)
        self.assertIn("10 energy", msg)
        self.assertEqual(player_where(self.state, P1), here1)
        self.assertEqual(player_where(self.state, P2), here2)
        self.assertTrue(self.state["players"][P1].get("carry_home"))

    def test_walk_home_is_not_legal_until_they_ask_and_you_stand_with_them(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 40
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn(f"walk {N2} home", actions)
        ok, msg = do_action(self.state, self.crops, f"walk {N2} home", player=P1, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("hasn't asked", msg)
        ok, _ = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok)
        # P2 is still in the cabin, not on P1's tile.
        actions = legal_actions(self.state, self.crops, player=P2, rules=self.rules)
        self.assertNotIn(f"walk {N1} home", actions)
        ok, msg = do_action(self.state, self.crops, f"walk {N1} home", player=P2, rules=self.rules)
        self.assertFalse(ok)
        self.assertIn("Stand on the same tile", msg)

    def test_already_ended_partner_gets_the_turn_back_to_carry(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        # P1 ends first in the cabin, then P2 asks to be carried.
        self.state["players"][P1]["energy"] = 80
        ok, _ = do_action(self.state, self.crops, "end turn", player=P1, rules=self.rules)
        self.assertTrue(ok)
        set_player_place(self.state, P2, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P2]["energy"] = 0
        ok, msg = do_action(self.state, self.crops, "pass turn home", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["day"]), 1)
        self.assertEqual(self.state["current_player"], P1)
        self.assertFalse(self.state["players"][P1]["ended_turn"])
        self.assertTrue(self.state["players"][P1].get("carry_reopened"))
        self.assertIn("walk", msg.lower())
        self.assertIn(N2, msg)
        # P1 can decline by ending again; P2 then passes out.
        ok, msg = do_action(self.state, self.crops, "end turn", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["day"]), 2)
        self.assertIn("passed out", msg)
        self.assertEqual(self.state["players"][P2]["energy"], 50)
        self.assertFalse(is_player_in_cabin(self.state, P2))

    def test_partner_ending_without_carrying_lets_them_pass_out(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 0
        ok, _ = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok)
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(int(self.state["day"]), 2)
        self.assertIn("passed out", msg)
        self.assertEqual(self.state["players"][P1]["energy"], 50)
        self.assertFalse(is_player_in_cabin(self.state, P1))

    def test_pass_turn_home_in_the_cabin_does_not_set_a_carry_request(self):
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("pass turn", actions)
        self.assertNotIn("pass turn home", actions)
        ok, msg = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertFalse(self.state["players"][P1].get("carry_home"))
        self.assertEqual(self.state["current_player"], P2)

    def test_walk_home_alone_still_goes_to_the_cabin(self):
        stand(self.state, P1, 2, 1)
        self.state["players"][P1]["energy"] = 40
        ok, msg = do_action(self.state, self.crops, "walk home", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertTrue(is_player_in_cabin(self.state, P1))
        self.assertIn("walks to the cabin", msg)

    def test_web_payload_lists_pass_and_walk_home_and_the_page_has_buttons(self):
        import web
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 0
        payload = web.api_payload(self.state, self.crops, player=P1)
        self.assertIn("pass turn", payload["actions"])
        self.assertIn("pass turn home", payload["actions"])
        html = web.render_page(viewer=P1)
        self.assertIn('id="pass-turn"', html)
        self.assertIn('id="pass-turn-home"', html)
        self.assertIn('id="walk-home"', html)
        ok, _ = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok)
        set_player_place(self.state, P2, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P2]["energy"] = 40
        payload = web.api_payload(self.state, self.crops, player=P2)
        self.assertIn(f"walk {N1} home", payload["actions"])






class TogetherRest(unittest.TestCase):
    def setUp(self):
        self.crops = load_crops()
        self.rules = load_rules()
        self.state = fresh_state(self.crops, weather_seed=1, rules=self.rules)
        self.state["current_player"] = P1
        stand(self.state, P1, CABIN_ROW, CABIN_COL)
        stand(self.state, P2, CABIN_ROW, CABIN_COL)
        self.state["players"][P1]["energy"] = 40
        self.state["players"][P2]["energy"] = 40

    def _end_both(self):
        first = self.state["current_player"]
        second = P2 if first == P1 else P1
        ok, msg1 = do_action(self.state, self.crops, "end turn", player=first, rules=self.rules)
        self.assertTrue(ok, msg1)
        ok, msg2 = do_action(self.state, self.crops, "end turn", player=second, rules=self.rules)
        self.assertTrue(ok, msg2)
        return msg1, msg2

    def test_both_in_the_cabin_above_10_get_five_and_the_preview_says_sleeping_close(self):
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 105 energy tomorrow, sleeping close tonight",
        )
        self.assertEqual(
            format_legal_action("end turn", self.state, self.crops, P1, self.rules),
            "end turn (sleep in cabin, 105 energy tomorrow, sleeping close tonight)",
        )
        _m1, msg2 = self._end_both()
        self.assertIn("Sleeping close tonight", msg2)
        self.assertEqual(self.state["players"][P1]["energy"], 105)
        self.assertEqual(self.state["players"][P1]["energy_max"], 105)
        self.assertEqual(self.state["players"][P2]["energy"], 105)
        self.assertEqual(self.state["players"][P2]["energy_max"], 105)

    def test_together_rest_does_not_apply_if_one_player_is_at_the_threshold(self):
        self.state["players"][P2]["energy"] = 10
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 100 energy tomorrow",
        )
        self.assertNotIn("sleeping close", sleep_outlook(self.state, P1, self.rules))
        _m1, msg2 = self._end_both()
        self.assertNotIn("Sleeping close tonight", msg2)
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 100)

    def test_together_rest_does_not_apply_if_the_other_player_passed_out(self):
        from hills import set_player_place, AREA_FARM
        set_player_place(self.state, P2, AREA_FARM, 3, 1)
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 100 energy tomorrow",
        )
        self.assertNotIn("sleeping close", sleep_outlook(self.state, P1, self.rules))
        _m1, msg2 = self._end_both()
        self.assertIn("passed out", msg2)
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 50)

    def test_carried_player_at_zero_qualifies_if_the_carrier_ends_in_the_cabin_above_10(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 0
        ok, _ = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok)
        set_player_place(self.state, P2, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P2]["energy"] = 40
        ok, msg = do_action(self.state, self.crops, f"walk {N1} home", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P2]["energy"], 30)
        self.assertTrue(self.state["players"][P1].get("carried_home"))
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 105 energy tomorrow, sleeping close tonight",
        )
        self.assertEqual(
            sleep_outlook(self.state, P2, self.rules),
            "You'll sleep in the cabin — 105 energy tomorrow, sleeping close tonight",
        )
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertIn("Sleeping close tonight", msg)
        self.assertEqual(self.state["players"][P1]["energy"], 105)
        self.assertEqual(self.state["players"][P2]["energy"], 105)

    def test_carried_player_does_not_get_together_rest_if_the_carrier_has_only_10(self):
        from hills import set_player_place, AREA_HILLS, HILLS_GATE
        set_player_place(self.state, P1, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P1]["energy"] = 0
        ok, _ = do_action(self.state, self.crops, "pass turn home", player=P1, rules=self.rules)
        self.assertTrue(ok)
        set_player_place(self.state, P2, AREA_HILLS, *HILLS_GATE)
        self.state["players"][P2]["energy"] = 20  # walk home costs 10, leaving 10
        ok, msg = do_action(self.state, self.crops, f"walk {N1} home", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P2]["energy"], 10)
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 100 energy tomorrow",
        )
        self.assertNotIn("sleeping close", sleep_outlook(self.state, P1, self.rules))
        ok, msg = do_action(self.state, self.crops, "end turn", player=P2, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertNotIn("Sleeping close tonight", msg)
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 100)

    def test_fire_fed_tea_and_together_rest_raise_the_cap_to_135(self):
        from inventory import add_to_pack, add_to_chest, sync_inventory_view
        add_to_chest(self.state, "wood", 1, self.rules)
        sync_inventory_view(self.state, self.rules)
        ok, msg = do_action(self.state, self.crops, "fuel fireplace", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        add_to_pack(self.state, P1, "herbal_tea", 1, self.rules)
        add_to_pack(self.state, P1, "carrot", 1, self.rules)
        ok, _ = do_action(self.state, self.crops, "drink herbal tea", player=P1, rules=self.rules)
        ok, _ = do_action(self.state, self.crops, "eat carrot", player=P1, rules=self.rules)
        self.assertEqual(
            sleep_outlook(self.state, P1, self.rules),
            "You'll sleep in the cabin — 135 energy tomorrow, sleeping close tonight",
        )
        self.assertEqual(
            format_legal_action("end turn", self.state, self.crops, P1, self.rules),
            "end turn (sleep in cabin, 135 energy tomorrow, sleeping close tonight)",
        )
        # P2 did not drink or eat, but still gets fire + together rest.
        self.assertEqual(
            sleep_outlook(self.state, P2, self.rules),
            "You'll sleep in the cabin — 115 energy tomorrow, sleeping close tonight",
        )
        _m1, msg2 = self._end_both()
        self.assertEqual(self.state["players"][P1]["energy"], 135)
        self.assertEqual(self.state["players"][P1]["energy_max"], 135)
        self.assertEqual(self.state["players"][P2]["energy"], 115)
        self.assertEqual(self.state["players"][P2]["energy_max"], 115)
        self.assertIn("wakes with 135 energy", msg2)
        self.assertIn("Sleeping close tonight", msg2)



if __name__ == "__main__":
    unittest.main()

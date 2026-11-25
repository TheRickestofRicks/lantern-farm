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
        self.assertFalse(ok, msg)
        self.assertIn("isn't selling", msg)

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
        self.assertEqual(self.state["players"][P1]["energy"], 100)
        self.assertEqual(self.state["players"][P2]["energy"], 100)
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
            ["farm_look", "farm_do", "farm_end_turn", "farm_forecast", "farm_journal", "farm_rules"],
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
            ["farm_look", "farm_do", "farm_end_turn", "farm_forecast", "farm_journal", "farm_rules"],
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
        self.assertIn("100", sleep_outlook(self.state, P1))
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
        self.assertEqual(shop_kinds(self.crops), ["strawberry", "everbearing"])
        self.assertTrue(crop_in_shop(self.crops["crops"]["strawberry"]))
        self.assertTrue(crop_in_shop(self.crops["crops"]["everbearing"]))
        self.assertFalse(crop_in_shop(self.crops["crops"]["kabocha"]))
        self.assertFalse(crop_in_shop(self.crops["crops"]["turnip"]))
        self.assertFalse(crop_in_shop(self.crops["crops"]["carrot"]))
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("buy strawberry 1", actions)
        self.assertIn("buy everbearing 1", actions)
        self.assertNotIn("buy kabocha 1", actions)
        self.assertNotIn("buy turnip 1", actions)
        self.assertNotIn("buy carrot 1", actions)

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
        self.state["day"] = 17
        self.state["season"] = "summer"
        self.assertEqual(shop_kinds(self.crops, "summer"), ["strawberry", "everbearing"])
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertIn("buy strawberry 1", actions)
        self.assertIn("buy everbearing 1", actions)
        ok, msg = buy(self.state, self.crops, "strawberry", 1)
        self.assertTrue(ok, msg)
        self.state["day"] = 31
        self.state["season"] = "autumn"
        self.assertEqual(shop_kinds(self.crops, "autumn"), [])
        actions = legal_actions(self.state, self.crops, player=P1, rules=self.rules)
        self.assertNotIn("buy strawberry 1", actions)
        self.assertNotIn("buy everbearing 1", actions)
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
        # 6 watered days still remain (17 - 6 = 11).
        self.assertEqual(crop["days_grown"], 11)
        self.assertNotEqual(crop["stage"], "withered")
        # Idempotent.
        self.assertFalse(migrate_calendar(state, self.crops))

    def test_shop_sells_everbearing_seedlings_and_they_fruit_this_year(self):
        from engine import shop_kinds, buy, sell
        self.assertIn("everbearing", shop_kinds(self.crops, "summer"))
        gold = self.state["gold"]
        ok, msg = buy(self.state, self.crops, "everbearing", 1)
        self.assertTrue(ok, msg)
        self.assertIn("seedling", msg.lower())
        self.assertEqual(self.state["gold"], gold - 40)
        self.assertEqual(self.state["inventory"]["everbearing_seedling"], 1)
        r, c = 1, 1
        till(self.state, self.crops, r, c)
        ok, msg = plant(self.state, self.crops, r, c, "everbearing")
        self.assertTrue(ok, msg)
        self.assertIn("seedling", msg.lower())
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
        cabin = layers_for_key("cabin", man)
        self.assertEqual([layer["role"] for layer in cabin], ["cabin"])
        self.assertTrue(cabin[0]["file"].endswith("cabin.png"))
        rain = layers_for_key("cabin_rain", man)
        self.assertTrue(rain[0]["file"].endswith("cabin_rain.png"))
        snowy = layers_for_key("strawberry_mature_wet_snow", man)
        self.assertEqual([layer["role"] for layer in snowy], ["ground", "crop"])
        self.assertIn("soil_watered_snow", snowy[0]["file"])
        self.assertIn("strawberry_mature", snowy[1]["file"])
        self.assertTrue(layers_for_key("soil_snow", man)[0]["file"].endswith("soil_snow.png"))
        self.assertTrue(layers_for_key("soil_tilled_snow", man)[0]["file"].endswith("soil_tilled_snow.png"))
        # Other crops still use the default SVG until a later pack batch.
        self.assertIsNone(layers_for_key("kabocha_sprouting_wet", man))
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
        from inventory import item_count, pack_of, chest_of, stack_count, TOOL_HOE, TOOL_CAN
        self.assertEqual(item_count(self.state, TOOL_HOE), 1)
        self.assertEqual(item_count(self.state, TOOL_CAN), 2)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_HOE), 1)
        self.assertEqual(stack_count(chest_of(self.state), TOOL_CAN), 2)
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
        self.assertEqual(self.state["players"][P1]["energy"], 65)

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
        energy = self.state["players"][P1]["energy"]
        ok, msg = do_action(self.state, self.crops, "craft strawberry jam", player=P1, rules=self.rules)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], energy - 5)
        from inventory import pack_has
        self.assertTrue(pack_has(self.state, P1, "strawberry_jam", 1, self.rules))

    def test_crafted_foods_sell_for_more_than_their_ingredients(self):
        from inventory import item_sell_price
        from engine import crop_info
        jam = item_sell_price("strawberry_jam", self.crops, self.rules)
        soup = item_sell_price("kabocha_soup", self.crops, self.rules)
        stew = item_sell_price("root_stew", self.crops, self.rules)
        berry = int(crop_info(self.crops, "strawberry")["sell_price"])
        kabocha = int(crop_info(self.crops, "kabocha")["sell_price"])
        carrot = int(crop_info(self.crops, "carrot")["sell_price"])
        turnip = int(crop_info(self.crops, "turnip")["sell_price"])
        self.assertGreater(jam, 3 * berry)
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




if __name__ == "__main__":
    unittest.main()

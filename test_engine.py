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

from config import display_name, player_ids, starting_player as config_starting_player

P1, P2 = player_ids()[0], player_ids()[1]
N1, N2 = display_name(P1), display_name(P2)

from engine import (
    NOTE_MAX,
    buy,
    crop_info,
    do_action,
    end_turn,
    energy_cost,
    fresh_state,
    harvest,
    load_crops,
    load_rules,
    migrate_state,
    parse_end_turn_command,
    plant,
    pluck,
    plot_eligible_for_weed,
    sanitize_note,
    season_for_day,
    sell,
    sleep,
    sprout_and_age_weeds,
    till,
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
        self.assertEqual(season_for_day(43, self.crops), "winter")
        self.assertEqual(season_for_day(15, self.crops), "summer")
        snow_seed = find_weather_seed({43: "snow"}, self.rules, self.crops)
        self.assertEqual(weather_for_day(43, self.crops, self.rules, seed=snow_seed), "snow")
        storm_seed = find_weather_seed({15: "storm"}, self.rules, self.crops)
        self.assertEqual(weather_for_day(15, self.crops, self.rules, seed=storm_seed), "storm")
        self.assertTrue(is_wet_weather("snow"))
        self.assertTrue(is_wet_weather("storm"))
        self.assertTrue(is_wet_weather("rain"))
        self.assertFalse(is_wet_weather("sun"))
        self.assertFalse(is_wet_weather("cloud"))

    def test_season_cycle(self):
        self.assertEqual(season_for_day(1, self.crops), "spring")
        self.assertEqual(season_for_day(14, self.crops), "spring")
        self.assertEqual(season_for_day(15, self.crops), "summer")
        self.assertEqual(season_for_day(29, self.crops), "autumn")
        self.assertEqual(season_for_day(43, self.crops), "winter")
        self.assertEqual(season_for_day(57, self.crops), "spring")


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

    def test_withers_after_configured_dry_days(self):
        r, c = self._planted("kabocha")
        limit = int(self.crops["wither_after_dry_days"])
        # Use only sunny days: 1 and 2 are sun, so two sleeps stay dry.
        self.assertGreaterEqual(limit, 2)
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
        self.assertEqual(crop["stage"], "withered")
        self.assertEqual(crop["days_grown"], 0)

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
            cmds = [
                "till 1 1",
                "plant 1 1 kabocha",
                "water 1 1",
                "till 2 2",
                "end turn",
            ]
            for cmd in cmds:
                ok, msg = do_action(state, self.crops, cmd, player=P1)
                self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "end turn", player=P2)
            self.assertTrue(ok, msg)
            ok, msg = do_action(state, self.crops, "water 1 1", player=P1)
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
        r, c = self._planted("turnip")  # 4 days
        for _ in range(4):
            # If a morning is already wet, water() may legitimately fail.
            water(self.state, self.crops, r, c)
            ok, msg = sleep(self.state, self.crops, no_weed_rules())
            self.assertTrue(ok, msg)
        crop = self.state["tiles"][r - 1][c - 1]["crop"]
        self.assertEqual(crop["stage"], "mature")
        before = int(self.state["inventory"]["turnip"])
        ok, msg = harvest(self.state, self.crops, r, c)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["inventory"]["turnip"], before + 1)
        self.assertIsNone(self.state["tiles"][r - 1][c - 1]["crop"])

    def test_buy_and_sell(self):
        gold = self.state["gold"]
        ok, msg = buy(self.state, self.crops, "carrot", 2)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["gold"], gold - 24)
        self.assertEqual(self.state["inventory"]["carrot_seed"], 2)
        self.state["inventory"]["carrot"] = 1
        ok, msg = sell(self.state, self.crops, "carrot", 1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["inventory"]["carrot"], 0)
        self.assertEqual(self.state["gold"], gold - 24 + 30)

    def test_out_of_season_withers_on_season_change(self):
        # Turnips do not grow in summer (day 15).
        state = fresh_state(self.crops)
        # Jump to the last day of spring with a living turnip.
        state["day"] = 14
        state["season"] = season_for_day(14, self.crops)
        state["weather"] = weather_for_day(14, self.crops, self.rules, seed=self.weather_seed)
        self.assertEqual(state["season"], "spring")
        ok, _ = till(state, self.crops, 1, 1)
        self.assertTrue(ok)
        # Give a seed if needed
        state["inventory"]["turnip_seed"] = 1
        ok, msg = plant(state, self.crops, 1, 1, "turnip")
        self.assertTrue(ok, msg)
        water(state, self.crops, 1, 1)
        ok, msg = sleep(state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        self.assertEqual(state["day"], 15)
        self.assertEqual(state["season"], "summer")
        crop = state["tiles"][0][0]["crop"]
        self.assertEqual(crop["stage"], "withered")
        self.assertIn("summer", msg.lower())

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

    def test_costs_come_from_rules_json(self):
        self.assertEqual(energy_cost("till", self.rules), 10)
        self.assertEqual(energy_cost("plant", self.rules), 10)
        self.assertEqual(energy_cost("water", self.rules), 10)
        self.assertEqual(energy_cost("harvest", self.rules), 0)
        self.assertEqual(energy_cost("buy", self.rules), 0)
        self.assertEqual(energy_cost("sell", self.rules), 0)
        self.assertEqual(energy_cost("end_turn", self.rules), 0)
        self.assertEqual(energy_cost("pluck", self.rules), 5)
        custom = copy.deepcopy(self.rules)
        custom["action_energy"]["till"] = 25
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P1, rules=custom)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 75)

    def test_till_plant_water_spend_ten_each(self):
        for cmd in ("till 1 1", "plant 1 1 kabocha", "water 1 1"):
            ok, msg = do_action(self.state, self.crops, cmd, player=P1)
            self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 70)

    def test_blocks_when_energy_is_too_low(self):
        self.state["players"][P1]["energy"] = 5
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertFalse(ok)
        self.assertIn("energy", msg.lower())
        self.assertIn("5", msg)
        self.assertFalse(self.state["tiles"][0][0]["tilled"])
        self.assertEqual(self.state["players"][P1]["energy"], 5)

    def test_failed_action_does_not_spend_energy(self):
        ok, msg = do_action(self.state, self.crops, "plant 1 1 kabocha", player=P1)
        self.assertFalse(ok)
        self.assertEqual(self.state["players"][P1]["energy"], 100)

    def test_harvest_buy_sell_are_free(self):
        # Grow a turnip with the sleep helper (doesn't spend energy), then harvest.
        ok, _ = till(self.state, self.crops, 1, 1)
        self.assertTrue(ok)
        ok, _ = plant(self.state, self.crops, 1, 1, "turnip")
        self.assertTrue(ok)
        for _ in range(4):
            water(self.state, self.crops, 1, 1)
            ok, msg = sleep(self.state, self.crops, no_weed_rules())
            self.assertTrue(ok, msg)
        # sleep() does not reset energy; still 100 because we didn't use do_action.
        self.state["players"][P1]["energy"] = 7
        self.state["current_player"] = P1
        self.state["players"][P1]["ended_turn"] = False
        ok, msg = do_action(self.state, self.crops, "harvest 1 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 7)
        gold = self.state["gold"]
        ok, msg = do_action(self.state, self.crops, "sell turnip 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 7)
        ok, msg = do_action(self.state, self.crops, "buy carrot 1", player=P1)
        self.assertTrue(ok, msg)
        self.assertEqual(self.state["players"][P1]["energy"], 7)
        self.assertEqual(self.state["gold"], gold + 20 - 12)

    def test_wrong_player_is_refused(self):
        ok, msg = do_action(self.state, self.crops, "till 1 1", player=P2)
        self.assertFalse(ok)
        self.assertIn(N1, msg)
        self.assertFalse(self.state["tiles"][0][0]["tilled"])

    def test_end_turn_hands_off_with_fresh_energy(self):
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
        ok, _ = do_action(self.state, self.crops, "till 2 2", player=P2)
        self.assertTrue(ok)
        self.assertEqual(self.state["players"][P2]["energy"], 90)

    def test_both_end_turns_advance_the_day_back_to_the_starting_player(self):
        ok, _ = do_action(self.state, self.crops, "till 1 1", player=P1)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "plant 1 1 kabocha", player=P1)
        self.assertTrue(ok)
        ok, _ = do_action(self.state, self.crops, "water 1 1", player=P1)
        self.assertTrue(ok)
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
        # Day 43 is the first day of winter, when snow is possible.
        seed = find_weather_seed({42: "sun", 43: "snow"}, self.rules, self.crops)
        state = fresh_state(self.crops, weather_seed=seed, rules=self.rules)
        state["day"] = 42
        state["season"] = "autumn"
        state["weather"] = "sun"
        r, c = 1, 1
        till(state, self.crops, r, c)
        state["inventory"]["carrot_seed"] = 1
        ok, msg = plant(state, self.crops, r, c, "carrot")
        self.assertTrue(ok, msg)
        # Jumping the calendar must not keep a wet flag from day 1.
        state["tiles"][0][0]["watered"] = False
        # No watering. Sleep to a snowy winter dawn.
        ok, msg = sleep(state, self.crops, no_weed_rules())
        self.assertTrue(ok, msg)
        self.assertEqual(state["day"], 43)
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
        self.assertEqual(rules["max_energy"], 100)
        ok, msg = mcp_server.farm_do(p2, "till 1 1")
        self.assertFalse(ok)
        self.assertIn(display_name(p1), msg)
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
        self.assertEqual(names, ["farm_look", "farm_do", "farm_end_turn", "farm_forecast", "farm_rules"])
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
        self.assertEqual(names, ["farm_look", "farm_do", "farm_end_turn", "farm_forecast", "farm_rules"])
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
        save_state(fresh_state(load_crops()), engine.STATE_PATH)
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
            body=json.dumps({"command": "till 1 1", "player": P2}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload.get("ok"), payload.get("message"))
        self.assertEqual(payload.get("viewer"), P1)
        tile = payload["state"]["tiles"][0][0]
        self.assertTrue(tile.get("tilled"))



if __name__ == "__main__":
    unittest.main()

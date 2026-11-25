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

    def test_weather_is_a_function_of_day(self):
        for day in range(1, 120):
            a = weather_for_day(day, self.crops)
            b = weather_for_day(day, self.crops)
            self.assertEqual(a, b)
            self.assertIn(a, {"sun", "rain", "snow"})

    def test_day_one_is_sunny(self):
        self.assertEqual(weather_for_day(1, self.crops), "sun")

    def test_known_rain_days(self):
        # Days 3, 5, 10, 14 of spring are rain.
        self.assertEqual(weather_for_day(3, self.crops), "rain")
        self.assertEqual(weather_for_day(5, self.crops), "rain")
        self.assertEqual(weather_for_day(10, self.crops), "rain")
        self.assertEqual(weather_for_day(14, self.crops), "rain")
        self.assertEqual(weather_for_day(1, self.crops), "sun")
        self.assertEqual(weather_for_day(2, self.crops), "sun")

    def test_winter_wet_days_are_snow(self):
        # 14 days per season: winter starts on day 43.
        self.assertEqual(season_for_day(43, self.crops), "winter")
        self.assertEqual(weather_for_day(43, self.crops), "sun")
        self.assertEqual(weather_for_day(45, self.crops), "snow")  # day 3 of winter

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
        self.state = fresh_state(self.crops)

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
        self.assertEqual(weather_for_day(1, self.crops), "sun")
        self.assertEqual(weather_for_day(2, self.crops), "sun")
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
        state["weather"] = weather_for_day(14, self.crops)
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
        self.assertEqual(names, ["farm_look", "farm_do", "farm_end_turn", "farm_rules"])
        p1 = starting_player()
        called = mcp_server.handle_rpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "farm_look", "arguments": {"player": p1}},
        })
        text = called["result"]["content"][0]["text"]
        self.assertIn("Day 1", text)
        self.assertFalse(called["result"]["isError"])
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



if __name__ == "__main__":
    unittest.main()

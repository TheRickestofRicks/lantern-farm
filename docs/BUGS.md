# Bug triage

New bugs get logged here first instead of being fixed on the spot (Rick, 2026-11-27). We pick from this list on purpose. After weekly usage passes about 50%, only critical bugs get fixed and the rest wait for next week.

Severity: **critical** (blocks play or loses saves), **major** (a feature is broken but there's a workaround), **minor** (cosmetic or inconsistent).

## Open
| Found | Bug | Severity | Notes |
|---|---|---|---|
| 2026-11-27 | Several sprites show red fringes where they were cut out for transparency | minor | Visual only. Rick will fix the sprites himself later. |
| 2026-11-27 | Tile selection cursor stays on your old r/c coordinates after changing area (e.g. cabin to farm) | minor | Visual, slight gameplay effect. Expected: follow your current tile or clear on area change. |
| 2026-11-27 | Sleeping-close bonus (+5) missing on Day 14 even though both players ended in the cabin on the double bed (r1c1); end-turn preview said 100 instead of 105 | major | Lumen ended with 8 energy after 2 snacks. rules.json has `together_energy: 10`, possibly a minimum-energy check, but Rick got the bonus on 2-6 energy on earlier days (e.g. Days 12-13). Investigate the condition. |
| 2026-11-27 | Can't carry a partner who passed out in the field once the new day starts (Day 19: Lumen at farm r1c1, Rick on the same tile, no `carry Lumen to bed` offered) | major | `player_requested_carry` needs `carry_home` or `ended_turn`, and both reset at day turn, so a passed-out partner stops counting as waiting. Workaround: pass the turn and the partner walks home. Idea: also offer carry when the partner woke away from the cabin with low energy, or keep a `passed_out` flag until they reach the cabin. |

## Fixed
| Found | Bug | Fixed in |
|---|---|---|
| 2026-11-27 | After `build chest` at cabin r1c2, ground drops on that tile become unreachable | 7c51fd7 |
| 2026-11-27 | Shop shows "everbearing strawberry seed"; everbearing ones are starters | 7c51fd7 |
| 2026-11-27 | E on the cabin door tile didn't leave the cabin | 3f9354c |
| 2026-11-27 | Hands slot rejected every tool except the pickaxe | fb5eb5d |
| 2026-11-27 | Autopass ended the turn immediately; used count never reset; no countdown | 41f9654 |
| 2026-11-27 | Cabin labelled "cabin" instead of r1 c3 | 8279f91 |

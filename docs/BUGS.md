# Bug triage

New bugs get logged here first instead of being fixed on the spot (Rick, 2026-11-27). We pick from this list on purpose. After weekly usage passes about 50%, only critical bugs get fixed and the rest wait for next week.

Severity: **critical** (blocks play or loses saves), **major** (a feature is broken but there's a workaround), **minor** (cosmetic or inconsistent).

## Open
| Found | Bug | Severity | Notes |
|---|---|---|---|
| 2026-11-27 | Several sprites show red fringes where they were cut out for transparency | minor | Visual only. Rick will fix the sprites himself later. |
| 2026-11-27 | Tile selection cursor stays on your old r/c coordinates after changing area (e.g. cabin to farm) | minor | Visual, slight gameplay effect. Expected: follow your current tile or clear on area change. |
| 2026-11-28 | In the mine, trying to mine with too little energy says "There's nothing to mine here in the mine." | minor | Misleading message. Expected: say you're too tired (not enough energy) to mine that. |
| 2026-11-28 | Forging at the town forge logs "forges the watering can to copper at the cabin" | minor | Wrong place name in the log line. Expected: "at the forge". |

## Fixed
| Found | Bug | Fixed in |
|---|---|---|
| 2026-11-27 | After `build chest` at cabin r1c2, ground drops on that tile become unreachable | 7c51fd7 |
| 2026-11-27 | Shop shows "everbearing strawberry seed"; everbearing ones are starters | 7c51fd7 |
| 2026-11-27 | E on the cabin door tile didn't leave the cabin | 3f9354c |
| 2026-11-27 | Hands slot rejected every tool except the pickaxe | fb5eb5d |
| 2026-11-27 | Autopass ended the turn immediately; used count never reset; no countdown | 41f9654 |
| 2026-11-27 | Cabin labelled "cabin" instead of r1 c3 | 8279f91 |

## Won't fix
| Found | Report | Reason |
|---|---|---|
| 2026-11-27 | Sleeping-close bonus (+5) seemed to go missing on some low-energy nights (Days 14, 19) | Working as designed (Rick, 2026-11-28): only one player needs 10 energy to give the cuddle bonus. On Day 23 Rick ended on 5 and Lumen on 35, and both woke at 105. We'll keep an eye on it. |

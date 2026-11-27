# Bug triage

New bugs get logged here first instead of being fixed on the spot (Rick, 2026-11-27). We pick from this list on purpose. After weekly usage passes about 50%, only critical bugs get fixed and the rest wait for next week.

Severity: **critical** (blocks play or loses saves), **major** (a feature is broken but there's a workaround), **minor** (cosmetic or inconsistent).

## Open
| Found | Bug | Severity | Notes |
|---|---|---|---|
| 2026-11-27 | Tile selection cursor stays on your old r/c coordinates after changing area (e.g. cabin to farm) | minor | Visual, slight gameplay effect. Expected: follow your current tile or clear on area change. |

## Fixed
| Found | Bug | Fixed in |
|---|---|---|
| 2026-11-27 | After `build chest` at cabin r1c2, ground drops on that tile become unreachable | 7c51fd7 |
| 2026-11-27 | Shop shows "everbearing strawberry seed"; everbearing ones are starters | 7c51fd7 |
| 2026-11-27 | E on the cabin door tile didn't leave the cabin | 3f9354c |
| 2026-11-27 | Hands slot rejected every tool except the pickaxe | fb5eb5d |
| 2026-11-27 | Autopass ended the turn immediately; used count never reset; no countdown | 41f9654 |
| 2026-11-27 | Cabin labelled "cabin" instead of r1 c3 | 8279f91 |

# Bug triage

New bugs get logged here first instead of being fixed on the spot (Rick, 2026-11-27). We pick from this list on purpose. After weekly usage passes about 50%, only critical bugs get fixed and the rest wait for next week.

Severity: **critical** (blocks play or loses saves), **major** (a feature is broken but there's a workaround), **minor** (cosmetic or inconsistent).

## Open
| Found | Bug | Severity | Notes |
|---|---|---|---|
| 2026-11-27 | After `build chest` at cabin r1c2, ground drops on that tile (hoe, axe, 2 watering cans) become unreachable: `take`/`pick up` only look in the chest ("The chest doesn't have that item"), and the items don't show in the chest either | critical | Blocks tilling, chopping and watering in Second Spring. Fix idea: move ground drops into the chest when it's built, or let take fall back to the ground. Then recover the tools in the second-spring save. |
| 2026-11-27 | Shop shows "everbearing strawberry seed"; everbearing ones are starters/seedlings, so the item name should say "starter" everywhere | minor | Spotted in the honour store. Check the item name, shop list, notes text and art manifest. |

## Fixed
| Found | Bug | Fixed in |
|---|---|---|
| 2026-11-27 | E on the cabin door tile didn't leave the cabin | 3f9354c |
| 2026-11-27 | Hands slot rejected every tool except the pickaxe | fb5eb5d |
| 2026-11-27 | Autopass ended the turn immediately; used count never reset; no countdown | 41f9654 |
| 2026-11-27 | Cabin labelled "cabin" instead of r1 c3 | 8279f91 |

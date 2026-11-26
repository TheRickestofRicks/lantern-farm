# Storybook pack — sources and prompts

First painted graphics pack for Lantern Farm. Soft, cozy, top-down ink-and-watercolour tiles meant to sit cleanly in a square plot cell. Existing procedural SVG art remains the default; this pack is optional and switchable in the browser.

## Method

- Generated at 1024×1024, then resized to 512×512 PNG.
- Ground tiles are opaque (dry and wet untilled soil, dry and wet tilled soil).
- Crop and weed overlays were generated on a flat vivid magenta/rose background, then chroma-keyed and despilled so they composite over the soil.
- Everbearing withered and everbearing regrowing reuse the June-bearing withered and regrowing overlays (the stages look the same at tile size).
- Cabin tiles are opaque painted scenes (clear, cloud, rain, storm, snow), always with a warm lantern glowing in the window.
- When the weather is snow, ground tiles use snowy variants (untilled, wet untilled, tilled, and watered tilled). Crops and weeds still layer on top.
- Rejected generations (too-regular furrows, a single tiny seed, a weed that read as a strawberry sprout, and early regrowing poses that matched a new sprout) were not used.

## Style brief (shared)

Top-down game tile, square 1:1, painted in a soft parchment ink-and-watercolour style: warm brown inks, gentle pigment blooms, fine hatching, no thick comic outline, no UI, no text, no signature, no lantern watermark, no frame. The plant or soil should fill the cell comfortably and read clearly when shrunk to a farm-grid tile.

## Ground prompts

- **soil** — Untilled dry earth, sandy warm brown, small stones and a few grass tufts in the corners, even flat ground, no plants, no furrows, no path, seamless-ish square tile.
- **soil_wet** — The same untilled layout, darkened and damp, soft water sheen and slightly cooler brown, no puddles that obscure the texture, no plants.
- **soil_tilled** — Hand-tilled garden soil, irregular clods and broken earth, not mechanical straight furrows, dry, no plants, no tools.
- **soil_watered** — The same hand-tilled clods, freshly watered, darker wet earth and small water glints, no standing flood, no plants.

## Overlay prompts (flat magenta/rose backdrop, subject only)

- **strawberry_seed** — A small cluster of three or four strawberry seeds (achenes / teardrop seeds) in the centre, no soil, no leaves, clearly readable at tile size.
- **strawberry_sprouting** — A tiny June-bearing strawberry sprout, three young serrated leaves on a short stem, no fruit, no flowers, no pot, no soil.
- **strawberry_growing** — A leafy June-bearing strawberry plant in flower, white blossoms with yellow centres, no ripe fruit, no pot, no soil.
- **strawberry_mature** — A full June-bearing strawberry plant with several ripe red berries and a couple of blossoms, no pot, no soil.
- **strawberry_dormant** — A small overwintering June-bearing strawberry, a few tired reddish-green leaves and a tight crown, no fruit, no pot, no soil.
- **strawberry_withered** — A wilted, dried June-bearing strawberry, hanging brown leaves and bare stems, no fruit, no pot, no soil.
- **strawberry_regrowing** — An established June-bearing strawberry crown putting out fresh green leaves beside one or two older tired leaves, not a brand-new sprout, no fruit, no pot, no soil.
- **everbearing_seedling** — A young everbearing strawberry seedling, a small cluster of serrated leaves (more developed than a first sprout), no fruit, no flowers, no pot, no soil.
- **everbearing_growing** — A leafy everbearing strawberry plant in flower, white blossoms, no ripe fruit, no pot, no soil.
- **everbearing_mature** — A fruiting everbearing strawberry plant with slightly more, slightly smaller ripe berries than the June-bearing mature plant, plus a couple of blossoms, no pot, no soil.
- **everbearing_dormant** — A compact overwintering everbearing strawberry, reddish autumn leaves around a tight crown, no fruit, no pot, no soil.
- **weed** — A single small chickweed or clover-like weed, rounded leaves and one tiny white flower, clearly not a strawberry, no pot, no soil.
- **weedy** — A small patch of the same chickweed/clover-like weed, two or three stems, a few tiny white flowers, no pot, no soil painted under the plant.

## Files

Processed tiles live in `static/packs/parchment/grounds/` and `static/packs/parchment/overlays/`. Original 1024×1024 generations (including rejected takes) are kept next to this note under `sources/originals/` when shipped with the pack.

## Cabin prompts

Same log cabin in every weather, top-down farm tile, parchment ink-and-watercolour, no text, no frame, no people, no animals, no signature. Warm lantern glowing in the four-pane window in every version. Thin chimney smoke. The cabin sits on a little yard of storybook soil with grass tufts at the corners, filling the square comfortably.

- **cabin** — Clear fair day, bare wooden shingle roof, warm golden-brown soil, no snow, no rain.
- **cabin_cloud** — The same cabin on an overcast grey day, muted cool light, no rain or snow, lantern still warm.
- **cabin_rain** — The same cabin in the rain: diagonal rain streaks, wet darker roof and soil, a few puddles, lantern glow on the wet steps.
- **cabin_storm** — The same cabin in a heavy storm: darker wet soil, dense rain, a distant lightning flash, lantern glowing strongly. Keep a top-down yard (avoid a wide horizon if it fights the neighbouring soil tiles).
- **cabin_snow** — The same cabin in the snow: a soft cap of snow on the roof, falling flakes, a snowy yard with tufts and stones poking through, lantern light on the steps.

An early storm take with a strong sky-and-treeline horizon was replaced with a darker, rain-like top-down composition that still reads as a storm. A first watered-snow ground that looked too glossy and framed was redone in the softer pack style.

## Snow ground prompts

Same style and layout as the matching non-snow ground tiles, no footprints, no path, no extra plants, no text, no frame. Creamy snow with cool blue-violet shadows, earth and stones still showing through.

- **soil_snow** — Untilled soil under a first snow; corner grass tufts and pebbles poke through.
- **soil_wet_snow** — The same untilled layout, slushier and thinner snow, more dark damp earth showing.
- **soil_tilled_snow** — Hand-tilled clods with snow settled in the hollows and darker earth on the raised clods.
- **soil_watered_snow** — Tilled clods, wetter and darker, with thinner slushy snow in the hollows and a gentle damp sheen (not a glossy 3D render).

## Weed placement (later pass)

The first `weed` and `weedy` overlays were painted in the centre of the cell, so they disappeared under crop sprites. They were recomposed from those originals (no new painting): a slightly darker, more saturated cut-out of the same plants, placed in the lower-left corner for a single weed, and in the lower-left and lower-right corners for a weedy plot, leaving the crop centre clear. The earlier centred keyed PNGs are kept as `sources/originals/weed_centered.png` and `weedy_centered.png`.

## Cabin door pass (later)

The first cabin tiles had wooden steps leading to a four-pane lantern window and no front door. All five weather variants were repainted so a clearly visible wooden front door sits at the top of the steps, with the lantern-lit window beside it. The same cabin is used in clear, cloud, rain, storm, and snow. Style and yard ground were referenced from the Storybook `soil.png` and `soil_wet.png` tiles so the cabin matches neighbouring plots. The earlier no-door 1024 sources and 512 pack tiles are kept as `sources/originals/*_no_door.jpg` and `*_no_door.png`.

## Item icons

Inventory, shop, chest, kitchen, and recipe-book icons were painted in the same ink-and-watercolour Storybook style as the soil, cabin, and plant tiles: a single centered object on a transparent square, not a flat vector placeholder. Tools, three visually distinct fertilizer sacks (teal general, green yield, steel-blue growth), staples, crafted foods, produce, and seed packets live in `items/`. Raw paintings are kept as `sources/originals/item_*.jpg`. The everbearing seedling icon is a closer crop of the existing seedling overlay.

The first yield fertilizer sack was both open at the top, with granules and berries spilling out, and tied closed at once. It was repainted as a single consistent sack: gathered and tied shut like the general and growth bags, still green, with a fruit emblem on the front and a few green granules beside it. The earlier painting is kept as `sources/originals/item_fertilizer_yield_open.jpg` (and the earlier processed icon as `item_fertilizer_yield_open.png`).

A shovel icon was painted in the same style as the hoe and watering can: a wooden-handled digging spade with a single solid metal blade (not a hoe). The raw painting is `sources/originals/item_shovel.jpg`.

The first hoe icon was a spade-like blade in line with the handle, too close to the shovel. It was repainted as a classic draw hoe: a long wooden handle with a flat rectangular blade set perpendicular at the end, so the silhouette is an L. The earlier painting is kept as `sources/originals/item_hoe_spade.jpg` (and the earlier processed icon as `item_hoe_spade.png`).

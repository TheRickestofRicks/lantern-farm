# Parchment pack — sources and prompts

First painted graphics pack for Lantern Farm. Soft, cozy, top-down ink-and-watercolour tiles meant to sit cleanly in a square plot cell. Existing procedural SVG art remains the default; this pack is optional and switchable in the browser.

## Method

- Generated at 1024×1024, then resized to 512×512 PNG.
- Ground tiles are opaque (dry and wet untilled soil, dry and wet tilled soil).
- Crop and weed overlays were generated on a flat vivid magenta/rose background, then chroma-keyed and despilled so they composite over the soil.
- Everbearing withered and everbearing regrowing reuse the June-bearing withered and regrowing overlays (the stages look the same at tile size).
- Cabin tiles stay on the default SVG art in this batch.
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

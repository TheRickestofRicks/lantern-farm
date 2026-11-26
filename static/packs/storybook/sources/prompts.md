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
- **cabin_smoke** — A transparent overlay of thicker chimney smoke rising from the same chimney mouth, used when the fireplace is fueled. The weather cabin tile itself is unchanged; only this smoke is stacked on top.

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

## Hills tiles (Phase 1)

Hills grounds, tree and forage overlays, and the axe, wood, and wild-forage item icons were painted in the same parchment ink-and-watercolour Storybook style as the farm soil and plant tiles, then chroma-keyed and resized to 512×512. Grounds are opaque full-bleed textures. Overlays and item icons sit on a keyed magenta field so they composite over the grass. Raw 1024 paintings are kept as `sources/originals/` (`hills_grass.jpg`, `overlay_tree_grown.jpg`, `item_axe.jpg`, and so on).

Ground prompts (top-down square farm tile, no text, no frame, no people, no signature; match the Storybook soil tile):

- **hills_grass** — Uneven wild grass in warm olive and gold-green, a few pebbles and tufts in the corners, no path, no trees.
- **hills_grass_snow** — The same hillside grass under a first creamy snow, tufts and pebbles poking through, no footprints.
- **hillside** — A rising grassy bank with a worn dirt path swelling toward the top of the square, stones and grass at the sides.
- **hillside_snow** — A full-bleed snowy hillside with rocks and pale grass tufts, no white sky, no cut-out silhouette.
- **mine_entrance_closed** — A boarded-up mine door set in a rocky cave mouth on a grassy bank, weathered planks nailed shut, a dirt approach, clearly closed.
- **mine_entrance_closed_snow** — The same sealed entrance, snow-dusted boards, full-bleed snowy ground around it. An earlier take that showed an open tunnel was replaced with the boarded door.

- **mine_floor** — A dark packed-earth mine tunnel floor, seen from above, brown and grey soil packed hard, a little grit and no grass. Full-bleed ground, no frame, no people.
- **mine_safe** — A warmer gold-flecked safe-chamber floor, still packed earth, a little brighter and more golden than the ordinary tunnel, seen from above, full-bleed.

Overlay prompts (subject only on a flat vivid magenta-rose field, no soil, no pot, no text):

- **tree_sapling** — A slender sapling with a thin brown trunk and a few fresh green leaves, seen slightly from above.
- **tree_young** — A young tree, slim trunk, a modest rounded crown of leaves.
- **tree_grown** — A mature deciduous tree with a sturdy trunk and a full green crown, no flowers, no fruit. An earlier take with white blossoms (too close to the strawberry reference) was replaced.
- **tree_stump** — A low round wooden stump seen from above, pale cut face with growth rings, a little bark and a few chips.
- **forage_wild_onion** — A small cluster of upright wild-onion leaves with one white flower, fairly small on the tile.
- **forage_wild_berry** — A low leafy bush with a few ripe red berries.
- **forage_wild_mushroom** — Three woodland mushrooms with tawny caps and pale stems.

- **mine_rock** — A plain grey-brown boulder sitting on the mine floor, no crystals, subject only on magenta.
- **mine_rock_copper** — The same boulder with visible copper-green and orange ore veins.
- **mine_rock_iron** — The same boulder with visible silver-grey iron crystals.
- **mine_rock_gold** — The same boulder with bright gold flecks and veins.
- **mine_ladder** — A ladder going down into a dark hole in the floor, framed by a square of wooden beams, seen from above, subject only on magenta. The hole and the space between rungs should key to transparency.
- **mine_shaft** — A wooden mineshaft door seen from inside the tunnel, set in a rough cave mouth, subject only on magenta. No pink fringe around the cave edge.
- **mine_ladder_up** — A wooden ladder ending in midair, no ceiling, no hole, the way up from a deeper floor, subject only on magenta. Spaces between rungs should key to transparency.
- **mine_lantern** — An oil lantern on a short post, sitting on the floor, warm glow, subject only on magenta, flush to the bottom of the square.
- **mine_elevator** — An empty wooden-and-iron mine elevator cage, no cargo, subject only on magenta. The interior of the cage should key to transparency.

- **zucchini_growing** — A young zucchini plant with lobed leaves and small fruits attached to the stems near the base, each with a yellow blossom at the fruit tip (real zucchini). Earlier takes with a floating flower and bare fruit tips were discarded. Wet and dry variants share this overlay.
- **zucchini_mature** — The same plant at harvest, with much larger plump fruits still attached at the stem and a blossom at each tip. Wet and dry variants share this overlay.

Item-icon prompts (single centered object on magenta, same style as the hoe and shovel):

- **axe** — A woodcutter's felling axe with a curved wooden haft and a wedge-shaped steel head. Early takes that followed the hoe reference too closely were discarded.
- **wood** — Three short cut logs stacked and tied with twine, no tools.
- **wild_onion** — One small onion bulb with a short tuft of green leaves.
- **wild_berry** — A cluster of ripe red berries with a couple of green leaves.
- **wild_mushroom** — Two or three woodland mushrooms with tawny-brown caps.

- **wild_berry_jam** — A glass jar of dark crimson-purple wild berry jam with a red gingham cloth lid tied with twine, a small cluster of ripe berries beside it.
- **wild_onion_soup** — A beige bowl of golden-brown onion soup, with onion rings and a few green onion tops on top.
- **mushroom_soup** — A beige bowl of creamy brown mushroom bisque, sliced mushrooms and a swirl of cream on top.
- **oyster_mushroom** — A cluster of fan-shaped cream and grey-beige oyster mushrooms with visible gills.
- **pickaxe** — A classic wooden-haft miner's pickaxe with a steel double-pointed head. The unforged / basic sprite.

- **stone** — A small pile of broken grey stone, a cheap mine material, single centered object on magenta.
- **copper_ore** — A chunk of rock with copper-green and orange mineral, single centered object on magenta.
- **iron_ore** — A chunk of rock with visible silver-grey iron crystals, single centered object on magenta.
- **gold_ore** — A chunk of rock with bright gold flecks, single centered object on magenta.
- **sugar** — A small rustic cloth sugar sack of coarse beige canvas, tied with twine, the open mouth showing a mound of loose white sugar crystals, a short wooden scoop and a little spilled sugar, subject only on magenta. No glass jar, no bottle, no milk bottle, no lid, no other container inside the sack.

- **hoe_copper**, **hoe_iron**, **hoe_gold** — The hoe with a copper, cool grey-blue iron, or gold blade. Same wooden haft as the basic hoe, subject only on magenta.
- **watering_can_copper**, **watering_can_iron**, **watering_can_gold** — The watering can in hammered copper, cool grey-blue iron, or gold, subject only on magenta.
- **axe_copper**, **axe_iron**, **axe_gold** — The felling axe with a copper, iron, or gold head and the same curved wooden haft, subject only on magenta.
- **pickaxe_copper**, **pickaxe_iron**, **pickaxe_gold** — The miner's pickaxe with a copper, iron, or gold head, subject only on magenta.
- **herbal_tea** — A handmade cream ceramic mug of golden-amber herbal tea on a saucer, a wisp of steam, a mint sprig and a couple of dried herb buds, subject only on magenta.

## Cabin interior

Interior tiles use an opaque wooden floor ground (`cabin_floor`) with furniture
overlays composited on top, the same way hills trees sit on grass. Overlays
were painted on a flat rose-magenta field, chroma-keyed, and resized to
512×512. Raw 1024 paintings live in `sources/originals/` (`cabin_floor.jpg`,
`cabin_bed.jpg`, and so on). The processed floor is a slight crop and edge
lift of the original painting so neighbouring tiles don’t show a heavy vignette
seam.

Style brief (shared with the rest of the pack): top-down square game tile,
parchment ink-and-watercolour, warm brown inks, gentle pigment blooms, fine
hatching, no thick comic outline, no UI, no text, no signature, no frame.
Furniture overlays have no floor of their own — they sit on `cabin_floor`.

- **cabin_floor** — Opaque full-bleed interior pine floorboards in honey,
  ochre, and umber, edge to edge, no furniture, no grass, no soil, no rug.
- **cabin_bed** — A modest wooden double bed from above, two cream pillows
  at the head, a cozy dusty-blue and cream quilt with a small stitched lantern
  and a quiet aurora of green-violet-rose needlework. Subject on magenta.
- **cabin_chest** — A closed rustic farmhouse wooden chest with dull iron
  bands and a hasp, subject on magenta.
- **cabin_door** — The inside face of a simple wooden cabin door in a short
  frame, iron latch, sitting at the bottom of the tile (the door is
  bottom-left in the room). Subject on magenta.
- **cabin_fireplace** — A stone farmhouse fireplace on the right side of the
  tile, unlit firebox with cold logs, subject on magenta.
- **cabin_fireplace_lit** — The same fireplace with a warm fire in the box.
- **cabin_kitchen** — A wooden kitchen island (bowl and cutting board) plus
  a compact cast-iron wood-fire cookstove, unlit, sitting on the floor as
  furniture. Subject on magenta; no floor painted in the overlay.
- **cabin_kitchen_lit** — The same island and stove with the firebox lit
  for the day.

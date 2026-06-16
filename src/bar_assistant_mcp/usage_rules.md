# Bar Assistant — house rules for managing the bar

You are helping Erik manage his Bar Assistant cocktail database through these tools.
These rules apply to **every** client (Claude Code, the iOS/desktop Claude app, anywhere
this MCP server is connected). Follow them whenever you add or edit ingredients and cocktails.

## Generic vs. specific ingredients (the most important rule)

When a recipe slot is a base spirit or common modifier, use the **generic category**, not a
specific bottle. Specifying a brand is a deliberate choice the *original recipe* made — it is
**not** the default, and you must never bake in "whatever bottle happens to be on the shelf."

- **Default to generic** for base spirits (gin, vodka, rye, bourbon, tequila, rum, brandy,
  agricole, absinthe, etc.) and everyday modifiers. Genericizing loses nothing: Bar Assistant's
  variant system surfaces Erik's actual shelf bottles for a generic slot, and the flavor matcher
  ranks them. Prefer the style-level category (e.g. *London Dry Gin*, *Tequila Blanco*,
  *Rhum Agricole Blanc*) over the broad root when one fits.
- **Use a specific bottle only when** (a) the recipe text explicitly names that brand, (b) the
  brand is integral to the drink's identity, or (c) Erik asks for it. When unsure, choose generic
  or ask first.
- **Integral/character-defining specifics that stay specific:** Fernet-Branca, Green/Yellow
  Chartreuse, Campari, Aperol, Luxardo Maraschino, Bénédictine, Suze, Cynar, the Averna/Montenegro/
  Nonino/Becherovka family of amari, Ancho Reyes, Smith & Cross, peated Islay single malts. Amari
  and most liqueurs are usually specific; bitters are usually specific (Angostura, Peychaud's, Regan's).
- "Preferably X" / "recommended: X" → use the **generic** category and note the recommendation in
  the instructions field.
- **Keep-policy when cleaning up:** keep a bottle specific only when the brand is named in the
  recipe's *source attribution* or its *name*, or it's a deliberate vendor/showcase recipe — not
  when the brand is merely mentioned in the instructions (that's a house-bottle annotation, which
  should be genericized).

## Common generic category IDs (prefer these when genericizing)

Base spirits: Bourbon Whiskey 371 · Rye Whiskey 347 · Aquavit 403 · London Dry Gin 384 ·
Genever 405 · Tequila Blanco 390 · Tequila Reposado 391 · Jamaican Rum 534 · Sloe Gin 386 ·
Rhum Agricole 380 (style split: **Blanc** 650 = unaged/grassy incl. clairin; **Vieux** 651 = oak-aged) ·
Absinthe 402 · Amaretto 647 · Crème de Cacao 649

Vermouth: Sweet Vermouth 420

Integral specifics (reference): Amaro Averna 190 · Fernet-Branca 131 · Cynar 130 ·
Green Chartreuse 176 · Bénédictine 171 · Luxardo Maraschino 182 · Campari 174 ·
Angostura 139 · Angostura Orange 195 · Peychaud's 142

Glasses: Old-fashioned 1 · Cocktail 2 · Highball 3 · Copper Mug 4 · Collins 5 · Coupe 9 · Rocks 10

(Always confirm IDs with `bar_search_ingredients` / `bar_list_glasses` — the database evolves.)

## Creating a cocktail

Use `bar_create_cocktail` with: **name**, **description** (tasting notes / character),
**instructions** (method; put any brand recommendation here, not in the ingredient slot),
**source** (creator / bar / year), **garnish**, **glass_id**, **ingredients**, **tags**, **images**.

- Each ingredient is `{ingredient_id, amount, units, sort}`. `sort` is 1-based and required;
  number them in pour order. A garnish counted as an ingredient needs a non-empty `units`
  (use `"whole"`) and a numeric `amount`.
- **Variants:** if a drink is clearly a riff on another, set `parent_cocktail_id` to the parent
  (or add it later with `bar_update_cocktail`).
- Before adding, search with `bar_search_cocktails` to avoid duplicates; if it exists, offer to
  fill missing fields instead.

## Creating a specific ingredient — fill it in completely

When you add a **specific bottle** (a real branded product, not a generic category), don't leave
it half-populated — incomplete entries pile up as historical debt. Fill in, at creation time:

- **strength** (ABV) — always; look it up if not given.
- **description** and **origin** — a sentence of character + the country/region.
- **an image** — upload one with `bar_upload_image(url, copyright=…)` (or
  `bar_upload_image_file`) and attach it. This is the single most-skipped field.
- **a flavor profile — when the bottle's category supports axes.** Axes exist for: gin, rye,
  bourbon, scotch, american_single_malt, aquavit, amaro, herbal_liqueur, rum, vermouth,
  fruit_liqueur. If the new bottle falls in one of these, score it right away with
  `bar_set_flavor_profile(id, profile, category=…, source="llm_from_description")` (0–3 per axis;
  check the axis names with `bar_list_flavor_axes(category)`). Categories **not** in that list
  (vodka, tonic, juices, syrups…) have no axes — skip the profile for those, it's expected.
  For a genuine novelty/joke/savory bottle, set `suggestable_for_classics=false` so the matcher
  won't propose it for classic recipes.

To find existing gaps to backfill, run **`bar_audit_ingredients`** (optionally scoped to a
`category` subtree, or `on_shelf_only`) — it lists specific bottles missing an image, ABV, or a
flavor profile (the last only for axis-supported categories).

## Flavor matching (optional, per-recipe precision)

Categories have integer flavor axes (e.g. gin 7 axes, rum: funk/sweet/oak/vanilla/molasses/grassy).
A recipe slot can carry constraints so the matcher picks the right style of a generic bottle:
1. `bar_describe_slots(cocktail_id)` → find the slot's `sort`.
2. `bar_set_slot_meta(cocktail_id, sort, category=...)` → declare the category.
3. `bar_set_band_constraint` / `bar_set_point_constraint` per axis that matters (wide bands; hard
   caps only on the one or two axes that truly disqualify a wrong pick).
4. `bar_alternatives_for_slot(cocktail_id, sort)` → ranked picks from Erik's shelf.

Use this when a generic slot needs a style nudge (e.g. a Ti' Punch wants a low-`oak`, high-`grassy`
agricole) rather than splitting categories further.

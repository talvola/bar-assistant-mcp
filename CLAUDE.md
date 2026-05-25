# Bar Assistant MCP Server

This is the MCP (Model Context Protocol) server for Bar Assistant, providing tools to manage cocktails, ingredients, and bar inventory.

## Related Projects

- `/home/erik/bar-assistant` - Bar Assistant API (Laravel backend)
- `/home/erik/bar-assistant-mcp` - This MCP server (current)
- `/home/erik/vue-salt-rim` - Salt Rim Web UI (Vue.js frontend)

## Adding Cocktails from URLs

When adding cocktails from blog posts or websites, follow this process:

### 1. Fetch and Check

- Use `WebFetch` to extract the recipe from the URL
- Search for the cocktail name with `bar_search_cocktails` to check if it already exists
- If it exists, offer to update missing fields (description, source, image, garnish, tags)

### 2. Ingredient Strategy

Decide whether each ingredient should be **generic** or **specific**:

| Type | When to Use | Examples |
|------|-------------|----------|
| **Generic** | Base spirits, common modifiers where brand doesn't matter | Bourbon Whiskey, Rye Whiskey, Sweet Vermouth, Aquavit |
| **Specific** | Unique products with distinctive flavor profiles | Fernet-Branca, Green Chartreuse, Amaro Averna, Campari |

**Guidelines:**
- If the recipe says "preferably X" or "recommended: X", use the **generic** category and note the recommendation in instructions
- If a specific brand is integral to the cocktail's identity, use the **specific** ingredient
- Amari and liqueurs are usually specific (Averna, Cynar, Benedictine)
- Bitters are usually specific (Angostura, Peychaud's, Regans)

### 3. Search for Ingredients

Search for each ingredient using `bar_search_ingredients`:
- Check if the ingredient exists (generic or specific)
- Note the IDs for existing ingredients
- Create any missing ingredients with `bar_create_ingredient`

### 4. Upload Image

If an image URL is available:
```
bar_upload_image(image_url, copyright="Source attribution")
```
Note the returned image ID for the cocktail creation.

### 5. Create the Cocktail

Use `bar_create_cocktail` with:

- **name**: Cocktail name
- **description**: Tasting notes, character description
- **instructions**: How to make it (include brand recommendations here)
- **source**: Creator, bar, location, year if known
- **garnish**: Garnish description
- **glass_id**: Look up with `bar_list_glasses`
- **ingredients**: Array of `{ingredient_id, amount, units, sort}` (sort is 1-based, required by the API; tools backfill if omitted)
- **tags**: Relevant tags (Stirred, Shaken, Rye, Bourbon, Tiki, etc.)
- **images**: Array of uploaded image IDs
- **parent_cocktail_id**: If this is a variant/riff of another cocktail

### 6. Cocktail Variants

If a cocktail is clearly a riff on another:
- Search for the parent cocktail
- Set `parent_cocktail_id` when creating
- Or update with `bar_update_cocktail` if added later

**Example family:**
```
Manhattan
  └── Rhythm and Soul (adds Herbsaint rinse, Averna)

Mergers & Acquisitions
  └── The Linguist (swaps rye/aquavit proportions)
```

## Spirits Inventory Sync (Google Sheets)

**Trigger:** After any successful `bar_create_ingredient` for a real bottled product (specific brand expression: Fernet-Branca, Bittermens Xocolatl Mole, StilL 630 RallyPoint, etc.). Skip generic categories (Bourbon Whiskey, Sweet Vermouth) and non-spirit items (syrups, juices, garnishes).

**Why:** Erik tracks physical bottle inventory in a separate sheet — ABV, origin, producer, tasting/usage notes for the bottle on the shelf. Bar Assistant tracks the recipe side. The two drift apart when new bottles get added to BA without a matching sheet row, and Erik sometimes forgets to ask — surface this proactively without waiting for the prompt.

**Sheet:** `https://docs.google.com/spreadsheets/d/10AOLpeJ2PpT-MskyOhVADhCctxWDxphwsjZWmpNjDBM/edit` — tab `Sheet1`. Columns: A=Product Name, B=Category, C=Notes, D=ABV %, E=Origin, F=Distillery/Producer, G=Description, H=Status.

**Process:**
1. After creating the BA ingredient, search Sheet1 for the brand+expression name.
2. **Placeholder row exists** (A,B filled; D–G blank): enrich D–G. Don't touch A, B, C, H.
3. **Row already enriched** (D–G filled): no-op — just mention it.
4. **No row exists**: append a new row at the bottom of the active list with A–G filled in. Leave H blank to match the recent-enrichment pattern.

**Description voice:** match existing rows (see rows ~180–204 to calibrate) — em-dash-heavy, includes process specifics (mash bill / botanicals / distillation / aging), tasting notes in nose / palate / finish format when documented, and one sentence on cocktail role. No marketing fluff. Use real research (producer pages, Difford's, Drinkhacker, retailer copy), not fabricated detail.

Don't ask permission to do the sync — do it after each qualifying ingredient creation and report what changed.

## Common Ingredient IDs (Reference)

**Base Spirits:**
- Bourbon Whiskey: 371
- Rye Whiskey: 347
- Aquavit: 403

**Vermouth:**
- Sweet Vermouth: 420

**Amari & Liqueurs:**
- Amaro Averna: 190
- Fernet-Branca: 131
- Cynar Ricetta Originale: 130
- Green Chartreuse: 176
- Benedictine D.O.M.: 171
- Luxardo Maraschino: 182
- Anise Liqueurs: 436

**Bitters:**
- Angostura Aromatic Bitters: 139
- Angostura Orange Bitters: 195
- Peychaud's Bitters: 142

**Syrups:**
- Rich Demerara Syrup: 494

**Garnishes:**
- Lemon peel: 339
- Orange peel: 311
- Maraschino cherry: 310

## Glass IDs

- Old-fashioned glass: 1
- Cocktail glass: 2
- Highball glass: 3
- Copper Mug: 4
- Collins glass: 5
- Martini Glass: 6
- Wine Glass: 7
- Collins Glass: 8
- Coupe glass: 9
- Rocks glass: 10

## Quick Add (No Review)

For trusted sources where review isn't needed:
1. Fetch URL
2. Check if exists
3. Search all ingredients
4. Upload image
5. Create cocktail

All in rapid succession without presenting a plan for approval.

## Flavor Matching (Phase A)

Per-category integer flavor axes (gin: 7 axes, 0–3, sourced from The Gin Is In), per-recipe-slot Point/Band constraints, and three use cases on top: ranked alternatives for a slot, recipes welcoming a bottle, and stock-gap finding. Storage in SQLite sidecar at `data/flavor.sqlite` (overridable via `BAR_ASSISTANT_FLAVOR_DB`).

**Modules:**
- `flavor.py` — pure engine (Bottle, RecipeSlot, Point, Band, assess, alternatives_for_slot, uses_for_bottle, find_gaps)
- `flavor_db.py` — SQLite layer (category_axes, ingredient_meta, flavor_profile, slot_meta, slot_constraint)

**MCP tools (in `server.py`):**
- `bar_list_flavor_axes(category="gin")`
- `bar_get_flavor_profile(ingredient_id)`
- `bar_set_flavor_profile(ingredient_id, profile, source, confidence, notes)`
- `bar_describe_slots(cocktail_id)` — list slots with `sort` indices and constraint status
- `bar_set_slot_meta(cocktail_id, sort, category, tolerance, also_accept_categories, proof_min, proof_max)`
- `bar_set_band_constraint(cocktail_id, sort, axis, lo, hi, out_weight, hard)`
- `bar_set_point_constraint(cocktail_id, sort, axis, value, weight)`
- `bar_delete_slot_constraint(cocktail_id, sort, axis)`
- `bar_get_slot_constraints(cocktail_id)`
- `bar_alternatives_for_slot(cocktail_id, sort, on_shelf_only, include_strays, top_n)`
- `bar_uses_for_bottle(ingredient_id, top_n)`
- `bar_find_gaps(cocktail_ids=None, threshold=3.0)` — shopping list: slots whose best in-stock match is a stretch

**Workflow to encode a recipe:**
1. `bar_describe_slots(cocktail_id)` → find the `sort` index of the slot to constrain.
2. `bar_set_slot_meta(cocktail_id, sort, category="gin")` — declare what category fills it.
3. One `bar_set_band_constraint` (or `bar_set_point_constraint`) per axis you care about — wide bands everywhere, hard caps on the one or two axes that *truly* disqualify a wrong pick.
4. `bar_alternatives_for_slot(cocktail_id, sort)` → ranked picks from your shelf.

**Bootstrap pipeline** (`scripts/`):
- `tgii_bootstrap.py` → fetches BA shelf gins, fuzzy-matches against TGII reviews sitemap, fetches/parses SVGs, merges LLM-scored entries for bottles not on TGII. Re-runnable; preserves `tgii_overrides.json` and `tgii_unofficial_scores.json`.
- `seed_flavor_db.py` → imports `tgii_bootstrap_results.json` into the SQLite. Idempotent.

To extend to other categories: define axes (`set_axes(conn, 'rum', [...])`), then bootstrap as for gin (find or build a published axis-scored corpus, then LLM-fill from descriptions for the long tail). Roadmap in memory `bar_assistant_roadmap`.

## Engineering Notes

### Ingredient payloads (cocktail create/update)
Always backfill `sort` on each ingredient before sending — the BA API's `CocktailIngredientRequest::fromArray` requires it with no default, returns 500 if missing. Pattern used in `server.py`: `{**ing, "sort": ing.get("sort", idx + 1)}`. Apply to any new write tool that accepts ingredients.

### Testing changes against the live BA API without redeploying
`.venv/bin/python -c "from bar_assistant_mcp.api import BarAssistantAPI; ..."` — import the fixed code directly, hit production BA with the stdio token from `.mcp.json`, clean up after. Faster than rebuilding the container.

### Debugging deployed-server errors
Laravel logs go to container stdout, not `storage/logs/laravel.log` (which is empty). Use the Portainer logs API on `bar-assistant-api` to read exceptions. Deploy/debug details in memory (`deployment_guide`, `ba_api_quirks`).

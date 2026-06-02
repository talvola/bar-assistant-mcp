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
- **Default base spirits to generic, and never bake in the current house bottle.** If the recipe text doesn't name a brand, use the generic category (Rye Whiskey 347, Bourbon 371, etc.) — not whatever specific bottle happens to be in stock. Specifying a base spirit is a deliberate choice the original recipe made, not the default. When in doubt, use generic or ask first; genericizing loses nothing because BA's variant system surfaces the actual shelf bottles (and the flavor matcher ranks them) for a generic slot.
- Only use a **specific** ingredient when (a) the recipe explicitly names that brand, (b) the brand is integral to the drink's identity (Fernet-Branca, Green Chartreuse, Campari, Luxardo Maraschino), or (c) Erik asks for it. Otherwise verify before choosing specific.
- If the recipe says "preferably X" or "recommended: X", use the **generic** category and note the recommendation in instructions
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

**Base Spirits (generic categories — prefer these when genericizing):**
- Bourbon Whiskey: 371
- Rye Whiskey: 347
- Aquavit: 403
- London Dry Gin: 384
- Genever: 405
- Tequila Blanco: 390
- Tequila Reposado: 391
- Jamaican Rum: 534
- Sloe Gin: 386

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
- Amaretto: 647 (generic; created 2026-06-01)
- Crème de Cacao: 649 (generic; created 2026-06-01)

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

## Flavor Matching (Phase B — native in Bar Assistant)

Per-category integer flavor axes (gin: 7 axes, 0–3), per-recipe-slot Point/Band constraints, and use cases on top: ranked alternatives for a slot, recipes welcoming a bottle, stock-gap finding. **As of the Phase B Slice 5 cut-over (2026-05-29), all flavor data + the scoring engine live natively in Bar Assistant** (tables `flavor_*`, engine in `app/Services/Flavor/`, endpoints under `/api/flavor` + per-ingredient/cocktail). The old MCP SQLite sidecar (`flavor.py`/`flavor_db.py`/`data/flavor.sqlite`) is **retired** — these MCP tools are now thin wrappers over the BA HTTP endpoints (see `api.py` flavor methods). Single source of truth is BA; Salt Rim and the MCP both read/write the same data.

Bootstrap artifacts (`scripts/tgii_*`, `flavor_encoding.json`) remain as the historical record of how the data was authored, but BA is authoritative now. To re-seed a fresh BA from scratch: run the BA migrations (seeds 11 categories) then `scripts/port_phase_a_to_ba.py` (loads profiles + slot constraints from `flavor_encoding.json`-derived data via the BA API).

**MCP tools (in `server.py`, all BA-backed):**
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
- `tgii_bootstrap.py --category {gin,aquavit}` → fetches BA shelf bottles for the category, fuzzy-matches against TGII's category sitemap, fetches/parses SVGs, merges LLM-scored entries for bottles not on TGII. Re-runnable; preserves `tgii_{cat}_overrides.json` and `tgii_{cat}_unofficial_scores.json`. Per-category outputs go to `tgii_{cat}_results.json`.
- `seed_flavor_db.py --category {gin,aquavit}` → imports results into the SQLite. Idempotent.
- `export_flavor_encoding.py` / `import_flavor_encoding.py` → dump/restore slot meta + slot constraints + any manual profile edits (`source='manual'`) to `scripts/flavor_encoding.json`. SQLite stays gitignored; manual encoding work lives in this JSON. **Run `export_flavor_encoding.py` after any session that adds slot constraints or hand-corrects a profile** — otherwise the changes only exist on the workstation.

**SQLite restore from scratch** (e.g., volume blown away on the NAS):
```bash
# Per category: bootstrap + seed (one round-trip to BA + TGII per category)
.venv/bin/python scripts/tgii_bootstrap.py --category gin
.venv/bin/python scripts/seed_flavor_db.py --category gin
.venv/bin/python scripts/tgii_bootstrap.py --category aquavit
.venv/bin/python scripts/seed_flavor_db.py --category aquavit
# Manual work
.venv/bin/python scripts/import_flavor_encoding.py
```

To extend to a new category that TGII covers (look at `https://theginisin.com/sitemap_index.xml` for available sitemaps):
1. Add an entry to `CATEGORIES` in `tgii_bootstrap.py` (BA path, min_path_depth, sitemap URL, slug regex, axes, SVG parser — see aquavit for a 6-axis flat-layout example).
2. Add axes to `DEFAULT_AXES` in `flavor_db.py` (auto-seeds on next DB connect).
3. Extend `_ensure_ingredient_meta` in `server.py` to infer the category from BA's materialized_path.
4. Run bootstrap → curate `tgii_{cat}_overrides.json` (slug fixes + `unofficial: true` for off-TGII bottles) → LLM-fill `tgii_{cat}_unofficial_scores.json` → re-run → seed.

For categories TGII doesn't cover (rum, whiskey, etc.), skip the SVG path entirely and LLM-from-description for the whole shelf.

## Engineering Notes

### Ingredient payloads (cocktail create/update)
Always backfill `sort` on each ingredient before sending — the BA API's `CocktailIngredientRequest::fromArray` requires it with no default, returns 500 if missing. Pattern used in `server.py`: `{**ing, "sort": ing.get("sort", idx + 1)}`. Apply to any new write tool that accepts ingredients.

When re-PUTting a whole cocktail (bulk edits), watch the **garnish-as-ingredient** slots: TheCocktailDB-seeded drinks store count garnishes (Olive, Lime, cherry…) as ingredients with `amount=1, units=''`. BA's write validation requires a **numeric `amount` AND a non-empty `units`** on every slot, so echoing back `units=''` 422s ("units required when amount present"), and sending `amount:null` 422s ("amount must be a number"). Fix when rebuilding the payload: if `units` is empty, set `units="whole"` (a unit already used in the DB for count items) and `amount` to `1` if missing. `units` is a free-form string (the data has `"oz Chilled"`, `"tsp superfine"`), so any non-empty label is accepted.

### Testing changes against the live BA API without redeploying
`.venv/bin/python -c "from bar_assistant_mcp.api import BarAssistantAPI; ..."` — import the fixed code directly, hit production BA with the stdio token from `.mcp.json`, clean up after. Faster than rebuilding the container.

FastMCP's `@mcp.tool()` is a passthrough — decorated functions remain plain callables. Test them as `server.bar_describe_slots(668)`, not `.fn(...)` (no wrapper attribute exists).

### Debugging deployed-server errors
Laravel logs go to container stdout, not `storage/logs/laravel.log` (which is empty). Use the Portainer logs API on `bar-assistant-api` to read exceptions. Deploy/debug details in memory (`deployment_guide`, `ba_api_quirks`).

### Picking up a rebuilt image
Portainer's restart endpoint (and `docker restart`) does NOT re-pull — the container stays on its original image ID. After rebuilding `:latest`, PUT the stack YAML to force a recreate. See `deployment_guide` memory for the API call.

### Parsing JSON from NAS-side curls
The NAS `talvola` SSH user has no `python3` in PATH (Asustor stock). When hitting Portainer/etc. APIs over ssh, pipe the response back to the workstation: `ssh ... 'curl -sk -H "X-API-Key: ..." https://localhost:19943/api/...' | python3 -c '...'`. (Watch out for f-string + backslash inside `python3 -c` — use indexed access or move to a heredoc.)

### Building images via the Portainer API: no BuildKit
The Portainer `/docker/build` endpoint doesn't enable BuildKit, so `COPY --chmod=`/`--chown=` fail ("requires BuildKit"). Use plain `COPY` + a root `RUN chmod/chown`. Non-BuildKit variants live alongside the upstream Dockerfiles: BA `Dockerfile.prod` + `dev/sandbox/Dockerfile.sandbox`; build with `&dockerfile=Dockerfile.prod` in the build URL.

### Build-context rsync flattens `src/`
`rsync ... Dockerfile pyproject.toml src/ <nas>:build/` copies the *contents* of `src/` into the build root, not `src/` itself. After rsync, fix on the NAS: `cd build && rm -rf src && mkdir src && mv bar_assistant_mcp src/` before tarring + building.

### Stack compose drift → container-name conflict on PUT
A running container's image can differ from its stack's YAML (e.g. a manually-swapped `salt-rim:custom` while the YAML says `salt-rim:v4`). PUTting fresh YAML then fails with "container name already in use." Fix: DELETE the conflicting container(s) first via the Portainer API (named volumes like `bar_data` persist across removal), then re-PUT.

### Legacy mixed-case slugs break variant edits (v6)
TheCocktailDB-seeded cocktails stored slugs with a mixed-case random suffix (e.g. `boulevardier-MBv9P`). BA v6's `Slug` value object (`src/Domain/Common/Slug.php`) enforces `^[a-z0-9]+(?:-[a-z0-9]+)*$`, so loading such a cocktail through the domain repo (`EloquentCocktailRepository::map`, the write path) throws a 500. PUTting a **variant** 500s because `updateCocktail` calls `findById` on the *parent* to validate `variantOf` — the bad slug is the parent's, not the one being edited. The slug isn't settable via the cocktail API, so fix it in the live sqlite: `UPDATE cocktails SET slug=lower(slug) WHERE slug<>lower(slug);` (verify `collisions=0` first). All 34 were case-only and normalized 2026-05-30.

### Reaching the live BA sqlite / running commands in the prod container
Portainer is reachable **directly from the workstation** at `https://192.168.1.64:19943` (no NAS hop needed; the NAS `talvola` user has neither docker-socket access nor `python3`). Drive the Docker **exec** API in two POSTs: create exec (`/endpoints/3/docker/containers/<id>/exec` with `{"AttachStdout":true,"AttachStderr":true,"Tty":true,"Cmd":["sh","-c",...]}`), then start it (`/endpoints/3/docker/exec/<execId>/start` with `{"Detach":false,"Tty":true}`). Live DB = `/var/www/cocktails/storage/bar-assistant/database.ba3.sqlite` (the `storage/database.sqlite` file is empty); `sqlite3` is in the image. Back up with `cp <db> <db>.bak-<tag>` before any write.

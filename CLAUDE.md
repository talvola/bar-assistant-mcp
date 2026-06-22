# Bar Assistant MCP Server

This is the MCP (Model Context Protocol) server for Bar Assistant, providing tools to manage cocktails, ingredients, and bar inventory.

## Related Projects

- `/home/erik/bar-assistant` - Bar Assistant API (Laravel backend)
- `/home/erik/bar-assistant-mcp` - This MCP server (current)
- `/home/erik/vue-salt-rim` - Salt Rim Web UI (Vue.js frontend)

## Usage rules — single source of truth (shared with ALL MCP clients)

The ingredient/cocktail **usage rules** (generic-vs-specific policy + keep-policy, common generic
IDs, glass IDs, cocktail-creation guide, flavor workflow) live in
`src/bar_assistant_mcp/usage_rules.md`. The server loads that file into FastMCP's `instructions`,
so it is delivered to **every** MCP client — including the iOS/desktop Claude app — and added to the
model's system prompt. It is `@import`ed below so this Claude Code session reads the identical text.
**Edit usage rules in `usage_rules.md`, not here.** This CLAUDE.md keeps only Claude-Code/dev-specific
guidance (the URL-add workflow, Google-Sheets sync, build/deploy, server internals).

> Deploy note: the iOS app only picks up `usage_rules.md` / `instructions` changes after the remote
> MCP container is rebuilt + recreated (LAN-only Portainer). The stdio/Claude-Code path picks them up
> on next launch automatically.

@src/bar_assistant_mcp/usage_rules.md

## Adding Cocktails from URLs

When adding cocktails from blog posts or websites, follow this process:

### 1. Fetch and Check

- Use `WebFetch` to extract the recipe from the URL
- Search for the cocktail name with `bar_search_cocktails` to check if it already exists
- If it exists, offer to update missing fields (description, source, image, garnish, tags)

### 2. Ingredient Strategy

Generic vs. specific, the keep-policy, and common generic IDs are in `usage_rules.md`
(imported above). Default base spirits to generic; only go specific when the recipe names the
brand, the brand defines the drink, or Erik asks.

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
   - Leave **C/Notes blank** too (it's empty on every enriched row); "A–G" here means the data columns A,B,D,E,F,G.
   - Keep **Category (B) a plain label** matching the sheet (Rum, Whiskey, Bacanora, Sherry) — strip parenthetical
     qualifiers research agents add (e.g. "Bacanora (agave spirit)" → "Bacanora", "Whiskey (limited release)" → "Whiskey").

**Description voice:** match existing rows (see rows ~180–204 to calibrate) — em-dash-heavy, includes process specifics (mash bill / botanicals / distillation / aging), tasting notes in nose / palate / finish format when documented, and one sentence on cocktail role. No marketing fluff. Use real research (producer pages, Difford's, Drinkhacker, retailer copy), not fabricated detail.

**Verify identity, not just the assumed style** — a request's framing can be wrong; research overturned it twice
(Astor Amaro is Sweetdram-made, not Forthave's Monofloral; Old Potrero Christmas Spirit is beer-distilled, not malted rye).

Don't ask permission to do the sync — do it after each qualifying ingredient creation and report what changed.

**Bulk backfill (Erik pre-adds name-only rows):** when many Column-A-only rows appear, fan out parallel
research subagents (~5–6 bottles each, primed with the rows ~180–204 voice calibration), then write all
enriched cells in one `update_cells` over `B<start>:G<end>` (leave C/Notes + H/Status blank).
- Major retailer pages (astorwines, klwines, thewhiskyexchange, …) **403 on WebFetch** — research via
  subagents using WebSearch + producer/Difford's/SherryNotes/Drinkhacker pages, or have Erik paste the text.
- Retailer **product-page ABV is often wrong** — trust the physical-label ABV Erik reports over it
  (Astor Amaro page 30% vs label 34%; Il Mallo page 38% vs bottle 42%).

## Common Ingredient IDs & Glass IDs

Moved to `usage_rules.md` (imported above, and served to all MCP clients). The agricole
style-split detail (Blanc 650 / Vieux 651, clairin-under-Blanc rationale) lives there too.
Extra dev-only references not in the shared file: Anise Liqueurs 436 · Rich Demerara Syrup 494 ·
Lemon peel 339 · Orange peel 311 · Maraschino cherry 310.

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

### Ingredient create/update gotchas
- **`POST /api/ingredients` returns an empty body** (not the created object). Don't read the new id from the response — look it up afterward by exact name: `GET /api/ingredients?filter[name]=<name>` then match `x["name"]==name` (the filter is a substring match, so filter then exact-match in code).
- **Ingredient update 422s if you echo back more than one image** ("images field must not have more than 1 items"). Some legacy/imported bottles carry 2 images; trim to `images[:1]` when rebuilding the update payload. Same class of gotcha as the garnish-units one.
- **Genericizing by style → subcategory:** when a generic category is too coarse (e.g. Rhum Agricole spans blanc/vieux/clairin), create style subcategories under it and reparent the bottles, mirroring how the tree already splits gin (London Dry/Old Tom/Navy Strength) and tequila (Blanco/Reposado/Añejo). The per-category flavor axes refine *within* a style; the subcategory handles the coarse split. See the Rhum Agricole entry under "Common Ingredient IDs".

### Auditing which cocktails use an ingredient
`GET /api/cocktails?filter[specific_ingredients]=<id>&per_page=100` returns **full** cocktail objects (name, `source`, `ingredients`), not just refs — use `meta.total` for a count and the `source`/`name` fields to classify generic-recipe (genericize) vs brand-named (keep specific). To bulk-swap an ingredient across recipes, GET each cocktail and re-PUT the whole `ingredients` array with the one id changed, preserving sort/units/substitutes/utensils/year/parent (apply the garnish empty-units + `sort` fixes above). To find house bottles to clean up: pull all `/api/ingredients`, use `hierarchy.root_ingredient_id` + `materialized_path` to locate leaf bottles under a base-spirit root, rank by `cocktails_count`.

### Testing changes against the live BA API without redeploying
`.venv/bin/python -c "from bar_assistant_mcp.api import BarAssistantAPI; ..."` — import the fixed code directly, hit production BA with the stdio token from `.mcp.json`, clean up after. Faster than rebuilding the container.

FastMCP's `@mcp.tool()` is a passthrough — decorated functions remain plain callables. Test them as `server.bar_describe_slots(668)`, not `.fn(...)` (no wrapper attribute exists).

### Debugging deployed-server errors
Laravel logs go to container stdout, not `storage/logs/laravel.log` (which is empty). Use the Portainer logs API on `bar-assistant-api` to read exceptions. Deploy/debug details in memory (`deployment_guide`, `ba_api_quirks`).

### Ingredient/cocktail list filters (v6 query gotchas)
The `/api/ingredients` and `/api/cocktails` list endpoints filter via Spatie QueryBuilder
(`app/Http/Filters/{Ingredient,Cocktail}QueryFilter.php`). Two traps the MCP tools now handle:
- **No `category_id` filter on ingredients** — it 400s. Categories ARE ingredients in v6, so
  filter a category's subtree with `filter[descendants_of]=<category ingredient id>` (recursive) or
  its direct children with `filter[parent_ingredient_id]` (`=null` → roots only). The MCP
  `bar_list_ingredients(category=…)` maps to `descendants_of`.
- **Boolean callback filters only honor the string `"true"`** — `filter[on_shelf]=1` (and
  `filter[favorites]=1`) are silently ignored (the callback checks `=== true`), returning the
  *unfiltered* set. Always send `"true"`. The old MCP code shipped `"1"`/`"0"` and so never
  actually filtered.
- **No server-side "missing image" or "leaf/specific-only" filter.** `bar_list_ingredients`
  (`specific_only`, `missing_image_only`) and `bar_list_cocktails` (`missing_image_only`) implement
  these client-side: page all results with `include=images,descendants`, then filter where
  `images` is empty / `hierarchy.descendants` is empty (leaf = specific bottle). Image/descendant
  relations are absent unless `include`d.

### Triaging a down stack (esp. after a NAS reboot)
Localize the failure with a probe ladder before touching anything — expected codes:
MCP OAuth discovery (`erikbar.../.well-known/oauth-authorization-server`) 200 · MCP `/mcp` 401 ·
Salt Rim `/` 200 · BA API `erikbarapi.../api/server/version` 200. iOS MCP login proxies to the BA
API, so a BA 502 breaks login while MCP itself probes healthy.
**`running (healthy)` can be a lie:** BA's healthcheck is a `runc exec`, which silently fails
("no space left on device") when the NAS `/tmp` tmpfs fills — the container shows `healthy` while
the app is wedged and unreachable on `:3000`/its bridge IP. Restart the one container (not a stack
recreate): `POST /endpoints/3/docker/containers/bar-assistant-api/restart` (204). The recurring
`/tmp`-filler is Plex sonic analysis — see `project_plex_tmp_breaks_docker` memory.

### Picking up a rebuilt image
Portainer's restart endpoint (and `docker restart`) does NOT re-pull — the container stays on its original image ID. After rebuilding `:latest`, PUT the stack YAML to force a recreate. See `deployment_guide` memory for the API call.

### Redeploying the MCP server (so iOS picks up usage_rules.md / instructions changes)
Portainer is reachable straight from the workstation (`https://192.168.1.64:19943`), so skip the rsync-to-NAS/flatten dance — build the context locally and POST it. Full command sequence in `deployment_guide` memory; in brief:
1. Rollback tag: `POST /endpoints/3/docker/images/bar-assistant-mcp:v6/tag?repo=bar-assistant-mcp&tag=pre-<label>`
2. `tar -cf ctx.tar --exclude=__pycache__ Dockerfile pyproject.toml README.md src` → `POST /endpoints/3/docker/build?t=bar-assistant-mcp:v6&dockerfile=Dockerfile` (Content-Type: application/x-tar). Stack 5 runs the **`:v6`** tag, not `:latest`.
3. `PUT /api/stacks/5?endpointId=3` with `{"StackFileContent":<yaml>,"Env":[],"Prune":false}` to **recreate** (a restart won't pick up the rebuilt tag).
Recreate drops in-memory OAuth tokens → **iOS must re-auth** on next connect (which is when it pulls the new instructions). The stdio/Claude-Code side gets `usage_rules.md` changes on next launch with no deploy.

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

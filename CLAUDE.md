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
- **ingredients**: Array with ingredient_id, amount, units, sort order
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

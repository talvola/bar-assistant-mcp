"""Bar Assistant MCP Server - Main server implementation."""

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .api import BarAssistantAPI
from . import flavor as fl
from . import flavor_db as fdb

# Initialize FastMCP server (auth wired in main() for HTTP mode)
mcp = FastMCP(
    "bar-assistant",
    host="0.0.0.0",
    port=8100,
    streamable_http_path="/mcp",
)

# Global API client (initialized on startup for stdio mode)
_api: BarAssistantAPI | None = None

# OAuth provider reference (set in main() for HTTP mode)
_oauth_provider = None


def get_api() -> BarAssistantAPI:
    """Get the API client for the current request.

    In stdio mode: returns the global client (env var auth).
    In HTTP mode: looks up the BA token from the OAuth access token.
    """
    if _api is not None:
        return _api

    # HTTP mode: resolve per-request API client from OAuth token
    if _oauth_provider is not None:
        from mcp.server.auth.middleware.auth_context import get_access_token

        from .auth import StoredAccessToken

        access_token = get_access_token()
        if access_token is not None and isinstance(access_token, StoredAccessToken):
            return BarAssistantAPI(
                access_token.ba_url, access_token.ba_token, access_token.ba_bar_id
            )

    raise RuntimeError(
        "Bar Assistant API not configured. "
        "Set BAR_ASSISTANT_URL and BAR_ASSISTANT_TOKEN environment variables."
    )


# ===== Formatting Helpers =====


def format_cocktail(cocktail: dict[str, Any], detailed: bool = False) -> str:
    """Format a cocktail for display."""
    cocktail_id = cocktail.get('id', '')
    name = cocktail.get('name', 'Unknown')
    lines = [f"**{name}** (ID: {cocktail_id})" if cocktail_id else f"**{name}**"]

    if cocktail.get("short_description"):
        lines.append(f"_{cocktail['short_description']}_")

    # Ingredients
    ingredients = cocktail.get("ingredients", [])
    if ingredients:
        lines.append("\nIngredients:")
        for ing in ingredients:
            name = ing.get("ingredient", {}).get("name", ing.get("name", "Unknown"))
            amount = ing.get("amount", "")
            units = ing.get("units", "")
            optional = " (optional)" if ing.get("optional") else ""
            lines.append(f"  - {amount} {units} {name}{optional}".strip())

    # Instructions
    if detailed and cocktail.get("instructions"):
        lines.append(f"\nInstructions:\n{cocktail['instructions']}")

    # Glass and method
    glass = cocktail.get("glass", {})
    method = cocktail.get("method", {})
    if glass or method:
        meta = []
        if glass and glass.get("name"):
            meta.append(f"Glass: {glass['name']}")
        if method and method.get("name"):
            meta.append(f"Method: {method['name']}")
        if meta:
            lines.append("\n" + " | ".join(meta))

    # Tags
    tags = cocktail.get("tags", [])
    if tags:
        tag_names = [t.get("name", "") for t in tags if t.get("name")]
        if tag_names:
            lines.append(f"Tags: {', '.join(tag_names)}")

    # ABV and rating
    if detailed:
        if cocktail.get("abv"):
            lines.append(f"ABV: {cocktail['abv']}%")
        if cocktail.get("average_rating"):
            lines.append(f"Rating: {cocktail['average_rating']}/5")

    return "\n".join(lines)


def format_ingredient(ingredient: dict[str, Any], detailed: bool = False) -> str:
    """Format an ingredient for display."""
    name = ingredient.get('name', 'Unknown')
    ing_id = ingredient.get('id', '')
    lines = [f"**{name}** (ID: {ing_id})"]

    if ingredient.get("description") and detailed:
        lines.append(f"_{ingredient['description']}_")

    category = ingredient.get("category", {})
    if category and category.get("name"):
        lines.append(f"Category: {category['name']}")

    if ingredient.get("strength"):
        lines.append(f"Strength: {ingredient['strength']}%")

    parent = ingredient.get("parent_ingredient", {})
    if parent and parent.get("name"):
        lines.append(f"Parent: {parent['name']}")

    return "\n".join(lines)


# ===== Cocktail Tools =====


@mcp.tool()
def bar_search_cocktails(query: str, limit: int = 10) -> str:
    """Search for cocktails by name. Returns matching cocktails with their ingredients."""
    client = get_api()
    data = client.search_cocktails(query, limit)
    cocktails = data.get("data", [])
    if not cocktails:
        return f"No cocktails found matching '{query}'"
    formatted = [format_cocktail(c) for c in cocktails]
    return f"Found {len(cocktails)} cocktails:\n\n" + "\n\n---\n\n".join(formatted)


@mcp.tool()
def bar_get_cocktail(id: str) -> str:
    """Get detailed information about a specific cocktail by ID or slug."""
    client = get_api()
    data = client.get_cocktail(id)
    cocktail = data.get("data", data)
    return format_cocktail(cocktail, detailed=True)


@mcp.tool()
def bar_list_cocktails(
    limit: int = 25,
    page: int = 1,
    favorites_only: bool | None = None,
    tag: str | None = None,
    sort: str | None = None,
) -> str:
    """List cocktails with optional filters. Use to browse the cocktail collection."""
    client = get_api()
    data = client.list_cocktails(
        limit=limit,
        page=page,
        filter_favorites=favorites_only,
        sort=sort,
    )
    cocktails = data.get("data", [])
    meta = data.get("meta", {})
    total = meta.get("total", len(cocktails))
    formatted = [f"- {c.get('name')}" for c in cocktails]
    return f"Cocktails ({len(cocktails)} of {total}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_makeable_cocktails(user_id: int = 1) -> str:
    """Get cocktails that can be made with ingredients currently on the shelf."""
    client = get_api()
    data = client.get_makeable_cocktails(user_id)
    cocktails = data.get("data", [])
    if not cocktails:
        return "No cocktails can be made with current shelf ingredients."
    formatted = [f"- {c.get('name')}" for c in cocktails]
    return f"You can make {len(cocktails)} cocktails:\n" + "\n".join(formatted)


@mcp.tool()
def bar_favorite_cocktails(user_id: int = 1) -> str:
    """Get user's favorite cocktails."""
    client = get_api()
    data = client.get_favorite_cocktails(user_id)
    cocktails = data.get("data", [])
    if not cocktails:
        return "No favorite cocktails."
    formatted = [f"- {c.get('name')}" for c in cocktails]
    return f"Favorite cocktails ({len(cocktails)}):\n" + "\n".join(formatted)


# ===== Ingredient Tools =====


@mcp.tool()
def bar_search_ingredients(query: str, limit: int = 10) -> str:
    """Search for ingredients by name."""
    client = get_api()
    data = client.search_ingredients(query, limit)
    ingredients = data.get("data", [])
    if not ingredients:
        return f"No ingredients found matching '{query}'"
    formatted = [format_ingredient(i) for i in ingredients]
    return f"Found {len(ingredients)} ingredients:\n\n" + "\n\n---\n\n".join(formatted)


@mcp.tool()
def bar_get_ingredient(id: str) -> str:
    """Get detailed information about a specific ingredient."""
    client = get_api()
    data = client.get_ingredient(id)
    ingredient = data.get("data", data)
    return format_ingredient(ingredient, detailed=True)


@mcp.tool()
def bar_list_ingredients(
    limit: int = 50,
    page: int = 1,
    on_shelf_only: bool | None = None,
    sort: str | None = None,
) -> str:
    """List ingredients with optional filters."""
    client = get_api()
    data = client.list_ingredients(
        limit=limit,
        page=page,
        filter_on_shelf=on_shelf_only,
        sort=sort,
    )
    ingredients = data.get("data", [])
    meta = data.get("meta", {})
    total = meta.get("total", len(ingredients))
    formatted = [f"- {i.get('name')}" for i in ingredients]
    return f"Ingredients ({len(ingredients)} of {total}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_ingredient_cocktails(id: str) -> str:
    """Get cocktails that use a specific ingredient."""
    client = get_api()
    data = client.get_ingredient_cocktails(id)
    cocktails = data.get("data", [])
    if not cocktails:
        return "No cocktails use this ingredient."
    formatted = [f"- {c.get('name')}" for c in cocktails]
    return f"Cocktails using this ingredient ({len(cocktails)}):\n" + "\n".join(formatted)


# ===== Shelf Tools =====


@mcp.tool()
def bar_get_shelf(user_id: int = 1) -> str:
    """Get ingredients currently on the user's shelf (what they have available)."""
    client = get_api()
    data = client.get_shelf(user_id)
    ingredients = data.get("data", [])
    if not ingredients:
        return "Shelf is empty."
    formatted = [f"- {i.get('name')}" for i in ingredients]
    return f"Shelf ingredients ({len(ingredients)}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_add_to_shelf(ingredient_ids: list[int], user_id: int = 1) -> str:
    """Add ingredients to the shelf."""
    client = get_api()
    client.add_to_shelf(user_id, ingredient_ids)
    return f"Added {len(ingredient_ids)} ingredient(s) to shelf."


@mcp.tool()
def bar_remove_from_shelf(ingredient_ids: list[int], user_id: int = 1) -> str:
    """Remove ingredients from the shelf."""
    client = get_api()
    client.remove_from_shelf(user_id, ingredient_ids)
    return f"Removed {len(ingredient_ids)} ingredient(s) from shelf."


# ===== Shopping List Tools =====


@mcp.tool()
def bar_get_shopping_list(user_id: int = 1) -> str:
    """Get the user's shopping list."""
    client = get_api()
    data = client.get_shopping_list(user_id)
    items = data.get("data", [])
    if not items:
        return "Shopping list is empty."
    formatted = [f"- {i.get('name')}" for i in items]
    return f"Shopping list ({len(items)}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_add_to_shopping_list(ingredient_ids: list[int], user_id: int = 1) -> str:
    """Add ingredients to the shopping list."""
    client = get_api()
    client.add_to_shopping_list(user_id, ingredient_ids)
    return f"Added {len(ingredient_ids)} item(s) to shopping list."


# ===== Collection Tools =====


@mcp.tool()
def bar_list_collections() -> str:
    """List cocktail collections."""
    client = get_api()
    data = client.list_collections()
    collections = data.get("data", [])
    if not collections:
        return "No collections found."
    formatted = [f"- {c.get('name')} (ID: {c.get('id')})" for c in collections]
    return f"Collections ({len(collections)}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_get_collection(id: int) -> str:
    """Get a specific cocktail collection with its cocktails."""
    client = get_api()
    data = client.get_collection(id)
    collection = data.get("data", data)
    name = collection.get("name", "Unknown")
    cocktails = collection.get("cocktails", [])
    formatted = [f"- {c.get('name')}" for c in cocktails]
    return f"**{name}**\n\nCocktails ({len(cocktails)}):\n" + "\n".join(formatted)


# ===== Reference Data Tools =====


@mcp.tool()
def bar_list_tags() -> str:
    """List all cocktail tags."""
    client = get_api()
    data = client.list_tags()
    tags = data.get("data", [])
    formatted = [f"- {t.get('name')} (ID: {t.get('id')})" for t in tags]
    return f"Tags ({len(tags)}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_list_glasses() -> str:
    """List all glass types."""
    client = get_api()
    data = client.list_glasses()
    glasses = data.get("data", [])
    formatted = [f"- {g.get('name')} (ID: {g.get('id')})" for g in glasses]
    return f"Glasses ({len(glasses)}):\n" + "\n".join(formatted)


@mcp.tool()
def bar_list_methods() -> str:
    """List cocktail preparation methods."""
    client = get_api()
    data = client.list_methods()
    methods = data.get("data", [])
    formatted = [f"- {m.get('name')} (ID: {m.get('id')})" for m in methods]
    return f"Methods ({len(methods)}):\n" + "\n".join(formatted)


# ===== Stats =====


@mcp.tool()
def bar_stats() -> str:
    """Get bar statistics (total cocktails, ingredients, etc)."""
    client = get_api()
    data = client.get_bar_stats()
    stats = data.get("data", data)
    lines = ["**Bar Statistics**"]
    if isinstance(stats, dict):
        for key, value in stats.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    return "\n".join(lines)


# ===== Image Upload Tools =====


@mcp.tool()
def bar_upload_image(image_url: str, copyright: str | None = None) -> str:
    """Upload an image from a URL. Returns the image ID to use when creating cocktails or ingredients."""
    client = get_api()
    image_data: dict[str, Any] = {"image": image_url}
    if copyright:
        image_data["copyright"] = copyright
    data = client.upload_images([image_data])
    images = data.get("data", [])
    if images:
        img = images[0]
        return f"Image uploaded successfully!\nID: {img.get('id')}\nPath: {img.get('file_path')}"
    return "Failed to upload image"


@mcp.tool()
def bar_upload_image_file(file_path: str, copyright: str | None = None) -> str:
    """Upload an image from a local file path. Returns the image ID to use when creating cocktails or ingredients."""
    client = get_api()
    p = Path(file_path)
    if not p.exists():
        return f"Error: File not found: {file_path}"

    file_bytes = p.read_bytes()
    base64_data = base64.b64encode(file_bytes).decode("utf-8")

    mime_type, _ = mimetypes.guess_type(str(p))
    if not mime_type:
        ext = p.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(ext, "image/jpeg")

    data_url = f"data:{mime_type};base64,{base64_data}"
    image_data: dict[str, Any] = {"image": data_url}
    if copyright:
        image_data["copyright"] = copyright

    data = client.upload_images([image_data])
    images = data.get("data", [])
    if images:
        img = images[0]
        return f"Image uploaded successfully from local file!\nID: {img.get('id')}\nPath: {img.get('file_path')}"
    return "Failed to upload image"


# ===== Create/Update/Delete Tools =====


@mcp.tool()
def bar_create_ingredient(
    name: str,
    strength: float = 0,
    description: str | None = None,
    origin: str | None = None,
    parent_ingredient_id: int | None = None,
    images: list[int] | None = None,
) -> str:
    """Create a new ingredient. Use parent_ingredient_id to place it in the hierarchy (e.g., under 'Gin' or 'Bourbon')."""
    client = get_api()
    ingredient_data: dict[str, Any] = {"name": name, "strength": strength}
    if description:
        ingredient_data["description"] = description
    if origin:
        ingredient_data["origin"] = origin
    if parent_ingredient_id:
        ingredient_data["parent_ingredient_id"] = parent_ingredient_id
    if images:
        ingredient_data["images"] = images

    data = client.create_ingredient(ingredient_data)
    ingredient = data.get("data", data)
    return f"Created ingredient: **{ingredient.get('name')}** (ID: {ingredient.get('id')})"


@mcp.tool()
def bar_create_cocktail(
    name: str,
    instructions: str,
    ingredients: list[dict[str, Any]],
    description: str | None = None,
    source: str | None = None,
    garnish: str | None = None,
    glass_id: int | None = None,
    cocktail_method_id: int | None = None,
    tags: list[str] | None = None,
    images: list[int] | None = None,
    parent_cocktail_id: int | None = None,
) -> str:
    """Create a new cocktail recipe with ingredients, instructions, and optional image."""
    client = get_api()
    # BA API's CocktailIngredientRequest::fromArray reads $source['sort'] without a
    # default, so omitting it produces a 500. Backfill positionally.
    normalized_ingredients = [
        {**ing, "sort": ing.get("sort", idx + 1)}
        for idx, ing in enumerate(ingredients)
    ]
    cocktail_data: dict[str, Any] = {
        "name": name,
        "instructions": instructions,
        "ingredients": normalized_ingredients,
    }
    if description:
        cocktail_data["description"] = description
    if source:
        cocktail_data["source"] = source
    if garnish:
        cocktail_data["garnish"] = garnish
    if glass_id:
        cocktail_data["glass_id"] = glass_id
    if cocktail_method_id:
        cocktail_data["cocktail_method_id"] = cocktail_method_id
    if tags:
        cocktail_data["tags"] = tags
    if images:
        cocktail_data["images"] = images
    if parent_cocktail_id:
        cocktail_data["parent_cocktail_id"] = parent_cocktail_id

    data = client.create_cocktail(cocktail_data)
    cocktail = data.get("data", data)
    return (
        f"Created cocktail: **{cocktail.get('name')}** (ID: {cocktail.get('id')})\n\n"
        + format_cocktail(cocktail, detailed=True)
    )


@mcp.tool()
def bar_update_cocktail(
    id: str,
    name: str | None = None,
    instructions: str | None = None,
    description: str | None = None,
    source: str | None = None,
    garnish: str | None = None,
    glass_id: int | None = None,
    cocktail_method_id: int | None = None,
    tags: list[str] | None = None,
    ingredients: list[dict[str, Any]] | None = None,
    images: list[int] | None = None,
    parent_cocktail_id: int | None = None,
) -> str:
    """Update an existing cocktail. Only provide fields you want to change."""
    client = get_api()

    # Fetch existing cocktail to preserve fields not being updated
    existing_data = client.get_cocktail(id)
    existing = existing_data.get("data") if existing_data else None
    if not existing:
        existing = existing_data if isinstance(existing_data, dict) else {}

    # Start with required fields from existing cocktail
    cocktail_data: dict[str, Any] = {
        "name": existing.get("name"),
        "instructions": existing.get("instructions"),
    }

    # Preserve existing ingredients if not provided (convert format)
    if ingredients is None:
        existing_ingredients = existing.get("ingredients", [])
        cocktail_data["ingredients"] = [
            {
                "ingredient_id": ing.get("ingredient", {}).get("id") or ing.get("ingredient_id"),
                "amount": ing.get("amount", 0),
                "units": ing.get("units", ""),
                "optional": ing.get("optional", False),
                "sort": ing.get("sort", idx + 1),
            }
            for idx, ing in enumerate(existing_ingredients)
            if ing.get("ingredient", {}).get("id") or ing.get("ingredient_id")
        ]

    # Preserve existing tags if not provided
    if tags is None:
        existing_tags = existing.get("tags", [])
        cocktail_data["tags"] = [
            tag.get("name") for tag in existing_tags if tag.get("name")
        ]

    # Preserve existing images if not provided
    if images is None:
        existing_images = existing.get("images", [])
        cocktail_data["images"] = [
            img.get("id") for img in existing_images if img.get("id")
        ]

    # Preserve other optional fields if they exist
    for key in ["description", "source", "garnish"]:
        if existing.get(key):
            cocktail_data[key] = existing[key]
    glass = existing.get("glass")
    if glass and isinstance(glass, dict) and glass.get("id"):
        cocktail_data["glass_id"] = glass["id"]
    method = existing.get("method")
    if method and isinstance(method, dict) and method.get("id"):
        cocktail_data["cocktail_method_id"] = method["id"]
    parent = existing.get("parent_cocktail")
    if parent and isinstance(parent, dict) and parent.get("id"):
        cocktail_data["parent_cocktail_id"] = parent["id"]

    # Override with provided changes
    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name
    if instructions is not None:
        updates["instructions"] = instructions
    if description is not None:
        updates["description"] = description
    if source is not None:
        updates["source"] = source
    if garnish is not None:
        updates["garnish"] = garnish
    if glass_id is not None:
        updates["glass_id"] = glass_id
    if cocktail_method_id is not None:
        updates["cocktail_method_id"] = cocktail_method_id
    if tags is not None:
        updates["tags"] = tags
    if ingredients is not None:
        updates["ingredients"] = [
            {**ing, "sort": ing.get("sort", idx + 1)}
            for idx, ing in enumerate(ingredients)
        ]
    if images is not None:
        updates["images"] = images
    if parent_cocktail_id is not None:
        updates["parent_cocktail_id"] = parent_cocktail_id
    cocktail_data.update(updates)

    data = client.update_cocktail(id, cocktail_data)
    cocktail = data.get("data") if data else None
    if not cocktail:
        cocktail = data if isinstance(data, dict) and data.get("name") else None
    if cocktail and isinstance(cocktail, dict):
        return f"Updated cocktail: **{cocktail.get('name')}** (ID: {cocktail.get('id')})"
    return f"Updated cocktail: **{cocktail_data.get('name')}** (ID: {id})"


@mcp.tool()
def bar_delete_cocktail(id: str) -> str:
    """Delete a cocktail by ID or slug."""
    client = get_api()
    client.delete_cocktail(id)
    return f"Deleted cocktail: {id}"


@mcp.tool()
def bar_update_ingredient(
    id: str,
    name: str | None = None,
    strength: float | None = None,
    description: str | None = None,
    origin: str | None = None,
    parent_ingredient_id: int | None = None,
    images: list[int] | None = None,
) -> str:
    """Update an existing ingredient. Only provide fields you want to change."""
    client = get_api()

    # Fetch existing ingredient to preserve fields not being updated
    existing_data = client.get_ingredient(id)
    existing = existing_data.get("data") if existing_data else None
    if not existing:
        existing = existing_data if isinstance(existing_data, dict) else {}

    ingredient_data: dict[str, Any] = {"name": existing.get("name")}

    # Preserve existing optional fields
    if existing.get("strength") is not None:
        ingredient_data["strength"] = existing["strength"]
    if existing.get("description"):
        ingredient_data["description"] = existing["description"]
    if existing.get("origin"):
        ingredient_data["origin"] = existing["origin"]
    parent = existing.get("hierarchy", {}).get("parent_ingredient")
    if parent and parent.get("id"):
        ingredient_data["parent_ingredient_id"] = parent["id"]

    # Preserve existing images if not provided
    if images is None:
        existing_images = existing.get("images", [])
        ingredient_data["images"] = [
            img.get("id") for img in existing_images if img.get("id")
        ]

    # Override with provided changes
    if name is not None:
        ingredient_data["name"] = name
    if strength is not None:
        ingredient_data["strength"] = strength
    if description is not None:
        ingredient_data["description"] = description
    if origin is not None:
        ingredient_data["origin"] = origin
    if parent_ingredient_id is not None:
        ingredient_data["parent_ingredient_id"] = parent_ingredient_id
    if images is not None:
        ingredient_data["images"] = images

    data = client.update_ingredient(id, ingredient_data)
    ingredient = data.get("data") if data else None
    if not ingredient:
        ingredient = data if isinstance(data, dict) and data.get("name") else None
    if ingredient and isinstance(ingredient, dict):
        return f"Updated ingredient: **{ingredient.get('name')}** (ID: {ingredient.get('id')})"
    return f"Updated ingredient: **{ingredient_data.get('name')}** (ID: {id})"


@mcp.tool()
def bar_delete_ingredient(id: str) -> str:
    """Delete an ingredient by ID or slug."""
    client = get_api()
    client.delete_ingredient(id)
    return f"Deleted ingredient: {id}"


# ===== Flavor Matching =====
#
# These tools layer a per-category flavor-axis system on top of BA's ingredient
# and cocktail data. Profiles + slot constraints live in a sidecar SQLite (see
# flavor_db.py); the engine is in flavor.py. Bootstrap data and design notes
# are in scripts/ and the project memory ("bar_assistant_roadmap").


_GIN_AXES_HELP = (
    "TGII gin axes (0–3 integer scale): juniper, citrus, floral, heat, spice, herbal, fruited."
)


def _ensure_ingredient_meta(ingredient_id: int) -> tuple[str, str, float | None]:
    """Ensure ingredient_meta has a row for this BA ingredient; return (name, category, proof)."""
    with fdb.connect() as conn:
        row = conn.execute(
            "SELECT name, category, proof FROM ingredient_meta WHERE ingredient_id=?",
            (ingredient_id,),
        ).fetchone()
        if row and row["name"]:
            return row["name"], row["category"] or "", row["proof"]

    ing = get_api().get_ingredient(ingredient_id).get("data", {})
    name = ing.get("name", f"#{ingredient_id}")
    # Category inference from BA's materialized_path
    path = (ing.get("materialized_path") or "").strip("/")
    category = ""
    if path.startswith("363/383"):
        category = "gin"
    elif path.startswith("363/403"):
        category = "aquavit"
    elif path.startswith("363/370/371"):
        category = "bourbon"
    elif path.startswith("363/370/347"):
        category = "rye"
    elif path.startswith("363/370/372"):
        category = "scotch"
    proof = (ing.get("strength") * 2) if ing.get("strength") else None
    with fdb.connect() as conn:
        fdb.upsert_ingredient_meta(conn, ingredient_id, name=name, category=category, proof=proof)
    return name, category, proof


@mcp.tool()
def bar_list_flavor_axes(category: str = "gin") -> str:
    """List the flavor axes defined for a category (e.g. 'gin').

    Axes are per-category and integer-scored. Gin uses The Gin Is In's 7-axis
    0–3 system. Use this to discover valid axis names before setting profiles
    or slot constraints.
    """
    with fdb.connect() as conn:
        axes = fdb.get_axes(conn, category)
    if not axes:
        return f"No axes defined for category '{category}'. Configure with bar_set_flavor_axes."
    return f"**{category}** axes (0–3): " + ", ".join(axes)


@mcp.tool()
def bar_get_flavor_profile(ingredient_id: int) -> str:
    """Return the flavor profile recorded for an ingredient (specific bottle).

    Profiles are per-axis integer scores on the category's scale (gin: 0–3 on
    juniper/citrus/floral/heat/spice/herbal/fruited). Returns provenance too
    (source = tgii / llm_from_description / manual; confidence; notes).
    """
    with fdb.connect() as conn:
        data = fdb.get_profile(conn, ingredient_id)
    if not data:
        return f"No flavor profile recorded for ingredient {ingredient_id}."
    lines = [f"**Profile for ingredient {ingredient_id}**"]
    lines.append("  " + " ".join(f"{a}={v}" for a, v in data["profile"].items()))
    lines.append(f"  source: {data['source']}   confidence: {data['confidence'] or '-'}   scored: {data['scored_at']}")
    if data["notes"]:
        lines.append(f"  notes: {data['notes']}")
    return "\n".join(lines)


@mcp.tool()
def bar_set_flavor_profile(
    ingredient_id: int,
    profile: dict[str, int],
    source: str = "manual",
    confidence: str | None = None,
    notes: str | None = None,
) -> str:
    """Set or update the flavor profile for an ingredient (partial updates allowed).

    Args:
        ingredient_id: BA ingredient_id of the specific bottle.
        profile: dict of axis → integer score. Unspecified axes are left as-is.
                 For gin: any of juniper, citrus, floral, heat, spice, herbal,
                 fruited; values 0–3. See bar_list_flavor_axes.
        source: provenance — "tgii", "llm_from_description", "manual", etc.
        confidence: "high" | "medium" | "low" | None.
        notes: free-text reasoning (e.g. tasting note that justifies the scoring).

    Used when re-scoring a bottle after tasting, correcting a stale LLM guess,
    or initially scoring a bottle that wasn't in the TGII bootstrap.
    """
    _ensure_ingredient_meta(ingredient_id)
    with fdb.connect() as conn:
        fdb.set_profile(conn, ingredient_id, profile, source=source, confidence=confidence, notes=notes)
    changed = ", ".join(f"{k}={v}" for k, v in profile.items())
    return f"Updated profile for ingredient {ingredient_id}: {changed}  (source={source})"


@mcp.tool()
def bar_describe_slots(cocktail_id: int) -> str:
    """List a cocktail's ingredient slots with their `sort` index and current ingredient.

    Each line shows the sort index (the canonical slot identifier), the
    ingredient currently in the slot, and whether the slot has flavor
    constraints declared in the flavor DB. Use this to find the right
    `slot_sort` before calling `bar_alternatives_for_slot` or constraint setters.
    """
    cocktail = get_api().get_cocktail(cocktail_id).get("data", {})
    if not cocktail:
        return f"Cocktail {cocktail_id} not found."

    with fdb.connect() as conn:
        existing_slots = {
            r["sort"] for r in conn.execute(
                "SELECT sort FROM slot_meta WHERE cocktail_id=?", (cocktail_id,)
            ).fetchall()
        }
        constrained = {
            r["sort"] for r in conn.execute(
                "SELECT DISTINCT sort FROM slot_constraint WHERE cocktail_id=?", (cocktail_id,)
            ).fetchall()
        }

    lines = [f"**{cocktail.get('name', '?')}** (id={cocktail_id}) slots:"]
    for ing in cocktail.get("ingredients", []):
        sort = ing.get("sort")
        name = ing.get("ingredient", {}).get("name", ing.get("name", "?"))
        amt = f"{ing.get('amount', '')} {ing.get('units', '')}".strip()
        flags = []
        if sort in existing_slots:
            flags.append("slot_meta✓")
        if sort in constrained:
            flags.append("constraints✓")
        tag = f"  [{', '.join(flags)}]" if flags else ""
        lines.append(f"  sort={sort}  {amt}  {name}{tag}")
    return "\n".join(lines)


@mcp.tool()
def bar_set_slot_meta(
    cocktail_id: int,
    sort: int,
    category: str,
    tolerance: str = "style",
    exact_ingredient_id: int | None = None,
    also_accept_categories: list[str] | None = None,
    proof_min: float | None = None,
    proof_max: float | None = None,
) -> str:
    """Declare the category + tolerance for a recipe slot.

    Required before setting axis constraints. `sort` is the 1-based BA sort
    index of the ingredient in the recipe (see bar_describe_slots).

    Args:
        cocktail_id: BA cocktail_id.
        sort: BA `sort` index of the slot (1-based).
        category: e.g. "gin", "rum", "whiskey".
        tolerance: "exact" (named bottle required) | "style" (match by vector)
                   | "any" (any in-category bottle works).
        exact_ingredient_id: required when tolerance="exact".
        also_accept_categories: list of other categories that can sub here
                   (e.g. ["bourbon"] on a rye slot). Cross-category subs get
                   a small flat penalty so in-category ranks first.
        proof_min / proof_max: enforce a proof range (US proof).
    """
    with fdb.connect() as conn:
        fdb.upsert_slot_meta(
            conn, cocktail_id, sort,
            category=category, tolerance=tolerance,
            exact_ingredient_id=exact_ingredient_id,
            also_accept_categories=also_accept_categories,
            proof_min=proof_min, proof_max=proof_max,
        )
    return f"Slot meta set for cocktail {cocktail_id} sort {sort}: category={category}, tolerance={tolerance}"


@mcp.tool()
def bar_set_band_constraint(
    cocktail_id: int,
    sort: int,
    axis: str,
    lo: int,
    hi: int,
    out_weight: float = 1.0,
    hard: bool = False,
) -> str:
    """Set a Band constraint on one axis of a recipe slot.

    Band = "acceptable range; zero penalty inside, graded penalty outside."
    Use Band for the *forgiving* axes of a slot — most slots are wide on most
    axes. Set `hard=True` for the one or two axes that *truly disqualify* a
    candidate (e.g. Negroni gin → floral Band(0,2,hard=True): aggressive floral
    fights Campari).

    For gin axes are 0–3; lo/hi are inclusive integer bounds.
    """
    with fdb.connect() as conn:
        fdb.set_constraint(conn, cocktail_id, sort, axis, "band",
                           band_lo=lo, band_hi=hi, out_weight=out_weight, hard=hard)
    h = " (hard)" if hard else ""
    return f"Band constraint set: cocktail {cocktail_id} sort {sort} {axis}=[{lo},{hi}] out_weight={out_weight}{h}"


@mcp.tool()
def bar_set_point_constraint(
    cocktail_id: int,
    sort: int,
    axis: str,
    value: int,
    weight: float = 1.0,
) -> str:
    """Set a Point constraint on one axis of a recipe slot.

    Point = "exact-ish target; penalty grows with distance." Use Point for the
    *exposed* axes of a slot — where the spirit's level on that axis genuinely
    matters (e.g. Martinez gin → juniper Point(2): we want a moderately
    juniper-forward but not over-the-top gin).

    For gin axes are 0–3; value is an integer.
    """
    with fdb.connect() as conn:
        fdb.set_constraint(conn, cocktail_id, sort, axis, "point",
                           point_value=value, weight=weight)
    return f"Point constraint set: cocktail {cocktail_id} sort {sort} {axis}={value} weight={weight}"


@mcp.tool()
def bar_delete_slot_constraint(cocktail_id: int, sort: int, axis: str) -> str:
    """Remove a single axis constraint from a recipe slot."""
    with fdb.connect() as conn:
        n = fdb.delete_constraint(conn, cocktail_id, sort, axis)
    return f"Deleted {n} constraint(s) for cocktail {cocktail_id} sort {sort} axis {axis}"


@mcp.tool()
def bar_get_slot_constraints(cocktail_id: int) -> str:
    """List all flavor constraints declared for a cocktail's slots."""
    with fdb.connect() as conn:
        slots = fdb.load_slots_for_cocktail(conn, cocktail_id)
    if not slots:
        return f"No slot constraints declared for cocktail {cocktail_id}."
    lines = [f"**Slot constraints for cocktail {cocktail_id}**"]
    for s in slots:
        also = f" (also_accept: {','.join(s.also_accept_categories)})" if s.also_accept_categories else ""
        lines.append(f"  sort={s.sort}  category={s.category}  tolerance={s.tolerance}{also}")
        for axis, c in s.constraints.items():
            if isinstance(c, fl.Point):
                lines.append(f"    {axis}: Point({c.value}) weight={c.weight}")
            else:
                h = ", hard" if c.hard else ""
                lines.append(f"    {axis}: Band({c.lo}–{c.hi}, out_weight={c.out_weight}{h})")
    return "\n".join(lines)


def _shelf_ingredient_ids() -> set[int]:
    out: set[int] = set()
    page = 1
    while True:
        resp = get_api().list_ingredients(filter_on_shelf=True, limit=200, page=page)
        for ing in resp.get("data", []):
            out.add(ing["id"])
        meta = resp.get("meta", {})
        if page >= meta.get("last_page", 1):
            break
        page += 1
    return out


@mcp.tool()
def bar_alternatives_for_slot(
    cocktail_id: int,
    sort: int,
    on_shelf_only: bool = True,
    include_strays: bool = False,
    top_n: int = 10,
) -> str:
    """Rank bottles by fit for a recipe's slot.

    The killer feature: given a recipe slot (declared via bar_set_slot_meta +
    bar_set_band_constraint / bar_set_point_constraint), rank in-stock bottles
    of the appropriate category by how well their flavor profiles match the
    slot's constraints. Includes "off-pattern" picks (disqualified by hard
    bands) when include_strays=True, with explanations.

    Args:
        cocktail_id: BA cocktail_id.
        sort: 1-based slot index (see bar_describe_slots).
        on_shelf_only: if true, restrict to bottles currently on shelf.
        include_strays: surface hard-disqualified picks too, with reasons.
        top_n: max bottles to return.
    """
    with fdb.connect() as conn:
        slot = fdb.load_slot(conn, cocktail_id, sort)
        if slot is None:
            return (f"No slot_meta declared for cocktail {cocktail_id} sort {sort}. "
                    "Call bar_set_slot_meta first.")
        bottles = fdb.load_bottles(conn, category=None)

    if on_shelf_only:
        shelf = _shelf_ingredient_ids()
        for b in bottles:
            b.in_stock = b.id in shelf
    else:
        for b in bottles:
            b.in_stock = True

    results = fl.alternatives_for_slot(bottles, slot, top_n=top_n, include_strays=include_strays)
    if not results:
        return f"No matches for cocktail {cocktail_id} slot {sort} (category={slot.category})."

    lines = [f"**Alternatives for cocktail {cocktail_id}, slot {sort} ({slot.category}):**"]
    for i, (b, a) in enumerate(results, 1):
        flags = f"  — {'; '.join(a.flags)}" if a.flags else ""
        conf = f" [{b.confidence}]" if b.confidence else ""
        lines.append(f"  {i}. {b.name}  penalty={a.penalty:.1f}  [{a.verdict}]{conf}{flags}")
    return "\n".join(lines)


@mcp.tool()
def bar_uses_for_bottle(ingredient_id: int, top_n: int = 10) -> str:
    """Given a bottle, list recipes (with declared slot constraints) that welcome it.

    Useful when a new bottle arrives — find which existing constrained recipes
    welcome it before adding the bottle to your shelf.
    """
    name, category, proof = _ensure_ingredient_meta(ingredient_id)
    with fdb.connect() as conn:
        prof = fdb.get_profile(conn, ingredient_id)
        slots = fdb.load_all_slots(conn)
    if not prof:
        return f"Ingredient {ingredient_id} ({name}) has no flavor profile yet."
    if not slots:
        return "No recipes have slot constraints declared yet."

    bottle = fl.Bottle(
        id=ingredient_id, name=name, category=category, profile=prof["profile"],
        proof=proof, source=prof.get("source") or "", confidence=prof.get("confidence") or "",
    )
    matches = fl.uses_for_bottle(bottle, slots, top_n=top_n)
    if not matches:
        return f"No constrained recipes accept category={category} for {name}."

    lines = [f"**Recipes welcoming {name}:**"]
    for slot, a in matches:
        flags = f"  — {'; '.join(a.flags)}" if a.flags else ""
        lines.append(f"  cocktail {slot.cocktail_id} sort {slot.sort}  penalty={a.penalty:.1f}  [{a.verdict}]{flags}")
    return "\n".join(lines)


@mcp.tool()
def bar_find_gaps(
    cocktail_ids: list[int] | None = None,
    threshold: float = 3.0,
) -> str:
    """Find recipe slots where the best in-stock bottle is a stretch — the shopping list.

    Loads constrained slots (all by default, or the subset matching `cocktail_ids`),
    pits them against in-stock bottles, and reports any slot whose best match is
    hard-disqualified or accumulates penalty ≥ `threshold`. Sorted worst-gap-first.

    Args:
        cocktail_ids: restrict to these cocktails; None = every constrained slot.
        threshold: penalty above which a slot counts as a gap (defaults to 3.0,
                   roughly "two-axis miss or one hard-cap brush").
    """
    with fdb.connect() as conn:
        all_slots = fdb.load_all_slots(conn)
        bottles = fdb.load_bottles(conn, category=None)
    if cocktail_ids is not None:
        wanted = set(cocktail_ids)
        slots = [s for s in all_slots if s.cocktail_id in wanted]
    else:
        slots = all_slots
    if not slots:
        return "No constrained slots to evaluate."

    shelf = _shelf_ingredient_ids()
    for b in bottles:
        b.in_stock = b.id in shelf

    gaps = fl.find_gaps(bottles, slots, threshold=threshold)
    if not gaps:
        return f"No gaps — every evaluated slot has an in-stock match under penalty {threshold}."

    names: dict[int, str] = {}
    def name_for(cid: int) -> str:
        if cid not in names:
            names[cid] = get_api().get_cocktail(cid).get("data", {}).get("name", f"#{cid}")
        return names[cid]

    lines = [f"**Gaps ({len(gaps)} slot(s) at threshold {threshold}):**"]
    for slot, bottle, penalty, reason in gaps:
        best = f"best: {bottle.name} (penalty={penalty:.1f})" if bottle else "best: nothing in stock"
        lines.append(f"  {name_for(slot.cocktail_id)} (id={slot.cocktail_id}) sort {slot.sort} [{slot.category}]  {best}  — {reason}")
    return "\n".join(lines)


# ===== Server Startup =====


def main():
    """Main entry point."""
    global _api, _oauth_provider

    # Determine transport from CLI args
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]

    # For stdio mode, require env vars for API config
    if transport == "stdio":
        base_url = os.environ.get("BAR_ASSISTANT_URL")
        api_token = os.environ.get("BAR_ASSISTANT_TOKEN")
        bar_id = int(os.environ.get("BAR_ASSISTANT_BAR_ID", "1"))

        if not base_url or not api_token:
            print(
                "Error: BAR_ASSISTANT_URL and BAR_ASSISTANT_TOKEN environment variables required.",
                file=sys.stderr,
            )
            sys.exit(1)

        _api = BarAssistantAPI(base_url, api_token, bar_id)

    elif transport == "streamable-http":
        _setup_http_auth()
        _add_debug_logging()

    mcp.run(transport=transport)


def _setup_http_auth():
    """Configure OAuth 2.1 auth for HTTP transport mode."""
    global _oauth_provider

    from urllib.parse import urlencode

    from mcp.server.auth.settings import (
        AuthSettings,
        ClientRegistrationOptions,
        RevocationOptions,
    )
    from pydantic import AnyHttpUrl
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, RedirectResponse

    from mcp.server.auth.provider import ProviderTokenVerifier

    from .auth import LOGIN_PAGE_TEMPLATE, BarAssistantOAuthProvider

    # Required env vars for HTTP mode
    ba_url = os.environ.get("BAR_ASSISTANT_URL")
    if not ba_url:
        print("Error: BAR_ASSISTANT_URL environment variable required.", file=sys.stderr)
        sys.exit(1)

    issuer_url = os.environ.get("MCP_ISSUER_URL", "http://localhost:8100")
    ba_bar_id = int(os.environ.get("BAR_ASSISTANT_BAR_ID", "1"))

    # Create OAuth provider
    _oauth_provider = BarAssistantOAuthProvider(
        ba_url=ba_url,
        ba_bar_id=ba_bar_id,
        issuer_url=issuer_url,
    )

    # Configure auth settings on FastMCP
    mcp.settings.auth = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["bar.read", "bar.write"],
            default_scopes=["bar.read", "bar.write"],
        ),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=[],
        resource_server_url=AnyHttpUrl(f"{issuer_url.rstrip('/')}/mcp"),
    )
    mcp._auth_server_provider = _oauth_provider
    mcp._token_verifier = ProviderTokenVerifier(_oauth_provider)

    # Monkey-patch build_metadata to include "none" in token auth methods
    # (needed for public clients like Claude.ai)
    import mcp.server.auth.routes as _auth_routes

    # Namespace the dynamic client registration endpoint under /oauth/ so it
    # doesn't collide with the Salt Rim frontend's /register page served behind
    # the same hostname. Must run before create_auth_routes / build_metadata.
    _auth_routes.REGISTRATION_PATH = "/oauth/register"

    _orig_build_metadata = _auth_routes.build_metadata

    def _patched_build_metadata(*args, **kwargs):
        metadata = _orig_build_metadata(*args, **kwargs)
        # Add "none" for public clients (Claude.ai)
        methods = list(metadata.token_endpoint_auth_methods_supported or [])
        if "none" not in methods:
            methods.append("none")
        metadata.token_endpoint_auth_methods_supported = methods
        return metadata

    _auth_routes.build_metadata = _patched_build_metadata

    # Fix Pydantic AnyHttpUrl trailing slash on issuer/authorization_servers
    # AnyHttpUrl("https://example.com") always serializes as "https://example.com/"
    # which can cause issuer URL mismatches in strict OAuth implementations
    import re
    from mcp.server.auth.json_response import PydanticJSONResponse

    _orig_render = PydanticJSONResponse.render

    def _patched_render(self, content):
        data = _orig_render(self, content)
        # Strip trailing slash from issuer URL (but not from path-based URLs)
        text = data.decode("utf-8")
        issuer_base = issuer_url.rstrip("/")
        # Fix "issuer":"https://example.com/" → "issuer":"https://example.com"
        text = text.replace(f'"{issuer_base}/"', f'"{issuer_base}"')
        return text.encode("utf-8")

    PydanticJSONResponse.render = _patched_render

    # Monkey-patch RequireAuthMiddleware to fix WWW-Authenticate for no-token requests
    # Per RFC 6750, when no token is provided, the challenge should be plain "Bearer"
    # without error="invalid_token" (which signals a failed token, not missing auth)
    from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware

    _orig_call = RequireAuthMiddleware.__call__

    async def _patched_call(self, scope, receive, send):
        from starlette.requests import HTTPConnection
        conn = HTTPConnection(scope)
        auth_header = conn.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            # No token provided — send plain Bearer challenge (RFC 6750 §3)
            await self._send_auth_error(
                send, status_code=401, error="", description="Authentication required"
            )
            return
        await _orig_call(self, scope, receive, send)

    RequireAuthMiddleware.__call__ = _patched_call

    # Also patch _send_auth_error to handle empty error code
    _orig_send_error = RequireAuthMiddleware._send_auth_error

    async def _patched_send_error(self, send, status_code, error, description):
        import json as _json
        if not error:
            # Plain Bearer challenge for no-token case
            www_auth_parts = []
            if description:
                www_auth_parts.append(f'error_description="{description}"')
            if self.resource_metadata_url:
                www_auth_parts.append(f'resource_metadata="{self.resource_metadata_url}"')
            www_authenticate = "Bearer" + (f" {', '.join(www_auth_parts)}" if www_auth_parts else "")

            body = {"error": "unauthorized", "error_description": description}
            body_bytes = _json.dumps(body).encode()
            await send({
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body_bytes)).encode()),
                    (b"www-authenticate", www_authenticate.encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body_bytes})
        else:
            await _orig_send_error(self, send, status_code, error, description)

    RequireAuthMiddleware._send_auth_error = _patched_send_error

    # Login page (GET)
    @mcp.custom_route("/auth/login", methods=["GET"])
    async def login_page(request: Request):
        from string import Template

        code_id = request.query_params.get("code_id", "")
        html = Template(LOGIN_PAGE_TEMPLATE).safe_substitute(code_id=code_id, error="")
        return HTMLResponse(html)

    # Login form submission (POST)
    @mcp.custom_route("/auth/login", methods=["POST"])
    async def login_submit(request: Request):
        from string import Template

        form = await request.form()
        code_id = str(form.get("code_id", ""))
        email = str(form.get("email", ""))
        password = str(form.get("password", ""))

        try:
            redirect_url = await _oauth_provider.complete_authorization(
                code_id, email, password
            )
            return RedirectResponse(url=redirect_url, status_code=302)
        except ValueError as e:
            error_html = f'<div class="error">{str(e)}</div>'
            html = Template(LOGIN_PAGE_TEMPLATE).safe_substitute(
                code_id=code_id, error=error_html
            )
            return HTMLResponse(html, status_code=400)


def _add_debug_logging():
    """Add debug logging for auth-related requests."""
    import logging

    logging.basicConfig(level=logging.DEBUG)
    # Enable debug logging for all MCP auth components
    for name in ("mcp", "uvicorn", "starlette"):
        logging.getLogger(name).setLevel(logging.DEBUG)


if __name__ == "__main__":
    main()

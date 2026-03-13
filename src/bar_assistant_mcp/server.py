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
    cocktail_data: dict[str, Any] = {
        "name": name,
        "instructions": instructions,
        "ingredients": ingredients,
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
        updates["ingredients"] = ingredients
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

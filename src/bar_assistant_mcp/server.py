"""Bar Assistant MCP Server - Main server implementation."""

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .api import BarAssistantAPI

# Initialize server
server = Server("bar-assistant")

# Global API client (initialized on startup)
api: BarAssistantAPI | None = None


def get_api() -> BarAssistantAPI:
    """Get the API client, raising error if not configured."""
    if api is None:
        raise RuntimeError(
            "Bar Assistant API not configured. "
            "Set BAR_ASSISTANT_URL and BAR_ASSISTANT_TOKEN environment variables."
        )
    return api


def format_cocktail(cocktail: dict[str, Any], detailed: bool = False) -> str:
    """Format a cocktail for display."""
    lines = [f"**{cocktail.get('name', 'Unknown')}**"]

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


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        # Cocktails
        Tool(
            name="bar_search_cocktails",
            description="Search for cocktails by name. Returns matching cocktails with their ingredients.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (cocktail name)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="bar_get_cocktail",
            description="Get detailed information about a specific cocktail by ID or slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Cocktail ID or slug",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="bar_list_cocktails",
            description="List cocktails with optional filters. Use to browse the cocktail collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Results per page (default 25)",
                        "default": 25,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default 1)",
                        "default": 1,
                    },
                    "favorites_only": {
                        "type": "boolean",
                        "description": "Only show favorites",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag name",
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort field (name, created_at, average_rating)",
                    },
                },
            },
        ),
        Tool(
            name="bar_makeable_cocktails",
            description="Get cocktails that can be made with ingredients currently on the shelf.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
            },
        ),
        Tool(
            name="bar_favorite_cocktails",
            description="Get user's favorite cocktails.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
            },
        ),
        # Ingredients
        Tool(
            name="bar_search_ingredients",
            description="Search for ingredients by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (ingredient name)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="bar_get_ingredient",
            description="Get detailed information about a specific ingredient.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Ingredient ID or slug",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="bar_list_ingredients",
            description="List ingredients with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Results per page (default 50)",
                        "default": 50,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default 1)",
                        "default": 1,
                    },
                    "on_shelf_only": {
                        "type": "boolean",
                        "description": "Only show ingredients on shelf",
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort field (name, created_at)",
                    },
                },
            },
        ),
        Tool(
            name="bar_ingredient_cocktails",
            description="Get cocktails that use a specific ingredient.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Ingredient ID or slug",
                    },
                },
                "required": ["id"],
            },
        ),
        # Shelf
        Tool(
            name="bar_get_shelf",
            description="Get ingredients currently on the user's shelf (what they have available).",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
            },
        ),
        Tool(
            name="bar_add_to_shelf",
            description="Add ingredients to the shelf.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ingredient_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of ingredient IDs to add",
                    },
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
                "required": ["ingredient_ids"],
            },
        ),
        Tool(
            name="bar_remove_from_shelf",
            description="Remove ingredients from the shelf.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ingredient_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of ingredient IDs to remove",
                    },
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
                "required": ["ingredient_ids"],
            },
        ),
        # Shopping List
        Tool(
            name="bar_get_shopping_list",
            description="Get the user's shopping list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
            },
        ),
        Tool(
            name="bar_add_to_shopping_list",
            description="Add ingredients to the shopping list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ingredient_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of ingredient IDs to add",
                    },
                    "user_id": {
                        "type": "integer",
                        "description": "User ID (default 1)",
                        "default": 1,
                    },
                },
                "required": ["ingredient_ids"],
            },
        ),
        # Collections
        Tool(
            name="bar_list_collections",
            description="List cocktail collections.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="bar_get_collection",
            description="Get a specific cocktail collection with its cocktails.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Collection ID",
                    },
                },
                "required": ["id"],
            },
        ),
        # Reference data
        Tool(
            name="bar_list_tags",
            description="List all cocktail tags.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="bar_list_glasses",
            description="List all glass types.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="bar_list_methods",
            description="List cocktail preparation methods.",
            inputSchema={"type": "object", "properties": {}},
        ),
        # Stats
        Tool(
            name="bar_stats",
            description="Get bar statistics (total cocktails, ingredients, etc).",
            inputSchema={"type": "object", "properties": {}},
        ),
        # Create operations
        Tool(
            name="bar_upload_image",
            description="Upload an image from a URL. Returns the image ID to use when creating cocktails or ingredients.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "URL of the image to upload",
                    },
                    "copyright": {
                        "type": "string",
                        "description": "Copyright attribution for the image",
                    },
                },
                "required": ["image_url"],
            },
        ),
        Tool(
            name="bar_upload_image_file",
            description="Upload an image from a local file path. Returns the image ID to use when creating cocktails or ingredients.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Local file path to the image (e.g., /path/to/image.jpg or C:\\temp\\image.webp)",
                    },
                    "copyright": {
                        "type": "string",
                        "description": "Copyright attribution for the image",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="bar_create_ingredient",
            description="Create a new ingredient. Use parent_ingredient_id to place it in the hierarchy (e.g., under 'Gin' or 'Bourbon').",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the ingredient",
                    },
                    "strength": {
                        "type": "number",
                        "description": "Alcohol strength as percentage (e.g., 40 for 40% ABV)",
                        "default": 0,
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the ingredient",
                    },
                    "origin": {
                        "type": "string",
                        "description": "Origin/country of the ingredient",
                    },
                    "parent_ingredient_id": {
                        "type": "integer",
                        "description": "ID of parent ingredient for categorization hierarchy",
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of image IDs to attach",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="bar_create_cocktail",
            description="Create a new cocktail recipe with ingredients, instructions, and optional image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the cocktail",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Step-by-step preparation instructions",
                    },
                    "description": {
                        "type": "string",
                        "description": "Short description of the cocktail",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source/origin of the recipe (URL, book, bartender name)",
                    },
                    "garnish": {
                        "type": "string",
                        "description": "Garnish description",
                    },
                    "glass_id": {
                        "type": "integer",
                        "description": "ID of the glass type",
                    },
                    "cocktail_method_id": {
                        "type": "integer",
                        "description": "ID of the preparation method (stirred, shaken, etc)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tag names",
                    },
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ingredient_id": {"type": "integer", "description": "ID of the ingredient"},
                                "amount": {"type": "number", "description": "Amount of ingredient"},
                                "units": {"type": "string", "description": "Units (ml, oz, dash, etc)"},
                                "optional": {"type": "boolean", "description": "Whether ingredient is optional"},
                                "sort": {"type": "integer", "description": "Sort order"},
                            },
                            "required": ["ingredient_id", "amount", "units"],
                        },
                        "description": "List of ingredients with amounts",
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of image IDs to attach",
                    },
                },
                "required": ["name", "instructions", "ingredients"],
            },
        ),
        Tool(
            name="bar_update_cocktail",
            description="Update an existing cocktail. Only provide fields you want to change.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Cocktail ID or slug",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name of the cocktail",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Step-by-step preparation instructions",
                    },
                    "description": {
                        "type": "string",
                        "description": "Short description of the cocktail",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source/origin of the recipe",
                    },
                    "garnish": {
                        "type": "string",
                        "description": "Garnish description",
                    },
                    "glass_id": {
                        "type": "integer",
                        "description": "ID of the glass type",
                    },
                    "cocktail_method_id": {
                        "type": "integer",
                        "description": "ID of the preparation method",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tag names",
                    },
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ingredient_id": {"type": "integer"},
                                "amount": {"type": "number"},
                                "units": {"type": "string"},
                                "optional": {"type": "boolean"},
                                "sort": {"type": "integer"},
                            },
                            "required": ["ingredient_id", "amount", "units"],
                        },
                        "description": "List of ingredients (replaces existing)",
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of image IDs",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="bar_delete_cocktail",
            description="Delete a cocktail by ID or slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Cocktail ID or slug",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="bar_update_ingredient",
            description="Update an existing ingredient. Only provide fields you want to change.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Ingredient ID or slug",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name of the ingredient",
                    },
                    "strength": {
                        "type": "number",
                        "description": "Alcohol strength as percentage",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the ingredient",
                    },
                    "origin": {
                        "type": "string",
                        "description": "Origin/country of the ingredient",
                    },
                    "parent_ingredient_id": {
                        "type": "integer",
                        "description": "ID of parent ingredient",
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of image IDs",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="bar_delete_ingredient",
            description="Delete an ingredient by ID or slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Ingredient ID or slug",
                    },
                },
                "required": ["id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        client = get_api()
        result: Any = None

        # Cocktails
        if name == "bar_search_cocktails":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            data = client.search_cocktails(query, limit)
            cocktails = data.get("data", [])
            if not cocktails:
                result = f"No cocktails found matching '{query}'"
            else:
                formatted = [format_cocktail(c) for c in cocktails]
                result = f"Found {len(cocktails)} cocktails:\n\n" + "\n\n---\n\n".join(
                    formatted
                )

        elif name == "bar_get_cocktail":
            cocktail_id = arguments.get("id")
            data = client.get_cocktail(cocktail_id)
            cocktail = data.get("data", data)
            result = format_cocktail(cocktail, detailed=True)

        elif name == "bar_list_cocktails":
            data = client.list_cocktails(
                limit=arguments.get("limit", 25),
                page=arguments.get("page", 1),
                filter_favorites=arguments.get("favorites_only"),
                sort=arguments.get("sort"),
            )
            cocktails = data.get("data", [])
            meta = data.get("meta", {})
            total = meta.get("total", len(cocktails))
            formatted = [f"- {c.get('name')}" for c in cocktails]
            result = f"Cocktails ({len(cocktails)} of {total}):\n" + "\n".join(
                formatted
            )

        elif name == "bar_makeable_cocktails":
            user_id = arguments.get("user_id", 1)
            data = client.get_makeable_cocktails(user_id)
            cocktails = data.get("data", [])
            if not cocktails:
                result = "No cocktails can be made with current shelf ingredients."
            else:
                formatted = [f"- {c.get('name')}" for c in cocktails]
                result = f"You can make {len(cocktails)} cocktails:\n" + "\n".join(
                    formatted
                )

        elif name == "bar_favorite_cocktails":
            user_id = arguments.get("user_id", 1)
            data = client.get_favorite_cocktails(user_id)
            cocktails = data.get("data", [])
            if not cocktails:
                result = "No favorite cocktails."
            else:
                formatted = [f"- {c.get('name')}" for c in cocktails]
                result = f"Favorite cocktails ({len(cocktails)}):\n" + "\n".join(
                    formatted
                )

        # Ingredients
        elif name == "bar_search_ingredients":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            data = client.search_ingredients(query, limit)
            ingredients = data.get("data", [])
            if not ingredients:
                result = f"No ingredients found matching '{query}'"
            else:
                formatted = [format_ingredient(i) for i in ingredients]
                result = f"Found {len(ingredients)} ingredients:\n\n" + "\n\n---\n\n".join(
                    formatted
                )

        elif name == "bar_get_ingredient":
            ingredient_id = arguments.get("id")
            data = client.get_ingredient(ingredient_id)
            ingredient = data.get("data", data)
            result = format_ingredient(ingredient, detailed=True)

        elif name == "bar_list_ingredients":
            data = client.list_ingredients(
                limit=arguments.get("limit", 50),
                page=arguments.get("page", 1),
                filter_on_shelf=arguments.get("on_shelf_only"),
                sort=arguments.get("sort"),
            )
            ingredients = data.get("data", [])
            meta = data.get("meta", {})
            total = meta.get("total", len(ingredients))
            formatted = [f"- {i.get('name')}" for i in ingredients]
            result = f"Ingredients ({len(ingredients)} of {total}):\n" + "\n".join(
                formatted
            )

        elif name == "bar_ingredient_cocktails":
            ingredient_id = arguments.get("id")
            data = client.get_ingredient_cocktails(ingredient_id)
            cocktails = data.get("data", [])
            if not cocktails:
                result = "No cocktails use this ingredient."
            else:
                formatted = [f"- {c.get('name')}" for c in cocktails]
                result = f"Cocktails using this ingredient ({len(cocktails)}):\n" + "\n".join(
                    formatted
                )

        # Shelf
        elif name == "bar_get_shelf":
            user_id = arguments.get("user_id", 1)
            data = client.get_shelf(user_id)
            ingredients = data.get("data", [])
            if not ingredients:
                result = "Shelf is empty."
            else:
                formatted = [f"- {i.get('name')}" for i in ingredients]
                result = f"Shelf ingredients ({len(ingredients)}):\n" + "\n".join(
                    formatted
                )

        elif name == "bar_add_to_shelf":
            user_id = arguments.get("user_id", 1)
            ingredient_ids = arguments.get("ingredient_ids", [])
            client.add_to_shelf(user_id, ingredient_ids)
            result = f"Added {len(ingredient_ids)} ingredient(s) to shelf."

        elif name == "bar_remove_from_shelf":
            user_id = arguments.get("user_id", 1)
            ingredient_ids = arguments.get("ingredient_ids", [])
            client.remove_from_shelf(user_id, ingredient_ids)
            result = f"Removed {len(ingredient_ids)} ingredient(s) from shelf."

        # Shopping List
        elif name == "bar_get_shopping_list":
            user_id = arguments.get("user_id", 1)
            data = client.get_shopping_list(user_id)
            items = data.get("data", [])
            if not items:
                result = "Shopping list is empty."
            else:
                formatted = [f"- {i.get('name')}" for i in items]
                result = f"Shopping list ({len(items)}):\n" + "\n".join(formatted)

        elif name == "bar_add_to_shopping_list":
            user_id = arguments.get("user_id", 1)
            ingredient_ids = arguments.get("ingredient_ids", [])
            client.add_to_shopping_list(user_id, ingredient_ids)
            result = f"Added {len(ingredient_ids)} item(s) to shopping list."

        # Collections
        elif name == "bar_list_collections":
            data = client.list_collections()
            collections = data.get("data", [])
            if not collections:
                result = "No collections found."
            else:
                formatted = [
                    f"- {c.get('name')} (ID: {c.get('id')})" for c in collections
                ]
                result = f"Collections ({len(collections)}):\n" + "\n".join(formatted)

        elif name == "bar_get_collection":
            collection_id = arguments.get("id")
            data = client.get_collection(collection_id)
            collection = data.get("data", data)
            name_str = collection.get("name", "Unknown")
            cocktails = collection.get("cocktails", [])
            formatted = [f"- {c.get('name')}" for c in cocktails]
            result = f"**{name_str}**\n\nCocktails ({len(cocktails)}):\n" + "\n".join(
                formatted
            )

        # Reference data
        elif name == "bar_list_tags":
            data = client.list_tags()
            tags = data.get("data", [])
            formatted = [f"- {t.get('name')} (ID: {t.get('id')})" for t in tags]
            result = f"Tags ({len(tags)}):\n" + "\n".join(formatted)

        elif name == "bar_list_glasses":
            data = client.list_glasses()
            glasses = data.get("data", [])
            formatted = [f"- {g.get('name')} (ID: {g.get('id')})" for g in glasses]
            result = f"Glasses ({len(glasses)}):\n" + "\n".join(formatted)

        elif name == "bar_list_methods":
            data = client.list_methods()
            methods = data.get("data", [])
            formatted = [f"- {m.get('name')} (ID: {m.get('id')})" for m in methods]
            result = f"Methods ({len(methods)}):\n" + "\n".join(formatted)

        # Stats
        elif name == "bar_stats":
            data = client.get_bar_stats()
            stats = data.get("data", data)
            lines = ["**Bar Statistics**"]
            if isinstance(stats, dict):
                for key, value in stats.items():
                    lines.append(f"- {key.replace('_', ' ').title()}: {value}")
            result = "\n".join(lines)

        # Create operations
        elif name == "bar_upload_image":
            image_url = arguments.get("image_url")
            copyright_text = arguments.get("copyright")
            image_data = {"image": image_url}
            if copyright_text:
                image_data["copyright"] = copyright_text
            data = client.upload_images([image_data])
            images = data.get("data", [])
            if images:
                img = images[0]
                result = f"Image uploaded successfully!\nID: {img.get('id')}\nPath: {img.get('file_path')}"
            else:
                result = "Failed to upload image"

        elif name == "bar_upload_image_file":
            file_path_str = arguments.get("file_path")
            copyright_text = arguments.get("copyright")

            # Handle the file path (support both Unix and Windows paths)
            file_path = Path(file_path_str)
            if not file_path.exists():
                result = f"Error: File not found: {file_path_str}"
            else:
                # Read file and encode as base64
                file_bytes = file_path.read_bytes()
                base64_data = base64.b64encode(file_bytes).decode("utf-8")

                # Determine MIME type
                mime_type, _ = mimetypes.guess_type(str(file_path))
                if not mime_type:
                    # Default based on extension
                    ext = file_path.suffix.lower()
                    mime_types = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                    }
                    mime_type = mime_types.get(ext, "image/jpeg")

                # Format as data URL
                data_url = f"data:{mime_type};base64,{base64_data}"

                image_data = {"image": data_url}
                if copyright_text:
                    image_data["copyright"] = copyright_text

                data = client.upload_images([image_data])
                images = data.get("data", [])
                if images:
                    img = images[0]
                    result = f"Image uploaded successfully from local file!\nID: {img.get('id')}\nPath: {img.get('file_path')}"
                else:
                    result = "Failed to upload image"

        elif name == "bar_create_ingredient":
            ingredient_data = {
                "name": arguments.get("name"),
                "strength": arguments.get("strength", 0),
            }
            if arguments.get("description"):
                ingredient_data["description"] = arguments["description"]
            if arguments.get("origin"):
                ingredient_data["origin"] = arguments["origin"]
            if arguments.get("parent_ingredient_id"):
                ingredient_data["parent_ingredient_id"] = arguments["parent_ingredient_id"]
            if arguments.get("images"):
                ingredient_data["images"] = arguments["images"]

            data = client.create_ingredient(ingredient_data)
            ingredient = data.get("data", data)
            result = f"Created ingredient: **{ingredient.get('name')}** (ID: {ingredient.get('id')})"

        elif name == "bar_create_cocktail":
            cocktail_data = {
                "name": arguments.get("name"),
                "instructions": arguments.get("instructions"),
                "ingredients": arguments.get("ingredients", []),
            }
            if arguments.get("description"):
                cocktail_data["description"] = arguments["description"]
            if arguments.get("source"):
                cocktail_data["source"] = arguments["source"]
            if arguments.get("garnish"):
                cocktail_data["garnish"] = arguments["garnish"]
            if arguments.get("glass_id"):
                cocktail_data["glass_id"] = arguments["glass_id"]
            if arguments.get("cocktail_method_id"):
                cocktail_data["cocktail_method_id"] = arguments["cocktail_method_id"]
            if arguments.get("tags"):
                cocktail_data["tags"] = arguments["tags"]
            if arguments.get("images"):
                cocktail_data["images"] = arguments["images"]

            data = client.create_cocktail(cocktail_data)
            cocktail = data.get("data", data)
            result = f"Created cocktail: **{cocktail.get('name')}** (ID: {cocktail.get('id')})\n\n{format_cocktail(cocktail, detailed=True)}"

        elif name == "bar_update_cocktail":
            cocktail_id = arguments.get("id")
            # Fetch existing cocktail to preserve fields not being updated
            existing_data = client.get_cocktail(cocktail_id)
            existing = existing_data.get("data") if existing_data else None
            if not existing:
                existing = existing_data if isinstance(existing_data, dict) else {}

            # Start with required fields from existing cocktail
            cocktail_data = {
                "name": existing.get("name"),
                "instructions": existing.get("instructions"),
            }

            # Preserve existing ingredients if not provided (convert format)
            if arguments.get("ingredients") is None:
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

            # Preserve existing tags if not provided (extract tag names)
            if arguments.get("tags") is None:
                existing_tags = existing.get("tags", [])
                cocktail_data["tags"] = [
                    tag.get("name") for tag in existing_tags if tag.get("name")
                ]

            # Preserve existing images if not provided (extract image IDs)
            if arguments.get("images") is None:
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

            # Override with user's changes
            for key in ["name", "instructions", "description", "source", "garnish",
                       "glass_id", "cocktail_method_id", "tags", "ingredients", "images"]:
                if arguments.get(key) is not None:
                    cocktail_data[key] = arguments[key]

            data = client.update_cocktail(cocktail_id, cocktail_data)
            cocktail = data.get("data") if data else None
            if not cocktail:
                cocktail = data if isinstance(data, dict) and data.get("name") else None
            if cocktail and isinstance(cocktail, dict):
                result = f"Updated cocktail: **{cocktail.get('name')}** (ID: {cocktail.get('id')})"
            else:
                # API may not return the updated cocktail, use the name we already have
                result = f"Updated cocktail: **{cocktail_data.get('name')}** (ID: {cocktail_id})"

        elif name == "bar_delete_cocktail":
            cocktail_id = arguments.get("id")
            client.delete_cocktail(cocktail_id)
            result = f"Deleted cocktail: {cocktail_id}"

        elif name == "bar_update_ingredient":
            ingredient_id = arguments.get("id")
            # Fetch existing ingredient to preserve fields not being updated
            existing_data = client.get_ingredient(ingredient_id)
            existing = existing_data.get("data") if existing_data else None
            if not existing:
                existing = existing_data if isinstance(existing_data, dict) else {}

            # Start with required fields from existing ingredient
            ingredient_data = {
                "name": existing.get("name"),
            }

            # Preserve existing optional fields
            if existing.get("strength") is not None:
                ingredient_data["strength"] = existing["strength"]
            if existing.get("description"):
                ingredient_data["description"] = existing["description"]
            if existing.get("origin"):
                ingredient_data["origin"] = existing["origin"]
            if existing.get("parent_ingredient", {}).get("id"):
                ingredient_data["parent_ingredient_id"] = existing["parent_ingredient"]["id"]

            # Preserve existing images if not provided (extract image IDs)
            if arguments.get("images") is None:
                existing_images = existing.get("images", [])
                ingredient_data["images"] = [
                    img.get("id") for img in existing_images if img.get("id")
                ]

            # Override with user's changes
            for key in ["name", "strength", "description", "origin",
                       "parent_ingredient_id", "images"]:
                if arguments.get(key) is not None:
                    ingredient_data[key] = arguments[key]

            data = client.update_ingredient(ingredient_id, ingredient_data)
            ingredient = data.get("data") if data else None
            if not ingredient:
                ingredient = data if isinstance(data, dict) and data.get("name") else None
            if ingredient and isinstance(ingredient, dict):
                result = f"Updated ingredient: **{ingredient.get('name')}** (ID: {ingredient.get('id')})"
            else:
                # API may not return the updated ingredient, use the name we already have
                result = f"Updated ingredient: **{ingredient_data.get('name')}** (ID: {ingredient_id})"

        elif name == "bar_delete_ingredient":
            ingredient_id = arguments.get("id")
            client.delete_ingredient(ingredient_id)
            result = f"Deleted ingredient: {ingredient_id}"

        else:
            result = f"Unknown tool: {name}"

        return [TextContent(type="text", text=str(result))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def run():
    """Run the MCP server."""
    global api

    # Get configuration from environment
    base_url = os.environ.get("BAR_ASSISTANT_URL")
    api_token = os.environ.get("BAR_ASSISTANT_TOKEN")
    bar_id = int(os.environ.get("BAR_ASSISTANT_BAR_ID", "1"))

    if not base_url or not api_token:
        print(
            "Error: BAR_ASSISTANT_URL and BAR_ASSISTANT_TOKEN environment variables required.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Initialize API client
    api = BarAssistantAPI(base_url, api_token, bar_id)

    # Run server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Main entry point."""
    import asyncio

    asyncio.run(run())


if __name__ == "__main__":
    main()

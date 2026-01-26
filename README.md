# Bar Assistant MCP Server

MCP (Model Context Protocol) server for [Bar Assistant](https://github.com/karlomikus/bar-assistant), a cocktail recipe and bar management application.

## Features

This MCP server provides tools for:

- **Cocktails**: Search, list, and get detailed cocktail information
- **Ingredients**: Search and browse ingredients
- **Shelf Management**: View and modify what's in your bar
- **Shopping List**: Manage your shopping list
- **Collections**: Browse cocktail collections
- **Reference Data**: List tags, glasses, and methods

## Installation

### Using pip

```bash
pip install bar-assistant-mcp
```

### From source

```bash
git clone https://github.com/yourusername/bar-assistant-mcp.git
cd bar-assistant-mcp
pip install -e .
```

## Configuration

The server requires the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `BAR_ASSISTANT_URL` | Yes | Base URL of your Bar Assistant API (e.g., `https://erikbarapi.duckdns.org`) |
| `BAR_ASSISTANT_TOKEN` | Yes | API token from Bar Assistant |
| `BAR_ASSISTANT_BAR_ID` | No | Bar ID (default: 1) |

### Getting an API Token

1. Log into your Bar Assistant instance
2. Go to Profile → Personal Access Tokens
3. Create a new token with appropriate permissions
4. Copy the token (it's only shown once)

## Configuration

### Claude Code (Linux/WSL)

Create or edit `.mcp.json` in your home directory or project directory:

```json
{
  "mcpServers": {
    "bar-assistant": {
      "command": "/path/to/bar-assistant-mcp/.venv/bin/python",
      "args": ["-m", "bar_assistant_mcp.server"],
      "env": {
        "BAR_ASSISTANT_URL": "https://your-bar-assistant-url.com",
        "BAR_ASSISTANT_TOKEN": "your-api-token"
      }
    }
  }
}
```

Then restart Claude Code. The MCP server will be available when working in that directory.

### Claude Desktop (Windows)

Edit `%APPDATA%\Claude\claude_desktop_config.json` (typically `C:\Users\YourName\AppData\Roaming\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bar-assistant": {
      "command": "python",
      "args": ["-m", "bar_assistant_mcp.server"],
      "env": {
        "BAR_ASSISTANT_URL": "https://your-bar-assistant-url.com",
        "BAR_ASSISTANT_TOKEN": "your-api-token"
      }
    }
  }
}
```

**Note for Windows:** You'll need to install the package first:
```cmd
pip install bar-assistant-mcp
```

Or if running from source, use the full path to python in the venv.

### Claude Desktop (macOS)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bar-assistant": {
      "command": "/path/to/bar-assistant-mcp/.venv/bin/python",
      "args": ["-m", "bar_assistant_mcp.server"],
      "env": {
        "BAR_ASSISTANT_URL": "https://your-bar-assistant-url.com",
        "BAR_ASSISTANT_TOKEN": "your-api-token"
      }
    }
  }
}
```

## Available Tools

### Cocktails

| Tool | Description |
|------|-------------|
| `bar_search_cocktails` | Search cocktails by name |
| `bar_get_cocktail` | Get detailed cocktail info |
| `bar_list_cocktails` | List cocktails with filters |
| `bar_makeable_cocktails` | Get cocktails you can make with shelf ingredients |
| `bar_favorite_cocktails` | Get favorite cocktails |

### Ingredients

| Tool | Description |
|------|-------------|
| `bar_search_ingredients` | Search ingredients by name |
| `bar_get_ingredient` | Get detailed ingredient info |
| `bar_list_ingredients` | List ingredients with filters |
| `bar_ingredient_cocktails` | Get cocktails using an ingredient |

### Shelf & Shopping

| Tool | Description |
|------|-------------|
| `bar_get_shelf` | Get shelf ingredients |
| `bar_add_to_shelf` | Add ingredients to shelf |
| `bar_remove_from_shelf` | Remove ingredients from shelf |
| `bar_get_shopping_list` | Get shopping list |
| `bar_add_to_shopping_list` | Add to shopping list |

### Collections & Reference

| Tool | Description |
|------|-------------|
| `bar_list_collections` | List cocktail collections |
| `bar_get_collection` | Get collection details |
| `bar_list_tags` | List all tags |
| `bar_list_glasses` | List glass types |
| `bar_list_methods` | List preparation methods |
| `bar_stats` | Get bar statistics |

## Development

### Setup

```bash
git clone https://github.com/yourusername/bar-assistant-mcp.git
cd bar-assistant-mcp
pip install -e ".[dev]"
```

### Testing

```bash
# Run the test script
cd mcpb
python test_mcp.py --list

# Call a specific tool
python test_mcp.py --call bar_search_cocktails '{"query": "margarita"}'
```

### Building MCPB Package

```bash
cd mcpb
python build_mcpb.py
```

## License

MIT

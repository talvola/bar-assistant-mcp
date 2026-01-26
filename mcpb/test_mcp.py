#!/usr/bin/env python3
"""
MCP Server Test Script for Bar Assistant.

Tests the MCP server by connecting via stdio and exercising its capabilities.

Usage:
    python test_mcp.py                                      # Run basic tests
    python test_mcp.py --list                               # List all available tools
    python test_mcp.py --call <tool> [json_args]            # Call a specific tool

Examples:
    python test_mcp.py --list
    python test_mcp.py --call bar_search_cocktails '{"query": "margarita"}'
    python test_mcp.py --call bar_get_shelf '{}'
    python test_mcp.py --call bar_makeable_cocktails '{}'

Requirements:
    pip install mcp

Environment:
    BAR_ASSISTANT_URL - API base URL
    BAR_ASSISTANT_TOKEN - API token
"""

import asyncio
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("Error: MCP library not installed. Run: pip install mcp")
    sys.exit(1)


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    duration_ms: int | None = None


def get_server_command() -> tuple[str, list[str]]:
    """Get the command to run the server."""
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent

    # Run as module from project directory
    return "python", ["-m", "bar_assistant_mcp.server"]


def get_env() -> dict[str, str]:
    """Get environment variables for the server."""
    env = dict(os.environ)

    # Check for secrets.json
    script_dir = Path(__file__).parent
    secrets_path = script_dir / "secrets.json"

    if secrets_path.exists():
        with open(secrets_path) as f:
            secrets = json.load(f)
        env.update(secrets)

    # Verify required vars
    required = ["BAR_ASSISTANT_URL", "BAR_ASSISTANT_TOKEN"]
    missing = [v for v in required if not env.get(v)]
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        print("Set them in environment or create mcpb/secrets.json")
        sys.exit(1)

    return env


async def run_basic_tests() -> None:
    """Run basic connectivity tests against the MCP server."""
    results: list[TestResult] = []
    start_time = time.time()

    print("=" * 60)
    print("Bar Assistant MCP Server Test Suite")
    print("=" * 60)

    command, args = get_server_command()
    env = get_env()

    # Need to run from project directory for imports to work
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent

    print(f"Command: {command} {' '.join(args)}")
    print(f"Working dir: {project_dir}")
    print(f"Time: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print("-" * 60)

    # Add src to PYTHONPATH
    pythonpath = env.get("PYTHONPATH", "")
    src_path = str(project_dir / "src")
    env["PYTHONPATH"] = f"{src_path}:{pythonpath}" if pythonpath else src_path

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
        cwd=str(project_dir)
    )

    try:
        print("\n[1/4] Connecting to server...")
        connect_start = time.time()

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                connect_duration = int((time.time() - connect_start) * 1000)
                results.append(TestResult("Connection", True, "Connected successfully", connect_duration))
                print(f"  ✓ Connected ({connect_duration}ms)")

                # Get server info
                print("\n[2/4] Getting server info...")
                server_info = session.server_info if hasattr(session, 'server_info') else None
                if server_info:
                    name = getattr(server_info, 'name', 'unknown')
                    version = getattr(server_info, 'version', 'unknown')
                    print(f"  ✓ Server: {name} v{version}")
                    results.append(TestResult("Server Info", True, f"{name} v{version}"))
                else:
                    print("  ⚠ No server info available")
                    results.append(TestResult("Server Info", True, "No server info (optional)"))

                # List tools
                print("\n[3/4] Listing tools...")
                tools_start = time.time()
                tools_result = await session.list_tools()
                tools_duration = int((time.time() - tools_start) * 1000)
                tools = tools_result.tools if hasattr(tools_result, 'tools') else []
                print(f"  ✓ Found {len(tools)} tools ({tools_duration}ms)")
                results.append(TestResult("List Tools", True, f"Found {len(tools)} tools", tools_duration))

                # Display tools
                if tools:
                    print("\n  Tools:")
                    for tool in tools:
                        desc = ""
                        if hasattr(tool, 'description') and tool.description:
                            desc = f" - {tool.description[:50]}{'...' if len(tool.description) > 50 else ''}"
                        print(f"    • {tool.name}{desc}")

                # Test a specific tool
                print(f"\n[4/4] Testing tool: bar_stats...")
                try:
                    call_start = time.time()
                    result = await session.call_tool("bar_stats", arguments={})
                    call_duration = int((time.time() - call_start) * 1000)
                    print(f"  ✓ Tool executed successfully ({call_duration}ms)")

                    # Show result preview
                    if hasattr(result, 'content') and result.content:
                        content = result.content[0]
                        if hasattr(content, 'text'):
                            text = content.text
                            preview = text[:200] + "..." if len(text) > 200 else text
                            print(f"  Response:\n{preview}")

                    results.append(TestResult("Call Tool: bar_stats", True, "Executed successfully", call_duration))
                except Exception as e:
                    print(f"  ✗ Tool failed: {e}")
                    results.append(TestResult("Call Tool: bar_stats", False, str(e)))

    except Exception as e:
        print(f"\n✗ Error: {e}")
        results.append(TestResult("Connection", False, str(e)))

    # Summary
    total_duration = int((time.time() - start_time) * 1000)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    print("\n" + "=" * 60)
    print("Test Summary")
    print("-" * 60)

    for result in results:
        icon = "✓" if result.passed else "✗"
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        print(f"  {icon} {result.name}: {result.message}{duration}")

    print("-" * 60)
    print(f"Total: {passed} passed, {failed} failed ({total_duration}ms)")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


async def list_tools() -> None:
    """List all available tools from the MCP server."""
    command, args = get_server_command()
    env = get_env()

    script_dir = Path(__file__).parent
    project_dir = script_dir.parent

    # Add src to PYTHONPATH
    pythonpath = env.get("PYTHONPATH", "")
    src_path = str(project_dir / "src")
    env["PYTHONPATH"] = f"{src_path}:{pythonpath}" if pythonpath else src_path

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
        cwd=str(project_dir)
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, 'tools') else []

                print(f"\nAvailable Tools ({len(tools)}):\n")

                for tool in tools:
                    print(f"  {tool.name}")

                    # Description
                    if hasattr(tool, 'description') and tool.description:
                        desc = tool.description.split('\n')[0][:80]
                        print(f"    {desc}")

                    # Parameters
                    if hasattr(tool, 'inputSchema') and tool.inputSchema:
                        schema = tool.inputSchema
                        if isinstance(schema, dict) and 'properties' in schema:
                            props = list(schema['properties'].keys())
                            required = schema.get('required', [])
                            if props:
                                param_list = ', '.join(
                                    f"{p}*" if p in required else p
                                    for p in props
                                )
                                print(f"    Params: {param_list}")

                    print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


async def call_tool(tool_name: str, tool_args: dict[str, Any]) -> None:
    """Call a specific tool on the MCP server."""
    command, args = get_server_command()
    env = get_env()

    script_dir = Path(__file__).parent
    project_dir = script_dir.parent

    # Add src to PYTHONPATH
    pythonpath = env.get("PYTHONPATH", "")
    src_path = str(project_dir / "src")
    env["PYTHONPATH"] = f"{src_path}:{pythonpath}" if pythonpath else src_path

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
        cwd=str(project_dir)
    )

    try:
        print(f"\nConnecting to server...")

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                print(f"Calling tool: {tool_name}")
                if tool_args:
                    print(f"Arguments: {json.dumps(tool_args, indent=2)}")
                print("-" * 60)

                start_time = time.time()
                result = await session.call_tool(tool_name, arguments=tool_args)
                duration = int((time.time() - start_time) * 1000)

                # Handle result
                is_error = getattr(result, 'isError', False)

                if is_error:
                    print(f"\n✗ Tool returned error:")
                    if hasattr(result, 'content'):
                        for content in result.content:
                            if hasattr(content, 'text'):
                                print(content.text)
                else:
                    print(f"\n✓ Success ({duration}ms)\n")
                    if hasattr(result, 'content'):
                        for content in result.content:
                            if hasattr(content, 'text'):
                                # Try to pretty-print JSON
                                try:
                                    parsed = json.loads(content.text)
                                    print(json.dumps(parsed, indent=2))
                                except json.JSONDecodeError:
                                    print(content.text)
                            else:
                                print(f"[{type(content).__name__}]", content)

                print("\n" + "-" * 60)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Bar Assistant MCP Server Test Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_mcp.py --list
  python test_mcp.py --call bar_search_cocktails '{"query": "margarita"}'
  python test_mcp.py --call bar_get_shelf '{}'
  python test_mcp.py --call bar_makeable_cocktails '{}'
        """
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available tools"
    )

    parser.add_argument(
        "--call",
        nargs="+",
        metavar=("TOOL", "JSON_ARGS"),
        help="Call a specific tool with optional JSON arguments"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determine mode and run
    if args.list:
        asyncio.run(list_tools())

    elif args.call:
        tool_name = args.call[0]
        tool_args = {}

        if len(args.call) > 1:
            try:
                tool_args = json.loads(args.call[1])
            except json.JSONDecodeError as e:
                print(f"Invalid JSON arguments: {e}")
                sys.exit(1)

        asyncio.run(call_tool(tool_name, tool_args))

    else:
        asyncio.run(run_basic_tests())


if __name__ == "__main__":
    main()

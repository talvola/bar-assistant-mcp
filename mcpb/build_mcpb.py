#!/usr/bin/env python3
"""
Build script for Bar Assistant MCP Server MCPB package.

This script:
1. Creates a staging directory with required files
2. Installs production dependencies
3. Packages everything into an .mcpb file

Usage:
    cd mcpb
    python3 build_mcpb.py
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def run_command(cmd: list[str], cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Command failed with return code {result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
    return result


def main():
    # Paths
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    build_dir = script_dir / "build"
    dist_dir = script_dir / "dist"
    src_dir = project_dir / "src"

    # Read manifest for version info
    manifest_path = script_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    name = manifest["name"]
    version = manifest["version"]

    print(f"Building {name} v{version}...")

    # Step 1: Clean previous builds
    print("\n=== Cleaning previous builds ===")
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    if not dist_dir.exists():
        dist_dir.mkdir(parents=True)

    # Step 2: Verify source files exist
    print("\n=== Verifying source files ===")
    if not src_dir.exists():
        print(f"Error: Source directory not found at {src_dir}")
        sys.exit(1)
    print(f"  [OK] Found src/")

    pyproject = project_dir / "pyproject.toml"
    if not pyproject.exists():
        print(f"Error: pyproject.toml not found at {pyproject}")
        sys.exit(1)
    print(f"  [OK] Found pyproject.toml")

    # Step 3: Copy Python package to staging directory
    print("\n=== Staging files ===")

    # Copy src/bar_assistant_mcp folder
    pkg_src = src_dir / "bar_assistant_mcp"
    pkg_dest = build_dir / "bar_assistant_mcp"
    shutil.copytree(pkg_src, pkg_dest)
    print("  [OK] Copied bar_assistant_mcp/")

    # Copy pyproject.toml
    shutil.copy(pyproject, build_dir / "pyproject.toml")
    print("  [OK] Copied pyproject.toml")

    # Copy README if exists
    readme = project_dir / "README.md"
    if readme.exists():
        shutil.copy(readme, build_dir / "README.md")
        print("  [OK] Copied README.md")

    # Step 4: Process manifest (merge secrets if present)
    print("\n=== Processing manifest ===")
    secrets_path = script_dir / "secrets.json"

    if secrets_path.exists():
        print("  Found secrets.json, merging credentials...")
        with open(secrets_path) as f:
            secrets = json.load(f)

        # Merge secrets into user_config defaults
        if "user_config" in manifest:
            for key, value in secrets.items():
                if key in manifest["user_config"]:
                    manifest["user_config"][key]["default"] = value
                    print(f"    Set default for {key}")

        print("  [OK] Secrets merged into manifest")
    else:
        print("  No secrets.json found - using defaults from manifest.json")

    # Write manifest to build directory
    with open(build_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print("  [OK] Wrote manifest.json")

    # Step 5: Install dependencies
    print("\n=== Installing dependencies ===")

    # Create a requirements.txt for the bundle
    requirements = ["mcp>=1.0.0", "httpx>=0.25.0"]
    with open(build_dir / "requirements.txt", "w") as f:
        f.write("\n".join(requirements))
    print("  [OK] Created requirements.txt")

    # Install dependencies into build directory
    result = run_command(
        ["pip", "install", "--target", str(build_dir / "lib"), "-r", str(build_dir / "requirements.txt")],
        check=False
    )
    if result.returncode == 0:
        print("  [OK] Dependencies installed")
    else:
        print("  Warning: pip install had issues, bundle may not include all deps")
        print(f"  stderr: {result.stderr}")

    # Step 6: Create MCPB package
    print("\n=== Creating MCPB package ===")
    output_file = dist_dir / f"{name}-{version}.mcpb"

    # Remove old package if exists
    if output_file.exists():
        output_file.unlink()

    # Create zip archive
    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in build_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(build_dir)
                zf.write(file_path, arcname)

    print(f"\n=== Build complete ===")
    print(f"Output: {output_file}")
    print(f"Size: {output_file.stat().st_size / 1024:.1f} KB")

    # List contents summary
    print("\n=== Package contents ===")
    run_command(["unzip", "-l", str(output_file)], check=False)


if __name__ == "__main__":
    main()

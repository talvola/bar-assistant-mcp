#!/usr/bin/env python3
"""
seed_flavor_db.py — import bootstrap results into the flavor SQLite.

Reads `scripts/tgii_bootstrap_results.json` (28 gins with 7-axis profiles) and
upserts each into the database. Also pulls ingredient name + proof from BA so
we don't have to hit BA again at query time. Idempotent.

Usage:
    .venv/bin/python scripts/seed_flavor_db.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bar_assistant_mcp.api import BarAssistantAPI
from bar_assistant_mcp.flavor_db import (
    connect, set_profile, upsert_ingredient_meta,
)


def ba_token() -> str:
    if t := os.environ.get("BAR_ASSISTANT_TOKEN"):
        return t
    cfg = json.loads((ROOT / ".mcp.json").read_text())
    return cfg["mcpServers"]["bar-assistant"]["env"]["BAR_ASSISTANT_TOKEN"]


def main() -> None:
    results_path = ROOT / "scripts" / "tgii_bootstrap_results.json"
    if not results_path.exists():
        sys.exit(f"Missing {results_path} — run tgii_bootstrap.py first.")
    results = json.loads(results_path.read_text())

    ba_url = os.environ.get("BAR_ASSISTANT_URL", "https://erikbarapi.duckdns.org")
    api = BarAssistantAPI(ba_url, ba_token(), bar_id=1)

    inserted = 0
    skipped = 0

    with connect() as conn:
        for r in results:
            profile = r.get("profile")
            if not profile:
                skipped += 1
                continue

            ing = api.get_ingredient(r["ba_id"]).get("data", {})
            upsert_ingredient_meta(
                conn,
                ingredient_id=r["ba_id"],
                name=r["ba_name"],
                category="gin",
                proof=(ing.get("strength") * 2) if ing.get("strength") else None,  # ABV % → US proof
            )

            source = r.get("source", "tgii")
            confidence = r.get("confidence") or None
            notes = r.get("reasoning") or r.get("notes") or None

            set_profile(
                conn,
                ingredient_id=r["ba_id"],
                profile=profile,
                source=source,
                confidence=confidence,
                notes=notes,
            )
            inserted += 1
            print(f"  + {r['ba_name']:<45}  source={source} conf={confidence or '-'}")

    api.close()
    print(f"\nSeeded {inserted} ingredients ({skipped} skipped with no profile).")
    print(f"Database: scripts/../data/flavor.sqlite")


if __name__ == "__main__":
    main()

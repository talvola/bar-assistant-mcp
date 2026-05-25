#!/usr/bin/env python3
"""
import_flavor_encoding.py — restore manual flavor work from JSON to SQLite.

Reads `scripts/flavor_encoding.json` (produced by export_flavor_encoding.py)
and upserts:

  - slot_meta + slot_constraint rows for each cocktail's encoded slots
  - flavor_profile rows for any manual profile edits (source='manual')

Idempotent — re-running over an existing DB upserts.

Run AFTER seed_flavor_db.py so bootstrap profiles (and ingredient_meta) are
present for any manual edits to attach to.

Usage:
    .venv/bin/python scripts/import_flavor_encoding.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bar_assistant_mcp.flavor_db import (
    connect, set_constraint, set_profile, upsert_ingredient_meta, upsert_slot_meta,
)

SRC = ROOT / "scripts" / "flavor_encoding.json"


def main() -> None:
    if not SRC.exists():
        sys.exit(f"Missing {SRC} — run export_flavor_encoding.py first, or "
                 "this file is gone from the working copy.")
    payload = json.loads(SRC.read_text())

    n_slots = 0
    n_constraints = 0
    n_manual = 0

    with connect() as conn:
        for cocktail in payload.get("cocktails", []):
            cid = cocktail["cocktail_id"]
            for slot in cocktail["slots"]:
                upsert_slot_meta(
                    conn,
                    cocktail_id=cid,
                    sort=slot["sort"],
                    category=slot["category"],
                    tolerance=slot.get("tolerance", "style"),
                    exact_ingredient_id=slot.get("exact_ingredient_id"),
                    also_accept_categories=slot.get("also_accept_categories"),
                    proof_min=slot.get("proof_min"),
                    proof_max=slot.get("proof_max"),
                )
                n_slots += 1
                for c in slot.get("constraints", []):
                    if c["kind"] == "point":
                        set_constraint(
                            conn, cid, slot["sort"], c["axis"], "point",
                            point_value=c["value"],
                            weight=c.get("weight", 1.0),
                        )
                    else:
                        set_constraint(
                            conn, cid, slot["sort"], c["axis"], "band",
                            band_lo=c["lo"], band_hi=c["hi"],
                            out_weight=c.get("out_weight", 1.0),
                            hard=c.get("hard", False),
                        )
                    n_constraints += 1

        for entry in payload.get("manual_profiles", []):
            iid = entry["ingredient_id"]
            # Make sure ingredient_meta row exists so the join later in queries works.
            upsert_ingredient_meta(
                conn,
                ingredient_id=iid,
                name=entry.get("name"),
                category=entry.get("category"),
            )
            set_profile(
                conn,
                ingredient_id=iid,
                profile=entry["profile"],
                source="manual",
                confidence=entry.get("confidence"),
                notes=entry.get("notes"),
            )
            n_manual += 1

    print(f"  imported {n_slots} slots / {n_constraints} constraints / {n_manual} manual profiles")
    print(f"  <- {SRC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

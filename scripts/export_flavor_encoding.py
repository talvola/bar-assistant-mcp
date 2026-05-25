#!/usr/bin/env python3
"""
export_flavor_encoding.py — dump manual flavor work to a versioned JSON.

The flavor SQLite (`data/flavor.sqlite`) holds two kinds of data:

  1. Bootstrap data — bottle flavor profiles seeded from the TGII pipeline
     (`tgii_bootstrap.py` + `seed_flavor_db.py`). Reproducible from the
     committed `tgii_{cat}_*.json` artifacts. Don't version the SQLite itself.

  2. Manual work — slot meta + slot constraints (per-recipe constraint
     encoding), and any flavor profiles tweaked by hand via the MCP's
     bar_set_flavor_profile tool (source='manual'). NOT reproducible from
     the bootstrap; this script writes them to `scripts/flavor_encoding.json`
     so they live in git.

The companion script `import_flavor_encoding.py` restores from the JSON.

Usage:
    .venv/bin/python scripts/export_flavor_encoding.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bar_assistant_mcp.flavor_db import connect

OUT = ROOT / "scripts" / "flavor_encoding.json"


def main() -> None:
    with connect() as conn:
        # Slot meta + per-axis constraints, grouped by (cocktail_id, sort).
        slot_meta_rows = conn.execute(
            "SELECT cocktail_id, sort, category, tolerance, exact_ingredient_id, "
            "also_accept_json, proof_min, proof_max "
            "FROM slot_meta ORDER BY cocktail_id, sort"
        ).fetchall()

        cocktails: dict[int, dict] = {}
        for r in slot_meta_rows:
            cid = r["cocktail_id"]
            cocktails.setdefault(cid, {"cocktail_id": cid, "slots": []})
            slot = {
                "sort": r["sort"],
                "category": r["category"],
                "tolerance": r["tolerance"],
            }
            if r["exact_ingredient_id"] is not None:
                slot["exact_ingredient_id"] = r["exact_ingredient_id"]
            if r["also_accept_json"]:
                slot["also_accept_categories"] = json.loads(r["also_accept_json"])
            if r["proof_min"] is not None:
                slot["proof_min"] = r["proof_min"]
            if r["proof_max"] is not None:
                slot["proof_max"] = r["proof_max"]
            slot["constraints"] = []
            cocktails[cid]["slots"].append(slot)

        # Index slots so we can hang constraints under them
        slot_index = {(c["cocktail_id"], s["sort"]): s
                      for c in cocktails.values() for s in c["slots"]}

        constraint_rows = conn.execute(
            "SELECT cocktail_id, sort, axis, kind, point_value, band_lo, band_hi, "
            "weight, out_weight, hard "
            "FROM slot_constraint ORDER BY cocktail_id, sort, axis"
        ).fetchall()
        for r in constraint_rows:
            key = (r["cocktail_id"], r["sort"])
            if key not in slot_index:
                print(f"  WARN: constraint for {key} has no slot_meta — skipped",
                      file=sys.stderr)
                continue
            c = {"axis": r["axis"], "kind": r["kind"]}
            if r["kind"] == "point":
                c["value"] = r["point_value"]
                if r["weight"] != 1.0:
                    c["weight"] = r["weight"]
            else:
                c["lo"] = r["band_lo"]
                c["hi"] = r["band_hi"]
                if r["out_weight"] != 1.0:
                    c["out_weight"] = r["out_weight"]
                if r["hard"]:
                    c["hard"] = True
            slot_index[key]["constraints"].append(c)

        # Hydrate cocktail names from ingredient_meta-like lookup (cocktail names
        # aren't in flavor SQLite). Skip — the importer doesn't need names; they're
        # nice-to-have for PR review but require hitting BA. Leave a TODO.

        # Manual profile edits (source='manual') — needs preserving across reseeds.
        manual_rows = conn.execute(
            "SELECT fp.ingredient_id, im.name, im.category, fp.axis, fp.value, "
            "fp.confidence, fp.notes, fp.scored_at "
            "FROM flavor_profile fp "
            "LEFT JOIN ingredient_meta im ON im.ingredient_id = fp.ingredient_id "
            "WHERE fp.source = 'manual' "
            "ORDER BY fp.ingredient_id, fp.axis"
        ).fetchall()

        manual_profiles: dict[int, dict] = {}
        for r in manual_rows:
            iid = r["ingredient_id"]
            entry = manual_profiles.setdefault(iid, {
                "ingredient_id": iid,
                "name": r["name"],
                "category": r["category"],
                "profile": {},
            })
            entry["profile"][r["axis"]] = r["value"]
            # Per-axis fields hoisted to entry level (they should usually agree
            # across axes for one ingredient, since bar_set_flavor_profile sets
            # them uniformly per call).
            if r["confidence"]:
                entry.setdefault("confidence", r["confidence"])
            if r["notes"]:
                entry.setdefault("notes", r["notes"])
            if r["scored_at"]:
                entry.setdefault("scored_at", r["scored_at"])

    payload = {
        "_README": (
            "Manual flavor-encoding work — slot constraints and any "
            "source='manual' profile edits. Regenerable from "
            "tgii_{cat}_*.json artifacts via tgii_bootstrap.py + "
            "seed_flavor_db.py, then this file via "
            "import_flavor_encoding.py. See CLAUDE.md."
        ),
        "cocktails": sorted(cocktails.values(), key=lambda c: c["cocktail_id"]),
        "manual_profiles": sorted(manual_profiles.values(),
                                  key=lambda p: p["ingredient_id"]),
    }

    OUT.write_text(json.dumps(payload, indent=2))
    n_cocktails = len(payload["cocktails"])
    n_slots = sum(len(c["slots"]) for c in payload["cocktails"])
    n_constraints = sum(len(s["constraints"])
                        for c in payload["cocktails"] for s in c["slots"])
    n_manual = len(payload["manual_profiles"])
    print(f"  exported {n_cocktails} cocktails / {n_slots} slots / {n_constraints} constraints / {n_manual} manual profiles")
    print(f"  -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

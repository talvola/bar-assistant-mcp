#!/usr/bin/env python3
"""
port_phase_a_to_ba.py — port the Phase A SQLite into a BA backend via HTTP.

Reads `data/flavor.sqlite` (Phase A storage) and POSTs profiles + slot meta
+ slot constraints to a target BA instance through the Slice 2 endpoints.

Idempotent: re-running with the same data is a no-op (PUT semantics).

Usage:
    .venv/bin/python scripts/port_phase_a_to_ba.py \\
        --ba-url http://192.168.1.64:3002 \\
        --token "1|abc..." \\
        --bar-id 1

For the sandbox: only ingredient IDs that exist in the target bar's BA DB
will receive profile data — others are reported as `skipped (missing)` and
no error is raised. This lets you smoke-test against a sparse sandbox.

For production: every ingredient ID from the SQLite should match (since
that's where the IDs came from). Any mismatch indicates a drift problem
worth surfacing.
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DEFAULT = ROOT / "data" / "flavor.sqlite"


def http(method: str, url: str, token: str, bar_id: int, body=None):
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Bar-Assistant-Bar-Id": str(bar_id),
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read() or b""
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"raw": body.decode(errors="replace")[:300]}
        return e.code, payload


def port_profiles(conn, base, token, bar_id, dry_run, verbose):
    rows = conn.execute("""
        SELECT
            im.ingredient_id, im.name, im.category, fp.axis, fp.value,
            fp.source, fp.confidence, fp.notes, fp.scored_at
        FROM ingredient_meta im
        JOIN flavor_profile fp ON fp.ingredient_id = im.ingredient_id
    """).fetchall()

    by_ing: dict[int, dict] = {}
    for r in rows:
        iid = r["ingredient_id"]
        if iid not in by_ing:
            by_ing[iid] = {
                "name": r["name"],
                "category": r["category"] or "",
                "profile": {},
                "source": None,
                "confidence": None,
                "notes": None,
                "scored_at": None,
            }
        e = by_ing[iid]
        e["profile"][r["axis"]] = r["value"]
        # last-write-wins for provenance fields (they're per-row in Phase A
        # but should usually agree across axes since bar_set_flavor_profile
        # sets them uniformly per call)
        if r["source"]:
            e["source"] = r["source"]
        if r["confidence"]:
            e["confidence"] = r["confidence"]
        if r["notes"]:
            e["notes"] = r["notes"]
        if r["scored_at"]:
            e["scored_at"] = r["scored_at"]

    counts = {"ok": 0, "missing": 0, "error": 0, "skipped_no_category": 0}
    for iid, entry in sorted(by_ing.items()):
        if not entry["category"]:
            counts["skipped_no_category"] += 1
            if verbose:
                print(f"  - skipped (no category): {iid} {entry['name']}")
            continue

        body = {
            "category": entry["category"],
            "profile": entry["profile"],
            "source": entry["source"],
            "confidence": entry["confidence"],
            "notes": entry["notes"],
            "scored_at": entry["scored_at"],
        }
        if dry_run:
            print(f"  DRY {iid:5d}  {entry['name'][:45]:<45}  cat={entry['category']:<22}  axes={len(entry['profile'])}")
            counts["ok"] += 1
            continue

        status, resp = http("PUT", f"{base}/api/ingredients/{iid}/flavor-profile", token, bar_id, body)
        if status == 200:
            counts["ok"] += 1
            if verbose:
                print(f"  ✓ {iid:5d}  {entry['name'][:45]:<45}  cat={entry['category']}")
        elif status == 404:
            counts["missing"] += 1
            if verbose:
                print(f"  ~ {iid:5d}  {entry['name'][:45]:<45}  not in target bar")
        else:
            counts["error"] += 1
            print(f"  ! {iid:5d}  {entry['name'][:45]:<45}  HTTP {status}  {resp}")

    return counts


def port_slots(conn, base, token, bar_id, dry_run, verbose):
    metas = conn.execute("""
        SELECT cocktail_id, sort, category, tolerance, exact_ingredient_id,
               also_accept_json, proof_min, proof_max
        FROM slot_meta
        ORDER BY cocktail_id, sort
    """).fetchall()
    constraints = conn.execute("""
        SELECT cocktail_id, sort, axis, kind, point_value, band_lo, band_hi,
               weight, out_weight, hard
        FROM slot_constraint
        ORDER BY cocktail_id, sort, axis
    """).fetchall()
    by_slot: dict[tuple[int, int], list[sqlite3.Row]] = {}
    for c in constraints:
        by_slot.setdefault((c["cocktail_id"], c["sort"]), []).append(c)

    counts = {"meta_ok": 0, "meta_missing": 0, "meta_error": 0,
              "constraint_ok": 0, "constraint_missing": 0, "constraint_error": 0}
    for m in metas:
        meta_body = {
            "category": m["category"],
            "tolerance": m["tolerance"] or "style",
            "exact_ingredient_id": m["exact_ingredient_id"],
            "also_accept_categories": json.loads(m["also_accept_json"]) if m["also_accept_json"] else None,
            "proof_min": m["proof_min"],
            "proof_max": m["proof_max"],
        }
        meta_url = f"{base}/api/cocktails/{m['cocktail_id']}/slots/{m['sort']}/meta"

        if dry_run:
            print(f"  DRY meta cid={m['cocktail_id']:4d} sort={m['sort']} cat={m['category']}")
            counts["meta_ok"] += 1
        else:
            status, resp = http("PUT", meta_url, token, bar_id, meta_body)
            if status == 200:
                counts["meta_ok"] += 1
                if verbose:
                    print(f"  ✓ meta cid={m['cocktail_id']:4d} sort={m['sort']} cat={m['category']}")
            elif status == 404:
                counts["meta_missing"] += 1
                if verbose:
                    print(f"  ~ meta cid={m['cocktail_id']} sort={m['sort']}  cocktail not in target bar — skipping constraints")
                continue
            else:
                counts["meta_error"] += 1
                print(f"  ! meta cid={m['cocktail_id']} sort={m['sort']} HTTP {status}  {resp}")
                continue

        for c in by_slot.get((m["cocktail_id"], m["sort"]), []):
            if c["kind"] == "point":
                body = {"kind": "point", "value": c["point_value"], "weight": float(c["weight"])}
            else:
                body = {
                    "kind": "band",
                    "lo": c["band_lo"],
                    "hi": c["band_hi"],
                    "out_weight": float(c["out_weight"]),
                    "hard": bool(c["hard"]),
                }
            url = f"{base}/api/cocktails/{c['cocktail_id']}/slots/{c['sort']}/constraints/{c['axis']}"
            if dry_run:
                counts["constraint_ok"] += 1
                continue
            status, resp = http("PUT", url, token, bar_id, body)
            if status == 200:
                counts["constraint_ok"] += 1
            elif status == 404:
                counts["constraint_missing"] += 1
            else:
                counts["constraint_error"] += 1
                print(f"  ! constraint cid={c['cocktail_id']} sort={c['sort']} axis={c['axis']} HTTP {status}  {resp}")
    return counts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ba-url", required=True, help="e.g. http://192.168.1.64:3002")
    p.add_argument("--token", default=os.environ.get("BAR_ASSISTANT_TOKEN"),
                   help="Sanctum API token (or set BAR_ASSISTANT_TOKEN env)")
    p.add_argument("--bar-id", type=int, default=int(os.environ.get("BAR_ASSISTANT_BAR_ID", "1")))
    p.add_argument("--db", type=Path, default=DB_DEFAULT, help="Phase A SQLite path")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--only", choices=("profiles", "slots", "all"), default="all")
    args = p.parse_args()

    if not args.token:
        sys.exit("Need --token or BAR_ASSISTANT_TOKEN env")
    if not args.db.exists():
        sys.exit(f"Phase A SQLite not found: {args.db}")

    base = args.ba_url.rstrip("/")
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # Sanity: target should accept auth + bar header
    status, resp = http("GET", f"{base}/api/flavor/categories", args.token, args.bar_id)
    if status != 200:
        sys.exit(f"Sanity check failed: GET /api/flavor/categories returned {status}: {resp}")
    print(f"  ✓ connected; target has {len(resp.get('data', []))} categories declared")

    if args.only in ("profiles", "all"):
        print("\n== Porting profiles ==")
        pc = port_profiles(conn, base, args.token, args.bar_id, args.dry_run, args.verbose)
        print(f"\n  profiles: ok={pc['ok']} missing={pc['missing']} error={pc['error']} skipped_no_category={pc['skipped_no_category']}")

    if args.only in ("slots", "all"):
        print("\n== Porting slot meta + constraints ==")
        sc = port_slots(conn, base, args.token, args.bar_id, args.dry_run, args.verbose)
        print(f"\n  slot_meta: ok={sc['meta_ok']} missing={sc['meta_missing']} error={sc['meta_error']}")
        print(f"  constraints: ok={sc['constraint_ok']} missing={sc['constraint_missing']} error={sc['constraint_error']}")


if __name__ == "__main__":
    main()

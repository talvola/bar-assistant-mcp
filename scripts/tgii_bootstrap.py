#!/usr/bin/env python3
"""
tgii_bootstrap.py — Match BA gin shelf to The Gin Is In flavor diagrams.

Pulls every gin on shelf from Bar Assistant, fuzzy-matches each name against
TGII's reviews sitemap, downloads + parses each match's flavor SVG, and writes
a JSON report classifying each as matched / ambiguous / no_match / no_svg.

Usage:
    .venv/bin/python scripts/tgii_bootstrap.py

Reads BAR_ASSISTANT_TOKEN from env, falling back to .mcp.json.

Output:
    scripts/tgii_bootstrap_results.json     full report with profiles
    stderr                                  progress and summary
"""
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bar_assistant_mcp.api import BarAssistantAPI

BA_URL = os.environ.get("BAR_ASSISTANT_URL", "https://erikbarapi.duckdns.org")
GIN_ANCESTOR_PATH = "363/383/"
TGII_SITEMAP = "https://theginisin.com/reviews-sitemap.xml"
TGII_SVG_TPL = "https://theginisin.com/wp-content/uploads/flavor-diagrams/{slug}.svg"
NS = {"svg": "http://www.w3.org/2000/svg"}
UA = "Mozilla/5.0 (bar-assistant-mcp tgii-bootstrap/0.1)"
TIMEOUT = 20
TOP_N = 5
AUTO_THRESHOLD = 0.85
SEPARATION = 0.08

OUT = ROOT / "scripts" / "tgii_bootstrap_results.json"
OVERRIDES = ROOT / "scripts" / "tgii_overrides.json"
UNOFFICIAL_SCORES = ROOT / "scripts" / "tgii_unofficial_scores.json"


def ba_token():
    if t := os.environ.get("BAR_ASSISTANT_TOKEN"):
        return t
    mcp = ROOT / ".mcp.json"
    if mcp.exists():
        cfg = json.loads(mcp.read_text())
        return cfg["mcpServers"]["bar-assistant"]["env"]["BAR_ASSISTANT_TOKEN"]
    sys.exit("Set BAR_ASSISTANT_TOKEN (env or .mcp.json)")


def http_get(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT
    ).read()


def load_tgii_slugs():
    xml = http_get(TGII_SITEMAP).decode()
    return re.findall(r"<loc>https://theginisin\.com/gin-reviews/([^/]+)/</loc>", xml)


def normalize(s):
    s = s.lower()
    s = re.sub(r"[‘’'`]", "", s)
    s = re.sub(r"\bgin\b", "", s)           # drop "gin" — present in nearly every name
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokenize(s):
    return set(t for t in normalize(s).split() if len(t) > 1)


def build_slug_index(slugs):
    """Per-slug token set plus IDF weights from the slug corpus."""
    per_slug = {s: tokenize(s.replace("-", " ")) for s in slugs}
    df = Counter()
    for tokens in per_slug.values():
        for t in tokens:
            df[t] += 1
    N = len(slugs)
    idf = {t: math.log(N / c) for t, c in df.items()}
    return per_slug, idf


def fuzzy_match(name, slugs, per_slug, idf, top_n=TOP_N):
    """IDF-weighted token overlap, with SequenceMatcher as tiebreak.

    score = 0.5 * weighted_recall + 0.4 * weighted_precision + 0.1 * char_ratio
      weighted_recall:    overlap weight / bottle-token weight (penalizes missing brand words)
      weighted_precision: overlap weight / slug-token weight  (penalizes extra unrelated words)
      char_ratio:         SequenceMatcher on the normalized strings (smooth tiebreak)
    """
    bottle_tokens = tokenize(name)
    if not bottle_tokens:
        return [(0.0, "")]
    bottle_weight = sum(idf.get(t, 0) for t in bottle_tokens) or 1.0
    name_n = normalize(name)

    scored = []
    for s, slug_tokens in per_slug.items():
        if not slug_tokens:
            continue
        overlap = bottle_tokens & slug_tokens
        if not overlap:
            continue
        overlap_w = sum(idf.get(t, 0) for t in overlap)
        slug_w = sum(idf.get(t, 0) for t in slug_tokens) or 1.0
        recall = overlap_w / bottle_weight
        precision = overlap_w / slug_w
        char = SequenceMatcher(None, name_n, normalize(s.replace("-", " "))).ratio()
        score = 0.5 * recall + 0.4 * precision + 0.1 * char
        scored.append((score, s))

    scored.sort(reverse=True)
    return scored[:top_n] or [(0.0, "")]


def parse_tgii_svg(svg_bytes):
    root = ET.fromstring(svg_bytes)
    axes = {}
    for g in root.findall("svg:g", NS):
        label_el = g.find("svg:text", NS)
        polys = g.findall("svg:polygon", NS)
        if label_el is None or len(polys) != 3:
            continue
        label = label_el.text.strip().lower()
        score = sum(
            1
            for p in polys
            if (p.get("fill") or "").upper() not in ("#FFFFFF", "#FFF", "", "WHITE", "NONE")
        )
        axes[label] = score
    return axes


def load_overrides():
    if not OVERRIDES.exists():
        return {}
    return json.loads(OVERRIDES.read_text())


def load_unofficial_scores():
    if not UNOFFICIAL_SCORES.exists():
        return {}
    raw = json.loads(UNOFFICIAL_SCORES.read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def write_overrides(overrides):
    OVERRIDES.write_text(json.dumps(overrides, indent=2, sort_keys=True))


def list_shelf_gins(api):
    """Shelf entries whose path starts with the Gin ancestor AND are bottles
    (depth > 2 — excludes subtype categories like 'Old Tom Gin' that are on
    shelf as placeholders rather than specific bottles)."""
    gins, page = [], 1
    while True:
        resp = api.list_ingredients(filter_on_shelf=True, limit=200, page=page)
        for ing in resp.get("data", []):
            path = (ing.get("materialized_path") or "").strip("/")
            if not path.startswith(GIN_ANCESTOR_PATH.strip("/")):
                continue
            if len(path.split("/")) <= 2:           # 363/383 = subtype category
                continue
            gins.append(ing)
        meta = resp.get("meta", {})
        if page >= meta.get("last_page", 1):
            break
        page += 1
    return gins


def fetch_profile(slug):
    """Fetch + parse a TGII SVG. Returns (profile, error_status, error_msg)."""
    try:
        return parse_tgii_svg(http_get(TGII_SVG_TPL.format(slug=slug))), None, None
    except urllib.error.HTTPError as e:
        return None, ("no_svg" if e.code == 404 else "svg_error"), f"HTTP {e.code}"
    except Exception as e:
        return None, "svg_error", f"{type(e).__name__}: {e}"


def main():
    print("Loading TGII reviews sitemap...", file=sys.stderr)
    slugs = load_tgii_slugs()
    per_slug, idf = build_slug_index(slugs)
    print(f"  {len(slugs)} gin reviews indexed", file=sys.stderr)

    overrides = load_overrides()
    if overrides:
        print(f"  {len(overrides)} override entries loaded from {OVERRIDES.name}", file=sys.stderr)
    unofficial_scores = load_unofficial_scores()
    if unofficial_scores:
        print(f"  {len(unofficial_scores)} LLM-derived scores loaded from {UNOFFICIAL_SCORES.name}", file=sys.stderr)

    print("Pulling shelf gins from Bar Assistant...", file=sys.stderr)
    api = BarAssistantAPI(BA_URL, ba_token(), bar_id=1)
    gins = list_shelf_gins(api)
    print(f"  {len(gins)} bottle-level gins on shelf\n", file=sys.stderr)

    results = []
    for ing in sorted(gins, key=lambda x: x["name"].lower()):
        name = ing["name"]
        key = str(ing["id"])
        candidates = fuzzy_match(name, slugs, per_slug, idf)
        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else (0.0, "")
        result = {
            "ba_id": ing["id"],
            "ba_name": name,
            "ba_path": ing.get("materialized_path"),
            "candidates": [{"score": round(s, 3), "slug": sl} for s, sl in candidates],
        }

        ov = overrides.get(key)
        if ov and ov.get("unofficial"):
            scored = unofficial_scores.get(key)
            if scored and "profile" in scored:
                result["status"] = "matched"
                result["source"] = "llm_from_description"
                result["profile"] = scored["profile"]
                if c := scored.get("confidence"):
                    result["confidence"] = c
                if r := scored.get("reasoning"):
                    result["reasoning"] = r
            else:
                result["status"] = "unofficial"
                result["source"] = "manual_override"
            if note := ov.get("notes"):
                result["notes"] = note
        elif ov and ov.get("slug"):
            slug = ov["slug"]
            profile, err_status, err_msg = fetch_profile(slug)
            result["matched_slug"] = slug
            result["source"] = "manual_override"
            if profile is not None:
                result["status"] = "matched"
                result["profile"] = profile
            else:
                result["status"] = err_status
                result["error"] = err_msg
        elif best[0] >= AUTO_THRESHOLD and (best[0] - second[0]) >= SEPARATION:
            slug = best[1]
            profile, err_status, err_msg = fetch_profile(slug)
            result["matched_slug"] = slug
            result["match_score"] = round(best[0], 3)
            result["source"] = "auto_fuzzy"
            if profile is not None:
                result["status"] = "matched"
                result["profile"] = profile
            else:
                result["status"] = err_status
                result["error"] = err_msg
        elif best[0] >= 0.50:
            result["status"] = "ambiguous"
        else:
            result["status"] = "no_match"

        results.append(result)
        print(f"  [{result['status']:11}] {name[:55]:<55}", file=sys.stderr)
        if result["status"] == "ambiguous":
            for s, sl in candidates[:3]:
                print(f"                 {sl:<45}  {s:.2f}", file=sys.stderr)
        elif result["status"] == "matched":
            src = result.get("source", "")
            if src == "llm_from_description":
                p = result["profile"]
                pstr = " ".join(f"{a[:3]}={p.get(a, '-')}" for a in
                                ("juniper", "citrus", "floral", "heat", "spice", "herbal", "fruited"))
                conf = result.get("confidence", "")
                print(f"                 -> LLM-scored ({conf})  {pstr}", file=sys.stderr)
            else:
                tag = " (override)" if src == "manual_override" else f"  ({best[0]:.2f})"
                print(f"                 -> {result['matched_slug']}{tag}", file=sys.stderr)
        elif result["status"] == "unofficial":
            print(f"                 (marked unofficial — needs LLM fallback)", file=sys.stderr)

    # Update overrides file with any rows still needing user input. Existing
    # entries are preserved (we never overwrite a slug the user has filled in);
    # only the suggestions list is refreshed.
    needs_input_statuses = {"ambiguous", "no_match", "no_svg", "svg_error"}
    new_overrides = dict(overrides)
    for r in results:
        if r["status"] not in needs_input_statuses:
            continue
        key = str(r["ba_id"])
        suggestions = [c["slug"] for c in r["candidates"][:5]]
        if key in new_overrides:
            new_overrides[key]["suggestions"] = suggestions
            new_overrides[key].setdefault("status_seen", r["status"])
        else:
            new_overrides[key] = {
                "name": r["ba_name"],
                "slug": None,        # fill in the correct TGII slug, OR…
                "unofficial": False, #   set this true if not on TGII (LLM fallback)
                "suggestions": suggestions,
                "notes": "",
                "status_seen": r["status"],
            }
    write_overrides(new_overrides)

    by_status = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)
    print(f"\n--- Summary of {len(results)} gins ---", file=sys.stderr)
    for st in ("matched", "unofficial", "ambiguous", "no_match", "no_svg", "svg_error"):
        n = len(by_status.get(st, []))
        if n:
            print(f"  {st:11}: {n}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nFull report   -> {OUT.relative_to(ROOT)}", file=sys.stderr)
    print(f"Overrides file -> {OVERRIDES.relative_to(ROOT)}  (edit, then re-run)", file=sys.stderr)
    api.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
tgii_bootstrap.py — Match BA shelf entries to The Gin Is In flavor diagrams.

Pulls every bottle on shelf for a given category from Bar Assistant, fuzzy-matches
each name against TGII's category sitemap, downloads + parses each match's flavor
SVG, and writes a JSON report classifying each as matched / ambiguous / no_match /
no_svg.

Usage:
    .venv/bin/python scripts/tgii_bootstrap.py                  # gin (default)
    .venv/bin/python scripts/tgii_bootstrap.py --category aquavit

Reads BAR_ASSISTANT_TOKEN from env, falling back to .mcp.json.

Per-category output (under scripts/):
    tgii_{cat}_results.json                  full report with profiles
    tgii_{cat}_overrides.json                user-edited slug overrides + unofficial flags
    tgii_{cat}_unofficial_scores.json        LLM-derived 0-3 axis scores
"""
import argparse
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
TGII_SVG_TPL = "https://theginisin.com/wp-content/uploads/flavor-diagrams/{slug}.svg"
NS = {"svg": "http://www.w3.org/2000/svg"}
UA = "Mozilla/5.0 (bar-assistant-mcp tgii-bootstrap/0.2)"
TIMEOUT = 20
TOP_N = 5
AUTO_THRESHOLD = 0.85
SEPARATION = 0.08


def parse_tgii_svg_grouped(svg_bytes):
    """Gin layout: each axis is a <g> containing 1 <text> label + 3 <polygon>."""
    root = ET.fromstring(svg_bytes)
    axes = {}
    for g in root.findall("svg:g", NS):
        label_el = g.find("svg:text", NS)
        polys = g.findall("svg:polygon", NS)
        if label_el is None or len(polys) != 3:
            continue
        label = label_el.text.strip().lower()
        score = _count_filled(polys)
        axes[label] = score
    return axes


def parse_tgii_svg_flat(svg_bytes, expected_axes):
    """Aquavit layout: flat children, sequence of 3 <polygon> + 1 <text> repeats.

    No <g> grouping. We walk children in order, batching every 3 polygons; the
    next text element is the axis label. Stop when we have all expected_axes.
    """
    root = ET.fromstring(svg_bytes)
    axes = {}
    pending_polys = []
    expected_lc = {a.lower() for a in expected_axes}
    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "polygon":
            pending_polys.append(el)
        elif tag == "text" and len(pending_polys) == 3:
            label = (el.text or "").strip().lower()
            if label in expected_lc:
                axes[label] = _count_filled(pending_polys)
            pending_polys = []
            if len(axes) == len(expected_axes):
                break
        elif tag == "text":
            # Stray text (title, watermark) without 3 preceding polys — reset.
            pending_polys = []
    return axes


def _count_filled(polys):
    return sum(
        1 for p in polys
        if (p.get("fill") or "").upper() not in ("#FFFFFF", "#FFF", "", "WHITE", "NONE")
    )


# --- Per-category configuration ---------------------------------------------

CATEGORIES = {
    "gin": {
        "ba_ancestor_path": "363/383/",
        # min path depth to count as a bottle (vs subtype placeholder). Gin in BA:
        # 363/ = spirits, 363/383/ = Gin category, 363/383/<style>/ = style root
        # (London Dry, Old Tom — also on shelf as placeholders), 363/383/<style>/<brand>/
        # = real bottle (depth 4 when ancestor includes brand parent).
        # In practice brand-bottles' materialized_path is 363/383/<style>/, depth 3.
        "min_path_depth": 3,
        "sitemap_url": "https://theginisin.com/reviews-sitemap.xml",
        "slug_re": re.compile(r"<loc>https://theginisin\.com/gin-reviews/([^/]+)/</loc>"),
        "category_word_re": re.compile(r"\bgin\b"),
        "axes": ("juniper", "citrus", "floral", "heat", "spice", "herbal", "fruited"),
        "svg_parser": lambda b, _axes: parse_tgii_svg_grouped(b),
    },
    "aquavit": {
        "ba_ancestor_path": "363/403/",
        # BA doesn't model aquavit subtypes, so brand bottles live directly under
        # the Aquavit category (depth 2: 363/403/).
        "min_path_depth": 2,
        "sitemap_url": "https://theginisin.com/aquavit-sitemap.xml",
        "slug_re": re.compile(r"<loc>https://theginisin\.com/aquavit/([^/]+)/</loc>"),
        "category_word_re": re.compile(r"\baquavit\b"),
        "axes": ("juniper", "citrus", "floral", "heat", "spice", "herbal"),
        "svg_parser": parse_tgii_svg_flat,
    },
    # ----- LLM-only categories (no TGII corpus) -----
    # `skip_tgii: True` short-circuits the sitemap fetch + fuzzy match — every
    # bottle goes straight to the override file as `unofficial: true` so we
    # LLM-score it from BA description + spirits-sheet research.
    #
    # Bourbon and rye share axes: spice (rye-grain pepper / baking spice),
    # sweet (corn/grain sweetness), oak (wood weight), vanilla (sweet wood),
    # fruit (esters/dried fruit), body (proof + viscosity). Same scale 0–3.
    "bourbon": {
        "ba_ancestor_path": "363/370/371/",
        "min_path_depth": 3,
        "skip_tgii": True,
        "category_word_re": re.compile(r"\b(bourbon|whiskey|whisky)\b"),
        "axes": ("spice", "sweet", "oak", "vanilla", "fruit", "body"),
    },
    "rye": {
        "ba_ancestor_path": "363/370/347/",
        "min_path_depth": 3,
        "skip_tgii": True,
        "category_word_re": re.compile(r"\b(rye|whiskey|whisky)\b"),
        "axes": ("spice", "sweet", "oak", "vanilla", "fruit", "body"),
    },
    # Scotch swaps `spice` for `smoke` — peat is the defining axis for scotch.
    "scotch": {
        "ba_ancestor_path": "363/370/372/",
        "min_path_depth": 3,
        "skip_tgii": True,
        "category_word_re": re.compile(r"\b(scotch|whisky|whiskey|malt)\b"),
        "axes": ("smoke", "sweet", "oak", "vanilla", "fruit", "body"),
    },
    # American Single Malt — distinct enough from scotch to be its own category
    # (heavier new-oak, often smoked rather than peated). Shares scotch's axes
    # since smoke is still the defining dimension. Used as scotch substitute in
    # smoke-forward applications (Penicillin float, Godfather, etc.).
    "american_single_malt": {
        "ba_ancestor_path": "363/370/431/",
        # `extra_bottle_ids` pulls in bottles whose materialized_path is outside
        # the main ancestor — Griffo Waldos (id=247) is a hop-influenced single
        # malt sitting at 363/370/470/ alongside the unrelated Seven Stills
        # experimentals, so we cherry-pick it.
        "extra_bottle_ids": (247,),
        "min_path_depth": 3,
        "skip_tgii": True,
        "category_word_re": re.compile(r"\b(single|malt|american|whiskey|whisky)\b"),
        "axes": ("smoke", "sweet", "oak", "vanilla", "fruit", "body"),
    },
    # Amaro covers bitter aperitivi (Aperol/Campari) + classical Italian
    # digestivi (Averna/Montenegro/Nonino) + fernet family + alpine/gentian +
    # American artisanal (BroVo, Brucato, etc). Most bottles live under
    # 364/407/ but Aperol/Campari are at 364/414/ (bittersweet aperitivi)
    # and Suze/Bonal are at 364/409/ (herbal liqueurs) — pulled in by id.
    # Seven axes capture the family variation: bitter is the defining axis,
    # opposed by sweet; the rest (citrus/herbal/dark/mint/root) distinguish
    # families like Fernet (mint+bitter), Cynar (root/vegetal), Averna (dark),
    # Montenegro (sweet+citrus), Suze (root/gentian).
    "amaro": {
        "ba_ancestor_path": "364/407/",
        "extra_bottle_ids": (
            174,  # Campari — under 364/414/ (bittersweet aperitivi)
            341,  # Aperol — under 364/414/
            187,  # Suze Saveur d'Autrefois — under 364/409/ (Herbal Liqueurs)
            543,  # Bonal Gentiane-Quina — under 365/435/ (Vermouth-adjacent quina)
            487,  # Brucato Amaro Chaparral — NULL path
            540,  # Salers Gentiane — under 364/409/, sweeter cousin of Suze
        ),
        # BA has both depth-2 brand bottles (Cappelletti Pasubio, BroVo collection,
        # Mödr, etc. — direct children of the Amaro category) AND depth-3 bottles
        # (Averna under 'Dark/Cola', Cynar under 'Vegetal', etc.). Use depth=2 to
        # capture both; subtype placeholders (Citrus Amaro, Vegetal Amaro, etc.)
        # are filtered downstream by skipping no-ABV / no-description entries
        # during scoring.
        "min_path_depth": 2,
        "skip_tgii": True,
        "category_word_re": re.compile(r"\b(amaro|amari|fernet|liqueur|aperitif)\b"),
        "axes": ("bitter", "sweet", "citrus", "herbal", "dark", "mint", "root"),
    },
    # Herbal liqueurs — sweet/aromatic, NOT bitter. Chartreuse family,
    # Benedictine, Agwa, Strega, etc. Distinct from amaro (no `bitter` axis;
    # `honey` + `cooling` distinguish the family-defining characters of
    # Benedictine vs Green Chartreuse vs Agwa).
    "herbal_liqueur": {
        "ba_ancestor_path": "364/409/",
        "min_path_depth": 2,
        "skip_tgii": True,
        "category_word_re": re.compile(r"\b(liqueur|herbal|amaro|aperitif)\b"),
        "axes": ("herbal", "sweet", "anise", "honey", "spice", "cooling"),
    },
}


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


def load_tgii_slugs(cfg):
    xml = http_get(cfg["sitemap_url"]).decode()
    return cfg["slug_re"].findall(xml)


def normalize(s, cfg):
    s = s.lower()
    s = re.sub(r"[‘’'`]", "", s)
    s = cfg["category_word_re"].sub("", s)   # drop the category word — present in nearly every name
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokenize(s, cfg):
    return set(t for t in normalize(s, cfg).split() if len(t) > 1)


def build_slug_index(slugs, cfg):
    per_slug = {s: tokenize(s.replace("-", " "), cfg) for s in slugs}
    df = Counter()
    for tokens in per_slug.values():
        for t in tokens:
            df[t] += 1
    N = len(slugs)
    idf = {t: math.log(N / c) for t, c in df.items()}
    return per_slug, idf


def fuzzy_match(name, slugs, per_slug, idf, cfg, top_n=TOP_N):
    """IDF-weighted token overlap, with SequenceMatcher as tiebreak."""
    bottle_tokens = tokenize(name, cfg)
    if not bottle_tokens:
        return [(0.0, "")]
    bottle_weight = sum(idf.get(t, 0) for t in bottle_tokens) or 1.0
    name_n = normalize(name, cfg)

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
        char = SequenceMatcher(None, name_n, normalize(s.replace("-", " "), cfg)).ratio()
        score = 0.5 * recall + 0.4 * precision + 0.1 * char
        scored.append((score, s))

    scored.sort(reverse=True)
    return scored[:top_n] or [(0.0, "")]


def list_shelf_bottles(api, cfg):
    """Shelf entries whose path starts with the category ancestor AND are at
    least cfg['min_path_depth'] deep (excludes subtype placeholders for
    categories like gin that model styles).

    cfg['extra_bottle_ids'] additionally pulls in specific BA ingredients by
    id — escape hatch for bottles that belong in the category but whose
    materialized_path lives elsewhere (e.g. Griffo Waldos under Hop-Influenced
    Whiskey rather than American Single Malt).
    """
    bottles, page = [], 1
    ancestor = cfg["ba_ancestor_path"].strip("/")
    min_depth = cfg["min_path_depth"]
    extra = set(cfg.get("extra_bottle_ids") or ())
    seen_ids = set()
    while True:
        resp = api.list_ingredients(filter_on_shelf=True, limit=200, page=page)
        for ing in resp.get("data", []):
            path = (ing.get("materialized_path") or "").strip("/")
            path_match = path.startswith(ancestor) and len(path.split("/")) >= min_depth
            if path_match or ing["id"] in extra:
                bottles.append(ing)
                seen_ids.add(ing["id"])
        meta = resp.get("meta", {})
        if page >= meta.get("last_page", 1):
            break
        page += 1
    # Fetch any extras not encountered above (they may not be on shelf right now
    # but the category still owns them; skip silently if BA returns 404).
    for iid in extra - seen_ids:
        try:
            ing = api.get_ingredient(iid).get("data")
            if ing:
                bottles.append(ing)
        except Exception:
            pass
    return bottles


def fetch_profile(slug, cfg):
    """Fetch + parse a TGII SVG. Returns (profile, error_status, error_msg)."""
    try:
        svg = http_get(TGII_SVG_TPL.format(slug=slug))
        return cfg["svg_parser"](svg, cfg["axes"]), None, None
    except urllib.error.HTTPError as e:
        return None, ("no_svg" if e.code == 404 else "svg_error"), f"HTTP {e.code}"
    except Exception as e:
        return None, "svg_error", f"{type(e).__name__}: {e}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--category", choices=list(CATEGORIES), default="gin")
    args = p.parse_args()
    cat = args.category
    cfg = CATEGORIES[cat]

    out_results = ROOT / "scripts" / f"tgii_{cat}_results.json"
    out_overrides = ROOT / "scripts" / f"tgii_{cat}_overrides.json"
    out_unofficial = ROOT / "scripts" / f"tgii_{cat}_unofficial_scores.json"

    if cfg.get("skip_tgii"):
        print(f"LLM-only category '{cat}' — skipping TGII sitemap fetch", file=sys.stderr)
        slugs, per_slug, idf = [], {}, {}
    else:
        print(f"Loading TGII {cat} sitemap...", file=sys.stderr)
        slugs = load_tgii_slugs(cfg)
        per_slug, idf = build_slug_index(slugs, cfg)
        print(f"  {len(slugs)} {cat} reviews indexed", file=sys.stderr)

    overrides = json.loads(out_overrides.read_text()) if out_overrides.exists() else {}
    if overrides:
        print(f"  {len(overrides)} override entries loaded from {out_overrides.name}", file=sys.stderr)
    unofficial_scores = {}
    if out_unofficial.exists():
        raw = json.loads(out_unofficial.read_text())
        unofficial_scores = {k: v for k, v in raw.items() if not k.startswith("_")}
        print(f"  {len(unofficial_scores)} LLM-derived scores loaded from {out_unofficial.name}", file=sys.stderr)

    print(f"Pulling shelf {cat}s from Bar Assistant...", file=sys.stderr)
    api = BarAssistantAPI(BA_URL, ba_token(), bar_id=1)
    bottles = list_shelf_bottles(api, cfg)
    print(f"  {len(bottles)} bottle-level {cat}s on shelf\n", file=sys.stderr)

    results = []
    for ing in sorted(bottles, key=lambda x: x["name"].lower()):
        name = ing["name"]
        key = str(ing["id"])
        candidates = fuzzy_match(name, slugs, per_slug, idf, cfg)
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
            profile, err_status, err_msg = fetch_profile(slug, cfg)
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
            profile, err_status, err_msg = fetch_profile(slug, cfg)
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
                pstr = " ".join(f"{a[:3]}={p.get(a, '-')}" for a in cfg["axes"])
                conf = result.get("confidence", "")
                print(f"                 -> LLM-scored ({conf})  {pstr}", file=sys.stderr)
            else:
                tag = " (override)" if src == "manual_override" else f"  ({best[0]:.2f})"
                print(f"                 -> {result['matched_slug']}{tag}", file=sys.stderr)
        elif result["status"] == "unofficial":
            print(f"                 (marked unofficial — needs LLM fallback)", file=sys.stderr)

    needs_input_statuses = {"ambiguous", "no_match", "no_svg", "svg_error"}
    new_overrides = dict(overrides)
    default_unofficial = cfg.get("skip_tgii", False)
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
                "slug": None,
                "unofficial": default_unofficial,
                "suggestions": suggestions,
                "notes": "",
                "status_seen": r["status"],
            }
    out_overrides.write_text(json.dumps(new_overrides, indent=2, sort_keys=True))

    by_status = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)
    print(f"\n--- Summary of {len(results)} {cat}s ---", file=sys.stderr)
    for st in ("matched", "unofficial", "ambiguous", "no_match", "no_svg", "svg_error"):
        n = len(by_status.get(st, []))
        if n:
            print(f"  {st:11}: {n}", file=sys.stderr)

    out_results.parent.mkdir(parents=True, exist_ok=True)
    out_results.write_text(json.dumps(results, indent=2))
    print(f"\nFull report   -> {out_results.relative_to(ROOT)}", file=sys.stderr)
    print(f"Overrides file -> {out_overrides.relative_to(ROOT)}  (edit, then re-run)", file=sys.stderr)
    api.close()


if __name__ == "__main__":
    main()

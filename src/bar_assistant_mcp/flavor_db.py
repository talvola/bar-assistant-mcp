"""SQLite storage for flavor profiles and recipe slot constraints.

Schema is conservative: composite primary keys keyed on BA ingredient_id /
cocktail_id + sort, so re-runs of the seeder and re-saves from MCP tools
upsert cleanly. The database file path is set by `BAR_ASSISTANT_FLAVOR_DB`
or defaults to `data/flavor.sqlite` next to the project root.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from .flavor import Band, Bottle, Constraint, Point, RecipeSlot


DEFAULT_AXES = {
    "gin": ["juniper", "citrus", "floral", "heat", "spice", "herbal", "fruited"],
    "aquavit": ["juniper", "citrus", "floral", "heat", "spice", "herbal"],
    # Bourbon and rye share axes; rye expresses higher on `spice` typically.
    "bourbon": ["spice", "sweet", "oak", "vanilla", "fruit", "body"],
    "rye": ["spice", "sweet", "oak", "vanilla", "fruit", "body"],
    # Scotch swaps `spice` for `smoke` — peat is the defining axis.
    "scotch": ["smoke", "sweet", "oak", "vanilla", "fruit", "body"],
}


def db_path() -> Path:
    if env := os.environ.get("BAR_ASSISTANT_FLAVOR_DB"):
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "flavor.sqlite"


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS category_axes (
            category   TEXT PRIMARY KEY,
            axes_json  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS flavor_profile (
            ingredient_id  INTEGER NOT NULL,
            axis           TEXT    NOT NULL,
            value          INTEGER NOT NULL,
            source         TEXT,
            confidence     TEXT,
            notes          TEXT,
            scored_at      TEXT,
            PRIMARY KEY (ingredient_id, axis)
        );

        CREATE TABLE IF NOT EXISTS ingredient_meta (
            ingredient_id  INTEGER PRIMARY KEY,
            name           TEXT,
            category       TEXT,
            proof          REAL,
            updated_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS slot_meta (
            cocktail_id              INTEGER NOT NULL,
            sort                     INTEGER NOT NULL,
            category                 TEXT    NOT NULL,
            tolerance                TEXT    NOT NULL DEFAULT 'style',
            exact_ingredient_id      INTEGER,
            also_accept_json         TEXT,
            proof_min                REAL,
            proof_max                REAL,
            PRIMARY KEY (cocktail_id, sort)
        );

        CREATE TABLE IF NOT EXISTS slot_constraint (
            cocktail_id  INTEGER NOT NULL,
            sort         INTEGER NOT NULL,
            axis         TEXT    NOT NULL,
            kind         TEXT    NOT NULL,    -- 'point' | 'band'
            point_value  INTEGER,
            band_lo      INTEGER,
            band_hi      INTEGER,
            weight       REAL    NOT NULL DEFAULT 1.0,
            out_weight   REAL    NOT NULL DEFAULT 1.0,
            hard         INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (cocktail_id, sort, axis)
        );
        """
    )
    # Seed any default-category axes that aren't already present. Lets new
    # categories added to DEFAULT_AXES propagate to existing DBs on next connect.
    existing = {r[0] for r in conn.execute("SELECT category FROM category_axes")}
    for cat, axes in DEFAULT_AXES.items():
        if cat not in existing:
            conn.execute(
                "INSERT INTO category_axes(category, axes_json) VALUES (?, ?)",
                (cat, json.dumps(axes)),
            )
    conn.commit()


@contextmanager
def connect(path: Optional[Path] = None):
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        _init_schema(conn)
        yield conn
    finally:
        conn.close()


# ---- axis registry ---------------------------------------------------------


def get_axes(conn: sqlite3.Connection, category: str) -> list[str]:
    row = conn.execute("SELECT axes_json FROM category_axes WHERE category=?", (category,)).fetchone()
    return json.loads(row["axes_json"]) if row else []


def set_axes(conn: sqlite3.Connection, category: str, axes: list[str]) -> None:
    conn.execute(
        "INSERT INTO category_axes(category, axes_json) VALUES (?, ?) "
        "ON CONFLICT(category) DO UPDATE SET axes_json=excluded.axes_json",
        (category, json.dumps(axes)),
    )
    conn.commit()


# ---- ingredient meta + profiles -------------------------------------------


def upsert_ingredient_meta(
    conn: sqlite3.Connection,
    ingredient_id: int,
    name: Optional[str] = None,
    category: Optional[str] = None,
    proof: Optional[float] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ingredient_meta(ingredient_id, name, category, proof, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ingredient_id) DO UPDATE SET
            name       = COALESCE(excluded.name, ingredient_meta.name),
            category   = COALESCE(excluded.category, ingredient_meta.category),
            proof      = COALESCE(excluded.proof, ingredient_meta.proof),
            updated_at = excluded.updated_at
        """,
        (ingredient_id, name, category, proof, date.today().isoformat()),
    )
    conn.commit()


def set_profile(
    conn: sqlite3.Connection,
    ingredient_id: int,
    profile: dict[str, int],
    source: str = "manual",
    confidence: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Upsert each axis in profile. Other axes for this ingredient are left as-is."""
    today = date.today().isoformat()
    for axis, value in profile.items():
        conn.execute(
            """
            INSERT INTO flavor_profile(ingredient_id, axis, value, source, confidence, notes, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ingredient_id, axis) DO UPDATE SET
                value=excluded.value,
                source=excluded.source,
                confidence=excluded.confidence,
                notes=excluded.notes,
                scored_at=excluded.scored_at
            """,
            (ingredient_id, axis, int(value), source, confidence, notes, today),
        )
    conn.commit()


def get_profile(conn: sqlite3.Connection, ingredient_id: int) -> dict:
    rows = conn.execute(
        "SELECT axis, value, source, confidence, notes, scored_at "
        "FROM flavor_profile WHERE ingredient_id=?",
        (ingredient_id,),
    ).fetchall()
    if not rows:
        return {}
    profile = {r["axis"]: r["value"] for r in rows}
    # Prefer the most-recent source/confidence/notes (they should usually agree across axes)
    latest = max(rows, key=lambda r: r["scored_at"] or "")
    return {
        "ingredient_id": ingredient_id,
        "profile": profile,
        "source": latest["source"],
        "confidence": latest["confidence"],
        "notes": latest["notes"],
        "scored_at": latest["scored_at"],
    }


def load_bottles(conn: sqlite3.Connection, category: Optional[str] = None) -> list[Bottle]:
    """All bottles with at least one profile entry, joined with ingredient_meta."""
    q = """
        SELECT im.ingredient_id, im.name, im.category, im.proof
        FROM ingredient_meta im
        WHERE EXISTS (SELECT 1 FROM flavor_profile fp WHERE fp.ingredient_id = im.ingredient_id)
    """
    params: tuple = ()
    if category:
        q += " AND im.category=?"
        params = (category,)
    rows = conn.execute(q, params).fetchall()

    bottles: list[Bottle] = []
    for r in rows:
        prof_rows = conn.execute(
            "SELECT axis, value, source, confidence, notes FROM flavor_profile WHERE ingredient_id=?",
            (r["ingredient_id"],),
        ).fetchall()
        profile = {p["axis"]: p["value"] for p in prof_rows}
        latest = max(prof_rows, key=lambda p: p["axis"])  # any row will do for provenance
        bottles.append(
            Bottle(
                id=r["ingredient_id"],
                name=r["name"] or f"#{r['ingredient_id']}",
                category=r["category"] or "",
                profile=profile,
                proof=r["proof"],
                source=latest["source"] or "",
                confidence=latest["confidence"] or "",
                notes=latest["notes"] or "",
            )
        )
    return bottles


# ---- slot meta + constraints ----------------------------------------------


def upsert_slot_meta(
    conn: sqlite3.Connection,
    cocktail_id: int,
    sort: int,
    category: str,
    tolerance: str = "style",
    exact_ingredient_id: Optional[int] = None,
    also_accept_categories: Optional[list[str]] = None,
    proof_min: Optional[float] = None,
    proof_max: Optional[float] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO slot_meta(cocktail_id, sort, category, tolerance, exact_ingredient_id,
                              also_accept_json, proof_min, proof_max)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cocktail_id, sort) DO UPDATE SET
            category=excluded.category,
            tolerance=excluded.tolerance,
            exact_ingredient_id=excluded.exact_ingredient_id,
            also_accept_json=excluded.also_accept_json,
            proof_min=excluded.proof_min,
            proof_max=excluded.proof_max
        """,
        (
            cocktail_id, sort, category, tolerance, exact_ingredient_id,
            json.dumps(also_accept_categories) if also_accept_categories else None,
            proof_min, proof_max,
        ),
    )
    conn.commit()


def set_constraint(
    conn: sqlite3.Connection,
    cocktail_id: int,
    sort: int,
    axis: str,
    kind: str,
    *,
    point_value: Optional[int] = None,
    band_lo: Optional[int] = None,
    band_hi: Optional[int] = None,
    weight: float = 1.0,
    out_weight: float = 1.0,
    hard: bool = False,
) -> None:
    if kind not in ("point", "band"):
        raise ValueError(f"kind must be 'point' or 'band', got {kind!r}")
    if kind == "point" and point_value is None:
        raise ValueError("kind='point' requires point_value")
    if kind == "band" and (band_lo is None or band_hi is None):
        raise ValueError("kind='band' requires band_lo and band_hi")
    conn.execute(
        """
        INSERT INTO slot_constraint(cocktail_id, sort, axis, kind, point_value,
                                    band_lo, band_hi, weight, out_weight, hard)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cocktail_id, sort, axis) DO UPDATE SET
            kind=excluded.kind,
            point_value=excluded.point_value,
            band_lo=excluded.band_lo,
            band_hi=excluded.band_hi,
            weight=excluded.weight,
            out_weight=excluded.out_weight,
            hard=excluded.hard
        """,
        (cocktail_id, sort, axis, kind, point_value, band_lo, band_hi,
         weight, out_weight, 1 if hard else 0),
    )
    conn.commit()


def delete_constraint(conn: sqlite3.Connection, cocktail_id: int, sort: int, axis: str) -> int:
    cur = conn.execute(
        "DELETE FROM slot_constraint WHERE cocktail_id=? AND sort=? AND axis=?",
        (cocktail_id, sort, axis),
    )
    conn.commit()
    return cur.rowcount


def load_slot(conn: sqlite3.Connection, cocktail_id: int, sort: int) -> Optional[RecipeSlot]:
    meta = conn.execute(
        "SELECT * FROM slot_meta WHERE cocktail_id=? AND sort=?",
        (cocktail_id, sort),
    ).fetchone()
    if not meta:
        return None

    constraints = _load_constraints_for(conn, cocktail_id, sort)
    return RecipeSlot(
        cocktail_id=cocktail_id,
        sort=sort,
        category=meta["category"],
        tolerance=meta["tolerance"],
        exact_ingredient_id=meta["exact_ingredient_id"],
        constraints=constraints,
        also_accept_categories=json.loads(meta["also_accept_json"]) if meta["also_accept_json"] else [],
        proof_min=meta["proof_min"],
        proof_max=meta["proof_max"],
    )


def load_slots_for_cocktail(conn: sqlite3.Connection, cocktail_id: int) -> list[RecipeSlot]:
    rows = conn.execute(
        "SELECT sort FROM slot_meta WHERE cocktail_id=? ORDER BY sort", (cocktail_id,),
    ).fetchall()
    return [s for r in rows if (s := load_slot(conn, cocktail_id, r["sort"]))]


def load_all_slots(conn: sqlite3.Connection) -> list[RecipeSlot]:
    rows = conn.execute("SELECT cocktail_id, sort FROM slot_meta ORDER BY cocktail_id, sort").fetchall()
    return [s for r in rows if (s := load_slot(conn, r["cocktail_id"], r["sort"]))]


def _load_constraints_for(conn: sqlite3.Connection, cocktail_id: int, sort: int) -> dict[str, Constraint]:
    rows = conn.execute(
        "SELECT axis, kind, point_value, band_lo, band_hi, weight, out_weight, hard "
        "FROM slot_constraint WHERE cocktail_id=? AND sort=?",
        (cocktail_id, sort),
    ).fetchall()
    out: dict[str, Constraint] = {}
    for r in rows:
        if r["kind"] == "point":
            out[r["axis"]] = Point(value=r["point_value"], weight=r["weight"])
        else:
            out[r["axis"]] = Band(
                lo=r["band_lo"], hi=r["band_hi"],
                out_weight=r["out_weight"], hard=bool(r["hard"]),
            )
    return out

"""Flavor-profile matching engine.

A small, low-dimensional matcher: per-category integer flavor axes (0–3 for gin
on the TGII scale), recipe slots with Point or Band constraints per axis,
Manhattan-style distance summed over masked axes, with hard-cap disqualification
for "this is definitely wrong" cases.

Design and rationale: see `bar_assistant_roadmap.md` in memory.

Pure-Python, no I/O. Storage lives in flavor_db.py; MCP wiring lives in
server.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


# --- Constraint primitives --------------------------------------------------


@dataclass
class Point:
    """Exact-ish target on an axis. Penalty grows with distance from `value`.
    Use when the spirit is exposed and its level on this axis genuinely matters
    (e.g. Martini gin — juniper level shows through).
    """

    value: int
    weight: float = 1.0


@dataclass
class Band:
    """Acceptable range [lo, hi] on an axis. Zero penalty inside; graded
    penalty outside, scaled by `out_weight`. Use for forgiving slots — most
    recipes are wide on most axes and only hard-capped on a few.

    `hard=True`: falling outside the band disqualifies the bottle from the
    in-pattern set (still surfaceable via include_strays).
    """

    lo: int
    hi: int
    out_weight: float = 1.0
    hard: bool = False


Constraint = Union[Point, Band]


# --- Domain objects ---------------------------------------------------------


@dataclass
class Bottle:
    id: int                     # BA ingredient_id
    name: str
    category: str               # e.g. "gin"
    profile: dict[str, int]     # axis -> value (0..3 for gin)
    proof: Optional[float] = None
    in_stock: bool = True
    source: str = ""            # provenance: tgii | llm_from_description | manual | manual_override
    confidence: str = ""        # high | medium | low | ""
    notes: str = ""


@dataclass
class RecipeSlot:
    cocktail_id: int
    sort: int                                       # 1-based position in BA recipe ingredient list
    category: str                                   # e.g. "gin"
    tolerance: str = "style"                        # exact | style | any
    exact_ingredient_id: Optional[int] = None       # required when tolerance=exact
    constraints: dict[str, Constraint] = field(default_factory=dict)
    also_accept_categories: list[str] = field(default_factory=list)  # cross-category subs (e.g. rye slot accepts bourbon)
    proof_min: Optional[float] = None
    proof_max: Optional[float] = None
    cross_category_penalty: float = 1.0             # flat penalty added when matching outside primary category


@dataclass
class Assessment:
    penalty: float
    disqualified: bool
    flags: list[str]
    cross_category: bool = False

    @property
    def verdict(self) -> str:
        if self.disqualified:
            return "off-pattern (hard limit)"
        if self.penalty == 0:
            return "squarely in pattern"
        if self.penalty <= 2:
            return "slight stray"
        return "notable stray"


# --- Core scoring -----------------------------------------------------------


def assess(bottle: Bottle, slot: RecipeSlot) -> Assessment:
    """Score one bottle against one slot. Lower penalty is better.

    Point  -> weight * |have - value|, flagged when nonzero
    Band   -> 0 inside [lo, hi]; outside, out_weight * distance-to-edge.
              `hard` band → disqualified=True when outside.

    A cross-category match (only happens when slot.also_accept_categories is
    used) adds a flat `slot.cross_category_penalty` to surface in-category first.
    """
    penalty = 0.0
    disqualified = False
    flags: list[str] = []
    cross_category = bottle.category != slot.category

    if cross_category:
        penalty += slot.cross_category_penalty
        flags.append(f"cross-category: {bottle.category} subbing for {slot.category}")

    for axis, c in slot.constraints.items():
        have = bottle.profile.get(axis, 0)

        if isinstance(c, Point):
            d = abs(have - c.value)
            if d:
                penalty += c.weight * d
                flags.append(f"{axis} {have} vs target {c.value}")

        elif isinstance(c, Band):
            if have < c.lo:
                gap = c.lo - have
                penalty += c.out_weight * gap
                flags.append(f"{axis} {have} below comfort band {c.lo}-{c.hi}")
                if c.hard:
                    disqualified = True
            elif have > c.hi:
                gap = have - c.hi
                penalty += c.out_weight * gap
                tag = " — likely to fight the drink" if c.hard else ""
                flags.append(f"{axis} {have} above comfort band {c.lo}-{c.hi}{tag}")
                if c.hard:
                    disqualified = True

    return Assessment(
        penalty=penalty, disqualified=disqualified, flags=flags, cross_category=cross_category
    )


def _proof_ok(bottle: Bottle, slot: RecipeSlot) -> bool:
    if slot.proof_min is not None and (bottle.proof is None or bottle.proof < slot.proof_min):
        return False
    if slot.proof_max is not None and (bottle.proof is None or bottle.proof > slot.proof_max):
        return False
    return True


def _eligible_categories(slot: RecipeSlot) -> set[str]:
    return {slot.category, *slot.also_accept_categories}


# --- The three use cases ----------------------------------------------------


def alternatives_for_slot(
    bottles: list[Bottle],
    slot: RecipeSlot,
    top_n: int = 10,
    include_strays: bool = False,
) -> list[tuple[Bottle, Assessment]]:
    """Rank in-stock bottles by fit for a recipe slot.

    - tolerance=exact: returns only the named bottle if present + in stock.
    - tolerance=style: in-category (or `also_accept_categories`) bottles ranked
      by assess(). Strays (disqualified) hidden unless include_strays=True.
    - tolerance=any: any in-category in-stock bottle, distance 0.
    """
    if slot.tolerance == "exact":
        for b in bottles:
            if b.id == slot.exact_ingredient_id and b.in_stock:
                return [(b, Assessment(0.0, False, []))]
        return []

    categories = _eligible_categories(slot)
    pool = [b for b in bottles if b.category in categories and b.in_stock and _proof_ok(b, slot)]

    if slot.tolerance == "any" or not slot.constraints:
        return [(b, Assessment(0.0, False, [])) for b in sorted(pool, key=lambda x: x.name)[:top_n]]

    results: list[tuple[Bottle, Assessment]] = []
    for b in pool:
        a = assess(b, slot)
        if a.disqualified and not include_strays:
            continue
        results.append((b, a))

    results.sort(key=lambda t: (t[1].disqualified, t[1].penalty, t[0].name))
    return results[:top_n]


def uses_for_bottle(
    bottle: Bottle,
    slots: list[RecipeSlot],
    top_n: int = 10,
) -> list[tuple[RecipeSlot, Assessment]]:
    """Given a bottle, rank slots whose constraints it satisfies.

    Useful when Erik buys a new bottle and wants to know which recipes welcome
    it. Operates on the full pool of slots that have constraints declared.
    """
    scored: list[tuple[RecipeSlot, Assessment]] = []
    for s in slots:
        if bottle.category not in _eligible_categories(s):
            continue
        if not _proof_ok(bottle, s):
            continue
        a = assess(bottle, s)
        scored.append((s, a))
    scored.sort(key=lambda t: (t[1].disqualified, t[1].penalty, t[0].cocktail_id))
    return scored[:top_n]


def find_gaps(
    bottles: list[Bottle],
    wishlist_slots: list[RecipeSlot],
    threshold: float = 3.0,
) -> list[tuple[RecipeSlot, Optional[Bottle], float, str]]:
    """Slots in the wishlist where the best in-stock match is a stretch.

    Returns (slot, best_bottle_or_None, penalty, reason) sorted worst-first.
    """
    gaps: list[tuple[RecipeSlot, Optional[Bottle], float, str]] = []
    for s in wishlist_slots:
        best = alternatives_for_slot(bottles, s, top_n=1, include_strays=True)
        if not best:
            gaps.append((s, None, float("inf"), "nothing in stock in this category"))
            continue
        b, a = best[0]
        if a.disqualified or a.penalty >= threshold:
            why = "; ".join(a.flags) if a.flags else "weak match"
            gaps.append((s, b, a.penalty, why))
    gaps.sort(key=lambda g: -g[2])
    return gaps

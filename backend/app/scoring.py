"""Deterministic quote scoring. Pure functions, no I/O, no LLM."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MAX_RATING = 5.0


@dataclass(frozen=True)
class QuoteInput:
    quote_id: int
    vendor_id: int
    unit_price: Decimal
    lead_time_days: int
    vendor_rating: float  # 0-5


@dataclass(frozen=True)
class Weights:
    price: float
    lead_time: float
    rating: float


@dataclass(frozen=True)
class ScoredQuote:
    quote_id: int
    vendor_id: int
    score: float  # 0-1
    price_score: float
    lead_time_score: float
    rating_score: float
    rank: int


def _lower_is_better(value: float, low: float, high: float) -> float:
    """Min-max normalise so the lowest value scores 1 and the highest 0. A single distinct value scores 1."""
    if high == low:
        return 1.0
    return (high - value) / (high - low)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_quotes(quotes: list[QuoteInput], weights: Weights) -> list[ScoredQuote]:
    """Score and rank quotes. Ties break on lower price, then shorter lead time, then lower vendor id."""
    if not quotes:
        raise ValueError("Cannot score an empty list of quotes")
    prices = [float(q.unit_price) for q in quotes]
    leads = [float(q.lead_time_days) for q in quotes]
    lo_p, hi_p, lo_l, hi_l = min(prices), max(prices), min(leads), max(leads)

    rows = []
    for q in quotes:
        p = _clamp01(_lower_is_better(float(q.unit_price), lo_p, hi_p))
        l = _clamp01(_lower_is_better(float(q.lead_time_days), lo_l, hi_l))
        r = _clamp01(q.vendor_rating / MAX_RATING)
        total = _clamp01(weights.price * p + weights.lead_time * l + weights.rating * r)
        rows.append((q, round(total, 4), round(p, 4), round(l, 4), round(r, 4)))

    rows.sort(key=lambda t: (-t[1], t[0].unit_price, t[0].lead_time_days, t[0].vendor_id))
    return [
        ScoredQuote(q.quote_id, q.vendor_id, total, p, l, r, rank)
        for rank, (q, total, p, l, r) in enumerate(rows, start=1)
    ]

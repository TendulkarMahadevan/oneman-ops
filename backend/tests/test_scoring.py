from decimal import Decimal

import pytest

from app.scoring import QuoteInput, Weights, score_quotes

W = Weights(0.5, 0.3, 0.2)


def q(i, price, lead, rating):
    return QuoteInput(i, i, Decimal(str(price)), lead, rating)


def test_scores_are_normalised_and_ranked():
    out = score_quotes([q(1, 100, 10, 5), q(2, 200, 20, 0)], W)
    assert [s.quote_id for s in out] == [1, 2]
    assert out[0].score == 1.0 and out[1].score == 0.0
    assert all(0 <= s.score <= 1 for s in out)


def test_weights_applied():
    # q1 cheapest only; q2 fastest + best rating
    out = score_quotes([q(1, 100, 30, 0), q(2, 200, 1, 5)], W)
    by = {s.quote_id: s for s in out}
    assert by[1].score == 0.5 and by[2].score == 0.5
    # tie breaks on lower price
    assert out[0].quote_id == 1


def test_single_distinct_value_scores_one():
    out = score_quotes([q(1, 100, 10, 5), q(2, 100, 10, 5)], W)
    assert all(s.score == 1.0 for s in out)


def test_rating_scaled_by_five():
    out = score_quotes([q(1, 100, 10, 2.5), q(2, 100, 10, 5)], W)
    by = {s.quote_id: s for s in out}
    assert by[1].rating_score == 0.5 and by[2].rating_score == 1.0


def test_rating_above_scale_is_clamped():
    out = score_quotes([q(1, 100, 10, 9)], W)
    assert out[0].rating_score == 1.0


def test_deterministic_tie_break_by_vendor_id():
    out = score_quotes([q(2, 100, 10, 4), q(1, 100, 10, 4)], W)
    assert [s.quote_id for s in out] == [1, 2]


def test_empty_rejected():
    with pytest.raises(ValueError):
        score_quotes([], W)

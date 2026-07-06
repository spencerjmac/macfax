"""
Tests for the NCAA projection-time transform (N-A) — and the guarantee that
it is SEPARATE from live v1.7 BPR.
"""

import math

from ncaa.analytics.player_value.bpr.projection_transform import (
    PROJECTION_K,
    ncaa_projection_player_value,
    project_ratings_map,
)


def test_blend_is_reliability_weighted():
    # at poss == K, exactly half-and-half
    v = ncaa_projection_player_value(bpr=4.0, box_bpr=2.0, off_poss=PROJECTION_K)
    assert math.isclose(v, 3.0, rel_tol=1e-9)
    # zero possessions → pure box
    assert ncaa_projection_player_value(4.0, 2.0, 0) == 2.0
    # huge sample → approaches live BPR
    v = ncaa_projection_player_value(4.0, 2.0, 1e9)
    assert abs(v - 4.0) < 1e-4


def test_missing_side_fallbacks():
    assert ncaa_projection_player_value(None, 2.0, 500) == 2.0
    assert ncaa_projection_player_value(4.0, None, 500) == 4.0
    assert ncaa_projection_player_value(None, None, 500) is None


def test_projection_value_differs_from_live_bpr():
    # The whole point: a typical starter's projection input is NOT their
    # live BPR. Live rankings must never route through this function.
    live_bpr, box, poss = 6.0, 2.0, 800   # rel ≈ 0.348
    v = ncaa_projection_player_value(live_bpr, box, poss)
    assert v is not None and abs(v - live_bpr) > 1.5


def test_live_pipeline_does_not_import_transform():
    # Static guard: the live rating pipeline must not consume the projection
    # transform — separation of evaluation vs projection is a product rule.
    import inspect
    from ncaa.analytics.player_value.bpr import pipeline
    src = inspect.getsource(pipeline)
    assert "projection_transform" not in src
    assert "ncaa_projection_player_value" not in src


def test_bulk_helper():
    rows = [
        {"player_id": 1, "bpr": 4.0, "box_bpr": 2.0, "off_poss": PROJECTION_K},
        {"player_id": 2, "bpr": None, "box_bpr": 1.0, "off_poss": 10},
        {"player_id": 3, "bpr": None, "box_bpr": None, "off_poss": 10},
    ]
    m = project_ratings_map(rows)
    assert math.isclose(m[1], 3.0) and m[2] == 1.0 and 3 not in m

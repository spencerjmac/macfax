"""
Tests for the BPR / Projection Value product split (docs/bpr_audit/09).

Core guarantee: NBA team outlooks are driven by projection_value
(pv_effective), NOT raw BPR — and the two paths stay separate.
"""

import math

from nba.management.commands.compute_nba_team_outlooks import (
    Command as OutlooksCommand,
    PV_SLOPE,
)


def _slot(pv: float, bpr: float, share: float = 1.0) -> dict:
    return {
        "player_name": "t",
        "minutes_share": share,
        "pv_effective": pv,
        "projected_obpr": bpr / 2,
        "projected_dbpr": bpr / 2,
        "projected_bpr": bpr,
        "acquisition_type": "returner",
        "age": 25,
    }


def _project(slots, league_pv_mean=0.0):
    cmd = OutlooksCommand()
    return cmd._project_team(
        slots, nba_avg_adj_o=115.0, nba_avg_adj_d=115.0,
        league_base_off=0.0, league_base_def=0.0,
        league_pv_mean=league_pv_mean,
    )


def test_outlook_adj_em_follows_projection_value_not_bpr():
    # Same BPR, different PV → different adj_em (PV drives the forecast)
    high_pv = _project([_slot(pv=2.0, bpr=5.0, share=s) for s in (1.0, 1.0, 1.0, 1.0, 1.0)])
    low_pv = _project([_slot(pv=-1.0, bpr=5.0, share=s) for s in (1.0, 1.0, 1.0, 1.0, 1.0)])
    assert high_pv["adj_em"] > low_pv["adj_em"] + 5

    # Different BPR, same PV → identical adj_em (BPR does NOT drive it)
    a = _project([_slot(pv=1.0, bpr=10.0) for _ in range(5)])
    b = _project([_slot(pv=1.0, bpr=-3.0) for _ in range(5)])
    assert math.isclose(a["adj_em"], b["adj_em"], abs_tol=1e-9)


def test_adj_em_is_centered_pv_slope():
    slots = [_slot(pv=1.5, bpr=0.0) for _ in range(5)]
    m = _project(slots, league_pv_mean=0.5)
    assert math.isclose(m["adj_em"], PV_SLOPE * (1.5 - 0.5), rel_tol=1e-6)


def test_legacy_bpr_path_still_reported_separately():
    slots = [_slot(pv=0.0, bpr=6.0) for _ in range(5)]
    m = _project(slots)
    # PV=league mean → PV adj_em 0; legacy path sees the BPR signal
    assert math.isclose(m["adj_em"], 0.0, abs_tol=1e-9)
    assert m["legacy_adj_em"] > 1.0


def test_off_def_split_sums_to_pv_total():
    slots = [_slot(pv=1.0, bpr=4.0) for _ in range(5)]
    m = _project(slots)
    assert math.isclose((m["adj_o"] - 115.0) + (115.0 - m["adj_d"]),
                        m["adj_em"], rel_tol=1e-6)

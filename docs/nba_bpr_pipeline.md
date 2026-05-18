# NBA BPR Pipeline — Production State

## What BPR Measures

BPR (Bayesian Performance Rating) measures a player's impact on their team's
offensive and defensive efficiency, in points per 100 possessions above league
average. It is a **context-adjusted** metric — it reflects how much a player
impacts winning lineups on their current team, not a pure skill estimate
independent of context.

## Architecture

Four-stage pipeline:

1. **Data sync** — `nba_sync_play_by_play`, `nba_sync_player_advanced`
2. **Baseline RAPM** — `nba_compute_baseline_rapm` (single season, no `--rapm-years`)
3. **Box BPR / prior** — `nba_compute_box_bpr` (career-stabilized box model)
4. **Final BPR** — `nba_compute_final_bpr` (prior-informed RAPM)

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Box model alpha | Fixed off=5, def=10 | CV selected 5–200 causing year-to-year prior scale instability |
| Lambda tiers | B_moderate (200/400/700/1200) | Asymmetric tuning (loosen stars, tighten role players) made results worse |
| Career window | 2016–present | Covers full career for all active players (up to 10 seasons) |
| Rate stat stabilization | Full career weight | Rate stats highly stable across role changes |
| Counting stat stabilization | 50% career weight | Role changes are real; full weight over-anchors to historical role |
| Baseline RAPM window | Single season | Pooled RAPM dilutes current-season star signal via cross-year shrinkage |
| Final RAPM window | 3-year pooled | More total stints → better lineup estimates for all players |
| Temporal decay | Off (RAPM_TEMPORAL_DECAY=1.0) | Tested 0.5× decay; improved nothing, available as `--cross-season-decay` flag |

## Known Properties (By Design)

- **Context-adjusted**: stars on underperforming teams rated lower than pure skill
- **Differs from BPM intentionally** — BPM ignores lineup context; BPR captures it
- **Jokić example**: on a disappointing Denver team, BPR correctly reflects lineup
  data rather than peak-season ability — this is a feature, not a bug
- **SGA, Wembanyama** correctly in top 5; leaderboard passes eye test

## Known Limitations

- Role players with lucky small-sample lineup stints can rank too high
- Single-season RAPM noise not fully eliminated — only partially mitigated
  by career-stabilized box prior
- YoY stability lower than box-only metrics (r=0.272 vs BPM r=0.755)
  — expected for a lineup-based metric; not a product-facing issue since
  the matchup predictor uses team-level adj_net, not individual BPR ranks

## Performance Benchmarks (2025-26)

| Metric | BPR | BPM | LEBRON |
|--------|-----|-----|--------|
| Retrodiction RMSE | 5.6 | 3.6 | 5.2 |
| Predictive r (team wins) | 0.503 | 0.573 | n/a |
| BPM correlation (individual) | 0.615 | 1.000 | n/a |
| Leaderboard (notable) | SGA #2, Wemb #4, Jokić #18 | — | — |

## Run Order (Fresh Season)

```bash
python manage.py nba_sync_play_by_play --season YYYY
python manage.py nba_sync_player_advanced --season YYYY
python manage.py nba_compute_baseline_rapm --season YYYY
python manage.py nba_compute_box_bpr --season YYYY
python manage.py nba_compute_final_bpr --season YYYY
```

## What Not To Change Without Testing

- **Alpha values (5/10)** — any change risks prior scale instability across seasons
- **Lambda tiers** — asymmetric tuning proven counterproductive; B_moderate is validated
- **Career window floor (2016)** — earlier data is pre-modern NBA era
- **Role discount factor (0.5)** — tuned against predictive test; changing requires re-test
- **Baseline RAPM as single-season** — pooled baseline causes 2026-year coefficients
  to shrink toward zero when 2026 observation count is low

## 2026 PBP Data Fix (May 2026)

Root cause: repeated `--force` re-syncs accumulated duplicate `NBAPlayerGameStint`
rows. `bulk_create(update_conflicts=True, unique_fields=["player","game","stint_index"])`
leaves orphan rows when `stint_index` shifts between runs. Result: 582K raw stints
but only 4,534 valid 5v5 lineup observations (0.78% conversion) vs expected ~25K.

Fix: deleted all 2026 stints, ran a single clean sync. Post-fix: 27,575 valid
observations, Jokić visible at #18, SGA at #2.

**Prevention**: never run `nba_sync_play_by_play --force` on an already-synced season
without first deleting existing stints:
```bash
# Safe re-sync for season YYYY:
python -c "
from nba.models import NBAPlayerGameStint, NBAGame
NBAPlayerGameStint.objects.filter(game__season__year=YYYY, game__counts_toward_regular_season=True).delete()
NBAGame.objects.filter(season__year=YYYY, counts_toward_regular_season=True).update(pbp_synced=False, pbp_quality_flag=False)
"
python manage.py nba_sync_play_by_play --season YYYY
```

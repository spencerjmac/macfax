# BPR Audit — Checkpoint Summary (2026-07-05)

Commit-ready summary of the full audit → v2 → wiring arc. Nothing committed yet; the entire working tree below is this work (world_cup + a few unrelated web files predate it).

## Suggested commit structure

```
feat(bpr): v2 audit, data repairs, truthful targets, projection split

1. NCAA data layer repaired: 259K phantom OT stints deleted, parser fixed
   at source (numeric sequence sort, deferred period reopen, sub-in guard),
   OT/neutral flags backfilled, 629 overlap games re-synced, dupes purged.
2. NCAA BPR v1.7: truthful_targets production default (pre-2025 placeholder
   stints excluded from RAPM pool/targets — ESPN has no substitution data
   before ~Feb 2025, verified); 2025+2026 recomputed, validation green.
3. Leak-free backtest framework: through_date rebuilds, backtest_bpr_suite
   (cross-season/rolling/player modes, combo arm, experiment hooks), audit
   commands, anti-leak tests. Legacy walkforward deprecated (leaked).
4. NBA: LEBRON_PRIOR_W 0.5→0.75 (forward-ablation validated); 2025 chain +
   2026 final refreshed; experiment harnesses (final-stage + box-chain).
5. Projection split shipped: NBAPlayerSeasonStats.projection_value
   (0.25·z(BPR)+0.75·z(BPM), migration 0022) drives team outlooks
   (PV_SLOPE=3.58 centered, PV_WINS_INTERCEPT=41); NCAA projection
   transform (k=1500) as library only. BPR stays player evaluation.
6. Frontend: BPRConfidenceBadge (source/confidence/Box-era provenance),
   last-updated stamp, split copy; glossary rewritten.
7. Docs: docs/bpr_audit/01-11 + recruiting ingest guide.
```

## File inventory (this work)

**Backend modified:** `ncaa/.../bpr/{constants,datasets,pipeline,preseason_model,rapm}.py`, `ncaa/management/commands/{compute_ncaa_bpr,sync_ncaa_pbp,backtest_bpr_walkforward}.py`, `nba/models.py`, `nba/management/commands/{compute_nba_team_outlooks,nba_compute_final_bpr,nba_forward_backtest}.py`, `recompute_all.sh` (NBA chain + PV step added).

**Backend new:** `ncaa/.../bpr/{through_date,backtest_lib,projection_transform}.py`, `ncaa/management/commands/{audit_bpr_data,backtest_bpr_suite,validate_bpr_through_date,fix_ncaa_stint_data,backfill_neutral_flags,dump_bpr_ratings,check_recruiting_data}.py`, `ncaa/tests/{test_bpr_through_date,test_projection_transform}.py`, `nba/analytics/projection_value.py`, `nba/management/commands/{nba_audit_bpr_data,nba_compute_projection_values,nba_experiment_final_bpr,nba_experiment_box_chain}.py`, `nba/migrations/0022_*`, `nba/tests/test_projection_value.py`, `analysis/nba/nba_blend_test.py`.

**Web:** `components/BPRConfidenceBadge.tsx` (new), `components/{NCAAPlayerRankingsTable,PlayerScoutingCard,outlook/PlayerOutlookTable}.tsx`, `lib/glossaryContent.ts`.

**Docs:** `docs/bpr_audit/01–11` + `recruiting_ingest_guide.md` + this file.

**Data state (DB):** NCAA 2025/2026 ratings at v1.7 (7.5K+3.5K rows); NBA 2025 chain + 2026 final at prior_w=0.75; projection_value populated 2022–2026; 2026-27 outlooks regenerated (league mean 40.97W).

## Verification state

- 11/11 new tests pass (`test_projection_transform`, `test_projection_value`, `test_bpr_through_date`).
- `compute_ncaa_bpr --season 2026 --validate-only`: all_passed + strict ✓.
- `projection_value` not serialized to any player endpoint; not referenced anywhere in `web/src`.
- Live NCAA pipeline provably does not import `projection_transform` (static test).
- **Pre-existing failures (NOT this work):** `nba/tests/test_matchup.py` — 2 series-engine tests (`test_home_court_format_b`, +1) fail with all changes stashed. Owned by the matchup engine, untouched here.

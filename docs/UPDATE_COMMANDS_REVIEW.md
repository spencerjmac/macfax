# Update Commands Audit

## Summary
The macfax update pipeline is **well-designed with proper orchestration**, but there are some considerations about what's included in each command.

---

## NCAA Pipeline

### `update_ncaa_all --season 2026`
**Orchestrator command** that runs all NCAA + NBA data in dependency order:

1. ✅ **NCAA Team Pipeline** (`update_ncaa_teams`)
   - 14 steps: ingest → compute all team metrics, ratings, analytics
   
2. ✅ **NCAA Player Pipeline** (`update_ncaa_players`) [optional with --skip-player]
   - 11 steps: ingest player gamelogs/PBP → compute all player stats, BPR, projections
   
3. ✅ **NBA Team Pipeline** (`update_nba_teams`) [optional with --skip-nba]
   - 2 steps: ingest → compute ratings
   
4. ✅ **NBA Player Pipeline** (`update_nba_players`) [optional with --skip-nba]
   - 3 steps: ingest → compute stats → sync advanced stats

**COMPREHENSIVE:** ✅ Yes — when run without flags, covers everything

---

### `update_ncaa_teams --season 2026`
**14 total steps:**

| # | Step | Purpose |
|---|------|---------|
| 1 | `ingest_gamelogs` | Fetch all game logs from NCAA API |
| 2 | `compute_team_metrics` | Basic team stats (PPG, FG%, etc) |
| 3 | `compute_national_averages` | League-wide baseline stats |
| 4 | `compute_adjusted_ratings` | Iterative rating solver |
| 5 | `compute_hca` | Home court advantage |
| 6 | `compute_sigma` | Prediction error distribution |
| 7 | `compute_adjusted_four_factors` | Offensive/defensive four factors |
| 8 | `compute_four_factor_index` | FFI composite score |
| 9 | `train_four_factor_regression` | FFI regression model |
| 10 | `fetch_net_rankings` | Pull NET rankings from external source |
| 11 | `compute_sor` | Strength of Record (Monte Carlo) |
| 12 | `compute_game_value` | RPI-style metric |
| 13 | `compute_sos` | Strength of Schedule |
| 14 | `compute_wab` | Wins Above Bubble |

**COMPREHENSIVE:** ✅ Yes — all team-level analytics computed

---

### `update_ncaa_players --season 2026`
**11 total steps:**

| # | Step | Purpose |
|---|------|---------|
| 1 | `sync_ncaa_player_gamelogs` | Fetch player box scores from NCAA API |
| 2 | `compute_ncaa_player_season_stats` | Aggregate player season stats |
| 3 | `sync_ncaa_pbp` | Fetch play-by-play data |
| 4 | `compute_ncaa_player_impact` | RAPM-like player impact |
| 5 | `compute_ncaa_bpr` | Box Plus-Minus (uses Evan Miya calibration) |
| 6 | `compute_player_ffi` | Player Four Factor Index |
| 7 | `compute_player_projections` | Phase 1: individual player projections |
| 8 | `compute_player_minutes` | Phase 2: playing time projections |
| 9 | `compute_roster_fit` | Phases 3+4: team chemistry/fit metrics |
| 10 | `compute_team_projections` | Phase 5: aggregate team win projections |
| 11 | `build_placeholder_archetypes` | Player archetype classification |

**COMPREHENSIVE:** ✅ Yes — all player-level analytics computed

**⚠️ DEPENDENCY:** Requires `update_ncaa_teams` to complete first (needs `compute_national_averages` and `compute_adjusted_ratings`)

---

## NBA Pipeline

### `update_nba_all --season 2026`
**8 core steps + optional PBP:**

**CORE PIPELINE (always runs):**

| # | Step | Purpose |
|---|------|---------|
| 1 | `nba_sync_games` | Fetch season/playin/playoff game logs from NBA.com |
| 2 | `nba_sync_team_logs` | Fetch per-player box scores |
| 3 | `nba_compute_ratings` (Regular Season) | Opponent-adjusted efficiency ratings |
| 4 | `nba_compute_player_stats` (Regular Season) | Player season aggregates |
| 5 | `nba_sync_player_advanced` | Advanced stats from NBA.com (RAPTOR, etc) |
| 6 | `nba_compute_box_bpr` | Box Plus-Minus ratings |
| 7 | `nba_compute_ratings` (Playoffs) | Playoff ratings recompute |
| 8 | `nba_compute_player_stats` (Playoffs) | Playoff player stats |

**OPTIONAL PBP PIPELINE (--with-pbp flag):**
- `nba_sync_play_by_play` — Detailed PBP ingestion
- `nba_compute_baseline_rapm` — Regression-based player impact
- `nba_compute_box_bpr` (re-run) — Re-train with RAPM targets

**COMPREHENSIVE:** ✅ Yes for standard use — all essential data computed
⚠️ **Note:** PBP is optional and takes hours on first run; typically not needed for daily updates

---

### `update_nba_teams --season 2026`
**2 total steps:**

| # | Step | Purpose |
|---|------|---------|
| 1 | `nba_sync_games` | Fetch all game logs (Regular Season/PlayIn/Playoffs) |
| 2 | `nba_compute_ratings` | Opponent-adjusted efficiency ratings |

**COMPREHENSIVE:** ⚠️ **INCOMPLETE** — Missing player-level data
- Does NOT sync per-player box scores
- Does NOT compute player stats
- Does NOT sync advanced stats
- **Use Case:** Team ratings only (rarely needed separately)

---

### `update_nba_players --season 2026`
**3 total steps:**

| # | Step | Purpose |
|---|------|---------|
| 1 | `nba_sync_team_logs` | Fetch per-player box scores |
| 2 | `nba_compute_player_stats` | Player season aggregates |
| 3 | `nba_sync_player_advanced` | Advanced stats from NBA.com |

**COMPREHENSIVE:** ⚠️ **INCOMPLETE** — Missing BPR computation
- Does NOT compute Box Plus-Minus (BPR)
- **Use Case:** When you only need raw stats, not advanced analytics

---

## Recommendations & Issues

### ✅ NCAA Pipeline — Good Design
- `update_ncaa_all` is truly comprehensive
- `update_ncaa_teams` and `update_ncaa_players` are independent but properly ordered
- All analytics are computed in dependency order

### ⚠️ NBA Pipeline — Needs Attention

**Issue 1:** `update_nba_teams` is too minimal
- **Current:** Only syncs games + computes team ratings
- **Missing:** Player-level data (box scores, stats, advanced metrics, BPR)
- **Result:** Running `update_nba_teams` alone leaves player data stale

**Issue 2:** `update_nba_players` is incomplete
- **Current:** Box scores + stats + advanced stats
- **Missing:** `nba_compute_box_bpr` step
- **Result:** BPR ratings are stale if you only run `update_nba_players`

**Issue 3:** Inconsistent naming
- `update_nba_teams` and `update_nba_players` don't actually cover everything they should
- Unlike NCAA, the NBA "teams" command includes player ingest
- The separation is artificial and confusing

---

## Usage Verification

### Current Safe Usage Patterns ✅

```bash
# NCAA — safe, comprehensive
fab manage --cmd "update_ncaa_all --season 2026"

# NBA — safe, comprehensive  
fab manage --cmd "update_nba_all --season 2026"

# Full pipeline
fab manage --cmd "update_ncaa_all --season 2026"
```

### Dangerous Usage Patterns ⚠️

```bash
# ❌ DO NOT do this — incomplete
fab manage --cmd "update_nba_teams --season 2026"

# ❌ DO NOT do this — BPR will be stale
fab manage --cmd "update_nba_players --season 2026"

# ❌ DO NOT do this — website data will be incomplete
fab manage --cmd "update_nba_teams --season 2026" && \
fab manage --cmd "update_nba_players --season 2026"
```

---

## Proposed Fixes

### Option A: Rename NBA commands (minimal fix)
Rename to clarify what each does:
- `update_nba_teams` → `update_nba_ingest` (games + player boxes only)
- `update_nba_players` → `update_nba_stats` (box aggs + advanced only)
- `update_nba_all` stays as main orchestrator ✅

### Option B: Add missing step to `update_nba_players`
Add `nba_compute_box_bpr` to end of `update_nba_players` pipeline so:
```bash
fab manage --cmd "update_nba_teams --season 2026"
fab manage --cmd "update_nba_players --season 2026"  # Now includes BPR
```

### Option C: Keep as-is (current state)
- Only use `update_nba_all` for normal updates
- `update_nba_teams` and `update_nba_players` are for advanced debugging only
- Document this clearly

---

## Current Recommendation

**For daily/regular updates:**
- NCAA: `python manage.py update_ncaa_all --season 2026 --workers 4`
- NBA: `python manage.py update_nba_all --season 2026 --workers 4`

**Both are comprehensive and will fully update the website.**

Do you want me to implement any of the proposed fixes (Option A, B, or C)?

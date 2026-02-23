# Game Log ETL Pipeline - Documentation

## Overview

This document describes the game log ingestion and processing pipeline for the 2025-26 CBB season (and beyond). The pipeline fetches game-level data from NCAA Stats API, computes team metrics, and generates adjusted ratings.

## Architecture

### Data Flow

```
NCAA API (self-hosted)
    ↓
ingest_gamelogs (Django command)
    ↓
Database: Game, TeamGameStats, ScoringEvent
    ↓
compute_team_metrics (Django command)
    ↓
Database: TeamSeasonMetrics
    ↓
compute_game_adjusted_ratings (Django command)
    ↓
Database: TeamSeasonRatings
    ↓
DRF API Endpoints
    ↓
Next.js Frontend
```

### Database Schema

#### Core Models

**TeamExternalId** - Maps external team IDs/names to canonical Team records
- `team` (FK to Team)
- `source` (ncaa, espn, etc.)
- `external_id` (string)
- `external_name` (string)
- `confidence` (float 0.0-1.0)
- `is_manual_override` (boolean)

**Game** - Central game metadata
- `season_year` (int, e.g., 2026)
- `game_date` (date)
- `home_team`, `away_team` (FK to Team)
- `home_score`, `away_score` (int nullable)
- `status` (scheduled/in_progress/final/canceled/postponed)
- `neutral_site` (boolean)
- `source_game_id` (unique string)
- `raw_json` (JSONField for audit)

**TeamGameStats** - Box score for one team in one game
- `game` (FK to Game)
- `team`, `opponent` (FK to Team)
- `home_away` (H/A/N)
- `pts`, `fgm`, `fga`, `fg3m`, `fg3a`, `ftm`, `fta`
- `oreb`, `dreb`, `reb`
- `ast`, `stl`, `blk`, `tov`, `pf`
- `raw_json`

**ScoringEvent** - Individual scoring plays for Kill Shots
- `game` (FK to Game)
- `seq` (int, sequence order)
- `period`, `clock`
- `scoring_team` (FK to Team)
- `points` (1/2/3)
- `home_score`, `away_score` (running totals)
- `raw_json`

**TeamSeasonMetrics** - Aggregated season metrics
- `team`, `season`
- Totals: `total_pts`, `total_fgm`, etc.
- Per-game: `ppg`, `papg`, `pace`
- Per-possession: `ortg`, `drtg`, `net_rtg`
- Four Factors: `efg_pct`, `tov_pct`, `orb_pct`, `ftr` (+ opponent)
- Kill Shots: `kill_shots_for`, `kill_shots_against`, `kill_shots_pg`
- CBB Analytics: `ast_g`, `ast_pct`, `blk_g`, etc.

**TeamSeasonRatings** - Adjusted ratings from regression
- `team`, `season`
- `adj_o`, `adj_d`, `adj_em`, `adj_tempo`
- `rank_adj_o`, `rank_adj_d`, `rank_adj_em`
- `hca_estimate`
- `games_played`, `total_possessions`

---

## Management Commands

### 1. ingest_gamelogs

**Purpose:** Fetch and store game data from NCAA API

**Usage:**
```bash
# Full season (from Nov 1 to today)
python manage.py ingest_gamelogs --season 2026

# Specific date range (7-day test window)
python manage.py ingest_gamelogs --season 2026 --start 2025-11-04 --end 2025-11-10

# Refresh existing games
python manage.py ingest_gamelogs --season 2026 --refresh

# Dry run (no DB writes)
python manage.py ingest_gamelogs --season 2026 --start 2025-11-04 --end 2025-11-10 --dry-run

# Rebuild team mappings before ingesting
python manage.py ingest_gamelogs --season 2026 --rebuild-mappings
```

**Process:**

1. **Build Team Mappings**
   - Load existing TeamExternalId records
   - Load manual overrides from `backend/team_alias_overrides.yml`
   - Use fuzzy matching (rapidfuzz) with 80% confidence threshold
   - Generate unmatched teams report (CSV/JSON)

2. **Fetch Game Index**
   - Iterate through date range
   - Call NCAA API scoreboard endpoint for each date
   - Extract game metadata (teams, scores, status)

3. **Upsert Games**
   - Create/update Game records (dedupe by source_game_id)
   - Store game metadata and raw JSON

4. **Fetch Game Details**
   - For each game, fetch full details from NCAA API
   - Extract team box score totals → TeamGameStats (2 rows per game)
   - Extract scoring sequence → ScoringEvent (ordered by seq)
   - Validate: fgm≤fga, ftm≤fta, non-negative stats

5. **Resumability**
   - Idempotent: re-running overwrites existing games with --refresh
   - Skips unchanged games without --refresh
   - Logs errors, continues processing

**Rate Limiting:**
- 0.5 sec delay between NCAA API requests
- Retry with exponential backoff on errors
- 30-second timeout per request
- Response caching (1 hour for scoreboard, 2 hours for game details)

**Output:**
- Summary: dates processed, games created/updated/skipped, errors
- Last updated timestamps

---

### 2. compute_team_metrics

**Purpose:** Compute season aggregates and derived metrics from game logs

**Usage:**
```bash
# All teams for a season
python manage.py compute_team_metrics --season 2026

# Specific teams only
python manage.py compute_team_metrics --season 2026 --teams duke north-carolina
```

**Computations:**

**A. Aggregates (from TeamGameStats)**
- Totals: sum of pts, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, tov, pf
- Possessions: `fga - oreb + tov + 0.475*fta` (per team per game)

**B. Per-Game Metrics**
- `ppg = total_pts / games`
- `papg = total_pts_allowed / games`
- `pace = total_possessions / games`

**C. Per-Possession Metrics (per 100 possessions)**
- `ortg = 100 * total_pts / total_possessions`
- `drtg = 100 * total_pts_allowed / total_opp_possessions`
- `net_rtg = ortg - drtg`

**D. Four Factors - Offense**
- `efg_pct = 100 * (fgm + 0.5*fg3m) / fga`
- `tov_pct = 100 * tov / possessions`
- `orb_pct = 100 * oreb / (oreb + opp_dreb)`
- `ftr = 100 * fta / fga`

**E. Four Factors - Defense**
- `opp_efg_pct` (opponent's eFG%)
- `opp_tov_pct` (opponent's TOV%)
- `drb_pct = 100 * dreb / (dreb + opp_oreb)`
- `opp_ftr` (opponent's FTR)

**F. Four Factor Margins**
- `efg_margin = efg_pct - opp_efg_pct`
- `tov_edge = opp_tov_pct - tov_pct` (higher is better)
- `reb_edge = orb_pct - (100 - drb_pct)`
- `ftr_margin = ftr - opp_ftr`

**G. Kill Shots**

**Algorithm:**
1. For each game, iterate through ScoringEvent records in order (by seq)
2. Track current run for each team
3. When team scores:
   - Add points to their run
   - Reset opponent run to 0
4. When run first reaches ≥10 points:
   - Award 1 kill shot to that team
   - Set flag to prevent double-counting
5. When opponent scores, reset flag

**Metrics:**
- `kill_shots_for` (total for season)
- `kill_shots_against` (total against)
- `kill_shots_pg = kill_shots_for / games`
- `kill_shots_conceded_pg = kill_shots_against / games`
- `kill_shot_margin_pg = kill_shots_pg - kill_shots_conceded_pg`

**H. CBB Analytics Stats**
- `ast_g = total_ast / games`
- `ast_pct = 100 * total_ast / total_fgm`
- `blk_g = total_blk / games`
- `blk_pct` (requires opponent FGA, use formula: 100 * blk / opp_fg2a)
- `dpf_g = total_pf / games` (defensive fouls, approximated as total fouls)

**Output:**
- TeamSeasonMetrics record per team
- Console summary: teams processed, errors

---

### 3. compute_game_adjusted_ratings

**Purpose:** Generate proprietary adjusted ratings via possessions-weighted regression

**Usage:**
```bash
# Estimate HCA from data
python manage.py compute_game_adjusted_ratings --season 2026

# Use fixed HCA (3.5 pts/100 poss)
python manage.py compute_game_adjusted_ratings --season 2026 --hca 3.5

# Increase regularization
python manage.py compute_game_adjusted_ratings --season 2026 --alpha 2.0
```

**Methodology:**

**Model:**
```
PPP = μ + Off(team) - Def(opponent) + HCA*is_home + ε
```

Where:
- `PPP` = Points per possession
- `μ` = Baseline (national average PPP)
- `Off(team)` = Team's offensive deviation from baseline
- `Def(opponent)` = Opponent's defensive deviation from baseline
- `HCA` = Home court advantage (pts per possession)
- `ε` = Error term

**Implementation:**

1. **Build Design Matrix**
   - Each game generates 2 observations (one per team)
   - X matrix: [intercept, off_1...off_n, def_1...def_n, hca]
   - y vector: points per possession
   - Weights: possessions played

2. **Weighted Ridge Regression**
   ```
   (X'WX + αI) β = X'Wy
   ```
   - W = diagonal matrix of possession weights
   - α = regularization parameter (default 1.0)
   - Solve using scipy.linalg.solve or numpy

3. **Extract Parameters**
   - Baseline μ from intercept
   - Off ratings from β[1:n_teams]
   - Def ratings from β[n_teams:2*n_teams]
   - HCA from β[2*n_teams] (if estimated)

4. **Compute Adjusted Ratings**
   - `adj_o = 100 * (μ + Off(team))`
   - `adj_d = 100 * (μ - Def(team))`
   - `adj_em = adj_o - adj_d`
   - `adj_tempo = average(possessions per game)`

5. **Assign Rankings**
   - Rank by adj_em (1 = best)
   - Rank by adj_o (1 = best offense)
   - Rank by adj_d (1 = best defense, lower adj_d is better)

**Parameters:**
- `--hca`: Fixed home court advantage (default: estimate from data)
  - Typical value: 3.0-4.0 points per 100 possessions
- `--alpha`: Ridge regularization (default: 1.0)
  - Higher α → more shrinkage toward zero
  - Use early in season when sample size is small

**Output:**
- TeamSeasonRatings record per team
- Console: baseline PPP, HCA estimate, teams processed

---

## API Endpoints

All endpoints support JSON responses. Timestamps in ISO 8601 format.

### Team Game Endpoints

**GET /api/teams/{slug}/games?season=2026**

Returns list of all games for a team.

Response:
```json
{
  "team": {
    "slug": "duke",
    "name": "Duke",
    "logo_url": "..."
  },
  "season_year": 2026,
  "games": [
    {
      "id": 123,
      "game_date": "2025-11-04",
      "home_team_name": "Duke",
      "away_team_name": "Kentucky",
      "home_score": 89,
      "away_score": 84,
      "status": "final",
      "neutral_site": true,
      "venue_name": "Madison Square Garden"
    }
  ],
  "last_updated": "2025-11-05T03:15:00Z"
}
```

**GET /api/teams/{slug}/gamelog?season=2026**

Returns game log with derived metrics.

Response:
```json
{
  "team": {...},
  "season_year": 2026,
  "game_log": [
    {
      "id": 456,
      "game_date": "2025-11-04",
      "opponent_name": "Kentucky",
      "opponent_slug": "kentucky",
      "home_away": "N",
      "pts": 89,
      "result": "W",
      "margin": 5,
      "possessions": 72.4,
      "ortg": 122.9,
      "drtg": 116.0,
      "efg_pct": 58.3,
      "tov_pct": 12.5,
      "orb_pct": 35.2,
      "ftr": 28.6
    }
  ],
  "total_games": 15,
  "last_updated": "2025-11-05T03:15:00Z"
}
```

**GET /api/teams/{slug}/season-stats?season=2026**

Returns combined season stats (metrics + ratings).

Response:
```json
{
  "team": {...},
  "season_year": 2026,
  "metrics": {
    "games": 15,
    "ppg": 85.3,
    "papg": 72.1,
    "pace": 71.2,
    "ortg": 119.8,
    "drtg": 101.3,
    "net_rtg": 18.5,
    "efg_pct": 54.2,
    "tov_pct": 14.8,
    "orb_pct": 32.1,
    "ftr": 31.5,
    "kill_shots_pg": 2.3,
    "kill_shots_conceded_pg": 1.1,
    "kill_shot_margin_pg": 1.2
  },
  "ratings": {
    "adj_o": 122.5,
    "adj_d": 98.2,
    "adj_em": 24.3,
    "adj_tempo": 72.1,
    "rank_adj_em": 3,
    "rank_adj_o": 5,
    "rank_adj_d": 12,
    "hca_estimate": 3.4
  }
}
```

### Game Endpoints

**GET /api/games?season=2026&team=duke&status=final**

List games with optional filters.

Query params:
- `season`: year
- `team`: team slug (returns games where team is home or away)
- `date`: YYYY-MM-DD
- `status`: scheduled/in_progress/final/canceled/postponed

**GET /api/games/{id}**

Full game details including team stats.

Response:
```json
{
  "id": 123,
  "source_game_id": "ncaa-12345",
  "season_year": 2026,
  "game_date": "2025-11-04",
  "home_team_name": "Duke",
  "away_team_name": "Kentucky",
  "home_score": 89,
  "away_score": 84,
  "status": "final",
  "neutral_site": true,
  "venue_name": "Madison Square Garden",
  "period_count": 2,
  "went_to_ot": false,
  "home_stats": {
    "pts": 89,
    "fgm": 32,
    "fga": 62,
    "fg3m": 9,
    "fg3a": 24,
    "ftm": 16,
    "fta": 20,
    "oreb": 11,
    "dreb": 24,
    "reb": 35,
    "ast": 18,
    "stl": 7,
    "blk": 4,
    "tov": 9,
    "pf": 15,
    "possessions": 72.4
  },
  "away_stats": {...}
}
```

---

## Team Mapping System

### Overview

The team mapping system ensures that external team names/IDs from NCAA API and ESPN are correctly matched to our canonical `Team` records.

### Components

**1. TeamMapper Class** (`backend/core/utils/team_mapping.py`)

Methods:
- `find_team(external_name, external_id, min_confidence=0.80)` → (Team, confidence, is_override)
- `map_and_save(external_name, external_id)` → TeamExternalId
- `bulk_map(teams_data)` → summary dict
- `export_unmatched(output_file)` → CSV/JSON report

**2. Manual Overrides** (`backend/team_alias_overrides.yml`)

Format:
```yaml
ncaa:
  "St. Mary's (CA)": "Saint Mary's"
  "12345": "Connecticut"

espn:
  "41": "Duke"
```

**3. Fuzzy Matching**

Uses rapidfuzz library:
- Normalizes team names (lowercase, remove "University", "State", "College", etc.)
- Compares against Team names and aliases
- Threshold: 0.80 (80% similarity)
- Algorithm: fuzz.ratio

**4. Workflow**

```
External Name/ID
    ↓
Check manual override? → Yes → Use canonical name
    ↓ No
Exact normalized match? → Yes → Use Team
    ↓ No
Fuzzy match ≥80%? → Yes → Use Team (log confidence)
    ↓ No
Add to unmatched list → Export report
```

### Usage

During `ingest_gamelogs`:
1. Mapper is initialized with `source='ncaa'`
2. For each team in game data:
   - Check if TeamExternalId exists
   - If not, run fuzzy match
   - Save mapping to DB (or dry-run log)
3. Unmatched teams are reported at end

Manual review:
1. Run dry-run: `python manage.py ingest_gamelogs --season 2026 --dry-run`
2. Check unmatched teams report
3. Add entries to `team_alias_overrides.yml`
4. Re-run: `python manage.py ingest_gamelogs --season 2026 --rebuild-mappings`

---

## Validation & Data Quality

### Automated Checks

**During Ingestion:**
- `fgm ≤ fga`
- `fg3m ≤ fg3a` and `fg3m ≤ fgm`
- `ftm ≤ fta`
- All stats ≥ 0
- Final games have 2 TeamGameStats rows

**After Compute Metrics:**
- Sum of ScoringEvent points within ±5 of final score
- No duplicate games (unique source_game_id)

**Coverage Reports:**
- `% games ingested = (games in DB / expected games for date range)`
- `% teams mapped = (TeamExternalId count / 362 D1 teams)`
- `% games with scoring data = (games with ScoringEvent / final games)`

### Manual Validation

**Sample Game Checks:**
```sql
-- Check for final games missing stats
SELECT g.* 
FROM core_game g
LEFT JOIN core_teamgamestats tgs ON g.id = tgs.game_id
WHERE g.status = 'final' AND tgs.id IS NULL;

-- Check scoring event totals vs final score
SELECT 
  g.id, g.source_game_id,
  g.home_score, g.away_score,
  SUM(CASE WHEN se.scoring_team_id = g.home_team_id THEN se.points ELSE 0 END) as home_calc,
  SUM(CASE WHEN se.scoring_team_id = g.away_team_id THEN se.points ELSE 0 END) as away_calc
FROM core_game g
LEFT JOIN core_scoringevent se ON g.id = se.game_id
WHERE g.status = 'final'
GROUP BY g.id
HAVING ABS(g.home_score - home_calc) > 5;
```

---

## Running the Full Pipeline

### Initial Setup (One-Time)

```bash
# 1. Create 2025-26 season
python manage.py shell
>>> from core.models import Season
>>> Season.objects.create(year=2026, display_name="2025-26", is_current=True)
>>> exit()

# 2. Ensure NCAA API is running
# Docker: docker run -p 3000:3000 henrygd/ncaa-api
# Or set NCAA_API_BASE_URL in settings

# 3. Set up team_alias_overrides.yml
# Add known problematic mappings
```

### Daily Ingestion (Production)

```bash
# 1. Ingest yesterday's games
python manage.py ingest_gamelogs --season 2026 --start $(date -d "yesterday" +%Y-%m-%d) --end $(date +%Y-%m-%d)

# 2. Compute metrics for updated teams
python manage.py compute_team_metrics --season 2026

# 3. Recompute ratings (includes new data)
python manage.py compute_game_adjusted_ratings --season 2026
```

### 7-Day Test Window (Development)

```bash
# Test with Nov 4-10, 2025
python manage.py ingest_gamelogs --season 2026 --start 2025-11-04 --end 2025-11-10

# Compute metrics
python manage.py compute_team_metrics --season 2026

# Compute ratings
python manage.py compute_game_adjusted_ratings --season 2026

# Verify API
curl http://localhost:8000/api/teams/duke/gamelog?season=2026
```

### Full Season Backfill

```bash
# Ingest full season (Nov 1 - today)
python manage.py ingest_gamelogs --season 2026

# This may take 30-60 minutes depending on game count
# Monitor progress in console output

# Then compute metrics and ratings
python manage.py compute_team_metrics --season 2026
python manage.py compute_game_adjusted_ratings --season 2026
```

---

## Troubleshooting

### Issue: Team mapping failures

**Symptoms:**
- Many unmatched teams in logs
- Games not being created

**Solution:**
1. Check `team_alias_overrides.yml` for missing entries
2. Run with `--dry-run` to see which teams fail
3. Add overrides for non-matching names
4. Re-run with `--rebuild-mappings`

### Issue: NCAA API errors

**Symptoms:**
- 500 errors, timeouts
- No games fetched

**Solution:**
1. Verify NCAA API is running: `curl http://localhost:3000`
2. Check NCAA_API_BASE_URL in Django settings
3. Reduce rate limit delay if API is slow
4. Use ESPN fallback (implement in code)

### Issue: Missing scoring events

**Symptoms:**
- Zero kill shots in metrics
- No ScoringEvent records

**Solution:**
- NCAA API may not always provide play-by-play
- Some games lack detailed event data
- This is expected for ~10-20% of games
- Kill shots will be 0 for those games

### Issue: Inconsistent possessions

**Symptoms:**
- ORtg/DRtg look wrong
- Huge differences between team possessions in same game

**Solution:**
- Verify formula: `fga - oreb + tov + 0.475*fta`
- Check for missing stats (zeros where there should be data)
- Validate raw_json from NCAA API

---

## Performance & Scalability

### Database Indexes

Automatically created via Django migrations:
- `Game`: (season_year, game_date), (home_team), (away_team), (status), (source_game_id unique)
- `TeamGameStats`: (game, team unique), (team), (game)
- `ScoringEvent`: (game, seq unique)
- `TeamSeasonMetrics`: (team, season unique)
- `TeamSeasonRatings`: (team, season unique), (season, adj_em)

### Expected Data Volumes (Full Season)

- Games: ~6,000 (362 teams * ~17 games each / 2)
- TeamGameStats: ~12,000 (2 per game)
- ScoringEvent: ~500,000 (assuming ~80 events per game)
- TeamSeasonMetrics: 362 (1 per team)
- TeamSeasonRatings: 362 (1 per team)

Total DB size: ~200-300 MB per season

### Caching Strategy

- NCAA API responses cached in Django cache (Redis/Memcached in prod)
- Scoreboard: 1 hour TTL
- Game details: 2 hours TTL (longer for completed games)
- Cache key format: `ncaa:scoreboard:{division}:{date}`

---

## Future Enhancements

1. **Real-Time Updates**
   - WebSocket support for live game updates
   - Auto-refresh during games

2. **Advanced Kill Shots**
   - Contextualize by score margin and time remaining
   - "Clutch" kill shots (in final 5 minutes of close games)

3. **Player-Level Data**
   - Individual box scores (if NCAA API supports)
   - Player contribution to team metrics

4. **Opponent-Adjusted Metrics**
   - Factorial ratings (offensive/defensive components)
   - Game-by-game opponent adjustments

5. **Predictive Models**
   - Win probability live tracking
   - Rest days, travel distance factors

---

## Support & Maintenance

### Logs

- Django logs: `backend/logs/` (configure in settings.py)
- Command output: stdout/stderr
- API logs: DRF logging

### Monitoring

Check these periodically:
- `TeamExternalId` count: should be ~362
- `Game` count per season: should grow daily
- `TeamSeasonMetrics` last_updated: should match last ingestion run
- API response times: use Django Debug Toolbar

### Contact

For issues with the pipeline:
1. Check this documentation
2. Review Django admin for data anomalies
3. Inspect raw_json fields for API response structure changes
4. Open issue in project repo

---

*Last Updated: 2025-02-18*

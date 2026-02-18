# Game-Level Adjusted Ratings (AOR/ADR/AEM)

## Overview

This feature adds three new team metrics computed from **game-level boxscore data** with opponent adjustments and venue tax:

- **AOR** (Adjusted Offensive Rating): Points scored per 100 possessions, adjusted for opponent defense quality and venue
- **ADR** (Adjusted Defensive Rating): Points allowed per 100 possessions, adjusted for opponent offense quality and venue
- **AEM** (Adjusted Net Rating): AOR - ADR (overall team strength)

Additionally, each metric has a **0-100 "2K-style" rating** (AOR_100, ADR_100, NET_100) computed via z-score mapping.

## Key Differences from KenPom's AdjO/AdjD

Unlike KenPom's adjusted efficiencies (adj_o, adj_d), which are season-level aggregate metrics:

1. **Game-level granularity**: Each game's efficiency is adjusted individually before aggregation
2. **Explicit venue tax**: Home/away/neutral multipliers applied per game via SiteFactor
3. **Bayesian shrinkage**: Stabilizes ratings with k=300 possessions toward national average
4. **Transparent formulas**: Complete computation pipeline is documented and auditable

## Formulas

### Per-Game Possessions
```
Poss = FGA - OR + TO + 0.475 × FTA
```

### Raw Efficiencies (per game)
```
RawOE = 100 × (Pts / Poss)
RawDE = 100 × (PtsAllowed / Poss)
```

### Venue Tax (SiteFactor)
| Location | Multiplier | Effect |
|----------|-----------|---------|
| Home | 0.9862 | Slightly easier (~1.4% boost) |
| Away | 1.0140 | Slightly harder (~1.4% penalty) |
| Neutral | 1.0000 | No adjustment |

### National Average Efficiency
```
NatAvg = 100 × (Σ all_games Pts / Σ all_games Poss)
```
Possession-weighted average across all D1 games.

### Game-Level Adjusted Ratings
```
AOR_game = RawOE × (NatAvg / OppAdjD) × SiteFactor
ADR_game = RawDE × (NatAvg / OppAdjO) × SiteFactor
```

**Critical**: Venue tax is applied **directly** in the game-level calculation.

### Opponent Adjustments
- **OppAdjD**: Opponent's adjusted defensive rating (for your offense)
- **OppAdjO**: Opponent's adjusted offensive rating (for your defense)

Sources (in priority order):
1. KenPom adj_o/adj_d (closest date ≤ game date)
2. Torvik adj_oe/adj_de as fallback
3. National average if unavailable

### Team-Season Aggregation (Bayesian Shrinkage)
```
weight_game = Poss × RecencyMult

AOR = (Σ weight × AOR_game + k × NatAvg) / (Σ weight + k)
ADR = (Σ weight × ADR_game + k × NatAvg) / (Σ weight + k)

where k = 300 possessions (shrinkage parameter)
```

**RecencyMult**: Currently defaults to 1.0. Architecture supports date-based weighting for future implementation.

### Net Rating
```
AEM = AOR - ADR
```

### 0-100 "2K-Style" Ratings

Using z-score mapping with scale factor = 15:

#### AOR_100 (Offense)
```
z_score = (AOR - mean_AOR) / stdev_AOR
AOR_100 = clamp(50 + 15 × z_score, 0, 100)
```

#### ADR_100 (Defense)
Lower ADR is better, so invert to "defense plus":
```
DEFPLUS = NatAvg - ADR
z_score = (DEFPLUS - mean_DEFPLUS) / stdev_DEFPLUS
ADR_100 = clamp(50 + 15 × z_score, 0, 100)
```

#### NET_100 (Overall)
```
z_score = (AEM - mean_AEM) / stdev_AEM
NET_100 = clamp(50 + 15 × z_score, 0, 100)
```

**Scale**: 50 = average, 99+ = elite (~3.3 std deviations above mean)

## Data Requirements

### Game-Level Boxscore Data

The `GameLog` model stores per-game statistics:

**Required fields:**
- `pts`, `pts_allowed` (points scored/allowed)
- `fga` (field goal attempts)
- `or_total` (offensive rebounds)
- `to` (turnovers)
- `fta` (free throw attempts)
- `location` (H/A/N for home/away/neutral)
- `opponent_name` (for opponent adjustment lookup)
- `date` (for temporal matching)

**Opponent boxscore (optional but recommended):**
- `opp_fga`, `opp_or`, `opp_to`, `opp_fta` (for more accurate possessions)

### Data Sources

#### Option 1: Scrape from Sports-Reference / ESPN
- Game-by-game boxscores with traditional stats
- Team schedules with locations (home/away/neutral)
- Date available for each game

#### Option 2: Use existing KenPom game schedule data
- KenPom provides predicted scores and locations
- May require supplemental boxscore scraping

#### Option 3: Barttorvik Game Logs API
- Comprehensive game-level data
- Includes boxscore stats and locations

### Opponent Adjustment Data

The computation pipeline expects daily snapshots of team efficiencies:
- KenPom: `adj_o`, `adj_d` by date
- Torvik: `adj_oe`, `adj_de` by date

Currently available in:
- `KenPom Data/kenpom_tableau.csv` (daily snapshots)
- `Bart Torvik/torvik_tableau.csv` (daily snapshots)

## Database Schema

### New Fields in `TeamSeasonStats`

```python
# Raw adjusted ratings (pts/100 possessions)
aor = FloatField(null=True, blank=True)
adr = FloatField(null=True, blank=True)
aem = FloatField(null=True, blank=True)

# 0-100 "2K-style" ratings
aor_100 = FloatField(null=True, blank=True)
adr_100 = FloatField(null=True, blank=True)
net_100 = FloatField(null=True, blank=True)

# Rankings
rank_aor = IntegerField(null=True, blank=True)
rank_adr = IntegerField(null=True, blank=True)
rank_aem = IntegerField(null=True, blank=True)
```

### New Model: `GameLog`

Stores game-level boxscore data. See [core/models.py](../core/models.py) for full schema.

**Auto-computed fields:**
- `possessions`: Computed via formula on save
- `raw_oe`, `raw_de`: Raw efficiencies
- `weight`: Possessions × recency_mult

## Usage

### 1. Populate Game Logs

**TODO**: Implement game log scraper/import.

Example manual entry (for testing):
```python
from core.models import Team, Season, GameLog

team = Team.objects.get(slug='michigan')
opponent = Team.objects.get(slug='ohio-state')
season = Season.objects.get(year=2026)

GameLog.objects.create(
    team=team,
    season=season,
    date='2026-02-10',
    opponent=opponent,
    opponent_name='Ohio State',
    location='H',  # Home
    pts=85,
    pts_allowed=78,
    fga=58,
    or_total=10,
    to=12,
    fta=20,
    # Opponent stats (optional)
    opp_fga=62,
    opp_or=8,
    opp_to=15,
    opp_fta=16,
)
```

### 2. Compute Adjusted Ratings

Run the management command:

```bash
cd backend
python manage.py compute_adjusted_ratings --season 2026
```

**Options:**
- `--dry-run`: Test computation without saving to database
- `--season YEAR`: Season to compute (required)

**Expected output:**
```
[1/6] Loading game logs... ✓ Found 4500 game logs
[2/6] Computing national average... ✓ NatAvg: 105.23 pts/100
[3/6] Computing game-level adjusted ratings... ✓ 4500 games
[4/6] Aggregating to team-season level... ✓ 365 teams
[5/6] Computing 0-100 ratings... ✓
[6/6] Computing ranks... ✓
[7/7] Saving to database... ✓ Updated 365 teams

Top 10 Teams by Net Rating:
Rank   Team                AOR      ADR      Net      Net_100
1      Connecticut         121.45   92.31    29.14    95.2
2      Purdue              119.87   94.12    25.75    91.8
...
```

### 3. Verify via API

```bash
curl http://localhost:8000/api/rankings?sort=aem&dir=desc | jq '.results[0]'
```

Example response:
```json
{
  "rank": 1,
  "team_name": "Connecticut",
  "aor": 121.45,
  "adr": 92.31,
  "aem": 29.14,
  "aor_100": 98.5,
  "adr_100": 96.2,
  "net_100": 95.2,
  "rank_aor": 2,
  "rank_adr": 5,
  "rank_aem": 1
}
```

### 4. View in Frontend

**Team Rankings Page** (`/rankings`):
- New columns: "Adj O", "Adj D ↓", "Net"
- Sortable by AOR, ADR (lower is better), AEM
- Color-coded: blue (offense), green (defense), purple (net)

**Team Profile Page** (`/team/{slug}`):
- Overview tab includes "Game-Level Adjusted Ratings" section
- Shows raw ratings + ranks + 0-100 ratings
- Only displays if data is available (graceful fallback to "N/A")

## Implementation Checklist

- [x] Database models updated (`TeamSeasonStats` + new `GameLog` model)
- [x] Migrations created and applied
- [x] ETL command script (`compute_adjusted_ratings.py`)
- [x] Backend API updated (serializers + views)
- [x] Frontend types updated
- [x] Team Rankings page updated with new columns
- [x] Team Profile page updated with new section
- [ ] **CRITICAL**: Game log data pipeline (scraper/import)
- [ ] Team name normalization/alias mapping
- [ ] Opponent adjustment lookup implementation
- [ ] Recency weighting implementation (future)

## TODO: Game Log Data Pipeline

The primary blocker for production use is **game-level boxscore data**.

### Recommended Approach

1. **Source**: Barttorvik or Sports-Reference
2. **Scraper**: Python script using Playwright/Selenium
3. **Fields to extract**:
   - Game date, opponent, location (H/A/N)
   - Team stats: Pts, FGA, OR, TO, FTA
   - Opponent stats: PtsAllowed, (optionally: FGA, OR, TO, FTA)
4. **Import**: Django management command to load CSV → `GameLog` table
5. **Schedule**: Daily scraper (similar to KenPom pipeline)

Example structure:
```
KenPom Data/
  game_logs/
    scrape_game_logs.py       # Scraper
    import_game_logs.py       # Django import command
    game_logs_2026.csv        # Raw data
```

### Alternative: Minimal Manual Entry (Testing)

For testing/demo purposes, manually create ~20-30 game logs for 5-10 teams:
```bash
python manage.py shell
>>> from core.models import GameLog
>>> # Create games manually...
>>> exit()
python manage.py compute_adjusted_ratings --season 2026
```

## Sanity Checks

After computation, verify results are reasonable:

1. **Possessions > 0** for all games
2. **AOR/ADR range**: Typically 90-130 pts/100
3. **AEM range**: Typically -20 to +30
4. **100 ratings**: ~68% of teams between 35-65 (normal distribution)
5. **Top teams**: Should correlate with KenPom (not identical, but similar)

## References

- **Venue Tax**: Based on empirical home court advantage studies (~3% swing)
- **Bayesian Shrinkage**: Standard technique to prevent small-sample noise (k=300 typical)
- **Opponent Adjustments**: Core principle of KenPom/Torvik systems
- **Possessions Formula**: Dean Oliver's "Basketball on Paper"

## Questions / Support

For issues or questions:
1. Check game log data is populated (`GameLog.objects.count()`)
2. Verify opponent adjustments are available (check KenPom CSVs)
3. Run with `--dry-run` to test without database changes
4. Review computation logs for warnings/errors

---

**Status**: ✅ Framework complete, awaiting game log data pipeline implementation.

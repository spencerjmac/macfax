# Game Log Pipeline - Quick Start Guide

## What Was Built

A complete game log ingestion and analytics pipeline for Division I men's college basketball with:

✅ **5 Django Models** (Game, TeamGameStats, ScoringEvent, TeamSeasonMetrics, TeamSeasonRatings, TeamExternalId)
✅ **3 ETL Commands** (ingest_gamelogs, compute_team_metrics, compute_game_adjusted_ratings)
✅ **6 API Endpoints** (games, gamelog, season-stats for teams)
✅ **Team Mapping System** with fuzzy matching and manual overrides
✅ **Kill Shots Algorithm** from scoring sequences
✅ **Proprietary Adjusted Ratings** via possessions-weighted ridge regression
✅ **Frontend Game Log Component** in React/TypeScript/Tailwind
✅ **Comprehensive Documentation** (see `backend/README_GAME_LOG_ETL.md`)

---

## Initial Setup

### 1. Database Migration

```bash
cd backend
python manage.py migrate core
```

This creates all the new tables (Game, TeamGameStats, ScoringEvent, etc.)

### 2. Create 2025-26 Season

```bash
python manage.py shell
```

```python
from core.models import Season
Season.objects.create(year=2026, display_name="2025-26", is_current=True)
exit()
```

### 3. Set Up NCAA API

**Option A: Self-hosted Docker (recommended)**
```bash
docker run -p 3000:3000 henrygd/ncaa-api
```

**Option B: Configure in Django settings**
```python
# backend/config/settings.py
NCAA_API_BASE_URL = 'http://localhost:3000'  # or your NCAA API URL
```

### 4. Review Team Alias Overrides

Check `backend/team_alias_overrides.yml` and add any known problematic mappings:

```yaml
ncaa:
  "St. Mary's (CA)": "Saint Mary's"
  "UConn": "Connecticut"
```

---

## Test Run (7-Day Window)

Test with a small date range first (Nov 4-10, 2025):

```bash
cd backend

# 1. Ingest games
python manage.py ingest_gamelogs --season 2026 --start 2025-11-04 --end 2025-11-10

# Expected output:
# - Dates processed: 7
# - Games created: 50-100
# - Team stats created: 100-200
# - Scoring events: varies

# 2. Compute metrics
python manage.py compute_team_metrics --season 2026

# Expected output:
# - Processed: ~50-100 teams (teams that played games)

# 3. Compute adjusted ratings
python manage.py compute_game_adjusted_ratings --season 2026

# Expected output:
# - Baseline PPP: ~1.00-1.05
# - HCA estimate: ~0.03-0.04 (3-4 pts/100)
# - Ratings computed for N teams
```

---

## Validate Results

### Check Database

```bash
python manage.py shell
```

```python
from core.models import Game, TeamGameStats, ScoringEvent, TeamSeasonMetrics, Team

# Count records
print(f"Games: {Game.objects.filter(season_year=2026).count()}")
print(f"Team Stats: {TeamGameStats.objects.filter(game__season_year=2026).count()}")
print(f"Scoring Events: {ScoringEvent.objects.filter(game__season_year=2026).count()}")
print(f"Metrics: {TeamSeasonMetrics.objects.filter(season__year=2026).count()}")

# Sample game
duke = Team.objects.get(slug='duke')
metrics = TeamSeasonMetrics.objects.get(team=duke, season__year=2026)
print(f"\nDuke Metrics:")
print(f"  Games: {metrics.games}")
print(f"  PPG: {metrics.ppg:.1f}")
print(f"  ORtg: {metrics.ortg:.1f}")
print(f"  Kill Shots/G: {metrics.kill_shots_pg:.2f}")
```

### Test API Endpoints

```bash
# In another terminal, start Django dev server
python manage.py runserver

# Then test endpoints
curl http://localhost:8000/api/teams/duke/gamelog?season=2026
curl http://localhost:8000/api/teams/duke/season-stats?season=2026
curl http://localhost:8000/api/games?season=2026&status=final
```

### Check Admin

Visit `http://localhost:8000/admin/` and check:
- **Core > Games** - Should see games from Nov 4-10
- **Core > Team Game Stats** - Should see box scores
- **Core > Scoring Events** - Should see play sequences
- **Core > Team Season Metrics** - Should see computed metrics
- **Core > Team External IDs** - Should see NCAA team mappings

---

## Full Season Backfill

Once test run looks good, backfill the full season:

```bash
# This will ingest from Nov 1, 2025 to today
python manage.py ingest_gamelogs --season 2026

# Expected time: 30-60 minutes depending on # of games
# Monitor console output for progress

# Then compute metrics and ratings
python manage.py compute_team_metrics --season 2026
python manage.py compute_game_adjusted_ratings --season 2026
```

---

## Daily Update (Production)

Set up a cron job or scheduled task to run nightly:

```bash
#!/bin/bash
# daily_update.sh

cd /path/to/backend

# Ingest yesterday's games
python manage.py ingest_gamelogs --season 2026 --start $(date -d "yesterday" +%Y-%m-%d) --end $(date +%Y-%m-%d)

# Recompute metrics for all teams
python manage.py compute_team_metrics --season 2026

# Recompute ratings (includes new games)
python manage.py compute_game_adjusted_ratings --season 2026

echo "Daily update complete: $(date)"
```

**Schedule it:**
```bash
# Linux/Mac crontab
0 4 * * * /path/to/daily_update.sh >> /var/log/cbb_update.log 2>&1

# Windows Task Scheduler (PowerShell)
# Run at 4 AM daily
```

---

## Frontend Integration

### Add Game Log Tab to Team Profile

In your team profile page (e.g., `frontend/src/app/teams/[slug]/page.tsx`):

```tsx
import GameLog from '@/components/GameLog';

export default function TeamPage({ params }: { params: { slug: string } }) {
  const [activeTab, setActiveTab] = useState('overview');
  
  return (
    <div>
      {/* Tab Navigation */}
      <div className="tabs">
        <button onClick={() => setActiveTab('overview')}>Overview</button>
        <button onClick={() => setActiveTab('gamelog')}>Game Log</button>
      </div>
      
      {/* Tab Content */}
      {activeTab === 'overview' && <TeamOverview />}
      {activeTab === 'gamelog' && (
        <GameLog teamSlug={params.slug} seasonYear={2026} />
      )}
    </div>
  );
}
```

---

## Troubleshooting

### Issue: "No module named 'rapidfuzz'"

```bash
cd backend
pip install rapidfuzz pyyaml requests aiohttp tenacity
```

### Issue: Team mapping failures

```bash
# Run dry-run to see unmatched teams
python manage.py ingest_gamelogs --season 2026 --start 2025-11-04 --end 2025-11-04 --dry-run

# Check console output for unmatched teams
# Add them to team_alias_overrides.yml

# Then rebuild mappings
python manage.py ingest_gamelogs --season 2026 --rebuild-mappings
```

### Issue: NCAA API connection error

```bash
# Verify NCAA API is running
curl http://localhost:3000

# Check Django settings
grep NCAA_API backend/config/settings.py

# Or set environment variable
export NCAA_API_BASE_URL=http://localhost:3000
```

### Issue: Missing scoring events

**This is normal.** NCAA API doesn't always provide play-by-play data. Kill shots will be 0 for those games. Typically 10-20% of games lack detailed event data.

---

## Key Files Created

**Backend:**
- `core/models.py` - New models added at end
- `core/migrations/0007_game_log_pipeline.py` - Migration
- `core/management/commands/ingest_gamelogs.py` - ETL command
- `core/management/commands/compute_team_metrics.py` - Metrics computation
- `core/management/commands/compute_game_adjusted_ratings.py` - Ratings regression
- `core/utils/team_mapping.py` - Team mapping utility
- `core/utils/ncaa_api.py` - NCAA API client
- `core/admin.py` - Updated with new models
- `api/serializers.py` - Game log serializers added
- `api/views.py` - Game log views added
- `api/urls.py` - Routes updated
- `team_alias_overrides.yml` - Manual team mappings
- `README_GAME_LOG_ETL.md` - Full documentation

**Frontend:**
- `src/components/GameLog.tsx` - Game log table component
- `src/types/api.ts` - TypeScript types

---

## Next Steps

1. ✅ Run test ingestion (7 days)
2. ✅ Validate data in admin
3. ✅ Test API endpoints
4. ✅ Test frontend component
5. 🔲 Full season backfill
6. 🔲 Set up daily cron job
7. 🔲 Monitor for team mapping issues
8. 🔲 Add Kill Shots to frontend visualizations
9. 🔲 Implement ESPN fallback (if needed)
10. 🔲 Add player-level data (future enhancement)

---

## Support

- **Documentation:** `backend/README_GAME_LOG_ETL.md` (comprehensive guide)
- **Models:** Check `core/models.py` for schema details
- **API:** Visit `/api/` for DRF browsable API
- **Admin:** Visit `/admin/` to inspect data

**Questions?** Review the full ETL documentation for detailed methodology, data definitions, and troubleshooting.

---

*Built: 2025-02-18*
*Pipeline Version: 1.0*

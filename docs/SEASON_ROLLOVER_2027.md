# MacFax 2026–27 basketball season rollover

As of October 28, 2026: the NBA regular season has begun (October 20);
NCAA men's basketball starts November 2. NBA game-based metrics should be
current; NCAA game-based rankings should display a preseason empty state until
there are games. World Cup 2026 stays archived behind its direct URLs, and is
not promoted in the MacFax navigation or homepage.

## Deployment checklist

After reviewing and merging the season-refresh PR, rebuild the production
containers using the normal deployment procedure in `docs/DEPLOYMENT.md`.
Do not delete prior-season data or run `docker compose down -v`.

1. Check activation, then roll over both season records. The season **ending**
   year is 2027 for **2026–27**:

   ```bash
   docker compose exec backend python manage.py activate_basketball_seasons --season 2027 --dry-run
   docker compose exec backend python manage.py activate_basketball_seasons --season 2027
   ```

2. Seed the latest conference names and season-specific mappings. This is
   idempotent and does not modify old season affiliations:

   ```bash
   docker compose exec backend python manage.py seed_conferences --season 2027 --dry-run
   docker compose exec backend python manage.py seed_conferences --season 2027
   ```

   Run `seed_conferences` again after new-season NCAA team metrics are
   populated. New leagues: **P12** (Pac-12), **UAC** (rebranded WAC), and
   **Metro** (rebranded MAAC). Older WAC and MAAC codes remain for history.
   The 2026–27 move list lives in `backend/ncaa/conf_utils.py`.

3. Ingest NBA current-season games and compute ratings using the existing
   production pipeline:

   ```bash
   docker compose exec backend python manage.py update_nba_all --season 2027
   ```

   Inspect the output for failures and confirm the underlying NBA provider
   returns 2026–27 games. Do not label last year's ratings as this year's
   if the provider is unavailable.

4. From November 2, when NCAA games begin, use the NCAA team pipeline
   followed by conference reseeding. Run the broader NCAA player pipeline
   as supported by live data:

   ```bash
   docker compose exec backend python manage.py update_ncaa_teams --season 2027
   docker compose exec backend python manage.py seed_conferences --season 2027
   ```

   `update_ncaa_all --season 2027` remains the combined NCAA/NBA update
   workflow once the source data is available.

5. **Update every scheduled ingestion job / cron entry** to `--season 2027`
   or calculate the season end year dynamically. Older jobs referencing
   `--season 2026` will otherwise keep refreshing the historical season.

6. Verify the public site **after** deployment and processing. Suggested
   manual acceptance tests:

   - Navbar and homepage show only NCAA and NBA, not World Cup.
   - A mobile-width navbar opens and links navigate correctly.
   - NBA rankings and visualizations show season `2026-27` and valid
     game-based data; if unavailable, show a truthful empty state.
   - NCAA rankings show `2026-27`, and do not show 2025–26 records as
     if current; before November 2, link to the roster outlook.
   - Current NCAA conference filters include the nine-team Pac-12 and
     2026–27 memberships, while historical 2025–26 conference filters
     and team pages retain the earlier memberships.
   - World Cup archive URLs remain reachable, but no active navigation
     links lead to them.
   - `/api/seasons/`, `/api/nba/seasons/`, `/api/conferences/?season=2027`,
     `/api/rankings/?season=2027`, and `/api/nba/rankings/?season=2027`
     return consistent data for the selected season.
   - Confirm no data ingestion errors, stale cache, broken pages, or
     current-season `2026` debug instructions on the public site.

## Historical-policy note

Season 2026 (2025–26) retains the old WCC, MWC, WAC, and MAAC membership.
Season 2027 (2026–27) uses current memberships. The backtested
championship-only NCAA Champion Checklist is intentionally unchanged.
The 2026 NBA Draft Big Board stays available by direct archive URL, but no
longer appears in the primary navigation.

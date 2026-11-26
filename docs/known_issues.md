# Known issues

Open data and code issues that are known but not fixed yet. Each entry says where it shows up, what is
known about the cause, and what a fix needs. Remove an entry when its fix ships.

Last checked: 2026-11-25. Prod checks were read-only.

## NBA

### Two neutral-site games store the opposite home team from NBA.com

| Game | Date | Stored home / away | NBA.com home / away |
|---|---|---|---|
| `0022500147` | 2025-11-01 | DAL / DET | DET / DAL |
| `0022501230` | 2025-12-13 | SAS / OKC | OKC / SAS |

- **Where:** local and prod (`public` and `nba_old`), unchanged since the 2026-06-03 sync.
- **How we know:** NBA.com's designated home comes from GameRotation (`HomeTeam` / `AwayTeam` in the cached
  `<game_id>_gamerotation.json.gz` under `NBA_CACHE_DIR/pbp_cache`). The other 5 neutral-site games of 2025-2027
  (`0022400147`, `0022400621`, `0022500578`, `0022500602`, `0022501229`) and 2027's `0022600189` match NBA.com.
- **Cause:** for neutral-site games, LeagueGameLog lists both teams as "X @ Y", and `nba_sync_games` used to take
  the home team from whichever row came first. Since 708c911 a stored game keeps its home team, so a re-sync no
  longer flips it, but that also keeps these two as they are.
- **Effect:** home and away, scores by side, `is_home`, rest days and back-to-back flags are swapped for these
  two games. Lineups and stints are unaffected, because they are keyed by team id.
- **Fix:** a data fix that swaps the two games' home and away fields (`NBAGame` and `NBATeamGameStats.is_home`),
  then recomputes 2026 rest days. Not done yet.

### Neutral-site games get home-court advantage

- **Where:** team ratings (`nba_compute_ratings`) and RAPM (`nba.analytics.rapm`).
- **Cause:** `NBAGame` has no neutral-site field. `nba_compute_ratings` passes a boolean `is_home` for every game,
  and `services/ratings_engine.py` skips home-court advantage only when `is_home` is None. RAPM sets
  `hca_sign = 1.0` for every game ("NBA always has a designated home team").
- **Scale:** about 5 regular-season games a season (international games and NBA Cup knockout games in Las
  Vegas); see the 2026 list above.
- **Fix:** needs a migration (a neutral-site field on `NBAGame`, filled by `nba_sync_games` when both rows read
  "@"), then `is_home=None` for those games in the ratings and a zero HCA sign in RAPM. **Do it after P18**
  (`DROP SCHEMA nba_old`; see `deploy_native_bpr.md`). Until then, a new column in an `nba_*` table would break
  the §7.5 rollback, which brings back `nba_old` without it.

### 2026 champion is missing

- **Where:** `NBATeamSeasonRatings.playoff_finish` for 2026 (local and prod). It feeds the Crystal Ball,
  Landscape and backtest checklist views.
- **Cause:** `nba_sync_playoff_results` reads a hard-coded `PLAYOFF_RESULTS` table that stops at 2025. It has
  nothing to do with the 2026 Finals games, which were missing until 2026-11-24.
- **Fix:** add 2026 to `PLAYOFF_RESULTS` (champion NYK, beat SAS 4-1 in the Finals, plus the runner-up,
  conference finals, conference semifinal and first-round losers), then run
  `nba_sync_playoff_results --season 2026`.

### Commit 708c911 points to "branch notes" that do not exist

The message of 708c911 (`fix(nba): neutral-site games keep their stored home team on re-sync`) says "see the
branch notes" for `0022500147` and `0022501230`. No such notes exist; this file is where that information lives
(see the first NBA entry). The commit is on `main` and pushed, so its message is left as it is.

## NCAA (prod)

### Stale rating and metric rows for teams that were not D1 that season (2005-2025)

- **Where:** prod `TeamSeasonRatings` (69 full-season and 58 pre-tournament rows) and `TeamSeasonMetrics`
  (114 rows), seasons 2005-2025, for teams with no D1 `TeamSeasonMembership` row that season. Most are in
  2005-2011 and 2019, for example Cal Baptist, Grand Canyon, North Florida, Seattle and UC San Diego in 2005,
  North Alabama in 2013, and 15 reclassifying arrivals in 2019. Local has none.
- **Cause:** they were computed in June 2026, when prod's D1 set came from `Team.is_d1` (D1 today). Locally,
  Task 6d deleted them. The full chain of 2026-11-25 writes D1 rows only and deletes nothing, so they stayed.
- **Effect:** they are unmaintained, with no luck, schedule or box-score fields. Combined with the next issue,
  some appear in the public ratings table, for example 9 rows in 2005 and North Alabama in 2013. The Crystal
  Ball views and backtest filter by membership, so those are unaffected.
- **Fix:** delete them with a data fix (needs its own go). Removing these rows also needs the next fix;
  otherwise the rankings still filter by today's D1 list.

### The ratings table filters by today's D1 list, not the season's membership

- **Where:** `RankingsViewSet` in `backend/api/views.py` (`team__is_d1=True`), on local and prod. It feeds
  `/ncaa/ratings`.
- **Effect:** for past seasons it hides real D1 teams that are not D1 today, and shows any team that is D1
  today. Examples: 2005 drops Birmingham-Southern, Centenary, Hartford, Savannah St. and St. Francis Brooklyn,
  and shows 9 teams that were not D1 then (336 rows against 332 D1 teams). 2013 drops Hartford, Savannah St.
  and St. Francis Brooklyn, and shows North Alabama (345 against 347).
- **Cause:** Task 6f.2 moved metrics, ratings and the Crystal Ball views to `ncaa/utils/d1.py` (`d1_q`), but
  about 35 readers of `Team.is_d1` were left out of scope, this view among them.
- **Fix:** use `d1_q(season, "team")` in the rankings view, then delete the stale rows above.

## NCAA (local and prod)

### 2005-2007 have no neutral-site games outside the NCAA tournament

- **Where:** apart from the NCAA tournament (below), every 2005, 2006 and 2007 game has
  `Game.neutral_site = false` and `home_away` 'H' / 'A'. 2008-2025 flag about 520-780 neutral games a season.
- **Cause:** the source has none. ESPN's own `neutralSite` in each game's `raw_json` is `false` for every
  2005-2007 game; from 2008 on it matches the stored flag exactly.
- **Effect:** in those three seasons every other neutral game counts as a home game: the rating solver's
  site factors, HCA (`compute_hca`: 4.13 / 3.73 / 4.01 with the tournament marked, against 3.8-4.2 for
  2008-2010), SOS, SOR, WAB, game value and quadrants treat them as home/away.
- **Venue data exists but is not reliable enough to fill the gap on its own.** `raw_json` holds ESPN's
  venue for most games (about 600 a season have none). Calling a game neutral when it is not at the home
  team's most-used venue, tested on seasons that have the flag: precision 0.88 / 0.80 / 0.86 and recall
  0.65 / 0.89 / 0.94 in 2008 / 2009 / 2010 (0.95 / 0.98 in 2015). Applied to 2005-2007 it would mark about
  390-490 games a season, with roughly one in seven wrong and some missed.
- **Done:** the NCAA tournament games (64 a season, opening round included) are marked neutral by
  `data_fixes/2026-11-24_ncaa_tourney_neutral_2005_2007.py`. They are all after Selection Sunday, so
  pre-tournament ratings do not change.
- **Not done:** the venue rule (decided 2026-11-24). Early-season events, conference tournaments and other
  neutral games of 2005-2007 still count as home games.

### Early-season HCA is too high (2027: 6.15)

- **Where:** `NationalAverages.hca_points` for the current season, from `compute_hca` in the nightly run.
  On 2026-11-25 (about six games a team), 2027 HCA was 6.15 against 3.4-4.2 for full seasons
  (2.07 and 2.86 in the COVID seasons 2021-2022). It was 5.91 before the neutral-site fix; that fix
  raised it by taking the 2027 neutral games out of the home sample.
- **Cause:** early-season home games are mostly mismatches (home "buy" games), and the strength
  adjustment uses ratings that are still unsettled, so the in-season sample overstates home-court
  advantage until enough games are played.
- **Effect:** every forecast that uses the national HCA leans toward home teams while it stays high:
  luck, WAB, SOR, game value and the matchup predictions.
- **Fix (follow-up, not done):** blend the current-season estimate with prior seasons' HCA until the
  season has enough games, for example weighted by games played.

# Known issues

Open data and code issues that are known but not fixed yet. Each entry says where it shows up, what is
known about the cause, and what a fix needs. Remove an entry when its fix ships.

Last checked: 2026-11-24. Prod checks were read-only.

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

### Boston College's games sit under Boston University on prod (2005-2025)

- **Where:** prod only. Local was fixed on 2026-11-12 (Task 6c).
- **What prod shows:** `boston-college` has games only for 2026 and 2027. `boston-university` has games for
  every season 2005-2027, holding both schools' games through 2025. That is plain in the doubled counts of
  2022-2025 (68, 63, 68 and 62 games), and BU's 2021 total (49) is merged the same way.
- **Cause:** ESPN team id 103 (Boston College) was mapped to `boston-university`. `TeamMapper._normalize`
  strips "university" and "college", so both names became "boston". The 2027 mapping was fixed on prod on
  2026-11-24; the history was not.
- **Effect:** prod's BU ratings, metrics, records and player boxes for 2005-2025 mix two teams, and BC is
  missing from those seasons.
- **Fix:** part of the planned prod history merge (local NCAA 2005-2026 into prod with an id remap). It is
  not a separate data fix.

### Every 2027 D1 team is flagged "reclassifying: assumed" on prod

- **Where:** prod `TeamSeasonMembership`, season 2027: all 365 D1 rows have `is_reclassifying = True` and a note
  that includes `reclassifying: assumed (first D1 season 2027)`. That includes the 4 rows upgraded on 2026-11-24
  (Boston College, New Haven, Southern Indiana, West Florida).
- **Cause:** `sync_team_season_membership` assumes a team is reclassifying when its first D1 season in the
  table is one of the last 4 seasons. Prod's table has membership rows for 2027 only, so every team looks new.
- **Effect:** only opt-in filters read the flag (`exclude_reclassifying` on the Crystal Ball and Cinderella views,
  and `backtest_checklist`). With it on, those views drop every 2027 team on prod.
- **Fix:** comes with the prod history merge, which brings earlier membership seasons. Locally the flags were
  checked against Wikipedia's standings marks (Tasks 8a.2 and 8b.2). The 4-season assumption itself is suspect
  for later seasons; see `sync_team_season_membership`.

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

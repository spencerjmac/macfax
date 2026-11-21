# Deploy native BPR (tasks 5.4–5.10) to prod

Plan written 2026-11-21 (task D.2). The prerequisites were added in D.3 (2026-11-21):
- `update_daily` runs NCAA first, then NBA in a subprocess with a timeout (§5);
- the trained box model is cached under `NBA_CACHE_DIR` (§6);
- a `.dockerignore` covers the cache directories (§6);
- the deploy scripts are in `tools/deploy_native/` (Appendix A).

Nothing in this plan has been run on prod. The only prod access so far is the read-only survey of 2026-11-21
(`macfax-runs/d2/prod_readonly.sh`; output in `macfax-runs/d2/prod/`).
Every prod step below needs an explicit go in chat. That includes `fab deploy` and every
`docker compose exec`/`run` that writes.

**Method: swap the 18 `nba_*` tables, not `fab db-push`.**
1. Load local's NBA tables into a staging schema on prod.
2. Check every row count against local.
3. Carry prod's hand-entered NBA values into staging.
4. In one transaction, move the live tables to a backup schema (`nba_old`) and the staged tables into `public`.
5. Reset the sequences.

NCAA, users, favourites and every other non-NBA table are never touched. No foreign key crosses between the
`nba_*` tables and any other app, which the dump DDL confirms. The whole sequence was rehearsed in a throwaway
Postgres 16 container (section 7.6).

## Prod at a glance (survey 2026-11-21)

| | Prod | Local |
|---|---|---|
| Code | `2333608` (deployed 2026-11-18) | `main` = `361ce47` (6 commits ahead: f2ac267, 9896ddf, a728c46, f4e1540, 8650849, 361ce47) |
| `nba` migrations | `0031_nbaplayerseasonstats_bpr_model` | `0033_rating_scale` (0032 raw columns, 0033 scale table: both additive and nullable) |
| Other apps | core 0073, world_cup 0002, favorites 0001 | same |
| Database | 3,142 MB; Postgres 16.13 (pg_dump 16.13) | 5,391 MB; pg_dump 16.15 |
| NBA seasons | 2016–2027 | 2005–2027 |
| Host | 4 CPUs, 7 GB RAM (4 GB available, 1 of 7 GB swap in use), 61 GB disk free | 12 CPUs, 14 GB RAM |
| Daily run | scheduler at 10:00 UTC = **03:00 MST**; 18.6–19.3 min total (legacy NBA + NCAA), all OK for the last 7 days | – |
| NBA caches | none (no `data/nba/pbp_cache` in the checkout or the image) | `~/.cache/macfax/nba`: pbp 283 MB (28,655 files), possessions 356 KB |

---

## 1. What `fab db-push` does today, and what it would overwrite

Source: `fabfile.py` `db_push`, which runs these steps in order.

1. It runs `pg_dump -Fc` on the **whole** local database `macfax` and uploads the file.
2. It runs `pg_dump -Fc` on the whole prod database to `/opt/macfax/backups/prod-<ts>.dump` and deletes all but the
   newest 5 `prod-*.dump` files.
3. It runs `docker compose stop backend web`. **The scheduler keeps running**, so an `update_daily` in progress
   loses its database halfway through.
4. It runs `DROP DATABASE cbb_analytics`, then `CREATE DATABASE`, then `pg_restore` of the local dump.
5. It runs `docker compose up -d`.

It replaces every one of the 62 tables with local's copy.

| Group | What prod loses |
|---|---|
| `django_migrations`, `django_content_type`, `auth_permission` | replaced by local's. They happen to match today (127 migrations on prod; local has the same plus nba 0032/0033). |
| `auth_user`, `django_session`, `django_admin_log` | 0 rows each on prod today, so nothing is lost now. Any future prod account would be lost. |
| `favorites_favoriteteam` | **prod's 1 favourite (1 device)**, replaced by local's 3 test favourites |
| NCAA (`core_*`, 29 tables) | **all prod NCAA data**: the side-flip and LSU-New Orleans repairs, the D.1 GP fix, and everything the daily job has written since. Prod and local NCAA differ a lot: `core_playergamestats` 1,348,275 on prod vs 2,353,063 locally, and `core_playergamestint` 1,929,730 vs 1,818,112. The NCAA history merge has not been done. |
| `world_cup_worldcupteam`, `validation_*` | replaced by local's (48 / 0 rows on both) |
| NBA (`nba_*`, 18 tables) | replaced by local's. This is the only part we want. |

**Verdict:** don't use it. It throws away prod's NCAA data, and it leaves the scheduler running while the
database is dropped. The NBA-only swap below gives the same NBA result without either risk.

## 2. NBA data prod needs that only local has

All 18 NBA tables, as of the survey (local counts are from the D.2 dump at 2026-11-21 10:59):

| Table | Local rows | Local size | Prod rows | Prod size | Local − prod |
|---|---:|---:|---:|---:|---:|
| nba_nbagame | 28,610 | 14 MB | 14,395 | 5 MB | +14,215 |
| nba_nbaplayergamestats | 721,307 | 149 MB | 372,284 | 75 MB | +349,023 |
| nba_nbaplayergamestint | 8,781,380 | 2,487 MB | 4,025,976 | 951 MB | +4,755,404 |
| nba_nbateamgamestats | 57,220 | 12 MB | 28,790 | 7 MB | +28,430 |
| nba_nbaplayerseasonstats | 17,664 | 18 MB | 9,689 | 9 MB | +7,975 |
| nba_nbateamseasonratings | 1,042 | 600 kB | 536 | 336 kB | +506 |
| nba_nbaplayer | 2,445 | 568 kB | 1,654 | 451 kB | +791 |
| nba_nbaseason | 24 | 40 kB | 13 | 41 kB | +11 |
| nba_nbaseasonratingscale | 22 | 40 kB | — (table arrives in 0033) | — | +22 |
| nba_nbaplayeravailability | 377 | 552 kB | 2,174 | 2 MB | −1,797 (carried over, §3) |
| nba_nbaprojectedrosterslot | 363 | 1,152 kB | 666 | 344 kB | −303 (§3) |
| nba_teamoutseasonmove | 381 | 656 kB | 381 | 147 kB | 0 (identical) |
| nba_teamseasonoutlook | 30 | 208 kB | 30 | 147 kB | 0 |
| nba_nbamodelcalibration | 11 | 40 kB | 11 | 41 kB | 0 |
| nba_nbateam | 30 | 80 kB | 30 | 82 kB | 0 |
| nba_nbabprmodelartifact, nba_nbaplayercontract, nba_projectedstarter | 0 | – | 0 | – | 0 |
| **Total** | | **≈2.7 GB** | | **≈1.05 GB** | |

The files to transfer are small:
- `pg_dump --no-owner --no-privileges -t 'nba_*'` (plain SQL, gzip -6) is **81 MB** and takes 18 s.
- Uncompressed it is 706 MB, of which the stints are 645 MB.
- The dump does contain all **8,781,380** stints; I counted the rows in every COPY block and all 18 tables match local exactly.
- A stint row is 27 small integers, about 73 bytes as text. A stint repeats almost verbatim for each of the 10 players on the floor, so gzip packs it to about 9 bytes a row.
- The 2.5 GB on disk is the 1,055 MB table plus 1,431 MB of indexes.
- The count check in step P7 confirms the row counts again after the load on prod.

What the data contains, by season (local; prod has no NBA data before 2016):

| | Local | Prod today |
|---|---|---|
| 2005 | games, box, stints, baseline RAPM; no native rows (it is the history start) | — |
| 2006–2015 | everything: games, box, stints, native-1 ratings with raw columns, box rows, a scale row each | — |
| 2016–2021 | native-1 + raw + scale; stints from the fixed parser (Phase P) | old-parser stints, about 7% fewer (2016: 382,113 vs 409,490). Ratings: `bpr` is NULL on every row, so **these seasons show no BPR on prod today**. |
| 2022–2026 | native-1 + raw + scale; projection values (654–713 per season) | legacy `bpr`/`projection_value` |
| 2027 | 235 games, 82,320 stints, 474 native ratings, scale row, baseline RAPM, 0 box rows (too early) | 235 games, **0 stints, 0 rated** |
| Scale rows | 22 (2006–2027) | table missing |
| Baseline RAPM | every season 2005–2027 | 2016–2026 |
| Career BPR | 1,443 of 2,445 players | 696 of 1,654 |
| 2027 outlooks | 30 teams, 363 roster slots from the 5.10 constants | 30 teams, 666 slots from the July pipeline |

Box score rows also differ slightly: 2021 has 31,546 locally vs 31,462 on prod, 2022 has 33,848 vs 33,745, and
2027 has 6,555 vs 6,551. Local has more rows in each case, from the Phase H re-syncs. Games are identical on both: all 14,395 of prod's games are
in local with the same status and scores, through 2026-11-20. Prod has no player that local lacks.

## 3. Prod-only data to keep

**Kept by construction.** The swap only renames the 18 `nba_*` tables, so the following are never written:

| Data | Prod rows |
|---|---|
| All NCAA tables (`core_*`) | 29 tables, 2.2 GB on disk (`core_game` 122,494; `core_playergamestats` 1,348,275; …) |
| Users | `auth_user` 0, `django_session` 0, `django_admin_log` 0 |
| Favourites | `favorites_favoriteteam` 1 (1 device). It stores NCAA slugs as plain text, with no foreign key. |
| `django_migrations`, content types, permissions | unchanged |
| `world_cup_worldcupteam`, `validation_*` | 48, 0 |

**Prod-only NBA values, carried into staging by `carry.sql`** (step P8; it writes only `nba_stage`).
Each value is matched by natural key, never by id, and each section prints what it changes:

| Value | Natural key | Prod vs local today | Action |
|---|---|---|---|
| Outlook text: `season_headline`, `macfax_take`, `development_spotlight_player`, `development_spotlight_text`, `season_defining_variable`, plus `is_published` and `snapshot_frozen_at` | (season year, `team_slug`) | **identical**. All 30 teams have no editorial text on either side. | prod's values overwrite staging wherever they differ. The differences are listed first. |
| Manual moves (`nba_teamoutseasonmove.source = 'manual'`) | (year, team_slug, move_type, player_name, detail) | **identical**: 3 rows, 2027 draft picks 56, 57 and 60 (Ishchenko, Ngo, Lewis), same `created_at`. All 381 moves match. | prod rows missing from staging are inserted and listed |
| Injury reports (`nba_nbaplayeravailability`) | (NBA.com player id, `game_date`, `source`) | prod has 2,174 rows, local 377. Prod's 2027 history runs to today (2,057 rows; local has 260). | missing rows are inserted, and rows where prod's `updated_at` is newer are updated. It also prints the number of unmapped rows, which must be 0. |
| Roster slots (`nba_nbaprojectedrosterslot`) | – | prod 666 (July pipeline, old constants), local 363 (5.10 constants) | **not carried: local's 363 replace prod's 666** (decided 2026-11-21, D.3). Slots are computed by `compute_nba_team_outlooks`, and the 5.10 values are the ones being deployed. |
| NBA rows newer than local | – | games: none. Season stats, team ratings and career BPR are rewritten by every daily run, and prod's 03:00 run updated them today. | the catch-up run (step P15) brings prod up to date on the native path |

## 4. Prod's playoff box/archetype copies: which pages read them

Prod has **1,992** playoff `nba_nbaplayerseasonstats` rows, 2016–2026, with `box_bpr` or a non-empty
`nba_archetype` (163–198 per season). The 2,037 in the task probably counts a slightly different set of columns.
Local has none.

- The **API** returns these values only with `?season_type=playoffs`, on four endpoints:
  - `/api/nba/players/`
  - `/api/nba/players/compare/`
  - `/api/nba/team/<slug>/players/`
  - `/api/nba/teams/<slug>/roster-value/`
- **No web page shows them:**
  - The ratings page does fetch playoff players, but `NBAPlayerRankingsTable` hides the Impact tab (the box and archetype columns) whenever `isPlayoffs`.
  - The compare page, the team page and the roster-value page never send `season_type`.
- **Expo** never sends `season_type`.
- **Backend calculations** read only regular-season rows: outlooks, career BPR, slope and the native chain.

After the swap these copies are gone (local has none), and nothing visible changes.

## 5. Does a failing `update_nba_all` stop `update_daily`'s NCAA steps?

**Not when it fails normally.** `update_daily._run` catches both `SystemExit` (the pipelines end with `sys.exit(1)`) and
`Exception`, records `[FAIL] NBA pipeline`, and moves on to NCAA. It exits 1 at the end. The test
`test_nba_failure_does_not_stop_ncaa_and_exit_is_nonzero` pins this behaviour.

**But before D.3, NBA did not run after NCAA. It ran first, in the same process, with no timeout** (`update_daily.handle`
called `update_nba_all` via `call_command`, then `update_ncaa_teams`, then `update_ncaa_players`). So:

- if an NBA step hung (an NBA API call, a lock), NCAA waited indefinitely, because neither `update_daily` nor
  `run_scheduler` has a timeout;
- if the process died (an out-of-memory kill, a segfault), NCAA was skipped that day. The scheduler survives,
  because it runs `update_daily` as a subprocess, and runs again the next day;
- the native NBA path takes longer than the legacy one, so NCAA would have started later every day.

**Done in D.3** (`ncaa/management/commands/update_daily.py`, tests in `ncaa/tests/test_update_daily.py`):

1. `update_daily` runs **NCAA first** (in process, as before), **then NBA**.
2. NBA runs as a subprocess with a timeout: `subprocess.run([sys.executable, "manage.py", "update_nba_all",
   "--season", S, "--workers", W], cwd=BASE_DIR, timeout=minutes * 60)`.
   - The timeout is env `NBA_TIMEOUT_MIN`, default **120**. A missing, unparsable or non-positive value means 120.
   - The prod estimate for a native run is in §6.
3. Each failure is logged as a failed step, `update_daily` exits 1 at the end, and NCAA has already finished:

   | Failure | Logged as |
   |---|---|
   | timeout (the child is killed) | `[FAIL] NBA pipeline: timed out after 120 min (killed)` |
   | non-zero exit | `exited with status N` |
   | death by signal (an OOM kill) | `killed by signal 9` |
   | the child cannot start | `could not start: …` |

4. The child's output goes straight to the scheduler log, and its memory goes back to the OS when it exits.
   - If the native writes are cut off partway, the next run redoes them: each `--write` step clears and rewrites its own season.
5. Tests (20 in the file, all pass):
   - NCAA runs before NBA;
   - NBA's exact command, `--season` and timeout;
   - a timeout, a non-zero exit and a signal each give `[FAIL]` and exit 1, with both NCAA pipelines having run;
   - an NCAA failure still runs NBA;
   - the env override, including bad values;
   - `--dry-run`, `--skip-nba` and `--skip-ncaa-players`.

**Memory.** `update_nba_all` runs its steps in one Python process, so its peak is the largest step plus
whatever earlier steps left allocated. Local peaks, measured with `/usr/bin/time -v` on read-only (`--dry-run`) runs for 2027:

| Step | Peak RSS | Wall time | CPU time / wall |
|---|---:|---:|---:|
| `nba_compute_baseline_rapm --season 2027 --dry-run` | 432 MB | 10.8 s | – |
| `nba_fit_box_pooled --season 2027 --dry-run`, no cache (D.2) | **2,499 MB** | 17.0 min | 1.04: single-threaded (1,001 s user + 67 s sys) |
| the same, **box model cache hit** (D.3) | **203 MB** | 11.2 s (10.0 s of it hashing inputs) | – |
| `nba_compute_native_bpr --season 2027 --dry-run` (warm possession cache) | 437 MB | 19.2 s | – |

The peak of a whole run was not measured, because that would need a write run. The first prod run (P15) records it with `ru_maxrss`.
Prod has 7 GB RAM with **≈4 GB available**. Postgres, Redis, two gunicorn workers and Next.js take the rest, and
1 GB of swap is already in use.

- **An uncached box fit dominates:** ≈2.5 GB, about 6× any other step.
- **With the box model cache (D.3)**, a daily run's box step only loads season Y and predicts, so the run should
  peak around the native step's ≈0.45 GB. A cache miss (new training data, a new library version, or the first run
  without a seed) still costs ≈2.5 GB once.
- **NCAA and NBA peaks are now separate:** NCAA runs first, and NBA runs in its own process.
- Step P15 records the real prod peak (`peak_rss_mb`). If it exceeds ≈3.5 GB, stop and revisit before
  re-enabling the scheduler.

## 6. Cache volume, `.dockerignore`, first-run time

**The volume.** Compose (from 5.9) mounts `macfax_nba_cache` at `/cache/nba` in `backend` and `scheduler`, with
`NBA_CACHE_DIR=/cache/nba`. The compose project is `macfax` (containers are `macfax-*-1`), so the real volume
name is **`macfax_macfax_nba_cache`**. `docker compose up -d` creates it during `fab deploy`. Prod has no cache today.

**What the seed buys:**
- **Possession cache** (`native_poss_cache/`, 356 KB). It is keyed on each season's stint fingerprint {n, secs, max_id,
  content}, where `content` is the database-side hash of the stint rows as text, ids included. The swap copies
  local's stints byte for byte, ids included, so every season 2006–2026 hits. Locally that cuts native BPR
  from 333 s to 19 s. 2027 changes daily and is recomputed each run anyway. Without the seed, the first run
  rebuilds the cache (≈5 min longer) and later runs are warm.
- **Box model cache** (`box_model_cache/`, D.3; ≈4 KB per season: `2026.pkl` 4.2 KB, `2027.pkl` 4.2 KB). `nba_fit_box_pooled --season Y` stores the
  trained offense and defense models as `<Y>.pkl`.
  - **Key:** a SHA-256 over the command's settings, the scikit-learn and numpy versions (pinned in
    `requirements.txt`: 1.8.0 and 1.26.4, the same locally) and a database-side content hash. The hash covers
    every row training reads:
    - the stints of seasons 2006..Y−1;
    - the games of those seasons;
    - the player-season columns used;
    - the regular team ratings;
    - the players in those seasons (pk → NBA.com id) and all teams.
  - **What leaves the key alone:** season Y's own rows and players added later.
  - **Cost and result:** hashing takes ≈10 s. A hit skips the 21 pooled-RAPM targets and all the fitting. Season
    Y's inputs are always read fresh.
  - **On prod:** after the swap, prod's training rows are local's byte for byte, ids included, so a seeded
    `2027.pkl` hits. Without the seed, the first run fits once (≈17–30 min, ≈2.5 GB) and stores it.
  - **Verified (D.3, read-only dry runs, `macfax-runs/d3/`).** Each season ran three ways: `--no-cache`, then a cold
    cache (miss, fit, store), then a warm cache (hit).

    | Season | Predictions | No cache | Cache hit | Peak RSS no cache / hit |
    |---|---:|---:|---:|---:|
    | 2026 | 385 | 975 s | 10.3 s | 2,442 MB / 200 MB |
    | 2027 | 0 (no player meets the box rule yet) | 1,029 s | 10.3 s | 2,468 MB / 203 MB |

    - The predictions, archetypes included, and the model numbers (scaler means and scales, ridge coefficients,
      intercepts, alphas, offense and defense) were **identical** in all three runs for both seasons.
    - 2026's predictions also equal the box rows stored in the DB for all 385 players.
    - The cold runs took 22 min because the two seasons ran in parallel.
  - **When it refits:** when a training season's rows change (a re-sync of an old season) or the season rolls over.
    Use `--no-cache` to force a fit.
- **pbp cache** (`pbp_cache/`, 283 MB, 28,655 files). These are raw NBA API play-by-play responses.
  `nba_sync_play_by_play` resumes, so it skips games already marked `pbp_synced`, and the swap brings
  local's flags for all 235 games of 2027. The cache therefore only matters when a game is re-parsed, which
  otherwise means refetching from the NBA API. It is cheap to seed, so seed it.

**Seed commands** (steps L4 and P5) extract the tarball into the volume through a one-off container. The image
runs as root, so the file owner matches the app.

**`.dockerignore`** (D.3), at the repo root. The build context for both `backend` and `web` is `.`, and
`backend/Dockerfile` does `COPY data/nba/ /data/nba/`. It excludes only the cache directories:

```
# NBA caches live in NBA_CACHE_DIR (a Docker volume on prod) since 5.9: never bake old copies
# from a checkout into an image. Only these two directories are excluded.
data/nba/pbp_cache/
data/nba/native_poss_cache/
```

The prod checkout has no cache directories (`data/nba` is 492 KB of CSVs), so prod images were clean already. The
main checkout still has an old 280 MB `data/nba/pbp_cache`, which a local `docker compose build` would have baked in.
`box_model_cache` only ever lives in `NBA_CACHE_DIR`, never in the checkout.

**Probe (D.3).** I built the worktree with backend's exact three COPY lines, with fake `pbp_cache/` and
`native_poss_cache/` files added to `data/nba/`. The context was 44.7 MB.
- **Absent from the image:** both cache directories.
- **Present:**
  - `/data/nba`: 12 CSVs (LEBRON 2016–2026, `bpr_2025_26.csv`);
  - NCAA `/app/ncaa/data/conferences/2027.csv`;
  - world_cup `/app/world_cup/data/{results_cache.csv, shootouts_cache.csv, teams.json}`;
  - `/app/data/bracket_2026.json`;
  - 366 logos in `/app/static/logos`;
  - `/metrics_output`.
- `web/Dockerfile` copies only `web/` and `packages/`, so the file doesn't touch it.

**First run's time.** The local native run of 2026-11-20 took 32.4 min. That run synced 145 new games: box scores 252 s,
pbp 409 s, box fit 927 s, native 333 s (cold). The first prod run after the swap has **no new games to fetch** if it
runs the same day as the dump. Its cost is then the fixed per-run steps:

| Step | Local | Prod estimate (4 CPUs vs 12) |
|---|---:|---:|
| game, box and pbp sync (0–15 new games) | <1 min | 1–2 min (NBA API bound) |
| player stats, minutes check, team ratings, advanced, baseline RAPM | ≈15 s | <1 min |
| box fit (`nba_fit_box_pooled --write`), cache hit (D.3) | 11 s | ≈1 min |
| box fit, cache miss (unseeded or new training data) | 927 s (17.0 min in the D.2 dry-run) | 17–30 min (single-threaded, so the core count doesn't help; it depends on prod's per-core speed, which is unknown) |
| native BPR | 19 s warm / 333 s cold | ≈1 min warm / 10–15 min cold |
| career, playoff steps, injuries | ≈10 s | <1 min |
| **Total** | **≈2 min with both caches warm** | **≈5 min with both caches warm; ≈20–35 min on a box-cache miss; +10–15 min if the possession cache isn't seeded** |

From then on the daily NBA run costs about the same, plus a few seconds per new game. Step P15 measures the real numbers.

## 7. Backup, order of steps, post-deploy checks, rollback

### 7.0 Prerequisites (local; before the deploy day)

1. **D.3 merged to `main` and pushed**, so `origin/main` (what `fab deploy` checks out) has:
   - the update_daily order and timeout;
   - the box model cache;
   - the `.dockerignore`;
   - the scripts in `tools/deploy_native/`.
2. A deploy task that says WRITE (local catch-up run and staging on prod) and approves each prod step.

### 7.1 Timing

- Start after prod's 03:00 MST run has finished: `update_daily finished` appears in the log, normally by ≈03:20.
- Plan for about 2 h of work, so that everything is finished, including the first native run (P15), well before
  the next 03:00 run. **Recommended: start between 08:00 and 18:00 MST on a day you can watch the next morning's run.**
- The site stays up for everything except P10–P13: about 1–2 min while backend and web are down for the swap and restart.
- The scheduler is stopped from P4 until P16, so no daily run can start mid-swap. If the work runs past
  02:30 MST, leave the scheduler stopped and run `update_daily` by hand later; never start it during a swap.

### 7.2 Local steps (in a worktree of `main`)

```bash
# L1. Worktree of main (code that matches what prod will run)
cd /home/spencer/Workspace/macfax && git fetch origin && git worktree add ../macfax-deploy origin/main
cd /home/spencer/Workspace/macfax-deploy/backend
PY=/home/spencer/Workspace/macfax/backend/.venv/bin/python
T=/home/spencer/Workspace/macfax-deploy/tools/deploy_native
OUT=/home/spencer/Workspace/macfax-runs/deploy; mkdir -p $OUT; TS=$(date +%Y%m%d_%H%M%S)

# L2. Bring local up to today on the native path (WRITE: backup first)
pg_dump -Fc -d macfax -f /home/spencer/Workspace/macfax/backups/macfax_${TS}_pre_deploy_catchup.dump
systemd-inhibit nohup $PY manage.py update_nba_all --season 2027 > $OUT/local_catchup_$TS.log 2>&1
tail -30 $OUT/local_catchup_$TS.log      # every step [OK]; stores ~/.cache/macfax/nba/box_model_cache/2027.pkl

# L3. NBA dump (plain SQL; loads into Postgres 16.13), its row counts, and the count check built from it
pg_dump -d macfax --no-owner --no-privileges -t 'nba_*' | gzip -6 > $OUT/nba_full_$TS.sql.gz
zcat $OUT/nba_full_$TS.sql.gz | awk '/^COPY /{t=$2;n=0;inb=1;next} inb&&/^\\\.$/{print t, n; inb=0; next} inb{n++}' \
  > $OUT/nba_full_counts_$TS.txt
wc -l $OUT/nba_full_counts_$TS.txt       # 18
bash $T/make_check_counts.sh $OUT/nba_full_counts_$TS.txt > $OUT/check_counts.sql

# L4. Cache seed (pbp, possessions, trained box models)
tar czf $OUT/nba_cache_seed_$TS.tgz -C ~/.cache/macfax/nba pbp_cache native_poss_cache box_model_cache
tar tzf $OUT/nba_cache_seed_$TS.tgz | grep -c box_model_cache/      # includes 2027.pkl

# L5. Upload (to prod's backups/, which git ignores)
scp -P 42222 $OUT/nba_full_$TS.sql.gz $OUT/nba_cache_seed_$TS.tgz $OUT/check_counts.sql \
    $T/to_stage.awk $T/carry.sql $T/swap.sql $T/rollback.sql $T/verify.sql macfax@sands.usu.edu:/opt/macfax/backups/
```

Do not run any local NBA job between L2 and L3. The dump must be the data that L3's counts describe.

### 7.3 Prod steps

Run these on prod after `ssh -p 42222 macfax@sands.usu.edu`, `cd /opt/macfax`, and `TS=<the same TS as L1>`.
Define a shortcut first:

```bash
PSQL="docker compose exec -T db psql -X -U cbb_user -d cbb_analytics -v ON_ERROR_STOP=1"
```

| # | Step | Command | Pass when |
|---|---|---|---|
| P1 | Pre-flight (read-only) | `git log -1 --oneline; docker compose ps; df -h /; free -g; docker compose logs --since 12h scheduler \| grep -E "starting update_daily\|update_daily (finished\|FAILED)"` | HEAD `2333608`; all 5 services up; ≥ 20 GB free; today's run shows `finished` |
| P2 | **Full backup** (named outside db-push's `prod-*` prune pattern) | `docker compose exec -T db pg_dump -U cbb_user -Fc cbb_analytics > backups/pre-native-swap-$TS.dump && ls -lh backups/pre-native-swap-$TS.dump && docker compose exec -T db pg_restore -l < backups/pre-native-swap-$TS.dump \| grep -c "TABLE DATA"` | ≈370 MB; TABLE DATA count = 61 (prod has 61 tables before 0033) |
| P3 | **Deploy code + migrate to 0033** (from local: `fab deploy`) | `fab deploy` runs `git reset --hard origin/main`, `build`, `up -d`; the backend command runs `migrate`. Then on prod: `$PSQL -Atc "SELECT max(name) FROM django_migrations WHERE app='nba'"` and `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7001/api/nba/health/` | `0033_rating_scale`; 200. If macfax.usu.edu returns 502: `docker exec swag nginx -t && docker exec swag nginx -s reload`. Prod still runs the **legacy** path (2026 has no native rows), which is safe if the swap is postponed. |
| P4 | Stop the scheduler | `docker compose stop scheduler && docker compose ps scheduler` | exited |
| P5 | Seed the cache volume | `docker volume ls \| grep nba_cache` then `docker compose run --rm --no-deps -v /opt/macfax/backups:/seed:ro scheduler sh -c "tar xzf /seed/nba_cache_seed_$TS.tgz -C /cache/nba && du -sh /cache/nba/* && ls /cache/nba/pbp_cache \| wc -l"` | `macfax_macfax_nba_cache` exists; ≈283 MB pbp, ≈356 KB possessions, box_model_cache with `2027.pkl`; file count as in L4 |
| P6 | **Load staging** (site stays up) | `zcat backups/nba_full_$TS.sql.gz \| awk -f backups/to_stage.awk \| $PSQL -q -1 > backups/stage_load_$TS.log 2>&1; echo rc=$?` | rc=0 (one transaction: a failure leaves no `nba_stage`). Estimate 5–10 min; disk +≈2.7 GB |
| P7 | **Count check** | `$PSQL -q -v schema=nba_stage -f - < backups/check_counts.sql` | `COUNTS OK: 18 tables, every count matches local` (any mismatch errors out, so stop there) |
| P8 | **Carry prod-only NBA values** | `$PSQL -f - < backups/carry.sql \| tee backups/carry_$TS.log` | `unmatched` 0, `unmapped_must_be_0` 0, `missing` 0; review the listed differences. Expected today: 0 outlook diffs, 0 manual moves, ≈1,800 injury rows inserted. |
| P9 | Pre-swap snapshot | `$PSQL -f - < backups/verify.sql > backups/verify_pre_$TS.txt 2>&1` | – |
| P10 | Stop backend + web; confirm no other sessions | `docker compose stop backend web && $PSQL -Atc "SELECT pid, application_name, state FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"` | no rows |
| P11 | **Swap** (one transaction) | `$PSQL -q -f - < backups/swap.sql; echo rc=$?` | rc=0. Seconds: only metadata moves. Any error rolls the whole swap back. |
| P12 | Clear NBA cache keys | `docker compose exec -T redis sh -c "redis-cli -n 1 --scan --pattern 'macfax:*:nba:*' \| xargs -r redis-cli -n 1 del"` | prints the number deleted (the matchup view's 30-min keys; NCAA keys untouched) |
| P13 | Start backend + web | `docker compose up -d backend web` (the backend reruns `migrate`, a no-op, and `nba_sync_teams`), then the curl from P3; swag reload if 502 | 200 |
| P14 | **Post-swap checks** | §7.4 | all pass |
| P15 | **First native run**, timed, with peak memory | `nohup docker compose run --rm --no-deps -T scheduler python -c "import resource, subprocess, time; t=time.time(); r=subprocess.run(['python','manage.py','update_nba_all','--season','2027']); print('rc', r.returncode, 'minutes', round((time.time()-t)/60, 1), 'peak_rss_mb', resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024)" > backups/native_first_run_$TS.log 2>&1 &` then `tail -f backups/native_first_run_$TS.log` | `[NATIVE] 2026 holds native ratings: native rating steps for 2027`, steps `[N3/14]`…`[N14/14]` all `[OK]`, last line `rc 0 …`. The box step logs `box model cache hit for 2027`. Record minutes and `peak_rss_mb`; native step ≈1 min (warm cache). |
| P16 | Start the scheduler | `docker compose start scheduler && docker compose logs --tail 3 scheduler` | `next run <tomorrow> 10:00 UTC` |
| P17 | Next morning | `docker compose logs --since 6h scheduler \| grep -E "\[(OK\|FAIL\|KEEP)\]\|update_daily"` | NCAA `[OK]`, then NBA `[OK]` (the full log shows `[NATIVE] …` and the `[N…/14]` steps), `finished`; duration noted |
| P18 | After 7 clean daily runs (separate go) | `$PSQL -c "DROP SCHEMA nba_old CASCADE"` | frees ≈1.05 GB |

### 7.4 Post-deploy checks (P14)

1. **Database:** `$PSQL -f - < backups/verify.sql > backups/verify_post_$TS.txt 2>&1`.
   - Schemas: `public` holds 62 tables (18 NBA), `nba_old` 18, and there is no `nba_stage`.
   - `nba` migration is `0033_rating_scale`.
   - Every row of the sequence check shows `ok = t`.
   - Per season matches local's §2 table: native 474–712 rows for 2006–2027, scale 1 per season, pv for 2022–2026, `po_box` 0.
   - Career BPR 1,443 players.
   - The 2027 top 10 matches local's list at dump time: on 2026-11-20 that was Wembanyama 13.28, Jokić 11.65, Gilgeous-Alexander 8.21, and so on.
   - Non-NBA counts are unchanged: `diff <(sed -n '/non-NBA/,$p' backups/verify_pre_$TS.txt) <(sed -n '/non-NBA/,$p' backups/verify_post_$TS.txt)` prints nothing.
     The NCAA daily job does not run while the scheduler is stopped, so nothing should move.
2. **API** on prod: `for u in health/ "rankings/?season=2027" "players/?season=2027" "players/?season=2016" "outlook/" "outlook/utah-jazz/" "team/boston-celtics/players/?season=2027" "matchup/?teamA=boston-celtics&teamB=utah-jazz&season=2027"; do echo "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' "http://127.0.0.1:7001/api/nba/$u") $u"; done`.
   - Every URL returns 200.
   - 2016 now returns ratings; it had none before.
3. **Pages** (browser, macfax.usu.edu and macfax.org):
   - `/nba` and `/nba/ratings`: 2027 shows BPR values. Also check 2016 and 2010, which are new on prod.
   - A team page, `/nba/outlook` and one outlook detail.
   - Model health.
   - An NCAA ratings page: unchanged.
   - Favourites still work.
4. **Logs:** `docker compose logs --since 10m backend | grep -iE "error|traceback" | head` prints nothing new.

### 7.5 Rollback

| When | Do |
|---|---|
| P3 fails (build or migrate) | `fab deploy` failed before `up -d`: prod still runs the old containers, so stop and diagnose. Failed after: redeploy the old code on prod: `git reset --hard 2333608 && docker compose build && docker compose up -d` (not `fab deploy`, which resets to `origin/main`). Migrations 0032/0033 can stay. The old code ignores the extra nullable columns and the extra table, so don't migrate backwards. |
| P5–P9 fail | `$PSQL -c "DROP SCHEMA IF EXISTS nba_stage CASCADE"`, then `docker compose start scheduler`. Prod is unchanged apart from the new code, which runs the legacy path. |
| P11 fails | It rolls back by itself (one transaction). Check `$PSQL -Atc "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'nba%'"` shows only `nba_stage`, then start backend and web. |
| P13–P17 show a problem | `docker compose stop backend web scheduler`, then `$PSQL -q -f - < backups/rollback.sql` (one transaction: the swapped-in tables go to `nba_failed`, `nba_old` returns to `public`, sequences are reset), then P12 (cache), then `docker compose up -d backend web` and `docker compose start scheduler`. Prod is back to its pre-swap NBA data, with migrations at 0033 and the new code on the legacy path. Add the code rollback above if needed. Keep `nba_failed` for diagnosis. |
| Disaster (schemas lost) | `backups/pre-native-swap-$TS.dump` is the full pre-swap database. Restoring from it, even for NBA tables only, is a separate decision. Don't restore the whole database. |

Notes:
- `rollback.sql` returns the NBA tables **as they were at P9**. Daily NBA rows written after the swap (P15 onwards) are
  lost on rollback. The next legacy run re-creates the data it needs.
- Injury reports written after the swap would need the same carry from `nba_failed` if they matter.

### 7.6 Rehearsal (done 2026-11-21, local, throwaway container)

`tools/deploy_native/rehearse.sh DUMP COUNTS OUT_DIR` sets up a `postgres:16-alpine` container with no network, removed afterwards. It was run in D.2 and rerun from `tools/` in D.3, with the same result:
- "prod" is the local NBA dump in `public`, with the stints cut to 20,000 (local disk has 4.5 GB free, too little for a full-size copy);
- plus fake prod-only edits: a headline, one outlook unpublished, a manual move, a new injury report and a newer injury report.

The rehearsal then ran steps P6 to P11, the checks and the rollback. Result (`rehearsal/run.log`):
- **Staging load:** rc 0.
- **Count check:**
  - with local's real counts it **failed** as it should (20,000 ≠ 8,781,380 → `COUNT MISMATCH`, rc 3);
  - with the sample counts it passed.
- **Carry:** prod's headline and unpublished flag were copied into staging, the manual move was inserted, and the injury reports showed 1 inserted and 1 updated (newer `updated_at`). The unmapped and missing counts were 0.
  - Its first version had a bug, a `RETURNING` that referenced a joined table. The rehearsal caught it and it is fixed.
- **Swap:**
  - rc 0; `nba_old` holds 18 tables;
  - all sequences are `max(id)+1` with `ok = t`;
  - a new insert got id `max+1`;
  - foreign keys point at the swapped-in `nba_nbagame`, `nba_nbaplayer` and `nba_nbateam`;
  - the non-NBA test table was untouched.
- **Rollback:** rc 0. `public` was back to the old tables (old headline, old counts), and the swapped-in tables were in `nba_failed`.

Not rehearsed:
- load time at full size;
- `fab deploy`;
- the cache seed (the box-cache key match on prod is checked by P15's `cache hit` line);
- the redis flush;
- the first native run on 4 CPUs (P15 measures it).

---

## Appendix A. Scripts (`tools/deploy_native/`)

| File | Used in | What it does |
|---|---|---|
| `to_stage.awk` | P6 | Rewrites a plain `pg_dump -t 'nba_*'` so every object lands in schema `nba_stage`: DDL and COPY headers change from `public.` to `nba_stage.`, data rows pass through untouched. |
| `make_check_counts.sh` | L3 | Builds `check_counts.sql` from the dump's per-table row counts. Run it with `psql -v schema=nba_stage`: it errors out unless all 18 tables exist and every count matches. |
| `carry.sql` | P8 | Copies prod's outlook text and publish state, manual moves and injury reports into `nba_stage` by natural key, listing every difference. It also reports games that differ and players missing. One transaction; writes only `nba_stage`. |
| `swap.sql` | P11 | One transaction: `public.nba_*` → `nba_old`, `nba_stage.nba_*` → `public`, then every identity sequence is reset to `max(id)+1`, `public` is asserted to hold 18 NBA tables, and the empty `nba_stage` is dropped. ANALYZE follows. |
| `rollback.sql` | §7.5 | The reverse: `public.nba_*` → `nba_failed`, `nba_old` → `public`, sequences reset, assert. |
| `verify.sql` | P9, P14 | Read-only: schemas, migration, sequences, NBA per season, career BPR, the 2027 top 10, and every non-NBA count (to diff before/after). |
| `rehearse.sh` | §7.6 | Runs the whole swap and rollback in a throwaway container on a sample of a dump. |

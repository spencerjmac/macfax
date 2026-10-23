--

## 1. One sentence

The `api/` folder is the front desk of the backend: it receives questions from the website and the phone app (for example "give me the rankings for 2026"), looks up or calculates the answer from the database, and sends it back as data.

## 2. The analogy: a restaurant

- **The customer** = the website (`web/`) or the phone app (`apps/expo/`).
- **The menu and the host** = `api/urls.py`. The customer says what they want ("rankings"); the host sends the order to the right kitchen station.
- **The kitchen stations (chefs)** = the `*_views.py` files. Each station cooks one kind of dish.
- **The recipes** = the "engine" files (`matchup_engine.py`, `bracket_engine.py`, `checklist.py`...). The chefs follow these to do the maths.
- **The pantry** = the database (tables like teams, games, ratings). The chefs take ingredients from it.
- **The plating** = `serializers.py`. It arranges what came out of the pantry into a neat plate (JSON, defined below) so the customer can read it.
- **The staff-only office** = `auth_views.py`, `job_views.py`, `job_tasks.py`. Only the manager (a logged-in admin) may go in, to log in and to start the big "re-cook everything" job.

## 3. The walkthrough

### 3a. How one request travels

Example: the website loads the Duke roster outlook page. It asks `GET /api/outlook/duke/`.

1. **`config/urls.py:9`** says "anything starting with `api/` goes to the api folder" (`path('api/', include('api.urls'))`). Lines 10 and 11 send `api/nba/` and `api/world-cup/` to two other folders (`nba/`, `world_cup/`) that this guide does not cover.
2. **`api/urls.py`** is the menu. The `outlook/<slug>/` line hands the request to `RosterOutlookView`. Order matters: the specific paths (`outlook/top/`, `outlook/scenario/`, ...) sit *before* the catch-all slug line, with a comment saying so (around line 61).
3. **`api/outlook_views.py`** (`RosterOutlookView.get`) loads the team's projection rows from the database, shapes them with small helper functions, and returns the result.
4. Django REST Framework (DRF) turns the result into JSON, because `config/settings.py` allows only the JSON renderer (`REST_FRAMEWORK`, around line 132).
5. The website receives the JSON and draws the page.

### 3b. Map of the files (32 source files plus a `tests/` folder; about 9,600 lines of source and 3,300 lines of tests)

**Wiring**
| File | What it is |
|---|---|
| `__init__.py` | Empty file that tells Python "this folder is a package". |
| `apps.py` | Tiny Django registration (`name = 'api'`). `config/settings.py` lists `"api"` in `INSTALLED_APPS`. |
| `urls.py` | The menu: every web address this folder answers, about 87 lines. |

**Main data endpoints**
| File | What it is |
|---|---|
| `views.py` | About 1,100 lines. Seasons, conferences, rankings, teams (list, game log), the NCAA matchup predictor, games, admin pipeline settings, league player list, team roster. |
| `serializers.py` | About 1,570 lines. Converts database rows to JSON. The giant one is `RankingsSerializer` (about 750 lines). |

**Chart endpoints, one file each (the website's "viz" pages)**
| File | Serves | Helper |
|---|---|---|
| `landscape_views.py` | NCAA Efficiency Landscape | none |
| `nba_landscape_views.py` | NBA Efficiency Landscape | `nba_landscape_config.py` (tier-line numbers) |
| `trapezoid_views.py` | NCAA Trapezoid of Excellence | `trapezoid_config.py` (numbers) |
| `crystal_ball_views.py` | NCAA Crystal Ball (15-item champion checklist for every team) | `checklist_utils.py` |
| `nba_crystal_ball_views.py` | NBA Crystal Ball (10-item checklist) | `nba_crystal_ball_config.py`, `checklist_utils.py` |
| `nba_luck_chart_views.py` | NBA "luck" chart (actual wins vs expected wins) | none |
| `cinderella_views.py` | Cinderella Index (which low seeds are dangerous) | `bracket_engine.py` |
| `bracket_views.py` | Tournament bracket simulation | `bracket_engine.py` |
| `viz_builder_views.py` | "Viz builder" (pick any two stats, get a scatter plot) | `stat_catalog.py` |

**Engines and helpers (the "recipes")**
| File | What it does |
|---|---|
| `matchup_engine.py` | Forecasts a game between two teams: pace, expected points, win probability, volatility. About 840 lines of pure maths with no web code. |
| `bracket_engine.py` | Simulates the NCAA tournament thousands of times (Monte Carlo = repeated random trials) to get each team's odds of reaching each round. |
| `checklist.py` | An NCAA 15-item "national champion checklist" for one team. Only reachable through `TeamViewSet`'s `stats` and `profile` sub-routes, which nothing calls. The checklist the website actually shows is computed in `packages/core/src/lib/rankings.ts`, and the Crystal Ball page uses `crystal_ball_views.py`. Kept for now, with its tests (`tests/test_checklist.py`) brought up to date; retire it together with those two sub-routes if you decide they are not needed. |
| `checklist_utils.py` | One small helper (`_item`) that builds one checklist row; shared by NCAA and NBA. |
| `resume_utils.py` | NCAA "quadrant" logic (is this a Quad 1 win?). Only `get_quadrant` is used today; the rest is kept for planned resume features. |
| `wp_reconstruction.py` | Rebuilds a game's win-probability curve from who was on the court (lineup "stints"). |
| `game_insights.py` | Asks Claude to write 3 short observations about a game, and saves them on the game. |

**Roster Outlook and market value**
| File | What it does |
|---|---|
| `outlook_views.py` | Next season's projected roster, "what if I add or remove a player" scenarios, player search, projected top teams, placeholder archetypes. |
| `market_value_views.py` | Player "market value" lists. Built but intentionally not linked from the website yet (its own docstring says so). |

**Other**
| File | What it does |
|---|---|
| `validation_views.py` | Accuracy report: how well did our predictions do? Three endpoints. |
| `game_detail_views.py` | One-game page: box score, win-probability curve, four factors, AI insights. |
| `auth_views.py` | Login, logout, "who am I", and the security-cookie handshake for the admin page. |
| `job_views.py`, `job_tasks.py` | Admin-only: start, watch, cancel and clean up the big "update everything" data job. |
| `tests/` | 9 test files (223 tests) that check the api works, plus `base.py` (see "Running the tests" below). |

### 3c. The 5 most important files in detail

**1) `urls.py`: the menu**
- *What:* a list of "address -> who handles it". Two styles:
  - **Router** (around lines 34-41): a shortcut that auto-creates standard addresses (list, detail) for 7 "ViewSets" (seasons, conferences, rankings, teams, matchup, games, jobs).
  - **Explicit `path(...)` lines** for everything else.
- *Why it exists:* without it Django wouldn't know which code answers which address. Every request would be "404 not found".
- *If missing/wrong:* the site's data calls all fail. A wrong order of lines (slug catch-all before specific paths) would make `outlook/top/` be treated as a team called "top". That's why the comment exists.
- The **tombstone comment** (around lines 67-77) is a note left where deleted code used to be. It explains the old `/api/scenarios/...` routes were removed on 2026-07-09 because nothing called them. `tests/test_scenario_retirement.py` checks they stay gone (404).

**2) `views.py`: the workhorse**
- `SeasonViewSet`, `ConferenceViewSet`: simple read-only lists.
- `RankingsViewSet`: the main table of teams with ratings, shaped by `RankingsSerializer`.
- `TeamViewSet`: list of teams plus extra sub-addresses `/stats`, `/profile`, `/games`, `/gamelog`, `/season-stats` (each an `@action`). Only `gamelog` is called by the website and phone app today; the others are kept on purpose as read-only API surface for future screens.
- `MatchupViewSet.list`: the head-to-head predictor. About 430 lines; calls many functions from `matchup_engine.py`. `compute_adjusted_variance` is a helper used inside it.
- `GameViewSet`, `PipelineConfigView` (admin only), `LeaguePlayersView`, `TeamRosterView`.
- *If missing:* the NCAA rankings, team and matchup pages stop working.

**3) `serializers.py`: the plating**
- A **serializer** takes a database row (or a bundle of rows) and decides exactly which fields to show and how to name and round them.
- `RankingsSerializer` builds each rankings row, with many computed fields.
- `TeamSeasonStatsSerializer` (used only by `TeamViewSet`'s `stats` and `profile` sub-routes) carries a `national_champion_checklist` field that calls `compute_national_champion_checklist` from `checklist.py`.
- Other serializers: seasons, conferences, teams, game logs, team metrics, player stats, pipeline config, job rows, placeholder archetypes.
- *If missing:* the views have no way to produce their JSON; most endpoints would crash on import.
- *Why it's long:* it does a lot of derived-stat maths inline. It is the file most worth splitting up someday.

**4) `outlook_views.py`: the "Roster Outlook" feature**
- Five views: `RosterOutlookView` (one team's outlook), `ProjectedTopTeamsView`, `ScenarioProjectionView` (a `POST` that re-projects a team after you edit its roster; described in the file as stateless), `PlayerSearchView`, `PlaceholderListView`.
- It works with projection tables (`TeamSeasonProjection`, `PlayerSeasonProjection`, `TeamRosterFit`) that other commands fill in ahead of time, so these views mostly *read and shape*.
- *If missing:* the `/ncaa/outlook` pages break.

**5) `job_views.py` + `job_tasks.py`: the admin "run the pipeline" panel**
- `DataProcessingJobViewSet` is admin-only (`permission_classes = [IsAdminUser]`).
- A **job** here is a record in the database of a long-running task. `run` starts the full "update all" command as a **subprocess** (a separate program started by this one) in a background thread. `run_update_all_subprocess` (`job_tasks.py`) streams its output line by line into the job's `logs` field.
- Endpoints that exist: list, `run`, `job_status` (the admin page polls this), `cancel`, `fix_stuck`, `clear_history`, delete, plus `logs` (snapshot) and `stream` (live Server-Sent-Events feed). The admin page (`web/src/app/admin/page.tsx`) uses list, `run`, `job_status`, `cancel`, `fix_stuck`, `clear_history` and delete. `logs` and `stream` are kept but not called by the website today.
- *If missing:* you could still run `update_all` from the command line, but the Admin page's buttons would break.

### 3d. The other pieces, briefly

- **`auth_views.py`** (4 functions): `csrf` hands the browser a security token; `login_view` checks username and password and starts a **session**; `logout_view`; `me`. Only the admin page uses these.
- **`game_detail_views.py` `ncaa_game_detail`**: builds the one-game payload (box score, win-probability curve, four factors, AI insights). The NBA twin lives in `nba/game_detail_views.py` and shares `wp_reconstruction.py` and `game_insights.py`.
- **`game_insights.py`**: `generate_game_insights` asks Claude for 3 observations and returns `None` if anything fails (the reason is logged). `load_or_generate_insights` is what the views call: it returns the saved insights if present, otherwise generates them and saves them on the game. **A failure shows a placeholder but is never saved**, so the next request tries again. (Before 2026-10-21 failures were saved and served forever; see `tests/test_game_insights.py`.) It needs the `anthropic` package and an Anthropic API key in the server environment.
- **`wp_reconstruction.py`**: `build_wp_curve` works for both NCAA and NBA.
- **Config files** (`trapezoid_config.py`, `nba_crystal_ball_config.py`, `nba_landscape_config.py`): plain constants with no logic. Their docstrings say the numbers come from backtests (past-data experiments) in `backtesting/management/commands/`.

### 3e. Kept on purpose even though nothing calls them yet

- `market_value_views.py` and its two routes: serve-only until the frontend is wired in (Phase 7).
- `TeamViewSet` actions `stats`, `profile`, `games`, `season-stats`.
- `resume_utils.py` functions `is_quality_win`, `is_bad_loss`, `get_quadrant_records`, `format_quadrant_record`.
- Job endpoints `logs` and `stream`.

### Running the tests

```
cd backend
python manage.py test api              # everything in this folder
python manage.py test api.tests.test_matchup_api   # one file
```

Django creates a throwaway `test_<dbname>` database, runs the tests, and deletes it; your real database is not touched. (`pytest` is not installed in `backend/.venv`; use `manage.py test`.)

Views such as `/api/matchup/` and `/api/rankings/` cache their answers. Tests that call them inherit from `IsolatedCacheTestCase` (`tests/base.py`), which swaps in a private in-memory cache and empties it before each test. Without it, tests read each other's cached answers and leave fake data in the dev server's Redis. If you add a test that calls a cached view, use that base class and call `super().setUp()` in your `setUp`.

### 3f. Removed on 2026-10-21 (recoverable from git history)

- `api/analyze_view.py` and the `analyze/` route: nothing called it, and it was a copy of the offline script `backend/analyze_criteria.py`, which still exists.
- Job endpoints `start_update_all`, `start_ingest`, `start_subjob` and the `run_*` helpers in `job_tasks.py` that only they used. They were marked "legacy", nothing called them, and their error handling referenced an undefined variable.

## 4. How it connects

**Who calls the api folder**
- **Website** `web/src/lib/api.ts` (a typed wrapper with one function per endpoint), `web/src/lib/data.ts` (server-side fetches for rankings, seasons, outlook), and `web/src/app/admin/page.tsx` (auth, jobs, pipeline-config).
- **Phone app** `apps/expo/src/lib/api.ts` uses only: `/api/rankings/`, `/api/seasons/`, `/api/teams/<slug>/gamelog/`, `/api/games/`, `/api/games/<id>/detail/`.
- **Shared TypeScript package** `packages/core` mainly holds *types* describing the JSON shapes (for example `packages/core/src/types/outlook.ts`). It doesn't contain extra calls.
- **Command-line tools inside the backend** import the "engine" files directly (no web request involved): `matchup_engine.forecast_game` is imported by `ncaa/management/commands/compute_sigma.py`, `compute_game_value.py`, `compute_sor.py`, `compute_wab.py`, `backtesting/.../backtest_early_season_prior.py`, `validation/management/commands/snapshot_predictions.py`. The crystal ball, trapezoid and config files are imported by backtest commands (`backtesting/management/commands/backtest_*.py`).
- **Server**: `docker-compose.yml` runs the `backend` service; its command starts gunicorn on port 7001 with `config.asgi:application`. `fabfile.py` only runs `manage.py` commands in that container.

**What the api folder calls**
- Database models in `ncaa/models` (and `nba`, etc.), via Django's database layer.
- `numpy` and `scipy` for maths; `anthropic` for AI insights (`game_insights.py`).
- The `nba/` app imports `api.game_insights`, `api.wp_reconstruction`, and `api.matchup_engine` (see `nba/game_detail_views.py` and `nba/matchup_engine.py`).

**Data in and out**
- In: the address, **query parameters** (the `?season=2026&top=50` part), sometimes a JSON body (scenario `POST`, login, jobs).
- Out: JSON. Default page size is 500 (`PAGE_SIZE` in `config/settings.py`). Login uses cookies/sessions (Session + Basic authentication).

### Endpoint cheat sheet (every route in `api/urls.py`)

All start with `/api/`. "Web" = a file under `web/src`; "Expo" = `apps/expo/src`.

| Address | View | Who calls it |
|---|---|---|
| `seasons/` | SeasonViewSet | web `lib/api.ts`, `lib/data.ts`; expo `lib/api.ts` |
| `conferences/` | ConferenceViewSet | web `lib/api.ts` (landscape and trapezoid pages) |
| `rankings/` | RankingsViewSet | web `lib/data.ts`; expo `lib/api.ts` |
| `teams/` | TeamViewSet | web `lib/api.ts` |
| `teams/<slug>/gamelog/` | TeamViewSet `gamelog` | web `lib/api.ts`; expo `lib/api.ts` |
| `teams/<slug>/stats, profile, games, season-stats` | TeamViewSet `@action`s | none today (kept on purpose) |
| `matchup/` | MatchupViewSet | web `lib/api.ts` |
| `games/` | GameViewSet | expo `lib/api.ts` (list) |
| `games/<id>/detail/` | ncaa_game_detail | web `lib/api.ts`; expo `lib/api.ts` |
| `jobs/` ... | DataProcessingJobViewSet | web `app/admin/page.tsx` only |
| `auth/csrf, login, logout, me` | auth_views | web `app/admin/page.tsx` only |
| `viz/landscape/`, `viz/trapezoid/`, `viz/crystal-ball/`, `viz/cinderella/`, `viz/bracket/`, `viz/stats/`, `viz/scatter/` | the matching `*_views` | web `lib/api.ts` + one page each under `app/ncaa/viz/` |
| `viz/nba-landscape/`, `viz/nba-crystal-ball/`, `viz/nba-luck-chart/` | NBA `*_views` | web `lib/api.ts` + one page each under `app/nba/viz/` |
| `pipeline-config/` | PipelineConfigView | web admin page |
| `team/<slug>/players/` | TeamRosterView | web `lib/api.ts` |
| `players/` | LeaguePlayersView | web `lib/api.ts` |
| `outlook/top/` | ProjectedTopTeamsView | web `lib/data.ts` |
| `outlook/scenario/` | ScenarioProjectionView | web `lib/api.ts` |
| `outlook/player-search/` | PlayerSearchView | web `lib/api.ts` |
| `outlook/placeholders/` | PlaceholderListView | web `lib/api.ts` |
| `outlook/<slug>/` | RosterOutlookView | web `lib/data.ts`, `lib/api.ts` |
| `market-value/players/`, `market-value/teams/<slug>/` | market_value_views | none today; tests only (`tests/test_market_value_api.py`) |
| `validation/summary, weekly, recent-games` | validation_views | web `lib/api.ts`, used by `app/validation/page.tsx` |

## 5. Words I'll need

- **API** (Application Programming Interface): a menu of addresses a program can visit to get data. Here, the website and phone app are the customers.
- **Backend / frontend**: backend = the behind-the-scenes server (this folder); frontend = what the user sees (`web/` website, `apps/expo/` phone app).
- **Endpoint / route**: one address on the menu, like `/api/rankings/`.
- **Request / response**: the question and the answer.
- **GET / POST**: GET = "give me data"; POST = "here's some data, do something with it".
- **Query parameter**: extra options after `?` in an address: `?season=2026`.
- **Slug**: a URL-friendly name like `duke` or `north-carolina`.
- **JSON**: a plain text format for data (`{"team": "Duke", "wins": 30}`) that every programming language can read.
- **Django**: the Python web framework the backend is built on. **Django REST Framework (DRF)**: an add-on that makes building JSON APIs easier.
- **View**: a piece of code that answers one kind of request. **ViewSet**: a view that handles several related requests (list, detail, extra actions). **`@action`**: adds an extra address to a ViewSet.
- **Router**: auto-generates the standard addresses for ViewSets.
- **Serializer**: converts database rows into JSON (and back).
- **Model**: a Python description of a database table. **Query / ORM**: asking the database for rows using Python instead of raw SQL.
- **Permission** (`AllowAny`, `IsAdminUser`, `IsAuthenticated`): who is allowed in. `AllowAny` = everyone; `IsAdminUser` = staff only.
- **Session / cookie / CSRF token**: how the server remembers you logged in; a CSRF token is a secret that proves a form really came from the site.
- **Subprocess / thread**: a separate program / a separate lane of work started in the background.
- **SSE (Server-Sent Events)**: a way for the server to keep a connection open and push live updates, such as job log lines.
- **Monte Carlo simulation**: run a random process thousands of times and count results to get probabilities.
- **Sigma**: a measure of "how spread out / uncertain" results are; used here in win-probability maths.
- **Backtest**: test a rule on past seasons to see if it would have worked.
- **Management command**: a script run with `python manage.py <name>`.
- **Tombstone comment**: a note left where code was deleted, explaining why.
- **Pure function**: maths-only code that takes inputs and returns outputs, with no database or web involved.

## 6. Say it to a friend

"Our app keeps all its basketball numbers in a big database on a server. The `api` folder is the service window in front of it. When the website or the phone app wants something, like this season's team rankings or a prediction for a game between two teams, it sends a request to a specific address. There's a menu file that says which address goes to which piece of code, and that piece of code grabs the numbers, does any maths, packages the answer in a simple text format, and sends it back. A few windows are staff-only, like the one that kicks off the big 'refresh all the data' job. Behind the windows are the formulas: a game predictor, a tournament simulator, and a champion checklist."

## 7. Teach-back

1. A person types `https://<site>/api/rankings/?season=2026`. Name the three files, in order, that the request passes through before data comes back.
2. Why does `outlook/top/` come *before* `outlook/<slug>/` in `urls.py`?
3. What is the difference between `views.py` and `serializers.py` (one sentence each)?
4. Which files in the folder are only for admins, and what stops a regular visitor from using them?
5. The AI game insights are saved on the game after the first request. What happens if Claude fails on that first request, and why is that the right behavior?

---

## Answers

1. `config/urls.py` (sends `api/...` into the api folder) -> `api/urls.py` (router entry `rankings` -> `RankingsViewSet`) -> `api/views.py` (`RankingsViewSet`), which uses `RankingsSerializer` from `api/serializers.py` to shape the rows into JSON.
2. Django checks the list top to bottom and takes the first match. `outlook/<slug>/` matches *any* word, so if it came first, `outlook/top/` would be treated as "the team named top". The comment next to those lines says exactly this.
3. `views.py` decides *what to fetch and which address does what*; `serializers.py` decides *how each database row looks as JSON* (fields, names, rounding).
4. `job_views.py` (the job manager) and `PipelineConfigView` in `views.py` both set `permission_classes = [IsAdminUser]`; `auth_views.py` is the login door. A visitor without a staff login gets a "not allowed" response.
5. The page shows the placeholder "Game insights temporarily unavailable." for that request, but nothing is saved. The next visit tries Claude again. If the failure were saved, that game would show the placeholder forever (this used to be a bug). `tests/test_game_insights.py` locks the behavior in.

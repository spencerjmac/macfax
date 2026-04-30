# Scenario API Contract

**Base URL:** `/api/scenarios/`

Sprint 3 adds a richer scenario layer on top of the existing `/api/outlook/scenario/` endpoint.
The new endpoints support manual player resolution (recruit rank → BPR prior, JUCO flags,
placeholder archetypes), in-memory Phase 2 (minutes allocation) and Phase 3 (fit scoring),
scenario persistence, and baseline comparison.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/scenarios/compute/` | Compute scenario in memory, return result (no DB write) |
| POST | `/api/scenarios/save/` | Persist a scenario snapshot |
| GET | `/api/scenarios/<id>/` | Retrieve a saved snapshot |
| GET | `/api/scenarios/?team_id=X` | List saved snapshots for a team |

---

## POST /api/scenarios/compute/

### Request

```json
{
  "team_id": 123,
  "season_year": 2026,
  "compare_to_baseline": false,
  "slots": [
    {
      "slot_type": "db_player",
      "projection_id": 4521
    },
    {
      "slot_type": "db_player",
      "projection_id": 4522
    },
    {
      "slot_type": "manual_player",
      "manual_spec": {
        "display_name": "Freshman PG",
        "position": "G",
        "recruitment_type": "newcomer",
        "national_rank": 18,
        "stars": 4,
        "slot_id": "uuid-abc-123"
      }
    },
    {
      "slot_type": "manual_player",
      "manual_spec": {
        "display_name": "Graduate Transfer Big",
        "position": "C",
        "recruitment_type": "transfer",
        "projected_obpr": 0.8,
        "projected_dbpr": 2.1,
        "intended_mpg": 28.0,
        "slot_id": "uuid-def-456"
      }
    }
  ]
}
```

#### Field descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `team_id` | int | ✓ | DB id of the Team |
| `season_year` | int | ✓ | Source season year (e.g. 2026 = 2025-26 season) |
| `compare_to_baseline` | bool | | If true, computes adj_em_delta vs. stored TeamSeasonProjection |
| `slots` | array | ✓ | 1–20 player slots |

#### ScenarioSlot fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slot_type` | `"db_player"` or `"manual_player"` | ✓ | |
| `projection_id` | int | if db_player | PlayerSeasonProjection pk |
| `manual_spec` | object | if manual_player | See ManualPlayerSpec below |

#### ManualPlayerSpec fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `display_name` | string | ✓ | Display name for UI |
| `position` | string | ✓ | ESPN position: `G`, `F`, `C`, `PG`, `SG`, `SF`, `PF` |
| `recruitment_type` | string | ✓ | `returner`, `transfer`, or `newcomer` |
| `projected_obpr` | float | | **Priority 1:** direct BPR override (offensive) |
| `projected_dbpr` | float | | **Priority 1:** direct BPR override (defensive) |
| `national_rank` | int | | **Priority 2:** national recruiting rank (newcomers/JUCO only) |
| `stars` | int 1–5 | | **Priority 2:** star rating fallback when rank is null |
| `composite_score` | float | | 247Sports-style composite (informational only) |
| `placeholder_key` | string | | **Priority 3:** PlaceholderArchetype key (e.g. `power_starter_g`) |
| `conf_group` | string | | **Priority 4:** `power`, `high_mid`, `mid_major`, `national` |
| `quality_tier` | string | | **Priority 4:** `elite`, `all_conference`, `starter`, `rotation`, `bench` |
| `intended_mpg` | float 0–40 | | Soft minutes constraint applied after Phase 2 allocation |
| `is_juco` | bool | | JUCO flag: lower uncertainty, slight BPR boost vs same-rank HS |
| `slot_id` | string | | Client-generated UUID echoed in response |

**Resolution priority** (highest wins):
1. `projected_obpr + projected_dbpr` both set → use directly
2. `national_rank` or `stars` set AND (`recruitment_type == "newcomer"` OR `is_juco == true`) → rank lookup via NEWCOMER_RANK_PRIORS
3. `placeholder_key` found in DB → use PlaceholderArchetype values
4. Auto-match by `conf_group + role_bucket(position) + quality_tier` in PlaceholderArchetype table, else flat type defaults

### Response (200 OK)

```json
{
  "team_id": 123,
  "season_year": 2026,
  "projected_season_year": 2027,
  "projected_adj_o": 114.2,
  "projected_adj_d": 104.8,
  "projected_adj_em": 9.4,
  "projected_adj_em_low": 5.1,
  "projected_adj_em_high": 13.7,
  "projected_national_rank": 35,
  "national_rank_range_low": 20,
  "national_rank_range_high": 50,
  "team_projection_uncertainty": 0.52,
  "continuity_score": 64.0,
  "transfer_dependence_score": 22.0,
  "offensive_fit_score": 58.3,
  "defensive_fit_score": 55.1,
  "overall_fit_score": 56.7,
  "off_subcomponents": {
    "creation_fit": 62.1,
    "shooting_fit": 54.0,
    "ball_security_fit": 58.0,
    "finishing_fit": 51.0,
    "pressure_fit": 50.0,
    "off_rebounding_fit": 49.5,
    "role_balance_off_fit": 60.0
  },
  "def_subcomponents": { "...": "..." },
  "top_off_strengths": ["creation_fit", "role_balance_off_fit"],
  "top_off_weaknesses": ["off_rebounding_fit"],
  "top_def_strengths": [],
  "top_def_weaknesses": [],
  "structural_penalties": {
    "offense": ["Non-Shooting Big"],
    "defense": []
  },
  "n_manual_players": 2,
  "n_db_players": 2,
  "has_mpg_overrides": true,
  "computed_at": "2026-04-29T12:34:56+00:00",
  "baseline_adj_em": null,
  "adj_em_delta": null,
  "players": [
    {
      "player_id": 4521,
      "display_name": "Returning Star",
      "slot_id": "4521",
      "is_manual": false,
      "source_tier": "db",
      "display_label": "",
      "role_bucket": "G",
      "rotation_rank": 1,
      "minutes_share": 1.05,
      "mpg": 42.0,
      "is_overridden": false,
      "projected_obpr": 3.8,
      "projected_dbpr": 0.9,
      "projected_bpr": 4.7,
      "projection_uncertainty": 0.38,
      "recruitment_type": "returner",
      "resolution_method": "db",
      "national_rank": null,
      "stars": null,
      "is_juco": false,
      "archetypes": ["primary_creator", "spacer"]
    },
    {
      "player_id": -1,
      "display_name": "Freshman PG",
      "slot_id": "uuid-abc-123",
      "is_manual": true,
      "source_tier": "rank_high",
      "display_label": "Top-100",
      "role_bucket": "G",
      "rotation_rank": 3,
      "minutes_share": 0.62,
      "mpg": 24.8,
      "is_overridden": false,
      "projected_obpr": 0.4,
      "projected_dbpr": 0.1,
      "projected_bpr": 0.5,
      "projection_uncertainty": 0.76,
      "recruitment_type": "newcomer",
      "resolution_method": "rank_lookup",
      "national_rank": 18,
      "stars": 4,
      "is_juco": false,
      "archetypes": []
    },
    {
      "player_id": -2,
      "display_name": "Graduate Transfer Big",
      "slot_id": "uuid-def-456",
      "is_manual": true,
      "source_tier": "bpr_override",
      "display_label": "Custom BPR",
      "role_bucket": "Big",
      "rotation_rank": 2,
      "minutes_share": 0.70,
      "mpg": 28.0,
      "is_overridden": true,
      "projected_obpr": 0.8,
      "projected_dbpr": 2.1,
      "projected_bpr": 2.9,
      "projection_uncertainty": 0.60,
      "recruitment_type": "transfer",
      "resolution_method": "bpr_override",
      "national_rank": null,
      "stars": null,
      "is_juco": false,
      "archetypes": ["rim_protector"]
    }
  ]
}
```

### Error responses

| Code | Condition |
|------|-----------|
| 400 | Validation failure (missing required fields, invalid types, unknown team/season) |
| 400 | Fewer than 3 players resolve successfully |
| 400 | Unknown `projection_id` |
| 500 | Unexpected internal error |

---

## source_tier values

| `source_tier` | `display_label` | When set |
|---------------|-----------------|----------|
| `db` | `""` (no badge) | DB player from PlayerSeasonProjection |
| `bpr_override` | `"Custom BPR"` | Manual player with explicit projected_obpr/dbpr |
| `rank_elite` | `"5★ / Top-30"` | national_rank ≤ 30 |
| `rank_high` | `"Top-100"` | national_rank 31–100 |
| `rank_mid` | `"Top-200"` | national_rank 101–200 |
| `rank_low` | `"Unranked"` | national_rank > 200 |
| `stars_fallback` | `"{n}★ Recruit"` | rank=null, stars set |
| `juco` | `"JUCO Transfer"` | is_juco=true |
| `placeholder` | archetype display_name | placeholder_key matched in DB |
| `default` | `"Type Default"` | No other priority matched |

---

## is_manual flag behavior

- `is_manual: true` — player was specified in `manual_spec`. Has a non-empty `display_label` (except for `bpr_override` which shows "Custom BPR"). `player_id` is a negative synthetic integer.
- `is_manual: false` — player loaded from DB via `projection_id`. `display_label` is `""`. `player_id` is the real DB player_id.

Manual players with `player_id < 0` must never be written to the DB by the client.

---

## intended_mpg override behavior

When a manual player has `intended_mpg` set (e.g. 28.0):
- Phase 2 (minutes allocation) runs normally for all players first.
- After allocation, the overridden player's `minutes_share` is pinned to `intended_mpg / 40` (clipped to [0.025, 0.875]).
- Remaining non-pinned players are re-scaled proportionally to maintain a team total of 5.00 shares (200 player-minutes).
- If multiple players have `intended_mpg`, all are pinned simultaneously, then the remainder distributes.
- `is_overridden: true` appears in the response for the affected player.

---

## archetype tags reference

Populated by `tag_archetypes()` after Phase 2 (role_bucket from minutes allocation is required).

**Offensive tags:**
| Tag | Condition |
|-----|-----------|
| `spacer` | High 3-point attempt volume |
| `shooter` | Above-average eFG% |
| `primary_creator` | High assists per game |
| `secondary_creator` | Moderate assists |
| `off_rebounder` | High offensive rebounds |
| `pressure_driver` | Draws many fouls |
| `ball_stopper` | High TOV + low creation |
| `non_shooting_big` | Big bucket + low 3PA |

**Defensive tags:**
| Tag | Condition |
|-----|-----------|
| `rim_protector` | High blocks per game |
| `disruptor` | High steals per game |
| `foul_prone` | High personal fouls |
| `switchable_wing` | Wing bucket + high steals |
| `weak_defender` | projected_dbpr well below average |

Manual players with no observed box stats receive position-average defaults;
archetypes may fire if those defaults cross the thresholds (e.g. a C position
will get rim protection credit if BIG_BLK_THRESHOLD is met).

---

## compare_to_baseline

When `"compare_to_baseline": true`:
- Loads the existing `TeamSeasonProjection` for `team_id` + `season_year`.
- Returns `"baseline_adj_em": <float>` and `"adj_em_delta": <scenario_em - baseline_em>`.
- If no baseline projection exists: both fields are `null`.

---

## POST /api/scenarios/save/

Persists a previously computed scenario for later retrieval.

### Request

```json
{
  "name": "My Duke 2027 Scenario",
  "scenario_request": { "...same as compute request..." },
  "scenario_result": { "...result from compute..." }
}
```

### Response (201 Created)

```json
{
  "id": 42,
  "created_at": "2026-04-29T12:35:00+00:00"
}
```

---

## GET /api/scenarios/<id>/

Returns saved snapshot including full `scenario_input` and `scenario_result` JSON.

---

## GET /api/scenarios/?team_id=X

Returns list of saved snapshots for a team. Max 50 results, ordered by `updated_at` desc.
Does NOT include `scenario_result` in list view (use detail endpoint for full data).

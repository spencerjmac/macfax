# Four Factor Index Implementation Summary

## Overview
Successfully implemented the Four Factor Index (4FI) metric across the full stack of the CBB Analytics Dashboard.

## Formula Implementation

### Weighted Z-Score (Source of Truth)
```
FourFactor_WZ = (0.4069 × eFG_Margin_Z) + 
                (0.4069 × TOV_Edge_Z) + 
                (0.1432 × Rebounding_Edge_Z) + 
                (0.0428 × FTR_Margin_Z)
```
**Note:** NO division by 4 (weights sum to ~1.0)

### 0-100 Scale Conversion
```
FourFactor_100 = MIN(100, MAX(0, 50 + SCALE × FourFactor_WZ))
```
- **SCALE = 20** (configurable constant in `backend/core/constants.py`)
- Values are clamped to [0, 100] range

## Backend Changes

### 1. Database Schema (`backend/core/models.py`)
Added to `TeamSeasonStats` model:
- `efg_margin_z` - eFG Margin Z-score
- `tov_edge_z` - Turnover Edge Z-score  
- `reb_edge_z` - Rebounding Edge Z-score
- `ftr_margin_z` - FTR Margin Z-score
- `four_factor_index_wz` - Weighted Z-score (for debugging)
- `four_factor_index_100` - Final 0-100 metric (indexed)
- `rank_four_factor_index_100` - National ranking

### 2. Configuration (`backend/core/constants.py`)
Created new constants file:
- `FOUR_FACTOR_SCALE = 20` (tunable spread parameter)
- `FOUR_FACTOR_WEIGHTS` (Dean Oliver's weights)

### 3. Data Ingestion (`backend/core/management/commands/ingest_data.py`)
Added `_compute_four_factor_index()` method:
1. Calculates season-wide statistics (mean, std) for each margin
2. Computes Z-scores for all teams
3. Calculates weighted Z-score using Oliver's weights
4. Converts to 0-100 scale with clamping
5. Assigns national rankings (1 = best)

### 4. API Serialization (`backend/api/serializers.py`)
Updated serializers to expose 4FI fields:
- `RankingsSerializer` - includes `four_factor_index_100`, `rank_four_factor_index_100`
- `TeamSeasonStatsSerializer` - includes all Z-scores and composite metrics

### 5. API Views (`backend/api/views.py`)
Added `four_factor_index_100` and `rank_four_factor_index_100` to sortable fields in rankings endpoint

### 6. Database Migration
Created and applied `0003_teamseasonstats_efg_margin_z_and_more.py`

### 7. Unit Tests (`backend/core/tests/test_four_factor_index.py`)
Comprehensive test suite covering:
- Weighted Z formula validation (NO /4)
- 0-100 scale conversion
- Clamping behavior
- Real data verification (Houston example)
- Weight sum validation
- **All 6 tests passing ✓**

## Frontend Changes

### 1. TypeScript Types (`frontend/src/types/index.ts`)
Added to interfaces:
- `TeamSeasonStats` - all Z-scores, WZ, 4FI, rank
- `RankingsRow` - `four_factor_index_100`, `rank_four_factor_index_100`

### 2. Rankings Page (`frontend/src/app/rankings/page.tsx`)
- Added sortable "4FI" column
- Displays value with 1 decimal place
- Shows "—" for null values
- Tooltip: "Four Factor Index (0–100). Built from weighted Z-scores of eFG margin, turnover edge, rebounding edge, and FTR margin."
- Styled in orange (`text-orange-600`)

### 3. Team Profile Page (`frontend/src/app/team/[slug]/page.tsx`)
Added new section in Overview tab:
- Large display card with orange theme
- Shows 4FI value (0-100) with 1 decimal
- Shows national rank
- Shows weighted Z-score (debugging)
- Grid display of all 4 component Z-scores
- Clean, responsive layout

## Data Verification

### Top 10 Teams by Four Factor Index
```
 1. Houston       92.0  (WZ:  2.10)
 2. Iowa St.      89.5  (WZ:  1.98)
 3. High Point    86.1  (WZ:  1.80)
 4. McNeese       84.9  (WZ:  1.75)
 5. Gonzaga       83.6  (WZ:  1.68)
 6. Georgia       81.8  (WZ:  1.59)
 7. Utah St.      81.2  (WZ:  1.56)
 8. Iowa          79.7  (WZ:  1.48)
 9. Michigan      79.5  (WZ:  1.47)
10. Duke          78.9  (WZ:  1.45)
```

### Houston Deep Dive
- **4FI (0-100):** 92.0
- **Rank:** #1
- **Weighted Z:** 2.100
- **Component Z-scores:**
  - eFG Margin Z: 1.322
  - TOV Edge Z: 3.416 (elite turnover forcing)
  - Reb Edge Z: 1.766
  - FTR Margin Z: -1.887 (weakness)

## Key Features

✅ **Configurable SCALE** - Easily tune distribution spread via `FOUR_FACTOR_SCALE` constant  
✅ **Null handling** - Missing Z-scores → null output (no silent zeros)  
✅ **National rankings** - Computed and stored for efficient querying  
✅ **API exposure** - Full serialization in both rankings and detail endpoints  
✅ **Sortable UI** - Works seamlessly with existing table sorting  
✅ **Responsive design** - Matches existing FiveThirtyEight aesthetic  
✅ **Unit tested** - 6 tests validating formulas and edge cases  
✅ **Data verified** - 365 teams processed, sensible rankings

## Usage

### Backend
```bash
# Re-compute 4FI after data changes
python manage.py ingest_data --season 2026 --force

# Run tests
python manage.py test core.tests.test_four_factor_index
```

### API Access
```
GET /api/rankings?sort=four_factor_index_100&dir=desc
GET /api/teams/{slug}/profile
```

### Tuning SCALE
Edit `backend/core/constants.py`:
```python
FOUR_FACTOR_SCALE = 20  # Default (good separation)
# Try 15 for more compression, 25 for more spread
```

Then re-run ingestion to recompute all values.

## Files Modified/Created

### Backend
- ✅ `backend/core/models.py` - Added 7 new fields
- ✅ `backend/core/constants.py` - NEW file with config constants
- ✅ `backend/core/management/commands/ingest_data.py` - Added Z-score computation
- ✅ `backend/api/serializers.py` - Exposed 4FI in serializers
- ✅ `backend/api/views.py` - Made 4FI sortable
- ✅ `backend/core/migrations/0003_teamseasonstats_efg_margin_z_and_more.py` - NEW migration
- ✅ `backend/core/tests/test_four_factor_index.py` - NEW test file

### Frontend
- ✅ `frontend/src/types/index.ts` - Added 4FI types
- ✅ `frontend/src/app/rankings/page.tsx` - Added 4FI column
- ✅ `frontend/src/app/team/[slug]/page.tsx` - Added 4FI overview section

## Next Steps (Optional Enhancements)

1. **Glossary Entry** - Add 4FI explanation to glossary page
2. **Historical Analysis** - Compare 4FI vs tournament success
3. **Visualization** - Add distribution chart showing 4FI spread
4. **Mobile Optimization** - May need horizontal scroll adjustments for rankings table
5. **Performance** - Consider materialized views if rankings queries slow down

## Notes

- The 4FI metric successfully identifies elite teams (Houston #1) with strong four-factor profiles
- Component Z-scores provide valuable insight into team strengths/weaknesses
- The 20-scale parameter provides good separation without excessive clustering
- All formulas match specification exactly (NO /4 in weighted sum)

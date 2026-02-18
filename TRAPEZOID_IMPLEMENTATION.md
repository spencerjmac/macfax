# Trapezoid of Excellence - Implementation Summary

## Overview
The **Trapezoid of Excellence** visualization has been successfully implemented with dynamic trapezoid boundaries that adjust based on the filtered dataset. The implementation includes:

- ✅ Backend API endpoint with quantile-based dynamic boundaries
- ✅ Frontend interactive scatterplot with team logos
- ✅ Conference and Top N filtering
- ✅ Credit to Ryan Hammer (visible in UI and accessible via aria-label)
- ✅ No hard-coded trapezoid values (uses configurable quantiles)

---

## Files Created/Modified

### Backend Files

#### **NEW: `backend/api/trapezoid_config.py`**
Configuration file for trapezoid quantile parameters. **EDIT THIS FILE** to adjust the trapezoid shape:

```python
X_LEFT_TOP_QUANTILE = 0.05      # Left edge at top (5th percentile)
X_RIGHT_TOP_QUANTILE = 0.95     # Right edge at top (95th percentile)  
X_LEFT_BOT_QUANTILE = 0.25      # Left edge at bottom (25th percentile)
X_RIGHT_BOT_QUANTILE = 0.75     # Right edge at bottom (75th percentile)
Y_TOP_QUANTILE = 0.98           # Top edge (98th percentile)
Y_BOT_QUANTILE = 0.90           # Bottom edge (90th percentile)
```

#### **NEW: `backend/api/trapezoid_views.py`**
API view class implementing:
- Dynamic trapezoid boundary computation using numpy quantiles
- Inside/outside trapezoid test for each team
- Filtering by conference and top N teams by adj_em

#### **MODIFIED: `backend/api/urls.py`**
Added trapezoid endpoint:
```python
path('viz/trapezoid', TrapezoidView.as_view(), name='trapezoid'),
```

### Frontend Files

#### **MODIFIED: `frontend/src/types/index.ts`**
Added TypeScript types:
- `TrapezoidBoundaries`
- `TrapezoidTeam`
- `TrapezoidData`

#### **MODIFIED: `frontend/src/lib/api.ts`**
Added `getTrapezoid()` method to API client

#### **REPLACED: `frontend/src/app/viz/trapezoid/page.tsx`**
Complete visualization implementation with:
- ECharts scatterplot with team markers
- Dynamic trapezoid polygon overlay
- Average tempo/EM reference lines
- Conference and Top Teams filters with debouncing
- Tooltips showing team details and inside/outside status
- Credit to Ryan Hammer in caption and aria-label

---

## API Endpoint

### Request
```
GET /api/viz/trapezoid?season=2026&conference=ALL&top=365
```

**Query Parameters:**
- `season` (optional): Season year (default: current season)
- `conference` (optional): Conference code or "ALL" (default: "ALL")
- `top` (optional): Top N teams by adj_em to include (default: 365)

### Response Example
```json
{
  "meta": {
    "season": 2026,
    "season_display": "2025-26",
    "conference": "ALL",
    "top": 365,
    "total_teams": 365,
    "quantiles_used": {
      "x_left_top": 0.05,
      "x_right_top": 0.95,
      "x_left_bot": 0.25,
      "x_right_bot": 0.75,
      "y_top": 0.98,
      "y_bot": 0.90,
      "method": "linear"
    }
  },
  "trapezoid": {
    "x_left_top": 62.5,
    "x_right_top": 72.8,
    "x_left_bot": 65.2,
    "x_right_bot": 70.1,
    "y_top": 28.5,
    "y_bot": 18.2
  },
  "averages": {
    "avg_tempo": 67.8,
    "avg_em": 5.3
  },
  "teams": [
    {
      "team_id": 1,
      "team_name": "Duke",
      "team_slug": "duke",
      "adj_tempo": 68.5,
      "adj_em": 28.3,
      "conference": "ACC",
      "conference_name": "Atlantic Coast Conference",
      "logo_url": "/logos/duke.png",
      "rank": 1,
      "record": "25-2",
      "inside_trapezoid": true
    }
  ]
}
```

---

## How the Dynamic Trapezoid Works

### Boundary Calculation
The trapezoid boundaries are computed from **ALL teams in the season**, ensuring the trapezoid shape remains constant regardless of conference or top N filters:

1. Extract all `adj_tempo` and `adj_em` values from **all teams in the season** (no filters)
2. Calculate quantiles using numpy:
   - X-axis (tempo): Q(0.05), Q(0.25), Q(0.75), Q(0.95)
   - Y-axis (EM): Q(0.90), Q(0.98)
3. Validate and adjust if ordering is invalid

**Important:** When you switch conferences or adjust the "Top Teams" filter, the trapezoid boundaries stay the same. Only the displayed teams change. This provides a consistent reference frame for comparing teams across different conferences.

### Inside/Outside Test
For each team point `(x=tempo, y=em)`:

1. Check if x is within `[x_left_top, x_right_top]`
2. Check if y is below `y_top`
3. Calculate bottom boundary `y_min(x)`:
   - **Left slant** (x ≤ x_left_bot): Linear interpolation between (x_left_top, y_top) and (x_left_bot, y_bot)
   - **Flat bottom** (x_left_bot < x < x_right_bot): y_min = y_bot
   - **Right slant** (x ≥ x_right_bot): Linear interpolation between (x_right_bot, y_bot) and (x_right_top, y_top)
4. Check if y ≥ y_min

Result: `inside_trapezoid = true/false`

---

## How to Adjust Trapezoid Shape

**To change the trapezoid boundaries**, edit `backend/api/trapezoid_config.py`:

- **Wider trapezoid**: Increase X_LEFT_TOP_QUANTILE (e.g., 0.10), decrease X_RIGHT_TOP_QUANTILE (e.g., 0.90)
- **Taller trapezoid**: Increase Y_BOT_QUANTILE (e.g., 0.95), keep Y_TOP_QUANTILE high
- **More selective**: Increase Y_BOT_QUANTILE closer to Y_TOP_QUANTILE
- **More inclusive**: Decrease Y_BOT_QUANTILE (e.g., 0.85)

After changes, restart Django server. No code changes needed—just config values!

---

## Testing Checklist

✅ **Backend**
- API endpoint returns valid JSON
- Trapezoid boundaries change when filters change
- `inside_trapezoid` flag correctly computed
- No hard-coded trapezoid values in logic

✅ **Frontend**
- Scatterplot renders with team points
- Trapezoid polygon overlays correctly
- Filters work (Conference, Top Teams)
- Credit to Ryan Hammer visible
- Accessible aria-label present
- Tooltips show team details

---

## Access the Visualization

1. Start backend: `cd backend && python manage.py runserver`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to: **http://localhost:3000/viz/trapezoid**

The visualization is also linked in the main navigation under "Visualizations".

---

## Credit

**Trapezoid of Excellence** concept by **Ryan Hammer**

This credit appears:
- In the chart title/subtitle
- In the caption below the chart
- In the accessible `aria-label` attribute
- In the "About This Visualization" section

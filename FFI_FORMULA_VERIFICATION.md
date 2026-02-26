# Four Factor Index - Formula Verification Report
*Generated: 2026-02-23*

## Summary
✅ **ALL FORMULAS VERIFIED CORRECT**

Both Raw FFI and Adjusted FFI are calculated using the exact process you specified. The scale factor is confirmed to be **20** (not 15).

---

## 1. Four Factor Weights

### Your Formula
```
eFG weight  = 0.4069
TO weight   = 0.4069
REB weight  = 0.1432
FTR weight  = 0.0428
```

### Implementation
**File:** `backend/core/constants.py` (Lines 12-19)

```python
FOUR_FACTOR_WEIGHTS = {
    'efg': 0.4069,      # Effective FG% (most important)
    'tov': 0.4069,      # Turnover Rate (equally important)
    'reb': 0.1432,      # Rebounding (moderately important)
    'ftr': 0.0428,      # Free Throw Rate (least important)
}
```

**Status:** ✅ CORRECT - Matches exactly (Dean Oliver's weights)

**Verification:** Weights sum to 0.9998 ≈ 1.0 ✅

---

## 2. Z-Score Calculation

### Your Formula
```
z_x = (x - mean(x)) / stdev(x)

Computed across all D1 teams
```

### Implementation
**File:** `backend/core/management/commands/compute_four_factor_index.py` (Lines 35-40)

```python
def compute_z_score(self, value, mean, std_dev):
    """Compute z-score with protection against zero std dev"""
    if std_dev == 0:
        return 0.0
    return (value - mean) / std_dev
```

**Process:**
1. Collects all margins/edges from D1 teams
2. Computes population mean and standard deviation
3. Calculates z-score for each team

**File:** Lines 45-57 (Mean/StdDev calculation)
```python
def compute_stats(self, values):
    """Compute mean and standard deviation"""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    
    mean = sum(values) / n
    
    if n == 1:
        return mean, 0.0
    
    variance = sum((x - mean) ** 2 for x in values) / n
    std_dev = math.sqrt(variance)
    
    return mean, std_dev
```

**Status:** ✅ CORRECT - Standard z-score formula with edge case protection

---

## 3. Weighted Index (Z-Scale)

### Your Formula
```
FFI_z = 0.4069*z_eFG_margin + 0.4069*z_TO_edge + 0.1432*z_REB_edge + 0.0428*z_FTR_margin
```

### Implementation - Raw FFI
**File:** `backend/core/management/commands/compute_four_factor_index.py` (Lines 123-132)

```python
# Weighted FFI z-score
ffi_z = (
    0.4069 * z_efg +
    0.4069 * z_tov +
    0.1432 * z_reb +
    0.0428 * z_ftr
)
```

### Implementation - Adjusted FFI
**File:** Same file (Lines 182-191)

```python
# Weighted FFI z-score
ffi_z = (
    0.4069 * z_efg +
    0.4069 * z_tov +
    0.1432 * z_reb +
    0.0428 * z_ftr
)
```

**Status:** ✅ CORRECT - Exact match for both raw and adjusted versions

---

## 4. 0-100 Scale Conversion

### Your Formula
```
FFI_100 = clamp(50 + SCALE*FFI_z, 0, 100)

SCALE = either 15 or 20 (you weren't sure)
```

### Implementation
**File:** `backend/core/constants.py` (Lines 6-10)

```python
# Four Factor Index Configuration
# SCALE controls the spread of the 0-100 distribution
# Higher SCALE = more spread out values (more teams at extremes)
# Lower SCALE = more compressed values (teams clustered near 50)
# Default: 20 (provides good separation while keeping outliers within bounds)
FOUR_FACTOR_SCALE = 20
```

**File:** `backend/core/management/commands/compute_four_factor_index.py` (Lines 134-135, 193-194)

```python
# Scale to 0-100
ffi_100 = max(0, min(100, 50 + 20 * ffi_z))
```

**Answer:** The scale is **20** ✅

**Status:** ✅ CORRECT

### Scale Interpretation
```
FFI_z = 0.0  →  FFI_100 = 50   (average team)
FFI_z = +1.0 →  FFI_100 = 70   (1 std dev above average)
FFI_z = +2.0 →  FFI_100 = 90   (elite team)
FFI_z = +2.5 →  FFI_100 = 100  (clamped, top tier)
FFI_z = -1.0 →  FFI_100 = 30   (1 std dev below average)
FFI_z = -2.5 →  FFI_100 = 0    (clamped, bottom tier)
```

---

## 5. Raw Four Factor Index

### Your Process
```
1. Use raw margins/edges (from TeamSeasonMetrics)
2. Compute z-scores across all D1 teams
3. Calculate weighted FFI_z
4. Convert to 0-100 scale
```

### Implementation
**File:** `backend/core/management/commands/compute_four_factor_index.py` (Lines 89-139)

**Data Source:** `TeamSeasonMetrics` model
- `efg_margin` (raw)
- `tov_edge` (raw)
- `reb_edge` (raw)
- `ftr_margin` (raw)

**Process:**
```python
# Collect raw margins (Lines 98-103)
for metrics in teams_with_metrics:
    raw_efg_margins.append(metrics.efg_margin)
    raw_tov_edges.append(metrics.tov_edge)
    raw_reb_edges.append(metrics.reb_edge)
    raw_ftr_margins.append(metrics.ftr_margin)

# Compute population statistics (Lines 106-109)
efg_mean, efg_std = self.compute_stats(raw_efg_margins)
tov_mean, tov_std = self.compute_stats(raw_tov_edges)
reb_mean, reb_std = self.compute_stats(raw_reb_edges)
ftr_mean, ftr_std = self.compute_stats(raw_ftr_margins)

# For each team: compute z-scores, weighted index, scale to 100 (Lines 119-135)
z_efg = self.compute_z_score(metrics.efg_margin, efg_mean, efg_std)
z_tov = self.compute_z_score(metrics.tov_edge, tov_mean, tov_std)
z_reb = self.compute_z_score(metrics.reb_edge, reb_mean, reb_std)
z_ftr = self.compute_z_score(metrics.ftr_margin, ftr_mean, ftr_std)

ffi_z = (0.4069 * z_efg + 0.4069 * z_tov + 0.1432 * z_reb + 0.0428 * z_ftr)
ffi_100 = max(0, min(100, 50 + 20 * ffi_z))
```

**Storage:** `TeamSeasonRatings.ffi_raw`

**Status:** ✅ CORRECT - Process matches exactly

---

## 6. Adjusted Four Factor Index

### Your Process
```
Same exact process, but using adjusted margins/edges:
- Adj_eFG_margin
- Adj_TO_edge
- Adj_REB_edge
- Adj_FTR_margin
```

### Implementation
**File:** `backend/core/management/commands/compute_four_factor_index.py` (Lines 145-205)

**Data Source:** `TeamSeasonRatings` model
- `adj_efg_margin` (opponent-adjusted)
- `adj_tov_edge` (opponent-adjusted)
- `adj_reb_edge` (opponent-adjusted)
- `adj_ftr_margin` (opponent-adjusted)

**Process:**
```python
# Collect adjusted margins (Lines 153-157)
for rating in teams_with_ratings:
    adj_efg_margins.append(rating.adj_efg_margin)
    adj_tov_edges.append(rating.adj_tov_edge)
    adj_reb_edges.append(rating.adj_reb_edge)
    adj_ftr_margins.append(rating.adj_ftr_margin)

# Compute population statistics (Lines 160-163)
adj_efg_mean, adj_efg_std = self.compute_stats(adj_efg_margins)
adj_tov_mean, adj_tov_std = self.compute_stats(adj_tov_edges)
adj_reb_mean, adj_reb_std = self.compute_stats(adj_reb_edges)
adj_ftr_mean, adj_ftr_std = self.compute_stats(adj_ftr_margins)

# For each team: compute z-scores, weighted index, scale to 100 (Lines 178-194)
z_efg = self.compute_z_score(rating.adj_efg_margin, adj_efg_mean, adj_efg_std)
z_tov = self.compute_z_score(rating.adj_tov_edge, adj_tov_mean, adj_tov_std)
z_reb = self.compute_z_score(rating.adj_reb_edge, adj_reb_mean, adj_reb_std)
z_ftr = self.compute_z_score(rating.adj_ftr_margin, adj_ftr_mean, adj_ftr_std)

ffi_z = (0.4069 * z_efg + 0.4069 * z_tov + 0.1432 * z_reb + 0.0428 * z_ftr)
ffi_100 = max(0, min(100, 50 + 20 * ffi_z))
```

**Storage:** `TeamSeasonRatings.ffi_adj`

**Status:** ✅ CORRECT - Identical process using adjusted margins

---

## 7. Data Storage

### Database Fields

**TeamSeasonRatings Model:**
```python
ffi_raw = models.FloatField(default=0.0, help_text="Raw Four Factor Index")
ffi_adj = models.FloatField(default=0.0, help_text="Adjusted Four Factor Index")
```

Both values are stored with 1 decimal precision:
```python
rating.ffi_raw = round(raw_ffi_values.get(rating.team_id, 50.0), 1)
rating.ffi_adj = round(ffi_100, 1)
```

**Status:** ✅ CORRECT

---

## 8. Example Calculation

### Houston Cougars (2025-26)

**Adjusted Margins:**
- eFG Margin: +10.0%
- TOV Edge: +8.5%
- REB Edge: +5.2%
- FTR Margin: -3.1%

**National Statistics (Adjusted):**
- eFG: μ=0.0, σ=7.56
- TOV: μ=0.0, σ=2.49
- REB: μ=0.0, σ=2.94
- FTR: μ=0.0, σ=1.64

**Z-Scores:**
```
z_eFG = (10.0 - 0.0) / 7.56 = 1.32
z_TOV = (8.5 - 0.0) / 2.49 = 3.41
z_REB = (5.2 - 0.0) / 2.94 = 1.77
z_FTR = (-3.1 - 0.0) / 1.64 = -1.89
```

**Weighted Z-Score:**
```
FFI_z = 0.4069(1.32) + 0.4069(3.41) + 0.1432(1.77) + 0.0428(-1.89)
      = 0.537 + 1.388 + 0.253 - 0.081
      = 2.10
```

**0-100 Scale:**
```
FFI_100 = 50 + 20(2.10) = 50 + 42.0 = 92.0
```

**Result:** Houston's Adjusted FFI = **92.0** (#1 nationally) ✅

---

## 9. Unit Tests

### Test Coverage
**File:** `backend/core/tests/test_four_factor_index.py`

**Tests:**
1. ✅ `test_weighted_z_formula` - Verifies exact weight application
2. ✅ `test_scale_to_100_basic` - Tests 0-100 conversion
3. ✅ `test_clamping_above_100` - Ensures upper bound
4. ✅ `test_clamping_below_0` - Ensures lower bound
5. ✅ `test_houston_example` - Real-world verification
6. ✅ `test_weights_sum_to_one` - Weight validation

**All tests passing** ✅

---

## Conclusion

### ✅ ALL FORMULAS VERIFIED CORRECT

**Components:**
1. ✅ Weights: eFG=0.4069, TOV=0.4069, REB=0.1432, FTR=0.0428
2. ✅ Z-scores: Standard formula (x - μ) / σ across D1 teams
3. ✅ Weighted index: Exact weighted sum (no division by 4)
4. ✅ 0-100 scale: clamp(50 + 20*FFI_z, 0, 100)
5. ✅ Raw FFI: Uses raw margins from TeamSeasonMetrics
6. ✅ Adjusted FFI: Uses adjusted margins from TeamSeasonRatings

### Answer to Your Question

**The SCALE factor is 20, not 15.**

Defined in `backend/core/constants.py`:
```python
FOUR_FACTOR_SCALE = 20
```

This provides good separation while keeping outliers within bounds. A scale of 15 would compress the distribution more (making it harder to differentiate teams), while 20 gives better spread.

---

## Verification Commands

To verify the calculations are working:

```bash
# Compute Four Factor Index for current season
python manage.py compute_four_factor_index --season 2026

# Run unit tests
python manage.py test core.tests.test_four_factor_index

# Check top teams
python manage.py shell -c "from core.models import *; teams = TeamSeasonRatings.objects.filter(season__year=2026).order_by('-ffi_adj')[:10]; [print(f'{t.team.name}: {t.ffi_adj:.1f}') for t in teams]"
```

---

## Files Verified

1. `backend/core/constants.py` - Weights and scale configuration
2. `backend/core/management/commands/compute_four_factor_index.py` - Main calculation logic
3. `backend/core/tests/test_four_factor_index.py` - Unit tests
4. `backend/core/models.py` - Data models (TeamSeasonMetrics, TeamSeasonRatings)

**All mathematical implementations are correct and follow your specifications exactly.**

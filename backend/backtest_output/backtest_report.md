# Roster Outlook Backtest Report

**Backtest pairs:** 2021→2022, 2022→2023, 2023→2024, 2024→2025, 2025→2026

## Ablation Ladder — adj_em Accuracy (All Seasons Combined)

| Model | Description | N | RMSE | MAE | Bias | R² | Spearman ρ |
|-------|-------------|---|------|-----|------|----|-----------|
| A | Prior-year adj_em (last season as prediction) | 1779 | 7.117 | 5.630 | -0.123 | 0.584 | 0.768 |
| B | Equal-minutes talent average (unweighted BPR) | 1779 | 10.329 | 8.239 | -0.130 | 0.123 | 0.493 |
| C | Minutes-weighted talent (actual mpg, no continuity/fit) | 1779 | 9.287 | 7.389 | -0.130 | 0.291 | 0.497 |
| D | Minutes-weighted talent + continuity adjustment | 1779 | 9.512 | 7.625 | -0.010 | 0.257 | 0.488 |
| E | Minutes-weighted talent + continuity + fit | 1779 | 9.545 | 7.654 | -0.064 | 0.252 | 0.489 |
| F | Counterfactual: direct returner BPR bump (+5%) — no continuity formula | 1779 | 9.345 | 7.439 | +0.029 | 0.283 | 0.497 |

## Paired Model Comparisons (Adjacent Models)

Δ MAE = MAE(B) − MAE(A); negative = improvement. Wilcoxon p-value tests H₀: no difference in absolute errors.

| Comparison | N | Δ RMSE | Δ MAE | MAE % Δ | B Better? | Wilcoxon p |
|------------|---|--------|-------|---------|-----------|-----------|
| A→B | 1779 | +3.212 | +2.609 | +46.4% | ✗ | 0.0000 * |
| B→C | 1779 | -1.043 | -0.851 | -10.3% | ✓ | 0.0000 * |
| C→D | 1779 | +0.226 | +0.237 | +3.2% | ✗ | 0.0000 * |
| D→E | 1779 | +0.033 | +0.029 | +0.4% | ✗ | 0.0000 * |
| E→F | 1779 | -0.201 | -0.214 | -2.8% | ✓ | 0.0000 * |

_* p < 0.05_

## Fit-Capable Window: D vs E (Source Years: 2023, 2024, 2025)

These are the source seasons where `TeamRosterFit` was backfilled from real BPR-capable data. Model E should differ from D here (genuine fit adjustment). On all other source years, E ≡ D (no fit data → zero adjustment).

| Model | N | RMSE | MAE | Bias | R² | Spearman ρ |
|-------|---|------|-----|------|----|-----------|
| D | 1081 | 8.885 | 7.030 | -0.110 | 0.395 | 0.663 |
| E | 1081 | 8.943 | 7.078 | -0.198 | 0.387 | 0.664 |

**D→E (fit-capable):** Δ RMSE = +0.058, Δ MAE = +0.047 (+0.7%), E better = ✗, Wilcoxon p = 0.0000 *

## Uncertainty Band Coverage (Models D & E)

| Model | N | Coverage Rate | Mean Band Width | Median Band Width |
|-------|---|---------------|-----------------|-------------------|
| D | 1435 | 67.8% | 18.52 | 18.44 |
| E | 1435 | 66.6% | 18.15 | 18.07 |

## Model A — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 7.117 | 5.630 | 0.584 | 0.768 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 7.129 | 5.537 | 0.265 | 0.554 |
| middle_lower | 631 | 6.788 | 5.333 | 0.074 | 0.302 |
| middle_upper | 490 | 6.963 | 5.502 | 0.148 | 0.431 |
| weak | 320 | 7.927 | 6.509 | -0.257 | 0.246 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 7.117 | 5.630 | 0.584 | 0.768 |

## Model B — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 10.329 | 8.239 | 0.123 | 0.493 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 14.735 | 12.801 | -2.139 | 0.244 |
| middle_lower | 631 | 8.007 | 6.309 | -0.289 | 0.034 |
| middle_upper | 490 | 8.068 | 6.447 | -0.143 | 0.006 |
| weak | 320 | 11.735 | 9.972 | -1.754 | 0.003 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 10.329 | 8.239 | 0.123 | 0.493 |

## Model C — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 9.287 | 7.389 | 0.291 | 0.497 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 11.126 | 8.965 | -0.789 | 0.235 |
| middle_lower | 631 | 8.143 | 6.335 | -0.333 | 0.033 |
| middle_upper | 490 | 8.427 | 6.744 | -0.247 | -0.006 |
| weak | 320 | 10.450 | 8.788 | -1.184 | 0.003 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| high | 418 | 8.729 | 6.838 | 0.405 | 0.559 |
| low | 765 | 9.826 | 7.954 | 0.197 | 0.414 |
| mid | 596 | 8.947 | 7.048 | 0.323 | 0.573 |

## Model D — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 9.512 | 7.625 | 0.257 | 0.488 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 11.170 | 9.111 | -0.803 | 0.224 |
| middle_lower | 631 | 8.410 | 6.579 | -0.422 | 0.002 |
| middle_upper | 490 | 8.725 | 7.019 | -0.337 | -0.069 |
| weak | 320 | 10.733 | 9.047 | -1.304 | -0.003 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| high | 418 | 9.195 | 7.391 | 0.340 | 0.536 |
| low | 421 | 9.652 | 7.856 | 0.265 | 0.602 |
| mid | 596 | 8.979 | 7.075 | 0.318 | 0.572 |
| unknown | 344 | 10.560 | 8.581 | -0.000 | nan |

## Model E — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 9.545 | 7.654 | 0.252 | 0.489 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 11.187 | 9.131 | -0.809 | 0.226 |
| middle_lower | 631 | 8.421 | 6.593 | -0.426 | 0.003 |
| middle_upper | 490 | 8.752 | 7.035 | -0.345 | -0.070 |
| weak | 320 | 10.827 | 9.133 | -1.345 | -0.000 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| high | 418 | 9.203 | 7.403 | 0.338 | 0.538 |
| low | 421 | 9.717 | 7.906 | 0.255 | 0.602 |
| mid | 596 | 9.028 | 7.117 | 0.310 | 0.573 |
| unknown | 344 | 10.560 | 8.581 | -0.000 | nan |

## Model F — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 9.345 | 7.439 | 0.283 | 0.497 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 11.201 | 9.041 | -0.813 | 0.234 |
| middle_lower | 631 | 8.179 | 6.362 | -0.345 | 0.032 |
| middle_upper | 490 | 8.513 | 6.817 | -0.273 | -0.003 |
| weak | 320 | 10.491 | 8.825 | -1.201 | 0.004 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| high | 418 | 8.850 | 6.958 | 0.388 | 0.553 |
| low | 421 | 9.200 | 7.457 | 0.332 | 0.605 |
| mid | 596 | 9.032 | 7.106 | 0.310 | 0.574 |
| unknown | 344 | 10.560 | 8.581 | -0.000 | nan |

---
_Generated by `backtest_roster_outlook` management command._

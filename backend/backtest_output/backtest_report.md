# Roster Outlook Backtest Report

**Backtest pairs:** 2021→2022, 2022→2023, 2023→2024, 2024→2025, 2025→2026

## Ablation Ladder — adj_em Accuracy (All Seasons Combined)

| Model | Description | N | RMSE | MAE | Bias | R² | Spearman ρ |
|-------|-------------|---|------|-----|------|----|-----------|
| A | Prior-year adj_em (last season as prediction) | 1779 | 7.117 | 5.630 | -0.123 | 0.584 | 0.768 |
| C | Minutes-weighted talent (actual mpg, no continuity/fit) | 1779 | 9.287 | 7.389 | -0.130 | 0.291 | 0.497 |
| D | Minutes-weighted talent + continuity adjustment | 1779 | 9.512 | 7.625 | -0.010 | 0.257 | 0.488 |
| E | Minutes-weighted talent + continuity + fit | 1779 | 9.545 | 7.654 | -0.064 | 0.252 | 0.489 |
| G | Blend: (1−w)·D_adj_em + w·prior_adj_em (shared weight) | 1779 | 7.079 | 5.589 | -0.112 | 0.588 | 0.763 |
| H | Blend: split w_off/w_def on adj_o and adj_d separately | 1779 | 7.079 | 5.589 | -0.112 | 0.588 | 0.763 |

## Paired Model Comparisons (Adjacent Models)

Δ MAE = MAE(B) − MAE(A); negative = improvement. Wilcoxon p-value tests H₀: no difference in absolute errors.

| Comparison | N | Δ RMSE | Δ MAE | MAE % Δ | B Better? | Wilcoxon p |
|------------|---|--------|-------|---------|-----------|-----------|
| A→C | 1779 | +2.169 | +1.759 | +31.2% | ✗ | 0.0000 * |
| C→D | 1779 | +0.226 | +0.237 | +3.2% | ✗ | 0.0000 * |
| D→E | 1779 | +0.033 | +0.029 | +0.4% | ✗ | 0.0000 * |
| E→G | 1779 | -2.466 | -2.065 | -27.0% | ✓ | 0.0000 * |
| G→H | 1779 | +0.000 | +0.000 | +0.0% | ✗ | 1.0000 |

_* p < 0.05_

## Fit-Capable Window (Source Years: 2023, 2024, 2025)

These are the source seasons where `TeamRosterFit` was backfilled from real BPR-capable data. Model E should differ from D here (genuine fit adjustment). On all other source years, E ≡ D (no fit data → zero adjustment). Models G/H blend D with prior-year actual team strength.

| Model | N | RMSE | MAE | Bias | R² | Spearman ρ |
|-------|---|------|-----|------|----|-----------|
| A | 1081 | 7.347 | 5.805 | -0.117 | 0.586 | 0.759 |
| D | 1081 | 8.885 | 7.030 | -0.110 | 0.395 | 0.663 |
| E | 1081 | 8.943 | 7.078 | -0.198 | 0.387 | 0.664 |
| G | 1081 | 7.426 | 5.870 | -0.116 | 0.577 | 0.754 |
| H | 1081 | 7.426 | 5.870 | -0.116 | 0.577 | 0.754 |

**D→E (fit-capable):** Δ RMSE = +0.058, Δ MAE = +0.047 (+0.7%), E better = ✗, Wilcoxon p = 0.0000 *

**D→G (fit-capable):** Δ RMSE = -1.458, Δ MAE = -1.160 (-16.5%), G better = ✓, Wilcoxon p = 0.0000 *

**D→H (fit-capable):** Δ RMSE = -1.458, Δ MAE = -1.160 (-16.5%), H better = ✓, Wilcoxon p = 0.0000 *

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

## Model G — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 7.079 | 5.589 | 0.588 | 0.763 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 6.981 | 5.415 | 0.295 | 0.541 |
| middle_lower | 631 | 6.835 | 5.359 | 0.061 | 0.282 |
| middle_upper | 490 | 7.024 | 5.557 | 0.133 | 0.403 |
| weak | 320 | 7.710 | 6.276 | -0.189 | 0.221 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| high | 418 | 6.848 | 5.404 | 0.634 | 0.772 |
| low | 421 | 7.555 | 6.119 | 0.550 | 0.764 |
| mid | 596 | 7.166 | 5.537 | 0.565 | 0.755 |
| unknown | 344 | 6.584 | 5.257 | 0.611 | 0.782 |

## Model H — Subgroup Metrics
### Conf Group

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| unknown | 1779 | 7.079 | 5.589 | 0.588 | 0.763 |

### Strength Bucket

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| elite | 338 | 6.981 | 5.415 | 0.295 | 0.541 |
| middle_lower | 631 | 6.835 | 5.359 | 0.061 | 0.282 |
| middle_upper | 490 | 7.024 | 5.557 | 0.133 | 0.403 |
| weak | 320 | 7.710 | 6.276 | -0.189 | 0.221 |

### Continuity Tier

| Group | N | RMSE | MAE | R² | Spearman ρ |
|-------|---|------|-----|----|-----------|
| high | 418 | 6.848 | 5.404 | 0.634 | 0.772 |
| low | 421 | 7.555 | 6.119 | 0.550 | 0.764 |
| mid | 596 | 7.166 | 5.537 | 0.565 | 0.755 |
| unknown | 344 | 6.584 | 5.257 | 0.611 | 0.782 |

## Prior-Year Blend Analysis (Models G & H)

Model G blends Model D’s roster projection with the prior-year actual adj_em from source-year `TeamSeasonRatings` (leakage-safe: source-year TSR only). Model H applies independent blend weights to adj_o and adj_d separately.

**Model G weight:** w = 0.90   **Model H weights:** w_off = 0.90, w_def = 0.90

**Blend formula (G):** `pred = (1-w)·D_pred + w·prior_adj`

_Run `backtest_roster_outlook --sweep-blend` to calibrate weights._

---
_Generated by `backtest_roster_outlook` management command._

# Four Factor Index - Quick Reference

## What is the Four Factor Index (4FI)?

The Four Factor Index is a composite metric (0-100) that measures a team's overall performance across Dean Oliver's Four Factors of Basketball Success:

1. **eFG% (Effective Field Goal %)** - Shooting efficiency (40.69% weight)
2. **Turnover Rate** - Ball security (40.69% weight)  
3. **Rebounding** - Second-chance opportunities (14.32% weight)
4. **Free Throw Rate** - Getting to the line (4.28% weight)

Higher scores indicate better overall four-factor performance.

## How to Use

### Rankings Page
- **Column:** "4FI" displays the 0-100 score
- **Sort:** Click column header to sort by 4FI (descending = best)
- **Tooltip:** Hover over column for formula explanation
- **Color:** Orange text highlights the metric

### Team Profile Page  
- **Location:** Overview tab, new "Four Factor Index" section
- **Display:**
  - Large orange card with main 4FI score
  - National rank (e.g., "#1 nationally")
  - Weighted Z-score (technical detail)
  - Component Z-scores for all 4 factors
- **Interpretation:**
  - 90-100: Elite (top ~1%)
  - 80-90: Excellent (top ~5%)
  - 70-80: Very Good (top ~15%)
  - 60-70: Above Average (top ~30%)
  - 50-60: Average
  - 40-50: Below Average
  - <40: Poor

## Score Interpretation

### Current Top Teams (2025-26 Season)
1. **Houston (92.0)** - Elite across all factors, especially turnover forcing
2. **Iowa St. (89.5)** - Balanced excellence
3. **High Point (86.1)** - Strong mid-major performer

### Component Z-Scores
- **Z > 2.0:** Elite (top 2.5%)
- **Z > 1.0:** Very good (top 16%)
- **Z = 0:** Average
- **Z < -1.0:** Below average
- **Z < -2.0:** Poor

Example - Houston's Z-scores:
- eFG Margin: +1.32 (very good shooting margin)
- TOV Edge: +3.42 (ELITE turnover forcing)
- Reb Edge: +1.77 (very good rebounding)
- FTR Margin: -1.89 (weakness - don't get to line as much)

## Technical Details

### Formula
```
Weighted_Z = (0.4069 × eFG_Z) + (0.4069 × TOV_Z) + (0.1432 × REB_Z) + (0.0428 × FTR_Z)
Four_Factor_Index = CLAMP(0, 100, 50 + 20 × Weighted_Z)
```

### Z-Score Calculation
Each component Z-score is computed using season-wide statistics:
```
Z = (Team_Value - Season_Mean) / Season_StdDev
```

### Why These Weights?
Dean Oliver's research (Basketball on Paper, 2004) found:
- Shooting efficiency (eFG%) and turnovers are equally important (~41% each)
- Rebounding matters less (~14%)  
- Free throw rate has minimal impact (~4%)

## API Access

### Rankings Endpoint
```bash
GET /api/rankings?sort=four_factor_index_100&dir=desc
```

Response includes:
- `four_factor_index_100` - The 0-100 score
- `rank_four_factor_index_100` - National rank

### Team Profile Endpoint  
```bash
GET /api/teams/{slug}/profile
```

Response includes all Z-scores:
- `efg_margin_z`
- `tov_edge_z`
- `reb_edge_z`
- `ftr_margin_z`
- `four_factor_index_wz` - Weighted Z
- `four_factor_index_100` - Final score

## Tuning (Advanced)

If you want to adjust the spread of scores, edit `backend/core/constants.py`:

```python
FOUR_FACTOR_SCALE = 20  # Default (recommended)
```

- **Lower values (15):** More compressed distribution (scores clustered near 50)
- **Higher values (25):** More spread (more teams at extremes)

After changing, re-run ingestion:
```bash
python manage.py ingest_data --season 2026 --force
```

## Comparison to Other Metrics

| Metric | What It Measures | 4FI Advantage |
|--------|------------------|---------------|
| AdjEM | Efficiency margin | 4FI breaks down *why* teams are efficient |
| Barthag | Win probability | 4FI shows process, not just outcomes |
| WAB | Resume quality | 4FI is predictive, not descriptive |
| Individual Four Factors | Single dimension | 4FI combines all factors with proper weights |

## Limitations

- **Z-scores are season-relative:** A 70.0 in one season ≠ 70.0 in another season
- **Equal weighting across teams:** Doesn't account for strategy differences
- **Missing data:** Teams without four-factor data show "—" (not included in rankings)
- **Margins only:** Doesn't consider raw values (e.g., a 45% eFG team with 50% opp eFG has same margin as 55% vs 60%)

## FAQ

**Q: Why is my favorite team ranked lower than expected?**  
A: 4FI measures four-factor efficiency, not overall quality. A team with great efficiency but slow tempo might have a lower AdjEM despite high 4FI.

**Q: Can 4FI predict tournament success?**  
A: Generally yes - elite four-factor teams tend to advance further. But upsets happen!

**Q: What's the difference between 4FI and AdjEM?**  
A: AdjEM is opponent-adjusted efficiency margin. 4FI breaks down performance into the 4 key factors using Z-scores, making it easier to identify strengths/weaknesses.

**Q: Why does the weighted Z-score not divide by 4?**  
A: The weights already sum to ~1.0, so no additional normalization is needed.

## Support

For questions or issues:
1. Check [FOUR_FACTOR_INDEX_IMPLEMENTATION.md](./FOUR_FACTOR_INDEX_IMPLEMENTATION.md) for technical details
2. Review [FOUR_FACTOR_ANALYSIS.md](./Bart%20Torvik/FOUR_FACTOR_ANALYSIS.md) for research background
3. Open an issue with specific questions

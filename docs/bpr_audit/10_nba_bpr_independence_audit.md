# BPR Audit — 10: NBA BPR ↔ LEBRON Independence Audit (PREPARED, NOT RUN)

**Status:** task definition only. Deliberately kept separate from the Projection Value wiring (doc 09/11) per the product plan. Run as its own work item.

## Question

Is product-facing NBA BPR too dependent on LEBRON to count as a MacFax-native metric — and if so, is there a native configuration that keeps most of the forward accuracy?

## What we already know (inputs to this audit, not conclusions)

- LEBRON enters twice: box-target blend (`LEBRON_BLEND_W=0.7` — proven **inert** downstream, doc 08 B-B) and the final prior (`LEBRON_PRIOR_W=0.75` + LEBRON-adjusted λ — **load-bearing**: pw000 loses player-forward on all pairs; ls000 is the worst single ablation, −0.058).
- So the dependency question is really about the **final-stage prior and λ schedule only**.
- Fully native (pw000 + ls000 both off) has never been run as a combined variant.

## Planned measurements

1. **Correlation profile**: r(BPR, LEBRON) per season, overall and by minutes tier — how much of published BPR ordering is LEBRON's ordering? Compare vs r(BPR, box_bpr) and r(BPR, baseline RAPM).
2. **Fully-native variant** (`nba_experiment_final_bpr --lebron-prior-w 0 --lebron-lambda-scale 0`): forward player r, team RMSE, star stability vs production. Quantifies the true price of independence.
3. **Native-λ alternative**: replace LEBRON-adjusted λ with a *self-referential* λ (scale by own box_bpr or prior-season baseline instead of LEBRON) — same anchoring idea, no external dependency. One harness run.
4. **Failure-mode inventory**: players where BPR ≈ LEBRON but both disagree with baseline RAPM (external-anchor override cases) — top-20 list.
5. **Risk statement**: what happens to the pipeline if BBall-Index stops publishing (staleness gates already hard-fail the compute; document the degradation path: prior falls back to pure box, λ to minutes tiers).

## Decision rule

Ship a native config only if it keeps ≥90% of the forward-accuracy gap over pw000/ls000 while cutting r(BPR, LEBRON) meaningfully; otherwise document the dependency as priced-in and accepted (with the fallback path as the mitigation).

## Commands

```bash
python manage.py nba_experiment_final_bpr --source-seasons 2022 2023 2024 \
    --lebron-prior-w 0 --lebron-lambda-scale 0 --run-name native_full
# native-λ variant requires a small harness extension (λ keyed on box_bpr percentile)
```

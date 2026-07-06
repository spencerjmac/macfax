# BPR Audit — 12: NBA BPR ↔ LEBRON Independence — Results

**Date:** 2026-07-05
**Question:** is player-facing NBA BPR too LEBRON-dependent, and is there a MacFax-native config that keeps player-evaluation quality?
**Projection Value untouched throughout (per plan).**

## 1. Executive summary

**Keep production (LEBRON_PRIOR_W=0.75). Ship no change.** The dependency is real but bounded: BPR correlates with LEBRON (r 0.80–0.84) *no more than with MacFax's own box model* (0.843) — that's the generic inter-correlation of any two competent impact metrics, not mirroring. Roughly **half the top-25 differs from LEBRON every season**, and the disagreements are exactly where MacFax's lineup data speaks. Every step toward independence bought little originality at a real quality price; full independence was catastrophic. The honest posture: NBA BPR is a **LEBRON-anchored, RAPM-corrected** metric whose native value lives in its disagreements — documented, not hidden.

## 2. Current dependency profile (stored production BPR)

| Season | Pearson | Spearman | Top-25 ovl | Top-50 | Top-100 |
|---|---|---|---|---|---|
| 2022 | 0.796 | 0.779 | 13/25 | 26/50 | 76/100 |
| 2023 | 0.808 | 0.767 | 13/25 | 37/50 | 68/100 |
| 2024 | 0.793 | 0.770 | 16/25 | 29/50 | 66/100 |
| 2025 | 0.830 | 0.827 | 12/25 | 31/50 | 69/100 |
| 2026 | 0.836 | 0.805 | 13/25 | 33/50 | 72/100 |

Reference point: r(BPR, MacFax box_bpr) = **0.843** (2026). Even the fully-native candidate correlates 0.553 with LEBRON — the natural floor for any decent metric pair.

## 3. Candidates

| | Config | Notes |
|---|---|---|
| A | Production: prior_w=0.75, LEBRON-λ 0.7 | |
| B | Fully native: prior_w=0, λ-scale=0 | no live LEBRON anywhere in the final stage; box priors retain only *historical* LEBRON teaching (candidate D collapses into B — the only current-season LEBRON was the final stage) |
| C | Low-LEBRON: prior_w=0.25, LEBRON-λ 0.7 | |
| E | Native-λ: prior_w=0, λ anchored on player's **own box_bpr** (cap 4.0) | the "same anchoring idea, no external dependency" design from doc 10 |
| F | Projection-only LEBRON | = policy of shipping B/E publicly; evaluated via B/E numbers |

## 4. Performance table

YoY over pairs 2022→23/23→24/24→25, ≥1000 min both years; star = top-25 by candidate; outlier = |rating|>8 among <1000-min players (2025); forward = player r vs next-season baseline RAPM (clean pairs); team RMSE = minutes-weighted aggregate → next adj_net.

| Candidate | YoY all | YoY star | YoY role | Outlier% | Forward r | Team RMSE |
|---|---|---|---|---|---|---|
| **A production** | **0.537** | **0.610** | **0.362** | **0.0%** | **0.295** | 3.937 |
| C low-LEBRON | 0.497 | 0.579 | 0.338 | 0.7% | 0.275 | 3.942 |
| E native-λ | 0.431 | 0.520 | 0.293 | 1.5% | 0.255 | 3.950 |
| B fully native | 0.267 | 0.333 | 0.164 | 1.9% | 0.216 | 3.930 |

## 5. Independence table

| Candidate | r vs LEBRON (pooled, ≥1000 min) | Top-25 overlap (4 seasons) |
|---|---|---|
| A production | 0.811 | 54/100 |
| C low-LEBRON | 0.767 | 51/100 |
| E native-λ | 0.707 | 46/100 |
| B fully native | 0.553 | 36/100 |

The trade curve is brutal: going A→C buys 0.044 of independence for −0.040 stability and −0.020 forward r; A→E buys 0.104 for −0.106 stability; A→B buys 0.258 for a halved metric. Nothing on the curve satisfies the "loses only a small amount but meaningfully more independent" ship rule.

## 6. Player examples — where BPR is native (2026, vs LEBRON)

Jrue Holiday +6.2, SGA +5.0, Wembanyama +4.2, Tari Eason +4.1, Amen Thompson +3.7 (RAPM sees lineup impact LEBRON's box-heavier frame doesn't); Jarace Walker −4.5 (RAPM punishes). Systematic archetype tilt: three-and-D **+0.72** and connectors **+0.46** above LEBRON — MacFax's lineup data credits glue players; stretch bigs −0.13. These disagreements are the product's native content — 46–48% of every top-25.

## 7. Recommended configuration

**Unchanged: LEBRON_PRIOR_W=0.75, LEBRON-adjusted λ (scale 0.7, cap 7), A_conservative tiers, 90d half-life.**

## 8. Ship / no-ship

**NO-SHIP for all candidates.** Keep A. Honest developer-facing statement (add to `nba_bpr_pipeline.md` if desired): *"NBA BPR uses LEBRON as a Bayesian prior and shrinkage anchor (75% prior weight; role-player λ anchoring). It is LEBRON-anchored, not LEBRON-mirroring: correlation with LEBRON (~0.81) is no higher than with our own box model (0.84), and ~half of every top-25 differs. If the LEBRON feed dies, staleness gates hard-fail the compute; the accepted degradation path is candidate C/E territory (documented performance cost above)."* Product-facing copy needs no change — the confidence/source layer (doc 07) already tells users what drives each rating.

## 9. Files changed

`nba/management/commands/nba_experiment_final_bpr.py` — `--native-lambda` (+cap) and `--dump-ratings` flags (harness only; no production code touched). No model/config changes shipped from this audit.

## 10. Reproduce

```bash
for cfg in "0.75 0.7 0 candA_prod" "0.0 0.0 0 candB_native" \
           "0.25 0.7 0 candC_low" "0.0 0.7 1 candE_nativelam"; do
  set -- $cfg; NL=""; [ "$3" = "1" ] && NL="--native-lambda"
  python manage.py nba_experiment_final_bpr --source-seasons 2022 2023 2024 2025 \
      --lebron-prior-w $1 --lebron-lambda-scale $2 $NL --dump-ratings --run-name $4
done
# evaluation: scratchpad eval script (YoY/star/role/outlier/independence table);
# dependency profile: shell snippets in this doc's session (stored BPR vs lebron-data-*.csv)
```

## 11. Remaining risks

- LEBRON feed discontinuation → C/E fallback costs are now priced (this doc). Mitigation exists; no action needed today.
- Independence numbers use same-season correlation; a skeptic could ask for partial correlation controlling for box_bpr — expected to lower apparent dependency further (the 0.84 internal reference bounds it).
- Candidate E's box-anchor cap (4.0) was a first cut; if independence pressure ever rises, tune E's cap/scale before revisiting B.

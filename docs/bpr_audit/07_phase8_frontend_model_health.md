# BPR Audit — 07: Phase 8 Frontend / Model-Health Surface

**Date:** 2026-07-05
**Goal:** make BPR trustworthy to users — surface source, confidence, and data-provenance honestly, without SaaS-speak or scare copy.

## Changes made

### New component — `web/src/components/BPRConfidenceBadge.tsx`
Single shared badge for both leagues:
- **Confidence**: High / Medium / Low, computed from sample size feeding the on-court component (NCAA: offensive possessions, thresholds 800/400; NBA: total minutes, thresholds 1500/700) and the rating source. Tooltip states explicitly that confidence reflects *sample size, not a judgment of the player*.
- **Source**: On-court (rapm) / Box-based (box_bpr) / Mixed / Partial, shown inline.
- **Box-era flag (NCAA pre-2025)**: seasons before 2025 render a "Box era" badge with the provenance tooltip: *"Pre-2025 college play-by-play has no substitution data, so this rating is driven by box score and team context rather than lineup impact."* Transparent, not scary — the exact framing requested.

Exported helper `bprConfidence(source, sample, league)` for reuse in tables/pages.

### Touched components
| File | Change |
|---|---|
| `web/src/components/NCAAPlayerRankingsTable.tsx` | The Impact tab's "Source" column upgraded to "Confidence" — renders the badge with `bpr_source` + `off_poss` + selected season (box-era aware). The strict/two-sided/all BPR-mode filters were already present and are unchanged. |
| `web/src/components/PlayerScoutingCard.tsx` (NBA) | Footnote row now carries a compact confidence badge computed from mpg×gp. |
| `web/src/lib/glossaryContent.ts` | BPR entry rewritten: source labels + confidence explained; NCAA pre-2025 box-era caveat added in plain language; evaluation-vs-projection distinction added ("BPR answers *how good is this player, in context, right now* — team forecasts may separately use a blended projection value where it predicts future results better out of sample"). |

### Copy added (verbatim, for reuse)
- Confidence tooltip: "Source: {On-court/Box-based/Mixed}. Confidence reflects sample size ({n} poss/min) feeding the on-court component — not a judgment of the player."
- Box-era tooltip: "Pre-2025 college play-by-play has no substitution data, so this rating is driven by box score and team context rather than lineup impact."
- Glossary NCAA note: "…ratings from 2025 onward use full lineup data and are validated out-of-sample against the strongest public college metrics."

## Model-health summary (what the numbers behind the badges are)

- NCAA v1.7: statistical tie with EvanMiya on 5,751 out-of-sample games; player YoY stability 0.69 (2025→26). Sources on 2026: 3,682 on-court / 110 box / 10 mixed / 10 partial.
- NBA: forward team signal beats LEBRON and persistence on our framework; behind VORP/BPM for pure next-season wins — hence the projection-blend distinction in the glossary.
- Last-updated + model version already stored per row (`bpr_model_version`, `bpr_last_updated`) and serialized; a "why did this rating change" note keyed to version bumps remains open (below).

## Not done / open

- Screenshots: not captured in this pass (requires running the app; badge markup is conventional Tailwind and mirrors the existing source-pill styling it replaced).
- `bpr_last_updated`/`bpr_model_version` display on cards — serialized but not yet rendered; small follow-up.
- "Why did this rating change" explainer tied to `bpr_model_version` transitions.
- NBA projection-blend labeling in outlook pages (pending doc 09 ship decision — the value must be labeled `Projection Value`, never "BPR").

## Verification

```bash
cd web && npx tsc --noEmit   # clean
```
Manual: NCAA rankings → Impact tab shows Confidence badges; season selector to a pre-2025 season shows "Box era" badges; NBA player page scouting card shows the compact badge in the footnote row.

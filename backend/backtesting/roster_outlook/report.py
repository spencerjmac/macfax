"""
report.py — Output generation for roster-outlook backtesting.

Produces three output formats per run:

  1. Row-level CSV  — one row per (team × source_year × model), all predictions + actuals.
  2. Summary JSON   — ablation table, per-model metrics, paired comparisons, subgroup metrics.
  3. Markdown report — human-readable ablation delta table + subgroup summaries.

All outputs are written to an output directory (configurable via management command flag).

Public entry point:
    generate_reports(all_results, output_dir, include_subgroups=True)
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from typing import Optional

from .ablation import AblationResult, TeamPrediction
from .data_loader import BacktestPair, ActualOutcome
from .metrics import (
    PointMetrics,
    PairedComparison,
    compute_point_metrics,
    compute_coverage,
    paired_comparison,
    subgroup_metrics,
)


# ── Subgroup definitions ──────────────────────────────────────────────────────

def _assign_subgroups(
    team_slug: str,
    source_outcome: Optional[ActualOutcome],
    returner_fraction: Optional[float],
) -> dict[str, str]:
    """
    Compute subgroup labels for a team.  Used to slice metrics.

    Subgroups:
      - conf_group:      'power' | 'mid_major' (from conf_utils.get_conf_group)
      - strength_bucket: 'elite' | 'middle' | 'weak' (source-year adj_em)
      - continuity_tier: 'high' | 'mid' | 'low' (returner fraction)
    """
    groups: dict[str, str] = {}

    # Conference group
    try:
        from core.conf_utils import get_conf_group
        from core.models import Team
        team = Team.objects.filter(slug=team_slug).first()
        if team and team.conference:
            groups["conf_group"] = get_conf_group(team.conference.slug)
        else:
            groups["conf_group"] = "unknown"
    except Exception:
        groups["conf_group"] = "unknown"

    # Strength in source year
    if source_outcome is not None:
        em = source_outcome.adj_em
        if em > 10.0:
            groups["strength_bucket"] = "elite"
        elif em > 0.0:
            groups["strength_bucket"] = "middle_upper"
        elif em > -10.0:
            groups["strength_bucket"] = "middle_lower"
        else:
            groups["strength_bucket"] = "weak"
    else:
        groups["strength_bucket"] = "unknown"

    # Continuity tier
    if returner_fraction is not None:
        if returner_fraction >= 0.65:
            groups["continuity_tier"] = "high"
        elif returner_fraction >= 0.40:
            groups["continuity_tier"] = "mid"
        else:
            groups["continuity_tier"] = "low"
    else:
        groups["continuity_tier"] = "unknown"

    return groups


# ── Row-level record building ─────────────────────────────────────────────────

def build_flat_records(
    result: AblationResult,
    pair: BacktestPair,
    model: str,
) -> list[dict]:
    """
    Build one flat dict per (team, model) for CSV output.

    Attaches actual outcome and subgroup labels to each row.
    Returns empty list if model has no predictions in the result.
    """
    records: list[dict] = []

    for team_slug, preds_by_model in result.predictions.items():
        pred = preds_by_model.get(model)
        if pred is None:
            continue

        actual = pair.actual_outcomes.get(team_slug)
        if actual is None:
            continue

        source_out = pair.source_outcomes.get(team_slug)
        returner_frac = pred.returner_fraction

        subgroups = _assign_subgroups(team_slug, source_out, returner_frac)

        row: dict = {
            "source_year": result.source_year,
            "target_year": result.target_year,
            "team_slug": team_slug,
            "model": model,
            # Predictions
            "pred_adj_o": round(pred.pred_adj_o, 4),
            "pred_adj_d": round(pred.pred_adj_d, 4),
            "pred_adj_em": round(pred.pred_adj_em, 4),
            "pred_adj_em_low": round(pred.pred_adj_em_low, 4) if pred.pred_adj_em_low is not None else None,
            "pred_adj_em_high": round(pred.pred_adj_em_high, 4) if pred.pred_adj_em_high is not None else None,
            # Actuals (leakage-safe: only used here after predictions are finalized)
            "actual_adj_o": round(actual.adj_o, 4),
            "actual_adj_d": round(actual.adj_d, 4),
            "actual_adj_em": round(actual.adj_em, 4),
            "actual_rank_adj_em": actual.rank_adj_em,
            "actual_tournament_seed": actual.tournament_seed,
            # Errors
            "error_adj_em": round(pred.pred_adj_em - actual.adj_em, 4),
            "abs_error_adj_em": round(abs(pred.pred_adj_em - actual.adj_em), 4),
            # Diagnostics
            "n_players": pred.n_players,
            "returner_fraction": round(returner_frac, 4) if returner_frac is not None else None,
            "continuity_score": round(pred.continuity_score, 2) if pred.continuity_score is not None else None,
            "uncertainty": round(pred.uncertainty, 4) if pred.uncertainty is not None else None,
            "base_team_offense": round(pred.base_team_offense, 4) if pred.base_team_offense is not None else None,
            # Fit flag (Model E only: True when TeamRosterFit existed for source_year)
            "fit_used": pred.fit_used if pred.model_name == "E" else None,
            # Subgroups
            **subgroups,
        }
        records.append(row)

    return records


# ── Aggregation helpers ───────────────────────────────────────────────────────

def _compute_model_metrics(records: list[dict]) -> Optional[PointMetrics]:
    """Compute PointMetrics from flat records list for one model."""
    preds = [r["pred_adj_em"] for r in records if r["pred_adj_em"] is not None]
    actuals = [r["actual_adj_em"] for r in records if r["actual_adj_em"] is not None]
    if len(preds) < 2:
        return None
    return compute_point_metrics(preds, actuals)


def _compute_model_coverage(records: list[dict]) -> Optional[dict]:
    """Compute CoverageMetrics from flat records if uncertainty bands present."""
    rows_with_bands = [
        r for r in records
        if r.get("pred_adj_em_low") is not None and r.get("pred_adj_em_high") is not None
    ]
    if len(rows_with_bands) < 2:
        return None
    lows = [r["pred_adj_em_low"] for r in rows_with_bands]
    highs = [r["pred_adj_em_high"] for r in rows_with_bands]
    actuals = [r["actual_adj_em"] for r in rows_with_bands]
    cov = compute_coverage(lows, highs, actuals)
    return cov.as_dict()


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_reports(
    all_pairs: list[tuple[AblationResult, BacktestPair]],
    output_dir: str,
    include_subgroups: bool = True,
    model_order: Optional[list[str]] = None,
    fit_capable_source_years: Optional[set[int]] = None,
) -> dict[str, str]:
    """
    Generate all report outputs for all backtest pair results.

    Args:
        all_pairs:               List of (AblationResult, BacktestPair) tuples, one per season pair.
        output_dir:              Directory path to write outputs (created if absent).
        include_subgroups:       Whether to include per-subgroup metric breakdowns.
        model_order:             Ordered list of model names for the ablation table.
        fit_capable_source_years: Source years that have real TeamRosterFit data. When provided,
                                  an additional fit-capable window section (D vs E comparison)
                                  is added to the JSON and Markdown reports.

    Returns:
        dict mapping output type → file path written.
    """
    os.makedirs(output_dir, exist_ok=True)
    if model_order is None:
        model_order = ["A", "B", "C", "D", "E", "F"]

    # ── Collect all flat records across seasons × models ───────────────────
    all_records_by_model: dict[str, list[dict]] = {m: [] for m in model_order}
    for ablation_result, pair in all_pairs:
        for model in model_order:
            recs = build_flat_records(ablation_result, pair, model)
            all_records_by_model[model].extend(recs)

    # ── 1. Row-level CSV ──────────────────────────────────────────────────
    csv_path = os.path.join(output_dir, "backtest_rows.csv")
    all_flat_rows: list[dict] = []
    for model_rows in all_records_by_model.values():
        all_flat_rows.extend(model_rows)

    if all_flat_rows:
        fieldnames = list(all_flat_rows[0].keys())
        with open(csv_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_flat_rows)

    # ── 2. Summary JSON ───────────────────────────────────────────────────
    summary: dict = {
        "backtest_pairs": [
            {"source_year": r.source_year, "target_year": r.target_year}
            for r, _ in all_pairs
        ],
        "models": {},
        "paired_comparisons": [],
        "subgroups": {},
    }

    # Fit-capable window: source years where TeamRosterFit existed for real
    if fit_capable_source_years:
        summary["fit_capable_source_years"] = sorted(fit_capable_source_years)
        fit_capable_recs: dict[str, list[dict]] = {}
        for model in model_order:
            fit_capable_recs[model] = [
                r for r in all_records_by_model[model]
                if r["source_year"] in fit_capable_source_years
            ]
        # D vs E comparison on fit-capable subset
        fc_window: dict = {}
        for model in model_order:
            recs = fit_capable_recs.get(model, [])
            if recs:
                m = _compute_model_metrics(recs)
                fc_window[model] = {
                    "n": len(recs),
                    "point_metrics": m.as_dict() if m else None,
                }
        fc_d_recs = fit_capable_recs.get("D", [])
        fc_e_recs = fit_capable_recs.get("E", [])
        if fc_d_recs and fc_e_recs:
            key_d = {(r["team_slug"], r["source_year"]): r["error_adj_em"] for r in fc_d_recs}
            key_e = {(r["team_slug"], r["source_year"]): r["error_adj_em"] for r in fc_e_recs}
            common = sorted(set(key_d) & set(key_e))
            if len(common) >= 6:
                err_d = [key_d[k] for k in common]
                err_e = [key_e[k] for k in common]
                cmp = paired_comparison(err_d, err_e, model_a="D", model_b="E")
                fc_window["D_vs_E_paired"] = cmp.as_dict() if cmp else None
        summary["fit_capable_window"] = fc_window

    for model in model_order:
        recs = all_records_by_model[model]
        if not recs:
            continue
        metrics = _compute_model_metrics(recs)
        coverage = _compute_model_coverage(recs)
        summary["models"][model] = {
            "n": len(recs),
            "point_metrics": metrics.as_dict() if metrics else None,
            "coverage": coverage,
        }

    # Paired comparisons: each adjacent model vs the previous
    model_names_present = [m for m in model_order if all_records_by_model.get(m)]
    for i in range(len(model_names_present) - 1):
        ma, mb = model_names_present[i], model_names_present[i + 1]
        recs_a = all_records_by_model[ma]
        recs_b = all_records_by_model[mb]
        # Align on common team+year keys
        key_a = {(r["team_slug"], r["source_year"]): r["error_adj_em"] for r in recs_a}
        key_b = {(r["team_slug"], r["source_year"]): r["error_adj_em"] for r in recs_b}
        common_keys = sorted(set(key_a) & set(key_b))
        if len(common_keys) >= 6:
            err_a = [key_a[k] for k in common_keys]
            err_b = [key_b[k] for k in common_keys]
            cmp = paired_comparison(err_a, err_b, model_a=ma, model_b=mb)
            if cmp is not None:
                summary["paired_comparisons"].append(cmp.as_dict())

    # Subgroup metrics (adj_em only, all models combined for brevity or per-model)
    if include_subgroups:
        for model in model_order:
            recs = all_records_by_model[model]
            if not recs:
                continue
            for sg_key in ("conf_group", "strength_bucket", "continuity_tier"):
                sg_metrics = subgroup_metrics(recs, sg_key)
                for group, m in sg_metrics.items():
                    summary["subgroups"].setdefault(model, {}).setdefault(sg_key, {})[group] = m.as_dict()

    json_path = os.path.join(output_dir, "backtest_summary.json")
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)

    # ── 3. Markdown report ────────────────────────────────────────────────
    md_path = os.path.join(output_dir, "backtest_report.md")
    _write_markdown_report(md_path, summary, all_pairs, model_order, fit_capable_source_years)

    return {
        "csv": csv_path,
        "json": json_path,
        "markdown": md_path,
    }


# ── Markdown rendering ────────────────────────────────────────────────────────

_MODEL_DESCRIPTIONS = {
    "A": "Prior-year adj_em (last season as prediction)",
    "B": "Equal-minutes talent average (unweighted BPR)",
    "C": "Minutes-weighted talent (actual mpg, no continuity/fit)",
    "D": "Minutes-weighted talent + continuity adjustment",
    "E": "Minutes-weighted talent + continuity + fit",
    "F": "Counterfactual: direct returner BPR bump (+5%) — no continuity formula",
}


def _write_markdown_report(
    path: str,
    summary: dict,
    all_pairs: list[tuple[AblationResult, BacktestPair]],
    model_order: list[str],
    fit_capable_source_years: Optional[set[int]] = None,
) -> None:
    lines: list[str] = []

    source_years = sorted({r.source_year for r, _ in all_pairs})
    target_years = sorted({r.target_year for r, _ in all_pairs})

    lines.append("# Roster Outlook Backtest Report")
    lines.append("")
    lines.append(f"**Backtest pairs:** {', '.join(f'{s}→{t}' for s, t in zip(source_years, target_years))}")
    lines.append("")

    # ── Ablation table ──────────────────────────────────────────────────
    lines.append("## Ablation Ladder — adj_em Accuracy (All Seasons Combined)")
    lines.append("")
    lines.append("| Model | Description | N | RMSE | MAE | Bias | R² | Spearman ρ |")
    lines.append("|-------|-------------|---|------|-----|------|----|-----------|")
    for m in model_order:
        info = summary["models"].get(m)
        if info and info.get("point_metrics"):
            pm = info["point_metrics"]
            desc = _MODEL_DESCRIPTIONS.get(m, m)
            lines.append(
                f"| {m} | {desc} | {pm['n']} "
                f"| {pm['rmse']:.3f} | {pm['mae']:.3f} | {pm['bias']:+.3f} "
                f"| {pm['r_squared']:.3f} | {pm['spearman_rho']:.3f} |"
            )
    lines.append("")

    # ── Paired comparison table ─────────────────────────────────────────
    if summary.get("paired_comparisons"):
        lines.append("## Paired Model Comparisons (Adjacent Models)")
        lines.append("")
        lines.append("Δ MAE = MAE(B) − MAE(A); negative = improvement. "
                     "Wilcoxon p-value tests H₀: no difference in absolute errors.")
        lines.append("")
        lines.append("| Comparison | N | Δ RMSE | Δ MAE | MAE % Δ | B Better? | Wilcoxon p |")
        lines.append("|------------|---|--------|-------|---------|-----------|-----------|")
        for cmp in summary["paired_comparisons"]:
            b_better = "✓" if cmp["delta_mae"] < 0 else "✗"
            sig = " *" if cmp["wilcoxon_p"] < 0.05 else ""
            lines.append(
                f"| {cmp['model_a']}→{cmp['model_b']} | {cmp['n']} "
                f"| {cmp['delta_rmse']:+.3f} | {cmp['delta_mae']:+.3f} "
                f"| {cmp['mae_pct_change']:+.1f}% | {b_better} "
                f"| {cmp['wilcoxon_p']:.4f}{sig} |"
            )
        lines.append("")
        lines.append("_* p < 0.05_")
        lines.append("")

    # ── Fit-capable window: D vs E comparison ───────────────────────────
    fc = summary.get("fit_capable_window")
    if fc and fit_capable_source_years:
        fc_years = sorted(fit_capable_source_years)
        lines.append(f"## Fit-Capable Window: D vs E (Source Years: {', '.join(str(y) for y in fc_years)})")
        lines.append("")
        lines.append(
            "These are the source seasons where `TeamRosterFit` was backfilled from real BPR-capable data. "
            "Model E should differ from D here (genuine fit adjustment). "
            "On all other source years, E ≡ D (no fit data → zero adjustment)."
        )
        lines.append("")
        lines.append("| Model | N | RMSE | MAE | Bias | R² | Spearman ρ |")
        lines.append("|-------|---|------|-----|------|----|-----------|")
        for m in ["D", "E"]:
            info = fc.get(m)
            if info and info.get("point_metrics"):
                pm = info["point_metrics"]
                desc = _MODEL_DESCRIPTIONS.get(m, m)
                lines.append(
                    f"| {m} | {pm['n']} "
                    f"| {pm['rmse']:.3f} | {pm['mae']:.3f} | {pm['bias']:+.3f} "
                    f"| {pm['r_squared']:.3f} | {pm['spearman_rho']:.3f} |"
                )
        lines.append("")
        paired = fc.get("D_vs_E_paired")
        if paired:
            b_better = "✓" if paired["delta_mae"] < 0 else "✗"
            sig = " *" if paired["wilcoxon_p"] < 0.05 else ""
            lines.append(
                f"**D→E (fit-capable):** Δ RMSE = {paired['delta_rmse']:+.3f}, "
                f"Δ MAE = {paired['delta_mae']:+.3f} ({paired['mae_pct_change']:+.1f}%), "
                f"E better = {b_better}, Wilcoxon p = {paired['wilcoxon_p']:.4f}{sig}"
            )
            lines.append("")

    # ── Coverage table (Models D/E with uncertainty bands) ──────────────
    cov_models = [m for m in model_order if summary["models"].get(m, {}).get("coverage")]
    if cov_models:
        lines.append("## Uncertainty Band Coverage (Models D & E)")
        lines.append("")
        lines.append("| Model | N | Coverage Rate | Mean Band Width | Median Band Width |")
        lines.append("|-------|---|---------------|-----------------|-------------------|")
        for m in cov_models:
            cov = summary["models"][m]["coverage"]
            lines.append(
                f"| {m} | {cov['n']} | {cov['coverage_rate']:.1%} "
                f"| {cov['mean_band_width']:.2f} | {cov['median_band_width']:.2f} |"
            )
        lines.append("")

    # ── Subgroup tables ─────────────────────────────────────────────────
    if summary.get("subgroups"):
        for model in model_order:
            sg_by_model = summary["subgroups"].get(model)
            if not sg_by_model:
                continue
            lines.append(f"## Model {model} — Subgroup Metrics")
            for sg_key, groups in sg_by_model.items():
                lines.append(f"### {sg_key.replace('_', ' ').title()}")
                lines.append("")
                lines.append("| Group | N | RMSE | MAE | R² | Spearman ρ |")
                lines.append("|-------|---|------|-----|----|-----------|")
                for group, pm in sorted(groups.items()):
                    lines.append(
                        f"| {group} | {pm['n']} | {pm['rmse']:.3f} "
                        f"| {pm['mae']:.3f} | {pm['r_squared']:.3f} | {pm['spearman_rho']:.3f} |"
                    )
                lines.append("")

    lines.append("---")
    lines.append("_Generated by `backtest_roster_outlook` management command._")
    lines.append("")

    with open(path, "w") as fh:
        fh.write("\n".join(lines))

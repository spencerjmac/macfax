"""
nba_bpr_diagnostic.py

Diagnostic analysis: WHY does BPR underperform BPM/WS48 in retrodiction?
Known failure modes from retrodiction run:
  - Overrates Indiana/Miami/Toronto role players
  - Underrates star-driven LAL
  - Biggest individual miss: Jokić (consensus z=+4.46 vs BPR z=+1.26)

Runs 6 analyses to locate the root cause.

Run:
    backend/.venv/bin/python nba_bpr_diagnostic.py
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import scipy.stats
import seaborn as sns
from rapidfuzz import fuzz, process as rfprocess

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Constants ──────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent.parent.parent
OUTPUT_DIR   = SCRIPT_DIR / "metrics_output"
METRICS_CSV  = OUTPUT_DIR / "nba_metrics_2025_26.csv"
BPR_CSV      = SCRIPT_DIR / "data" / "nba" / "bpr_2025_26.csv"

MIN_MINUTES   = 200
NULL_THRESH   = 0.30
FUZZY_CUTOFF  = 82

CONSENSUS_METRICS = ["BPM", "LEBRON", "WS48", "PER"]
ALL_CORR_METRICS  = ["bpr", "BPM", "OBPM", "DBPM", "LEBRON", "WS48", "PER", "VORP", "RAPTOR_total"]

# Retrodiction errors from prior run (team→ predicted_wins − actual_wins)
RETRO_ERRORS = {
    "IND": +15.1, "MIA": +10.0, "TOR": +8.7, "DAL": +8.4,
    "LAL": -11.1, "NYK": -8.2, "DEN": -7.5, "SAC": +6.9,
    "WAS": -6.1,  "HOU": -6.0,
}

OUTPUT_DIR.mkdir(exist_ok=True)


# ── Utilities ──────────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def zscore(series: pd.Series) -> pd.Series:
    mu, sigma = series.mean(), series.std()
    return (series - mu) / sigma if sigma > 0 else pd.Series(0.0, index=series.index)


def pct_rank(series: pd.Series, value: float) -> float:
    """Percentile rank of value in series (0–100, higher = better)."""
    return float((series < value).mean() * 100)


def pearson_r(x: pd.Series, y: pd.Series) -> float:
    valid = pd.concat([x, y], axis=1).dropna()
    if len(valid) < 5:
        return float("nan")
    r, _ = scipy.stats.pearsonr(valid.iloc[:, 0], valid.iloc[:, 1])
    return round(float(r), 3)


# ── Step 0: Load & Merge ───────────────────────────────────────────────────────

def load_and_merge() -> pd.DataFrame:
    print("[LOAD] Reading CSVs...")
    metrics = pd.read_csv(METRICS_CSV)

    bpr_raw = pd.read_csv(BPR_CSV)
    # Deduplicate traded players: keep row with most games played
    bpr = (bpr_raw.sort_values("gp", ascending=False)
                  .drop_duplicates(subset=["nba_id"], keep="first")
                  .reset_index(drop=True))
    bpr["_norm"] = bpr["player_name"].map(norm_name)

    # Fuzzy merge metrics → bpr on player name
    bpr_norm_list = bpr["_norm"].tolist()
    bpr_cols = ["bpr", "obpr", "dbpr", "box_bpr", "baseline_obpr", "baseline_dbpr"]

    matched_data = {c: [] for c in bpr_cols}
    n_matched = 0
    for _, row in metrics.iterrows():
        key = norm_name(row["player_name"])
        res = rfprocess.extractOne(key, bpr_norm_list, scorer=fuzz.WRatio, score_cutoff=FUZZY_CUTOFF)
        if res:
            bpr_row = bpr.iloc[res[2]]
            for c in bpr_cols:
                matched_data[c].append(bpr_row.get(c, np.nan))
            n_matched += 1
        else:
            for c in bpr_cols:
                matched_data[c].append(np.nan)

    df = metrics.copy()
    for c in bpr_cols:
        df[c] = matched_data[c]

    # Min-minutes filter
    df = df[df["minutes"] >= MIN_MINUTES].copy().reset_index(drop=True)

    print(f"[LOAD] {len(df)} players after ≥{MIN_MINUTES} min filter "
          f"({n_matched} BPR matches out of {len(metrics)})")

    # Report null rates
    for col in ALL_CORR_METRICS:
        if col in df.columns:
            null_pct = df[col].isna().mean()
            if null_pct > NULL_THRESH:
                print(f"  [SKIP] {col}: {null_pct:.0%} null — excluded from analyses")

    return df


# ── Analysis 1: Correlation Matrix ─────────────────────────────────────────────

def analysis_correlation(df: pd.DataFrame) -> None:
    print("\n" + "=" * 65)
    print("ANALYSIS 1 — METRIC CORRELATION MATRIX")
    print("=" * 65)

    cols = [c for c in ALL_CORR_METRICS
            if c in df.columns and df[c].isna().mean() <= NULL_THRESH]
    sub = df[cols].dropna()

    corr = sub.corr(method="pearson").round(3)
    print(corr.to_string())

    # Flag weak BPR correlations
    print("\nBPR correlations with each metric:")
    for col in [c for c in cols if c != "bpr"]:
        r = corr.loc["bpr", col]
        warn = "  [WARN < 0.70]" if r < 0.70 else ""
        print(f"  bpr ↔ {col:<16} r = {r:.3f}{warn}")

    # Heatmap
    fig, ax = plt.subplots(figsize=(10, 8))
    mask = np.zeros_like(corr, dtype=bool)
    mask[np.triu_indices_from(mask, k=1)] = True  # show lower triangle + diagonal
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdYlGn", center=0,
                vmin=-1, vmax=1, ax=ax, mask=False,
                linewidths=0.5, cbar_kws={"label": "Pearson r"})
    ax.set_title("NBA Player Metric Correlation Matrix (2025-26, ≥200 min)", pad=12)
    plt.tight_layout()
    path = OUTPUT_DIR / "correlation_matrix.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[SAVED] {path.name}")


# ── Analysis 2: Divergence ─────────────────────────────────────────────────────

def analysis_divergence(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 65)
    print("ANALYSIS 2 — Z-SCORE CONSENSUS vs BPR DIVERGENCE")
    print("=" * 65)

    avail_consensus = [m for m in CONSENSUS_METRICS
                       if m in df.columns and df[m].isna().mean() <= NULL_THRESH]
    if "bpr" not in df.columns or df["bpr"].isna().mean() > NULL_THRESH:
        print("[SKIP] BPR not available")
        return df

    # Z-score each consensus metric, average → z_consensus
    z_frames = {}
    for m in avail_consensus:
        valid_mask = df[m].notna()
        z_frames[m] = zscore(df.loc[valid_mask, m])

    z_df = pd.DataFrame(z_frames)
    df["z_consensus"] = z_df.mean(axis=1)
    df["z_bpr"]       = zscore(df["bpr"].where(df["bpr"].notna()))
    df["divergence"]  = df["z_bpr"] - df["z_consensus"]
    df["abs_div"]     = df["divergence"].abs()

    bulls = df[df["divergence"] > 1.5].sort_values("divergence", ascending=False)
    bears = df[df["divergence"] < -1.5].sort_values("divergence")

    show_cols = ["player_name", "team", "minutes", "USG_pct", "bpr",
                 "z_bpr", "z_consensus", "divergence", "BPM", "LEBRON", "WS48"]
    show_cols = [c for c in show_cols if c in df.columns]

    print(f"\nBPR_BULLS (BPR inflates vs consensus, divergence > +1.5): {len(bulls)} players")
    print(bulls[show_cols].round(3).to_string(index=False))

    print(f"\nBPR_BEARS (BPR suppresses vs consensus, divergence < -1.5): {len(bears)} players")
    print(bears[show_cols].round(3).to_string(index=False))

    div_out = df[["player_name", "team", "minutes", "USG_pct", "bpr",
                  "z_bpr", "z_consensus", "divergence", "abs_div",
                  "BPM", "LEBRON", "WS48", "PER"]].sort_values("divergence").round(3)
    path = OUTPUT_DIR / "divergence_full.csv"
    div_out.to_csv(path, index=False)
    print(f"\n[SAVED] {path.name} ({len(div_out)} players)")

    return df


# ── Analysis 3: Usage Curve ────────────────────────────────────────────────────

def analysis_usage_curve(df: pd.DataFrame) -> None:
    print("\n" + "=" * 65)
    print("ANALYSIS 3 — USAGE CURVE (key hypothesis test)")
    print("=" * 65)

    if "USG_pct" not in df.columns or "bpr" not in df.columns:
        print("[SKIP] USG_pct or bpr missing")
        return

    bins  = [0, 18, 22, 28, 100]
    labels = ["Q1 (<18%)", "Q2 (18-22%)", "Q3 (22-28%)", "Q4 (>28%)"]
    df["usg_quartile"] = pd.cut(df["USG_pct"], bins=bins, labels=labels)

    rows = []
    print(f"\n{'Quartile':<14} {'N':>4} {'BPR':>6} {'BPM':>6} {'LEBRON':>7} "
          f"{'WS48':>6} {'r(BPR,BPM)':>11} {'r(BPR,LEB)':>11} {'AvgDiv':>8}")
    print("-" * 85)

    for label in labels:
        grp = df[df["usg_quartile"] == label].dropna(subset=["bpr"])
        if len(grp) < 5:
            continue
        r_bpm  = pearson_r(grp["bpr"], grp["BPM"])   if "BPM"    in grp.columns else np.nan
        r_leb  = pearson_r(grp["bpr"], grp["LEBRON"]) if "LEBRON" in grp.columns else np.nan
        avg_div = grp["divergence"].mean() if "divergence" in grp.columns else np.nan
        row = {
            "quartile":   label,
            "n":          len(grp),
            "mean_bpr":   round(grp["bpr"].mean(), 3),
            "mean_bpm":   round(grp["BPM"].mean(), 3) if "BPM" in grp.columns else np.nan,
            "mean_lebron":round(grp["LEBRON"].mean(), 3) if "LEBRON" in grp.columns else np.nan,
            "mean_ws48":  round(grp["WS48"].mean(), 3) if "WS48" in grp.columns else np.nan,
            "r_bpr_bpm":  r_bpm,
            "r_bpr_leb":  r_leb,
            "avg_divergence": round(avg_div, 3),
        }
        rows.append(row)
        print(f"{label:<14} {row['n']:>4} {row['mean_bpr']:>6.2f} {row['mean_bpm']:>6.2f} "
              f"{row['mean_lebron']:>7.3f} {row['mean_ws48']:>6.3f} "
              f"{r_bpm:>11.3f} {r_leb:>11.3f} {avg_div:>8.3f}")

    usg_df = pd.DataFrame(rows)
    path = OUTPUT_DIR / "usage_curve.csv"
    usg_df.to_csv(path, index=False)
    print(f"\n[SAVED] {path.name}")

    # Confirmation test
    if len(rows) >= 2:
        q1_div = rows[0]["avg_divergence"]
        q4_div = rows[-1]["avg_divergence"]
        if q1_div > 0 and q4_div < 0:
            print(f"\n[CONFIRMED] Usage bias detected: Q1 divergence={q1_div:+.3f}, "
                  f"Q4 divergence={q4_div:+.3f}")
            print("  BPR systematically OVERRATES low-usage role players and "
                  "UNDERRATES high-usage stars.")
        elif q1_div < 0 and q4_div > 0:
            print(f"\n[REVERSED] Opposite of hypothesis: Q1={q1_div:+.3f}, Q4={q4_div:+.3f}")
        else:
            print(f"\n[INCONCLUSIVE] Q1={q1_div:+.3f}, Q4={q4_div:+.3f} — no clear pattern")


# ── Analysis 4: Component Breakdown ───────────────────────────────────────────

def analysis_components(df: pd.DataFrame) -> tuple[list[str], float, float]:
    """Returns (bears_names, obpr_r, dbpr_r) for use in summary."""
    print("\n" + "=" * 65)
    print("ANALYSIS 4 — OFFENSIVE vs DEFENSIVE COMPONENT BREAKDOWN")
    print("=" * 65)

    pairs = [
        ("obpr", "OBPM",    "Offensive BPR vs BBref OBPM"),
        ("dbpr", "DBPM",    "Defensive BPR vs BBref DBPM"),
        ("obpr", "O_LEBRON","Offensive BPR vs O-LEBRON"),
        ("dbpr", "D_LEBRON","Defensive BPR vs D-LEBRON"),
    ]
    correlations = {}
    for a, b, label in pairs:
        if a in df.columns and b in df.columns:
            r = pearson_r(df[a], df[b])
            correlations[(a, b)] = r
            print(f"  {label:<35} r = {r:.3f}")

    obpr_r = correlations.get(("obpr", "OBPM"), np.nan)
    dbpr_r = correlations.get(("dbpr", "DBPM"), np.nan)

    # Per-player component divergence
    if "obpr" in df.columns and "OBPM" in df.columns:
        df["o_div"] = zscore(df["obpr"]) - zscore(df["OBPM"].where(df["OBPM"].notna()))
        df["d_div"] = zscore(df["dbpr"]) - zscore(df["DBPM"].where(df["DBPM"].notna()))
        print(f"\n  Mean o_div (z_obpr - z_OBPM): {df['o_div'].mean():+.3f}")
        print(f"  Mean d_div (z_dbpr - z_DBPM): {df['d_div'].mean():+.3f}")
        worse = "offensive" if abs(df["o_div"].std()) > abs(df["d_div"].std()) else "defensive"
        print(f"  → Higher variance divergence on: {worse} side")

    # Scatter plot
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("BPR Component vs BBref Component (2025-26, ≥200 min)", fontsize=13)

    highlight = {
        "nikola jokic": "Jokić",
        "shai gilgeous-alexander": "SGA",
        "giannis antetokounmpo": "Giannis",
        "lebron james": "LeBron",
        "luka doncic": "Dončić",
    }

    # Top BPR_BEARS for highlighting
    bears_names: list[str] = []
    if "divergence" in df.columns:
        top_bears = df.nsmallest(5, "divergence")["player_name"].tolist()
        bears_names = top_bears
        for n in top_bears:
            highlight[norm_name(n)] = n.split()[-1]

    for ax, (x_col, y_col, xlabel, ylabel) in zip(axes, [
        ("obpr", "OBPM",  "OBPR (BPR offensive)", "OBPM (BBref offensive)"),
        ("dbpr", "DBPM",  "DBPR (BPR defensive)", "DBPM (BBref defensive)"),
    ]):
        if x_col not in df.columns or y_col not in df.columns:
            ax.set_visible(False)
            continue
        sub = df[[x_col, y_col, "player_name"]].dropna()
        ax.scatter(sub[x_col], sub[y_col], alpha=0.4, s=20, color="steelblue")

        # OLS line
        m_x = sub[x_col].values.reshape(-1, 1)
        from sklearn.linear_model import LinearRegression
        reg = LinearRegression().fit(m_x, sub[y_col].values)
        x_line = np.linspace(sub[x_col].min(), sub[x_col].max(), 100)
        ax.plot(x_line, reg.predict(x_line.reshape(-1, 1)), "k--", lw=1.5, alpha=0.7)

        # Highlight key players
        for _, row in sub.iterrows():
            key = norm_name(row["player_name"])
            if key in highlight:
                ax.scatter(row[x_col], row[y_col], color="red", s=60, zorder=5)
                ax.annotate(highlight[key], (row[x_col], row[y_col]),
                            fontsize=7, xytext=(4, 4), textcoords="offset points")

        r = pearson_r(sub[x_col], sub[y_col])
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"r = {r:.3f}")
        ax.axhline(0, color="gray", lw=0.5); ax.axvline(0, color="gray", lw=0.5)

    patch_blue = mpatches.Patch(color="steelblue", label="All players")
    patch_red  = mpatches.Patch(color="red", label="Stars / BPR_BEARS")
    fig.legend(handles=[patch_blue, patch_red], loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    plt.tight_layout()
    path = OUTPUT_DIR / "component_scatter.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[SAVED] {path.name}")

    return bears_names, obpr_r, dbpr_r


# ── Analysis 5: Team Bias ─────────────────────────────────────────────────────

def analysis_team_bias(df: pd.DataFrame) -> tuple[str, float]:
    """Returns (biggest_bias_team, r_bias_retro)."""
    print("\n" + "=" * 65)
    print("ANALYSIS 5 — TEAM BIAS (player BPR inflation → team win errors)")
    print("=" * 65)

    if "z_bpr" not in df.columns or "z_consensus" not in df.columns:
        print("[SKIP] z_bpr / z_consensus not computed")
        return "", float("nan")

    # Minutes-weighted mean z-scores per team
    rows = []
    for team, grp in df.groupby("team"):
        total_min = grp["minutes"].sum()
        if total_min == 0:
            continue
        w = grp["minutes"] / total_min
        mean_z_bpr  = (grp["z_bpr"]       * w).sum()
        mean_z_cons = (grp["z_consensus"]  * w).sum()
        team_bias   = mean_z_bpr - mean_z_cons
        rows.append({
            "team":        team,
            "team_bias":   round(float(team_bias), 3),
            "mean_z_bpr":  round(float(mean_z_bpr), 3),
            "mean_z_cons": round(float(mean_z_cons), 3),
        })

    bias_df = pd.DataFrame(rows).sort_values("team_bias", ascending=False)

    # Cross-ref with retrodiction errors
    bias_df["retro_error"]     = bias_df["team"].map(RETRO_ERRORS)
    bias_df["direction_match"] = bias_df.apply(
        lambda r: (
            "YES" if (not pd.isna(r["retro_error"]) and
                      np.sign(r["team_bias"]) == np.sign(r["retro_error"]))
            else ("NO" if not pd.isna(r["retro_error"]) else "—")
        ), axis=1
    )

    print(f"\n{'Team':<6} {'Bias':>7} {'z_BPR':>7} {'z_Cons':>7} "
          f"{'RetroErr':>9} {'Match':>6}")
    print("-" * 50)
    for _, row in bias_df.iterrows():
        re_str = f"{row['retro_error']:+.1f}" if not pd.isna(row["retro_error"]) else "   —"
        print(f"{row['team']:<6} {row['team_bias']:>+7.3f} {row['mean_z_bpr']:>7.3f} "
              f"{row['mean_z_cons']:>7.3f} {re_str:>9} {row['direction_match']:>6}")

    # Correlation between team_bias and retro_error
    paired = bias_df.dropna(subset=["retro_error"])
    r_corr = pearson_r(paired["team_bias"], paired["retro_error"])
    print(f"\nPearson r(team_bias, retro_error) = {r_corr:.3f}  (n={len(paired)} teams)")
    if r_corr > 0.50:
        print("  → CONFIRMED: player-level BPR inflation directly drives team win prediction errors.")

    path = OUTPUT_DIR / "team_bias.csv"
    bias_df.to_csv(path, index=False)
    print(f"[SAVED] {path.name}")

    biggest = bias_df.iloc[0]["team"] if not bias_df.empty else ""
    return biggest, r_corr


# ── Analysis 6: Jokić Deep Dive ───────────────────────────────────────────────

def analysis_jokic(df: pd.DataFrame) -> tuple[str, float, float]:
    """Returns (suppressed_side, z_obpr, z_obpm)."""
    print("\n" + "=" * 65)
    print("ANALYSIS 6 — JOKIĆ DEEP DIVE")
    print("=" * 65)

    jokic_row = df[df["player_name"].str.contains("Joki", case=False, na=False)]
    if jokic_row.empty:
        print("[SKIP] Jokić not found in merged data")
        return "unknown", 0.0, 0.0
    jokic = jokic_row.iloc[0]

    metrics_to_show = [
        ("bpr",           "BPR",          df["bpr"],          True),
        ("BPM",           "BPM",          df["BPM"],          True),
        ("LEBRON",        "LEBRON",        df["LEBRON"],       True),
        ("WS48",          "WS/48",         df["WS48"],         True),
        ("obpr",          "OBPR",          df["obpr"],         True),
        ("dbpr",          "DBPR",          df["dbpr"],         True),
        ("OBPM",          "OBPM",          df["OBPM"],         True),
        ("DBPM",          "DBPM",          df["DBPM"],         True),
        ("USG_pct",       "USG%",          df["USG_pct"],      True),
        ("PER",           "PER",           df["PER"],          True),
        ("VORP",          "VORP",          df["VORP"],         True),
    ]

    print(f"\n  {'Metric':<12} {'Value':>8} {'Pct rank':>10} {'Z-score':>9}")
    print(f"  {'-'*43}")

    z_obpr = z_obpm = 0.0
    for col, label, series, higher_better in metrics_to_show:
        if col not in jokic or pd.isna(jokic[col]):
            print(f"  {label:<12} {'—':>8}")
            continue
        val   = jokic[col]
        pct   = pct_rank(series.dropna(), val) if higher_better else 100 - pct_rank(series.dropna(), val)
        z     = (val - series.mean()) / series.std() if series.std() > 0 else 0.0
        print(f"  {label:<12} {val:>8.3f} {pct:>9.1f}th {z:>+9.2f}")
        if col == "obpr": z_obpr = z
        if col == "OBPM": z_obpm = z

    # Optional DB pull for MPIR / ts_pct
    try:
        import os
        sys.path.insert(0, str(SCRIPT_DIR / "backend"))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django
        django.setup()
        from nba.models import NBAPlayerSeasonStats  # type: ignore
        qs = NBAPlayerSeasonStats.objects.filter(
            player__name__icontains="Jokic",
            season__year=2026,
            season_type="regular",
        )
        if qs.exists():
            row = qs.first()
            db_extras = {
                "o_mpir":          row.o_mpir,
                "d_mpir":          row.d_mpir,
                "ts_pct":          row.ts_pct,
                "on_court_adj_o":  row.on_court_adj_o,
                "on_court_adj_d":  row.on_court_adj_d,
                "on_court_adj_em": row.on_court_adj_em,
            }
            print("\n  Additional DB fields:")
            for k, v in db_extras.items():
                print(f"    {k:<20} {v}")
    except Exception:
        pass

    # Component comparison
    suppressed = "offense" if abs(z_obpr - z_obpm) > abs(
        (jokic.get("dbpr", 0) - df["dbpr"].mean()) / df["dbpr"].std() -
        (jokic.get("DBPM", 0) - df["DBPM"].mean()) / df["DBPM"].std()
    ) else "defense"

    print(f"\n  Key gap: z_obpr={z_obpr:+.2f} vs z_OBPM={z_obpm:+.2f} → "
          f"BPR suppresses Jokić most on {'offense' if abs(z_obpr - z_obpm) > 0.5 else 'defense'}")

    return suppressed, z_obpr, z_obpm


# ── Diagnostic Summary ─────────────────────────────────────────────────────────

def write_summary(
    df: pd.DataFrame,
    obpr_r: float,
    dbpr_r: float,
    biggest_bias_team: str,
    jokic_side: str,
    z_obpr: float,
    z_obpm: float,
) -> None:
    print("\n" + "=" * 65)
    print("BPR DIAGNOSTIC REPORT")
    print("=" * 65)

    # Overall BPR-consensus r
    cons_r = pearson_r(df["bpr"], df["z_consensus"]) if "z_consensus" in df.columns else float("nan")

    # Usage bias
    if "usg_quartile" in df.columns and "divergence" in df.columns:
        q1_div = df[df["usg_quartile"] == "Q1 (<18%)"]["divergence"].mean()
        q4_div = df[df["usg_quartile"] == "Q4 (>28%)"]["divergence"].mean()
        usage_confirmed = "YES" if (q1_div > 0 and q4_div < 0) else "NO"
        usage_detail = f"Q1 div={q1_div:+.3f}, Q4 div={q4_div:+.3f}"
    else:
        usage_confirmed = "UNKNOWN"
        usage_detail = ""

    # Recommend fix
    if usage_confirmed == "YES":
        if abs(obpr_r - dbpr_r) > 0.05:
            fix = "usage-weighting + " + ("offensive" if obpr_r < dbpr_r else "defensive") + " model"
        else:
            fix = "usage-weighting (applies to both offense and defense)"
    else:
        fix = "investigate further — usage bias not confirmed"

    lines = [
        "BPR DIAGNOSTIC REPORT — 2025-26 NBA Season",
        "=" * 50,
        f"1. Overall BPR-consensus correlation: {cons_r:.3f}",
        f"2. Offensive component (obpr vs OBPM): {obpr_r:.3f}",
        f"3. Defensive component (dbpr vs DBPM): {dbpr_r:.3f}",
        f"4. Usage bias confirmed: {usage_confirmed} — {usage_detail}",
        f"5. Biggest team bias: {biggest_bias_team} "
        f"(BPR over/underrates this team's players most)",
        f"6. Jokić: suppressed most on {jokic_side}, "
        f"z_obpr={z_obpr:+.2f} vs z_OBPM={z_obpm:+.2f}",
        f"7. Recommended fix priority: {fix}",
    ]
    report = "\n".join(lines)
    print(report)

    path = OUTPUT_DIR / "bpr_diagnostic_report.txt"
    path.write_text(report + "\n", encoding="utf-8")
    print(f"\n[SAVED] {path.name}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("NBA BPR Diagnostic Analysis — 2025-26 Season")
    print("=" * 65)

    df = load_and_merge()

    analysis_correlation(df)
    df = analysis_divergence(df)
    analysis_usage_curve(df)
    _, obpr_r, dbpr_r = analysis_components(df)
    biggest_bias_team, _ = analysis_team_bias(df)
    jokic_side, z_obpr, z_obpm = analysis_jokic(df)

    write_summary(df, obpr_r, dbpr_r, biggest_bias_team, jokic_side, z_obpr, z_obpm)

    print("\nDone. Check metrics_output/ for all saved files.")


if __name__ == "__main__":
    main()

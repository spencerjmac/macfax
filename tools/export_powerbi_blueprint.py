"""Export the Power BI competition dataset; the database transaction is read-only.

Run from the repository root:
    backend/.venv/bin/python tools/export_powerbi_blueprint.py
"""

import csv
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "powerbi"


def main():
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.db import connection, transaction
    from ncaa.models import TeamSeasonRatings

    fields = (
        "team_id", "team__name", "team__slug", "season_id", "season__year",
        "adj_o", "adj_d", "adj_em", "computed_at",
    )
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        pre = list(TeamSeasonRatings.all_objects.filter(
            is_pre_tournament=True, season__year__range=(2005, 2026),
        ).exclude(season__year=2020).values(*fields))
        winners = list(TeamSeasonRatings.all_objects.filter(
            is_pre_tournament=False, tournament_finish="Champ",
            season__year__range=(2005, 2026),
        ).exclude(season__year=2020).values("team_id", "season_id", "season__year"))

    # All historical snapshot rows, rather than teams' present-day D1 flags.
    valid = [r for r in pre if all(
        r[k] is not None and math.isfinite(r[k]) and r[k] > 0
        for k in ("adj_o", "adj_d")
    )]
    by_year = defaultdict(list)
    for r in valid:
        by_year[r["season__year"]].append(r)
    expected_years = set(range(2005, 2027)) - {2020}
    if set(by_year) != expected_years:
        raise ValueError("Missing expected seasons; inspect before presenting.")
    winner_counts = Counter(r["season__year"] for r in winners)
    if set(winner_counts) != expected_years or any(n != 1 for n in winner_counts.values()):
        raise ValueError("Expected exactly one recorded tournament winner per included season.")
    winner_keys = {(r["season_id"], r["team_id"]) for r in winners}
    if not winner_keys <= {(r["season_id"], r["team_id"]) for r in valid}:
        raise ValueError("A tournament winner has no valid pre-tournament snapshot.")

    rows = []
    for year, teams in sorted(by_year.items()):
        n = len(teams)
        if n < 2:
            raise ValueError("Not enough teams to calculate season percentiles.")
        off_counts = Counter(t["adj_o"] for t in teams)
        def_counts = Counter(t["adj_d"] for t in teams)
        off_rank, def_rank = {}, {}
        rank = 1
        for value, count in sorted(off_counts.items(), reverse=True):
            off_rank[value] = rank
            rank += count
        rank = 1
        for value, count in sorted(def_counts.items()):
            def_rank[value] = rank
            rank += count
        for t in sorted(teams, key=lambda r: r["team__name"]):
            champion = (t["season_id"], t["team_id"]) in winner_keys
            o_rank, d_rank = off_rank[t["adj_o"]], def_rank[t["adj_d"]]
            o_pct = 100 * (n - o_rank) / (n - 1)
            d_pct = 100 * (n - d_rank) / (n - 1)
            vacated = champion and year == 2013 and t["team__slug"] == "louisville"
            rows.append({
                "season_team": f"{year} {t['team__name']}",
                "team": t["team__name"],
                "season": year,
                "offense_percentile": round(o_pct, 4),
                "defense_percentile": round(d_pct, 4),
                "offense_rank": o_rank,
                "defense_rank": d_rank,
                "teams_in_season": n,
                "adjusted_offense": round(t["adj_o"], 4),
                "adjusted_defense": round(t["adj_d"], 4),
                "adjusted_margin": round(t["adj_o"] - t["adj_d"], 4),
                "result": "Tournament winner" if champion else "Other team-seasons",
                "is_winner": int(champion),
                "top_decile_both": int(o_pct >= 90 and d_pct >= 90),
                "marker_size": 12 if champion else 1,
                "winner_label": (f"{year} {t['team__name']}" + ("*" if vacated else "")) if champion else "",
                "title_note": "2013 title vacated; on-court winner retained" if vacated else "",
                "snapshot": "Pre-tournament",
                "ratings_computed_at": t["computed_at"].isoformat(),
            })

    champs = [r for r in rows if r["is_winner"]]
    in_box = [r for r in rows if r["top_decile_both"]]
    champs_in_box = [r for r in champs if r["top_decile_both"]]
    summary = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Local Macfax NCAA TeamSeasonRatings database",
        "seasons": sorted(by_year),
        "rows": len(rows),
        "displayed_zoom_rows": sum(r["offense_percentile"] >= 75 and r["defense_percentile"] >= 75 for r in rows),
        "discarded_invalid_rating_rows": len(pre) - len(valid),
        "tournament_winners": len(champs),
        "winners_top_decile_both": len(champs_in_box),
        "winners_top_decile_both_pct": round(100 * len(champs_in_box) / len(champs), 1),
        "all_teams_top_decile_both": len(in_box),
        "all_teams_top_decile_both_pct": round(100 * len(in_box) / len(rows), 1),
        "winners_outside_box": [r for r in champs if not r["top_decile_both"]],
        "percentile_formula": "100 * (N - competition_rank) / (N - 1); offense descending, defense ascending, within each season",
        "notes": [
            "2020 omitted because the tournament was canceled.",
            "Louisville 2013 retained as the on-court winner; title was vacated.",
            "Pre-tournament snapshots may be reconstructed retrospectively; this is descriptive, not an out-of-sample prediction test.",
            "Marker size is a visual emphasis weight (12 winner / 1 other), not a basketball statistic.",
            "Percentiles use all valid team snapshots available in each historical season, not present-day D1 membership.",
        ],
    }
    if len({r["season_team"] for r in rows}) != len(rows):
        raise ValueError("Chart point labels are not unique.")
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "championship_blueprint.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    paste_fields = [
        "season_team", "offense_percentile", "defense_percentile", "result",
        "marker_size", "offense_rank", "defense_rank", "adjusted_offense",
        "adjusted_defense", "title_note",
    ]
    with (OUT / "browser_paste.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=paste_fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(r for r in rows if r["offense_percentile"] >= 75 and r["defense_percentile"] >= 75)
    (OUT / "data_notes.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Exported {len(rows):,} team-seasons and {len(champs)} tournament winners.")
    print(f"Top decile on both axes: {len(champs_in_box)}/{len(champs)} winners; {len(in_box)}/{len(rows)} team-seasons.")
    print("Winners outside that region:")
    for r in champs:
        if not r["top_decile_both"]:
            print(f"  {r['season_team']}: offense #{r['offense_rank']}, defense #{r['defense_rank']}")
    print(f"Files: {OUT}")


if __name__ == "__main__":
    main()

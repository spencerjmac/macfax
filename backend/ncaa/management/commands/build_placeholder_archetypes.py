"""
build_placeholder_archetypes
-----------------------------
Builds (or rebuilds) the PlaceholderArchetype table from real PlayerSeasonProjection
and PlayerSeasonStats data.

Usage::

    python manage.py build_placeholder_archetypes
    python manage.py build_placeholder_archetypes --season 2026

Algorithm
---------
1.  Load all PlayerSeasonProjection rows for the source season (default: latest).
2.  For each row, resolve the team slug → conference group via CONF_MAP.
3.  Group players into two layers of archetype buckets:

    Tier 1 — 15 broad baseline archetypes (always present):
      - 3 Elite  (national top-15% BPR among starters, one per role)
      - 6 Power  (starters + rotation × 3 roles; power-conf players only)
      - 6 Mid    (starters + rotation × 3 roles; ALL non-power players)
        Note: mid_major pools WCC/MWC/A10/Amer + smaller confs for bucket mass.

    Tier 2 — 6 high_mid archetypes (added when sample sizes are sufficient):
      - WCC, MWC, A10, Amer combined into 'high_mid' conference cluster
      - 3 starters + 3 rotation × 3 roles
      - Only built when bucket size ≥ MIN_SPECIFIC_BUCKET (see constant below).

4.  For each bucket, compute medians of all projection fields.
5.  Join with PlayerSeasonStats (same season) to compute median stat profile.
6.  Compute bucket-aware placeholder uncertainty (see _bucket_uncertainty()).
7.  Persist results to PlaceholderArchetype (upsert by key).

Minimum bucket sizes:
  MIN_BUCKET_SIZE    = 30   — warn but still write if below this for Tier 1.
  MIN_SPECIFIC_BUCKET= 40   — skip Tier 2 archetypes below this threshold.

Uncertainty formula (see _bucket_uncertainty()):
  placeholder_uncertainty =
      median_player_unc          # direct signal from individual projections
      + n_penalty                # UNC_SAMPLE_WEIGHT × max(0, (IDEAL_N-n)/IDEAL_N)
      + spread_penalty           # UNC_SPREAD_WEIGHT × min(stdev_bpr, CAP) / CAP
  clipped to [UNC_MIN, UNC_MAX]
"""

from __future__ import annotations

import statistics
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from ncaa.conf_utils import get_conf_group, get_conf_detail
from ncaa.models import PlaceholderArchetype, PlayerSeasonProjection, PlayerSeasonStats


# --------------------------------------------------------------------------- #
# Archetype specification
# Each tuple: (key, display_name, conf_group, role_bucket, quality_tier)
# --------------------------------------------------------------------------- #

# Elite threshold: top-15% of national starters → computed dynamically.
_ARCHETYPES: list[tuple[str, str, str, str, str]] = [
    # ── Tier 1: 15 broad baseline archetypes ──────────────────────────────── #
    # key,                      display_name,                    conf_group,   role,   tier
    ("elite_g",                 "All-American Guard",            "national",   "G",    "elite"),
    ("elite_wing",              "All-American Wing",             "national",   "Wing", "elite"),
    ("elite_big",               "All-American Big",              "national",   "Big",  "elite"),
    ("power_starter_g",         "Power Conf Guard (Starter)",    "power",      "G",    "starter"),
    ("power_starter_wing",      "Power Conf Wing (Starter)",     "power",      "Wing", "starter"),
    ("power_starter_big",       "Power Conf Big (Starter)",      "power",      "Big",  "starter"),
    ("power_rotation_g",        "Power Conf Guard (Reserve)",    "power",      "G",    "rotation"),
    ("power_rotation_wing",     "Power Conf Wing (Reserve)",     "power",      "Wing", "rotation"),
    ("power_rotation_big",      "Power Conf Big (Reserve)",      "power",      "Big",  "rotation"),
    ("mid_starter_g",           "Mid-Major Guard (Starter)",     "mid_major",  "G",    "starter"),
    ("mid_starter_wing",        "Mid-Major Wing (Starter)",      "mid_major",  "Wing", "starter"),
    ("mid_starter_big",         "Mid-Major Big (Starter)",       "mid_major",  "Big",  "starter"),
    ("mid_rotation_g",          "Mid-Major Guard (Reserve)",     "mid_major",  "G",    "rotation"),
    ("mid_rotation_wing",       "Mid-Major Wing (Reserve)",      "mid_major",  "Wing", "rotation"),
    ("mid_rotation_big",        "Mid-Major Big (Reserve)",       "mid_major",  "Big",  "rotation"),

    # ── Tier 2: 6 high_mid cluster archetypes ─────────────────────────────── #
    # WCC + MWC + A10 + Amer pooled.  Only written when n ≥ MIN_SPECIFIC_BUCKET.
    ("high_mid_starter_g",      "High Mid-Major Guard (Starter)",   "high_mid", "G",    "starter"),
    ("high_mid_starter_wing",   "High Mid-Major Wing (Starter)",    "high_mid", "Wing", "starter"),
    ("high_mid_starter_big",    "High Mid-Major Big (Starter)",     "high_mid", "Big",  "starter"),
    ("high_mid_rotation_g",     "High Mid-Major Guard (Reserve)",   "high_mid", "G",    "rotation"),
    ("high_mid_rotation_wing",  "High Mid-Major Wing (Reserve)",    "high_mid", "Wing", "rotation"),
    ("high_mid_rotation_big",   "High Mid-Major Big (Reserve)",     "high_mid", "Big",  "rotation"),
]

STARTER_MS_MIN  = 0.375   # minutes_share_p2 ≥ this → starter
ROTATION_MS_MIN = 0.20    # minutes_share_p2 ≥ this → rotation
ROTATION_MS_MAX = 0.375   # minutes_share_p2 < this → rotation (upper bound)
ELITE_BPR_PERCENTILE = 0.85  # Bottom of the elite tier (top 15% nationally)

# Tier 1 minimum bucket size — warn but still write if below this.
MIN_BUCKET_SIZE = 30
# Tier 2 minimum bucket size — skip the archetype entirely if below this.
MIN_SPECIFIC_BUCKET = 40

# ── Uncertainty formula constants ────────────────────────────────────────── #
# placeholder_uncertainty = base_unc + n_penalty + spread_penalty
# clipped to [UNC_MIN, UNC_MAX].
#
# n_penalty:      max UNC_SAMPLE_WEIGHT when n=0, zero when n ≥ UNC_IDEAL_N
# spread_penalty: max UNC_SPREAD_WEIGHT when BPR stdev ≥ UNC_SPREAD_CAP, else linear
UNC_IDEAL_N       = 100   # buckets this large get no small-sample penalty
UNC_SAMPLE_WEIGHT = 0.05  # max additive penalty from small sample size
UNC_SPREAD_WEIGHT = 0.03  # max additive penalty from wide BPR spread
UNC_SPREAD_CAP    = 3.0   # BPR stdev is normalized against this value
UNC_MIN           = 0.10  # hard floor on placeholder uncertainty
UNC_MAX           = 0.90  # hard ceiling on placeholder uncertainty


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.median(values)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return value at percentile pct (0..1) from a sorted list."""
    if not sorted_values:
        return 0.0
    idx = max(0, int(len(sorted_values) * pct) - 1)
    return sorted_values[idx]


def _bucket_uncertainty(base_unc: float, bpr_vals: list[float], n: int) -> float:
    """
    Compute bucket-aware placeholder uncertainty ∈ [UNC_MIN, UNC_MAX].

    Three additive components:
      base_unc      — median of individual player projection_uncertainty values
      n_penalty     — small-sample surcharge: UNC_SAMPLE_WEIGHT × max(0, (IDEAL_N-n)/IDEAL_N)
                      e.g. n=50 → +0.025, n=100+ → +0.000
      spread_penalty — wide-spread surcharge: UNC_SPREAD_WEIGHT × min(stdev, CAP) / CAP
                      e.g. stdev=1.5 → +0.015, stdev≥3.0 → +0.030

    Larger, tighter buckets receive lower uncertainty (more information). The
    additive structure keeps the formula interpretable: total extra penalty is
    at most +0.08 above the player-level median signal.
    """
    n_penalty = UNC_SAMPLE_WEIGHT * max(0.0, (UNC_IDEAL_N - n) / UNC_IDEAL_N)
    bpr_stdev = statistics.stdev(bpr_vals) if len(bpr_vals) >= 2 else 0.0
    spread_penalty = UNC_SPREAD_WEIGHT * min(bpr_stdev, UNC_SPREAD_CAP) / UNC_SPREAD_CAP
    adjusted = base_unc + n_penalty + spread_penalty
    return max(UNC_MIN, min(UNC_MAX, adjusted))


class Command(BaseCommand):
    help = "Build placeholder archetype records from real projection data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Source season year (from_season.year). Defaults to latest available.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print results without writing to the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        season_year = options["season"]
        dry_run = options["dry_run"]

        # ── 1. Resolve source season ──────────────────────────────────────── #
        qs_all = PlayerSeasonProjection.objects.select_related("player", "team")
        if season_year:
            qs_all = qs_all.filter(from_season__year=season_year)
        else:
            # Use the latest from_season available
            latest = (
                PlayerSeasonProjection.objects
                .order_by("-from_season__year")
                .values_list("from_season__year", flat=True)
                .first()
            )
            if latest is None:
                raise CommandError("No PlayerSeasonProjection rows found.")
            season_year = latest
            qs_all = qs_all.filter(from_season__year=season_year)

        self.stdout.write(f"Source season: {season_year}. Loading projections…")
        rows = list(qs_all.only(
            "player_id", "team__slug",
            "role_bucket",
            "minutes_share_p2",
            "mpg_p2",
            "projected_obpr",
            "projected_dbpr",
            "projected_bpr",
            "projection_uncertainty",
        ))
        self.stdout.write(f"  Loaded {len(rows)} projections.")

        if not rows:
            raise CommandError(f"No projections found for season {season_year}.")

        # ── 2. Assign conf_group to each projection row ───────────────────── #
        # buckets[cg][role][tier] = list of projection dicts
        # Uses get_conf_group (coarse: power|mid_major) for Tier 1 archetypes.
        # high_mid_buckets[role][tier] = list for Tier 2 archetypes only,
        # using get_conf_detail (fine: power|high_mid|mid_major).
        buckets: dict[str, dict[str, dict[str, list[dict]]]] = {}
        for cg in ("national", "power", "mid_major"):
            buckets[cg] = {role: {"starter": [], "rotation": [], "all_starters": []}
                           for role in ("G", "Wing", "Big")}

        high_mid_buckets: dict[str, dict[str, list[dict]]] = {
            role: {"starter": [], "rotation": []}
            for role in ("G", "Wing", "Big")
        }

        nat_starter_bpr: dict[str, list[float]] = {"G": [], "Wing": [], "Big": []}

        for row in rows:
            slug = row.team.slug
            cg = get_conf_group(slug)           # coarse: 'power' | 'mid_major'
            cg_detail = get_conf_detail(slug)   # fine: 'power' | 'high_mid' | 'mid_major'
            role = row.role_bucket
            if role not in ("G", "Wing", "Big"):
                continue
            ms = row.minutes_share_p2
            if ms is None:
                continue

            record = {
                "player_id":    row.player_id,
                "obpr":         row.projected_obpr,
                "dbpr":         row.projected_dbpr,
                "bpr":          row.projected_bpr,
                "ms":           ms,
                "mpg":          row.mpg_p2,
                "uncertainty":  row.projection_uncertainty,
            }

            if ms >= STARTER_MS_MIN:
                buckets[cg][role]["starter"].append(record)
                buckets["national"][role]["all_starters"].append(record)
                nat_starter_bpr[role].append(row.projected_bpr)
                if cg_detail == "high_mid":
                    high_mid_buckets[role]["starter"].append(record)
            elif ms >= ROTATION_MS_MIN:
                buckets[cg][role]["rotation"].append(record)
                if cg_detail == "high_mid":
                    high_mid_buckets[role]["rotation"].append(record)

        # ── 3. Compute elite BPR thresholds (per role) ────────────────────── #
        elite_thresholds: dict[str, float] = {}
        for role in ("G", "Wing", "Big"):
            sorted_bpr = sorted(nat_starter_bpr[role])
            elite_thresholds[role] = _percentile(sorted_bpr, ELITE_BPR_PERCENTILE)
            self.stdout.write(
                f"  Elite BPR threshold [{role}]: ≥{elite_thresholds[role]:.3f} "
                f"(p{ELITE_BPR_PERCENTILE*100:.0f} of {len(sorted_bpr)} national starters)"
            )

        # ── 4. Load stat profiles (PlayerSeasonStats for season_year) ─────── #
        self.stdout.write("  Loading PlayerSeasonStats for stat profiles…")
        stat_qs = PlayerSeasonStats.objects.filter(season__year=season_year).values(
            "player_id",
            "efg_pct", "fg3_pct", "ts_pct", "ast_to",
            "oreb_pg", "dreb_pg", "tov",
        )
        stats_by_player: dict[int, dict] = {r["player_id"]: r for r in stat_qs}
        self.stdout.write(f"  Loaded {len(stats_by_player)} stat profiles.")

        # ── 5. Build each archetype ───────────────────────────────────────── #
        results = []
        for spec in _ARCHETYPES:
            key, display_name, conf_group, role, tier = spec
            player_records = self._select_bucket(
                buckets, high_mid_buckets, conf_group, role, tier, elite_thresholds
            )

            n = len(player_records)

            # Tier 2 archetypes (high_mid) are skipped — not just warned — when
            # the bucket is too small. This keeps the taxonomy clean.
            if conf_group == "high_mid" and n < MIN_SPECIFIC_BUCKET:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [{key}] SKIPPED: only {n} players in bucket "
                        f"(need ≥{MIN_SPECIFIC_BUCKET} for Tier 2 archetypes)"
                    )
                )
                continue

            if n < MIN_BUCKET_SIZE:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [{key}] WARNING: only {n} players in bucket (min {MIN_BUCKET_SIZE})"
                    )
                )

            # Projection medians
            obpr_vals  = [r["obpr"]        for r in player_records if r["obpr"]        is not None]
            dbpr_vals  = [r["dbpr"]        for r in player_records if r["dbpr"]        is not None]
            bpr_vals   = [r["bpr"]         for r in player_records if r["bpr"]         is not None]
            ms_vals    = [r["ms"]          for r in player_records if r["ms"]          is not None]
            mpg_vals   = [r["mpg"]         for r in player_records if r["mpg"]         is not None]
            unc_vals   = [r["uncertainty"] for r in player_records if r["uncertainty"] is not None]

            archetype_bpr = _median(bpr_vals) or 0.0

            # Bucket-aware uncertainty (improved formula combining base signal,
            # small-sample penalty, and BPR-spread penalty).
            base_unc = _median(unc_vals) or 0.5
            adjusted_unc = _bucket_uncertainty(base_unc, bpr_vals, n)

            # Stat profile medians from PlayerSeasonStats
            pids = [r["player_id"] for r in player_records]
            stat_rows = [stats_by_player[pid] for pid in pids if pid in stats_by_player]

            def stat_med(field: str) -> float | None:
                vals = [s[field] for s in stat_rows if s.get(field) is not None]
                return _median(vals)

            archetype = {
                "key":               key,
                "display_name":      display_name,
                "conf_group":        conf_group,
                "role_bucket":       role,
                "quality_tier":      tier,
                "projected_obpr":    _median(obpr_vals) or 0.0,
                "projected_dbpr":    _median(dbpr_vals) or 0.0,
                "projected_bpr":     archetype_bpr,
                "minutes_share":     _median(ms_vals) or 0.0,
                "mpg":               _median(mpg_vals) or 0.0,
                "uncertainty":       adjusted_unc,
                "efg_pct":           stat_med("efg_pct"),
                "fg3_pct":           stat_med("fg3_pct"),
                "ts_pct":            stat_med("ts_pct"),
                "ast_to":            stat_med("ast_to"),
                "oreb_pg":           stat_med("oreb_pg"),
                "dreb_pg":           stat_med("dreb_pg"),
                "tov":               stat_med("tov"),
                "sample_n":          n,
                "source_season_year": season_year,
            }
            results.append(archetype)
            self.stdout.write(
                f"  [{key}] n={n:4d}  BPR={archetype_bpr:+.2f}  "
                f"ms={archetype['minutes_share']:.3f}  unc={adjusted_unc:.3f}"
            )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\n[dry-run] Not writing to database."))
            return

        # ── 6. Upsert to DB ───────────────────────────────────────────────── #
        created = updated = 0
        for a in results:
            obj, was_created = PlaceholderArchetype.objects.update_or_create(
                key=a["key"],
                defaults={k: v for k, v in a.items() if k != "key"},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created} created, {updated} updated "
                f"({len(results)} total archetypes from season {season_year})."
            )
        )

    # ----------------------------------------------------------------------- #

    def _select_bucket(
        self,
        buckets: dict,
        high_mid_buckets: dict,
        conf_group: str,
        role: str,
        tier: str,
        elite_thresholds: dict[str, float],
    ) -> list[dict]:
        """Return the list of player records that belong to this archetype bucket."""
        if tier == "elite":
            # Elite: national starters above the BPR threshold for this role
            threshold = elite_thresholds[role]
            return [
                r for r in buckets["national"][role]["all_starters"]
                if (r["bpr"] or 0.0) >= threshold
            ]

        if conf_group == "high_mid":
            # Tier 2: uses the fine-grained high_mid bucket (WCC/MWC/A10/Amer)
            bucket_key = "starter" if tier == "starter" else "rotation"
            return high_mid_buckets[role][bucket_key]

        bucket_key = "starter" if tier == "starter" else "rotation"
        return buckets[conf_group][role][bucket_key]

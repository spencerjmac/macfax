"""
audit_offseason_moves — flag suspect TeamOutseasonMove classifications.

Phase 4 Stage 1, Step 3 (REPORT ONLY — no auto-fixes). Move details are
editorial data; corrections are a human decision. This command only surfaces
the rows a human should look at, severity-tagged.

Flags:
  HIGH  outside-nba-but-has-stats: detail says "outside NBA" yet the player
        has NBAPlayerSeasonStats rows — mislabeled origin (the Thomas Sorber
        class). The move loses a real BPR prior it should have.
  HIGH  orphan: a non-drafted move whose player_name will not resolve via the
        production name resolver (exact→normalized). It silently gets no prior
        BPR. Drafted rookies are NOT orphans — they legitimately predate our
        NBAPlayer table — so they are excluded from this flag.
  MED   signed-from-nba-team: move_type='signed' but detail points at a real
        NBA source team — likely a trade mislabeled as a free-agent signing
        (the Jared McCain class). AMBIGUOUS: a waive-then-sign is also possible,
        so this is flagged with evidence, not auto-corrected.
  LOW   drafted-missing-mps: a drafted move without mps_score (round/pick may
        still be present; the pick predictor survives, MPS is the nice-to-have).
  LOW   drafted-missing-pick: a drafted move without overall_pick or round —
        the pick-based rookie prior (Phase 4) cannot bin it.

Usage:
    python manage.py audit_offseason_moves
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand

from nba.models import NBAPlayer, NBAPlayerSeasonStats, TeamOutseasonMove
from nba.utils.name_utils import normalize_name

# a detail that names a real NBA source (slug or "outside NBA")
_ACQUIRED_RE = re.compile(r"acquired from\s+(.+)", re.IGNORECASE)


class Command(BaseCommand):
    help = "Report suspect offseason-move classifications (report only, no writes)."

    def handle(self, *args, **options):
        # normalized-name index of every NBAPlayer, mirroring the production
        # resolver's tier-2 (compute_nba_team_outlooks._resolve_player_by_name)
        norm_index: dict[str, list] = {}
        for p in NBAPlayer.objects.all().only("id", "name"):
            norm_index.setdefault(normalize_name(p.name), []).append(p)
        exact_names = {n.lower() for n in NBAPlayer.objects.values_list("name", flat=True)}
        team_slugs = set(
            TeamOutseasonMove.objects.exclude(team__isnull=True)
            .values_list("team__team_slug", flat=True)
        )

        def resolve(name: str):
            if name.lower() in exact_names:
                return "ok"
            c = norm_index.get(normalize_name(name), [])
            if len(c) == 1:
                return "ok"
            return "ambiguous" if len(c) > 1 else "orphan"

        def has_stats(name: str) -> bool:
            c = norm_index.get(normalize_name(name), [])
            ids = [p.id for p in c]
            if name.lower() in exact_names:
                ids += list(
                    NBAPlayer.objects.filter(name__iexact=name).values_list("id", flat=True)
                )
            if not ids:
                return False
            return NBAPlayerSeasonStats.objects.filter(
                player_id__in=ids, season_type="regular", bpr__isnull=False
            ).exists()

        findings: list[tuple[str, str, str, str]] = []  # (severity, flag, name, evidence)

        for m in TeamOutseasonMove.objects.select_related("team").all():
            detail = m.detail or ""
            low = detail.lower()

            # HIGH: outside-NBA but has stats
            if "outside" in low and has_stats(m.player_name):
                findings.append((
                    "HIGH", "outside-nba-but-has-stats", m.player_name,
                    f"{m.move_type}; detail={detail!r}; player HAS NBA stats",
                ))

            # HIGH: orphan (non-drafted, unresolvable)
            if m.move_type != "drafted":
                r = resolve(m.player_name)
                if r != "ok":
                    findings.append((
                        "HIGH", f"orphan-{r}", m.player_name,
                        f"{m.move_type}; name will not resolve → no prior BPR",
                    ))

            # MED: signed but sourced from a real NBA team
            if m.move_type == "signed":
                mo = _ACQUIRED_RE.search(low)
                src = mo.group(1).strip() if mo else ""
                if src and "outside" not in src:
                    findings.append((
                        "MED", "signed-from-nba-team", m.player_name,
                        f"detail={detail!r}; source looks like a trade, not an FA signing",
                    ))

            # LOW: drafted data gaps
            if m.move_type == "drafted":
                if m.overall_pick is None or m.round_number is None:
                    findings.append((
                        "LOW", "drafted-missing-pick", m.player_name,
                        f"overall_pick={m.overall_pick}, round={m.round_number}",
                    ))
                elif m.mps_score is None:
                    findings.append((
                        "LOW", "drafted-missing-mps", m.player_name,
                        f"pick {m.overall_pick} present; mps_score is null",
                    ))

        self._print(findings)

    def _print(self, findings):
        order = {"HIGH": 0, "MED": 1, "LOW": 2}
        findings.sort(key=lambda f: (order[f[0]], f[1], f[2]))
        total = TeamOutseasonMove.objects.count()
        self.stdout.write(f"\n{'='*70}\nOFFSEASON MOVE AUDIT — {total} moves, {len(findings)} findings\n{'='*70}")
        from collections import Counter
        by_sev = Counter(f[0] for f in findings)
        by_flag = Counter(f[1] for f in findings)
        self.stdout.write(f"  by severity: {dict(by_sev)}")
        self.stdout.write(f"  by flag: {dict(by_flag)}\n")
        cur = None
        for sev, flag, name, ev in findings:
            if sev != cur:
                self.stdout.write(f"\n── {sev} ──")
                cur = sev
            self.stdout.write(f"  [{flag}] {name:28} {ev}")
        self.stdout.write(self.style.WARNING(
            "\nREPORT ONLY — no rows modified. Move details are editorial; "
            "corrections are a human decision."
        ))

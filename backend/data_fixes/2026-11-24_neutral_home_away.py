"""
Normalize TeamGameStats.home_away on neutral-site games: 'N' wherever Game.neutral_site is set.

Why: NCAA-sourced games (2026+) arrive without a neutral flag, so their box rows are written 'H' / 'A'.
backfill_neutral_flags sets Game.neutral_site from ESPN afterwards but, until the fix that ships with
this script, left the box rows alone. ESPN-sourced seasons (2008-2025) already store 'N' on every
flagged game, so only 2026+ rows change. game_site() reads the flag first either way; this makes the
stored rows agree with it. Rows with 'N' on an unflagged game are reported but not touched (none
are known).

  python data_fixes/2026-11-24_neutral_home_away.py                  # rehearsal: counts + asserts, rolled back
  python data_fixes/2026-11-24_neutral_home_away.py --apply          # commit
  python data_fixes/2026-11-24_neutral_home_away.py --expect 1178    # also assert the number of rows changed

Run from backend/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402

from ncaa.models import TeamGameStats  # noqa: E402
from ncaa.models.games import sync_home_away_to_site  # noqa: E402


class Rehearsal(Exception):
    pass


def counts():
    with connection.cursor() as c:
        c.execute("""
            SELECT g.season_year,
                   sum((g.neutral_site AND t.home_away IN ('H', 'A'))::int),
                   sum((NOT g.neutral_site AND t.home_away = 'N')::int)
            FROM core_teamgamestats t JOIN core_game g ON g.id = t.game_id
            GROUP BY 1
            HAVING sum((g.neutral_site AND t.home_away IN ('H', 'A'))::int) > 0
                OR sum((NOT g.neutral_site AND t.home_away = 'N')::int) > 0
            ORDER BY 1""")
        return {y: (a, b) for y, a, b in c.fetchall()}


def main():
    apply = "--apply" in sys.argv
    expect = int(sys.argv[sys.argv.index("--expect") + 1]) if "--expect" in sys.argv else None

    before = counts()
    print("before (season: flagged games with H/A rows, unflagged games with N rows):", before or "none")
    game_ids = set(TeamGameStats.objects.filter(game__neutral_site=True, home_away__in=["H", "A"])
                   .values_list("game_id", flat=True))
    rows_expected = sum(a for a, _ in before.values())
    seasons = sorted(y for y, (a, _) in before.items() if a)
    assert all(y >= 2026 for y in seasons), f"only 2026+ rows should need this, found seasons {seasons}"

    try:
        with transaction.atomic():
            changed = sync_home_away_to_site(game_ids)
            after = counts()
            print(f"games {len(game_ids)}, rows changed {changed}")
            print("after:", after or "none")
            assert changed == rows_expected, f"changed {changed} rows, expected {rows_expected}"
            assert all(a == 0 for a, _ in after.values()), "flagged games with H/A rows remain"
            if expect is not None:
                assert changed == expect, f"changed {changed} rows, --expect {expect}"
            if not apply:
                raise Rehearsal
    except Rehearsal:
        print("REHEARSAL: rolled back (pass --apply to commit)")
        return
    print("APPLIED")


if __name__ == "__main__":
    main()

"""
Mark 2005-2007 NCAA tournament games neutral-site.

Why: no 2005-2007 game has a neutral flag. The source has none (ESPN's own neutralSite is false for every
game of those seasons, NCAA tournament included; from 2008 on it matches Game.neutral_site exactly), so
every game counts as a home game in the ratings, HCA, SOS, SOR, WAB, game value and quadrants. The NCAA
tournament is the one set of games known to be neutral. Other neutral games of those seasons (early-season
events, conference tournaments) stay unflagged: see docs/known_issues.md.

Which games: ESPN's tournamentId 22 (NCAA tournament) in raw_json, plus the opening-round game at Dayton,
which has no tournamentId: after Selection Sunday, headline mentioning REGION or PLAY-IN, and not NIT.
That is 64 games a season (63 + the opening round). All are after Selection Sunday, so pre-tournament
ratings cannot change.

Sets Game.neutral_site and the box rows' home_away ('N', via sync_home_away_to_site), as 2008+ store them.

  python data_fixes/2026-11-24_ncaa_tourney_neutral_2005_2007.py           # rehearsal: asserts, rolled back
  python data_fixes/2026-11-24_ncaa_tourney_neutral_2005_2007.py --apply   # commit

Run from backend/. Idempotent: a second --apply changes nothing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402

from ncaa.models import Game, TeamGameStats  # noqa: E402
from ncaa.models.games import sync_home_away_to_site  # noqa: E402

SEASONS = (2005, 2006, 2007)
GAMES_PER_SEASON = 64


class Rehearsal(Exception):
    pass


def tournament_games():
    """{season: [(game id, game_date, selection_sunday_date, neutral_site)]} by the rule in the docstring."""
    with connection.cursor() as c:
        c.execute("""
            SELECT g.season_year, g.id, g.game_date, s.selection_sunday_date, g.neutral_site
            FROM core_game g JOIN core_season s ON s.year = g.season_year
            WHERE g.season_year = ANY(%s) AND g.status = 'final'
              AND ((g.raw_json -> '_raw' -> 'competitions' -> 0 ->> 'tournamentId') = '22'
                   OR (g.game_date > s.selection_sunday_date
                       AND coalesce(g.raw_json -> '_raw' -> 'competitions' -> 0 -> 'notes' -> 0 ->> 'headline', '')
                           ~* '(REGION|PLAY-IN)'
                       AND coalesce(g.raw_json -> '_raw' -> 'competitions' -> 0 -> 'notes' -> 0 ->> 'headline', '')
                           !~* 'NIT'))
            ORDER BY 1, 3""", [list(SEASONS)])
        out = {y: [] for y in SEASONS}
        for y, gid, d, ss, ns in c.fetchall():
            out[y].append((gid, d, ss, ns))
        return out


def main():
    apply = "--apply" in sys.argv
    found = tournament_games()
    for y in SEASONS:
        games = found[y]
        assert len(games) == GAMES_PER_SEASON, f"{y}: {len(games)} tournament games, expected {GAMES_PER_SEASON}"
        assert all(d > ss for _, d, ss, _ in games), f"{y}: a tournament game on or before Selection Sunday"
        print(f"{y}: {len(games)} games, {sum(1 for *_, ns in games if ns)} already neutral, "
              f"{games[0][1]} to {games[-1][1]}")
    ids = [gid for y in SEASONS for gid, *_ in found[y]]
    other_before = Game.objects.filter(season_year__in=SEASONS, neutral_site=True).exclude(id__in=ids).count()
    try:
        with transaction.atomic():
            flagged = Game.objects.filter(id__in=ids, neutral_site=False).update(neutral_site=True)
            rows = sync_home_away_to_site(ids)
            print(f"games flagged {flagged}, box rows set to 'N' {rows}")
            assert Game.objects.filter(id__in=ids, neutral_site=False).count() == 0
            assert TeamGameStats.objects.filter(game_id__in=ids).exclude(home_away="N").count() == 0
            assert Game.objects.filter(season_year__in=SEASONS, neutral_site=True).exclude(id__in=ids).count() \
                == other_before, "a game outside the tournament changed"
            if not apply:
                raise Rehearsal
    except Rehearsal:
        print("REHEARSAL: rolled back (pass --apply to commit)")
        return
    print("APPLIED")


if __name__ == "__main__":
    main()

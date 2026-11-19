"""
Task 12 step 2: undo the Player field overwrites from Task 11's 2014 trial.

Task 11's write_player_rows upserted Player identity fields from the 2014 ESPN boxes, so 1,412 players who already
existed got their 2014 name / short name / jersey / position / headshot. 323 of them differed from before (322
jerseys, 1 short name, 1 headshot). 2026-11-16_task12_restore_player_fields.csv holds their values from the
pre-Task-11 dump (backups/macfax_20261116_094656_pre_task11_backfill_sample.dump, core_player restored into a
scratch database). The backfill script (2026-11-16_task12_player_backfill_2005_2014.py) only inserts new players.

  python data_fixes/2026-11-16_task12_restore_player_fields.py [--apply]     (from backend/; default: rehearsal)
"""
import csv, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()
from django.db import connection, transaction  # noqa: E402

from ncaa.models import Player  # noqa: E402

CSV = Path(__file__).resolve().parent / "2026-11-16_task12_restore_player_fields.csv"
FIELDS = ["display_name", "short_name", "jersey", "position", "headshot_url"]


class Rollback(Exception):
    pass


def expect(label, got, want):
    print(f"  {label}: {got}" + ("" if got == want else f"  (EXPECTED {want})"))
    if got != want:
        raise SystemExit(f"assertion failed: {label}")


def others_checksum(ids):
    with connection.cursor() as c:
        c.execute("""select count(*), md5(string_agg(id || ':' || espn_athlete_id || ':' || display_name || ':' || short_name
                     || ':' || jersey || ':' || position || ':' || headshot_url, ',' order by id))
                     from core_player where not (id = any(%s))""", [ids])
        return c.fetchone()


def run():
    rows = list(csv.DictReader(open(CSV)))
    expect("rows in CSV", len(rows), 323)
    ids = [int(r["player_id"]) for r in rows]
    cur = {p.id: p for p in Player.objects.filter(id__in=ids)}
    expect("players found, ESPN id matching", sum(1 for r in rows if int(r["player_id"]) in cur
           and cur[int(r["player_id"])].espn_athlete_id == r["espn_athlete_id"]), 323)
    expect("players currently differing from the CSV", sum(1 for r in rows if any(
        getattr(cur[int(r["player_id"])], f) != r[f] for f in FIELDS)), 323)
    before = others_checksum(ids)
    for r in rows:
        p = cur[int(r["player_id"])]
        for f in FIELDS:
            setattr(p, f, r[f])
    expect("players updated", Player.objects.bulk_update(list(cur.values()), FIELDS), 323)
    after = {p.id: p for p in Player.objects.filter(id__in=ids)}
    expect("players now equal to the CSV", sum(1 for r in rows if all(
        getattr(after[int(r["player_id"])], f) == r[f] for f in FIELDS)), 323)
    expect("other players unchanged", others_checksum(ids), before)


if __name__ == "__main__":
    if "--apply" not in sys.argv:
        try:
            with transaction.atomic():
                run(); raise Rollback()
        except Rollback:
            print("REHEARSAL OK (rolled back)")
        sys.exit(0)
    with transaction.atomic():
        run()
    print("DONE")

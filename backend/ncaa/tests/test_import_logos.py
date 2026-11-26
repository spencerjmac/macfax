"""import_logos: mapping by Team.name and the current-season "D1 without a logo" warning."""
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from ncaa.models import Season, Team, TeamSeasonMembership


class ImportLogosTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2027, display_name="2026-27", is_current=True)
        # Names as the DB stores them (NCAA style); both need a mapping entry
        self.wmu = Team.objects.create(name="Western Mich.", slug="western-mich", is_d1=True)
        self.uwf = Team.objects.create(name="West Florida", slug="west-florida", is_d1=True)
        self.nomap = Team.objects.create(name="Nowhere St.", slug="nowhere-st", is_d1=True)
        self.non_d1 = Team.objects.create(name="Some College", slug="some-college", is_d1=False)
        for t in (self.wmu, self.uwf, self.nomap):
            TeamSeasonMembership.objects.create(season=self.season, team=t, is_d1=True,
                                                is_reclassifying=False, source="manual")
        self.tmp = tempfile.TemporaryDirectory()
        for stem in ("western_michigan_broncos", "west_florida_argonauts"):
            Path(self.tmp.name, f"{stem}.png").write_bytes(b"\x89PNG")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        out = StringIO()
        call_command("import_logos", logos_dir=self.tmp.name, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_abbreviated_names_map_and_missing_d1_are_listed(self):
        output = self._run()
        self.wmu.refresh_from_db()
        self.uwf.refresh_from_db()
        self.assertEqual(self.wmu.logo_url, "/static/logos/western_michigan_broncos.png")
        self.assertEqual(self.uwf.logo_url, "/static/logos/west_florida_argonauts.png")
        self.assertIn("Updated: 2", output)
        # Only the current-season D1 team without a logo is listed (not the non-D1 team)
        self.assertIn("2027 D1 teams without a logo (1): Nowhere St.", output)
        self.assertNotIn("Some College", output.split("without a logo")[-1])

    def test_all_logos_present_says_so(self):
        self.nomap.logo_url = "/static/logos/whatever.png"
        self.nomap.save(update_fields=["logo_url"])
        output = self._run()
        self.assertIn("All 2027 D1 teams have a logo.", output)

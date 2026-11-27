"""
TeamMapper name matching: no confident mapping from a lossy name match (Task 6c).

TeamMapper._normalize strips "college"/"university"/"state"/"the", so different schools share a key:
"Boston College" and "Boston University" are both "boston"; "Georgia", "Georgia College" and
"Georgia State" are all "georgia"; "Texas College" is "texas". The old exact-normalized match
returned whichever team was indexed last with confidence 1.0, and map_and_save stored it as a
permanent TeamExternalId. That is how ESPN 103 (Boston College) landed on Boston University and
how Georgia's opponents' box rows came to point at Georgia College.

Invariants pinned here:
- A name equal to one team's name (case and punctuation ignored) still maps with confidence 1.0.
- A name that only matches after stripping those words, or whose key hits several teams, is
  ambiguous: find_team returns no team, it is logged in mapper.ambiguous, and map_and_save saves
  no TeamExternalId and creates no team.
- An ambiguous key never resolves in search_index.
- "&" is spelled out, so "Missouri S&T" is not "Missouri St.".
"""

from django.test import TestCase

from ncaa.models import Team, TeamExternalId
from ncaa.utils.team_mapping import TeamMapper


def make(name, is_d1=True, slug=None):
    return Team.objects.create(name=name, slug=slug or name.lower().replace(" ", "-").replace(".", "")
                               .replace("&", "and"), is_d1=is_d1)


class MapperTestBase(TestCase):
    source = "espn"

    def mapper(self):
        # No override file: test the name logic only.
        return TeamMapper(source=self.source, override_file="/nonexistent/overrides.yml")

    def assertMaps(self, mapper, name, team):
        found, conf, _ = mapper.find_team(name)
        self.assertEqual(found, team, f"{name!r} should map to {team}")
        self.assertEqual(conf, 1.0)

    def assertAmbiguous(self, mapper, name):
        found, conf, _ = mapper.find_team(name)
        self.assertIsNone(found, f"{name!r} must not map")
        self.assertEqual(conf, 0.0)
        self.assertIn(name, [a["external_name"] for a in mapper.ambiguous])


class BostonTests(MapperTestBase):
    def setUp(self):
        self.bc = make("Boston College")
        self.bu = make("Boston University")

    def test_each_full_name_maps_to_its_own_school(self):
        m = self.mapper()
        self.assertMaps(m, "Boston College", self.bc)
        self.assertMaps(m, "Boston University", self.bu)
        self.assertMaps(m, "boston college", self.bc)

    def test_shared_key_is_ambiguous_not_last_added(self):
        m = self.mapper()
        self.assertNotIn("boston", m.search_index)
        self.assertEqual(m.ambiguous_keys["boston"], sorted([self.bc.id, self.bu.id]))
        self.assertAmbiguous(m, "Boston")

    def test_bc_name_never_saved_against_bu(self):
        # The original bug: BC missing from the index, ESPN 103 "Boston College" -> BU.
        self.bc.delete()
        m = self.mapper()
        self.assertIsNone(m.map_and_save("Boston College", "103"))
        self.assertFalse(TeamExternalId.objects.filter(source="espn", external_id="103").exists())
        self.assertAmbiguous(m, "Boston College")


class GeorgiaTests(MapperTestBase):
    def setUp(self):
        self.uga = make("Georgia")
        self.gcsu = make("Georgia College", is_d1=False)
        self.gsu = make("Georgia St.")

    def test_exact_names_map(self):
        m = self.mapper()
        self.assertMaps(m, "Georgia", self.uga)
        self.assertMaps(m, "Georgia College", self.gcsu)
        self.assertMaps(m, "Georgia St.", self.gsu)
        self.assertMaps(m, "Georgia St", self.gsu)

    def test_georgia_key_does_not_resolve_to_georgia_college(self):
        m = self.mapper()
        self.assertNotIn("georgia", m.search_index)
        self.assertEqual(m.ambiguous_keys["georgia"], sorted([self.uga.id, self.gcsu.id]))

    def test_georgia_state_is_ambiguous(self):
        # "Georgia State" strips to "georgia" (Georgia and Georgia College), never to Georgia St.
        m = self.mapper()
        self.assertAmbiguous(m, "Georgia State")
        self.assertIsNone(m.map_and_save("Georgia State", "999001"))
        self.assertFalse(TeamExternalId.objects.filter(external_id="999001").exists())

    def test_georgia_without_its_own_row_is_not_mapped_to_georgia_college(self):
        self.uga.delete()
        m = self.mapper()
        self.assertAmbiguous(m, "Georgia")
        self.assertIsNone(m.map_and_save("Georgia", "61"))
        self.assertFalse(TeamExternalId.objects.filter(external_id="61").exists())


class MissouriTests(MapperTestBase):
    def setUp(self):
        self.mizzou = make("Missouri")
        self.mostate = make("Missouri St.")

    def test_missouri_snt_is_not_missouri_st(self):
        m = self.mapper()
        self.assertNotEqual(m._literal("Missouri S&T"), m._literal("Missouri St."))
        found, _, _ = m.find_team("Missouri S&T")
        self.assertIsNone(found)
        self.assertIsNone(m.map_and_save("Missouri S&T", "2402"))
        self.assertFalse(TeamExternalId.objects.filter(external_id="2402").exists())

    def test_missouri_snt_maps_once_it_has_a_team(self):
        snt = make("Missouri S&T", is_d1=False)
        m = self.mapper()
        self.assertMaps(m, "Missouri S&T", snt)
        self.assertMaps(m, "Missouri St.", self.mostate)

    def test_missouri_state_is_not_missouri(self):
        m = self.mapper()
        self.assertAmbiguous(m, "Missouri State")


class TexasTests(MapperTestBase):
    def setUp(self):
        self.texas = make("Texas")

    def test_texas_college_is_not_texas(self):
        m = self.mapper()
        self.assertAmbiguous(m, "Texas College")
        self.assertIsNone(m.map_and_save("Texas College", "2637"))
        self.assertFalse(TeamExternalId.objects.filter(external_id="2637").exists())
        self.assertFalse(Team.objects.filter(name="Texas College").exists())

    def test_texas_college_maps_to_its_own_team(self):
        tc = make("Texas College", is_d1=False)
        m = self.mapper()
        self.assertMaps(m, "Texas College", tc)
        self.assertMaps(m, "Texas", self.texas)

    def test_unambiguous_exact_match_still_saves(self):
        m = self.mapper()
        mapping = m.map_and_save("Texas", "251")
        self.assertEqual(mapping.team, self.texas)
        self.assertEqual(mapping.confidence, 1.0)


class NcaaRenamedTeamTests(TestCase):
    """2026-27: the NCAA scoreboard renamed New Orleans to "LSU New Orleans " (trailing space). The name
    missed ncaa_team_name_mappings.yml, so map_and_save created a non-D1 "LSU New Orleans " team, its
    games went there, and New Orleans (D1) fell out of the rankings with no games."""

    def setUp(self):
        self.uno = make("New Orleans")

    def test_lsu_new_orleans_maps_to_new_orleans(self):
        m = TeamMapper(source="ncaa")
        for name in ("LSU New Orleans ", "LSU New Orleans", " New Orleans "):
            found, conf, _ = m.find_team(name)
            self.assertEqual(found, self.uno, repr(name))
            self.assertEqual(conf, 1.0)

    def test_no_non_d1_team_created(self):
        m = TeamMapper(source="ncaa")
        mapping = m.map_and_save("LSU New Orleans ", "6652878_home")
        self.assertEqual(mapping.team, self.uno)
        self.assertEqual(Team.objects.count(), 1)


class NcaaNonD1ReuseTests(TestCase):
    """2026-11-27: the NCAA ingest created non-D1 opponents with get_or_create(name=...), so a school the
    ESPN side had already created under its own name got a second row ("Mt. St. Mary (NY)" beside
    "Mount St Mary"), and its games could not be matched to ESPN. Before creating a non-D1 team,
    map_and_save reuses a team whose name, alias, or ESPN mapping name equals the NCAA name."""

    def mapper(self):
        return TeamMapper(source="ncaa", override_file="/nonexistent/overrides.yml")

    def test_reuses_a_team_with_the_name_as_alias(self):
        keep = Team.objects.create(slug="mount-st-mary", name="Mount St Mary", is_d1=False,
                                   aliases=["Mt. St. Mary (NY)", "Mount St Mary Knights"])
        mapping = self.mapper().map_and_save("Mt. St. Mary (NY)", "6649646_away")
        self.assertEqual(mapping.team, keep)
        self.assertEqual(Team.objects.count(), 1)

    def test_reuses_a_team_by_its_espn_mapping_name(self):
        keep = make("East West", is_d1=False)
        TeamExternalId.objects.create(team=keep, source="espn", external_id="3107", external_name="East-West U.")
        mapping = self.mapper().map_and_save("East-West U.", "6648874_away")
        self.assertEqual(mapping.team, keep)
        self.assertEqual(Team.objects.count(), 1)
        self.assertEqual(TeamExternalId.objects.get(team=keep, source="espn").external_id, "3107")   # untouched

    def test_name_match_ignores_case_punctuation_and_padding(self):
        keep = make("St. Joseph's (Brkln)", is_d1=False, slug="st-josephs-brooklyn")
        mapping = self.mapper().map_and_save(" st josephs (brkln) ", "6656306_away")
        self.assertEqual(mapping.team, keep)
        self.assertEqual(Team.objects.count(), 1)

    def test_new_school_is_created_once_and_reused(self):
        m = self.mapper()
        first = m.map_and_save("Warner", "1_away").team
        self.assertFalse(first.is_d1)
        self.assertEqual(m.map_and_save("Warner", "2_away").team, first)          # same run
        self.assertEqual(self.mapper().map_and_save("WARNER", "3_away").team, first)   # later run
        self.assertEqual(Team.objects.count(), 1)

    def test_several_candidates_are_ambiguous_and_neither_is_reused(self):
        a = Team.objects.create(slug="trinity-tx", name="Trinity (TX)", is_d1=False, aliases=["Trinity"])
        b = Team.objects.create(slug="trinity-ct", name="Trinity (CT)", is_d1=False, aliases=["Trinity"])
        m = self.mapper()
        team = m.map_and_save("Trinity", "9_away").team
        self.assertNotIn(team, (a, b))
        self.assertEqual(team.name, "Trinity")
        self.assertTrue(any(x["reason"] == "several existing teams" for x in m.ambiguous))

    def test_dry_run_creates_nothing(self):
        self.assertIsNone(self.mapper().map_and_save("Warner", "1_away", dry_run=True))
        self.assertEqual(Team.objects.count(), 0)

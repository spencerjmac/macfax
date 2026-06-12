"""
DRF Serializers for CBB Analytics API
"""

from django.db import models
from rest_framework import serializers
from ncaa.models import (
    Season,
    Conference,
    Team,
    TeamSeasonStats,
    Game,
    TeamGameStats,
    ScoringEvent,
    TeamSeasonMetrics,
    TeamSeasonRatings,
    DataProcessingJob,
    PipelineConfig,
    PlayerSeasonStats,
    PlaceholderArchetype,
)
from .checklist import compute_national_champion_checklist, compute_season_context


class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ["id", "year", "display_name", "is_current"]


class ConferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conference
        fields = ["id", "code", "name"]


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "slug", "name", "aliases", "logo_url"]


class TeamSeasonStatsSerializer(serializers.ModelSerializer):
    """Full stats for a team in a season"""

    team_name = serializers.CharField(source="team.name", read_only=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True)
    team_logo = serializers.CharField(source="team.logo_url", read_only=True)
    conference_code = serializers.CharField(source="conference.code", read_only=True)
    conference_name = serializers.CharField(source="conference.name", read_only=True)
    season_year = serializers.IntegerField(source="season.year", read_only=True)
    record = serializers.CharField(read_only=True)
    national_champion_checklist = serializers.SerializerMethodField()

    class Meta:
        model = TeamSeasonStats
        fields = [
            # Identifiers
            "id",
            "team_name",
            "team_slug",
            "team_logo",
            "conference_code",
            "conference_name",
            "season_year",
            # Record
            "games",
            "wins",
            "losses",
            "record",
            # Rankings
            "rank",
            "rank_adj_em",
            "rank_adj_o",
            "rank_adj_d",
            "rank_aor",
            "rank_adr",
            "rank_aem",
            "rank_four_factor_index_100",
            "t_rank",
            "ap_poll_week6",
            # Core Metrics
            "adj_em",
            "adj_o",
            "adj_d",
            "adj_tempo",
            # Game-Level Adjusted Ratings (NEW)
            "aor",
            "adr",
            "aem",
            "aor_100",
            "adr_100",
            "net_100",
            # Four Factors - Offense
            "efg_pct",
            "tov_pct",
            "orb_pct",
            "ftr",
            # Four Factors - Defense
            "efg_pct_d",
            "tov_pct_d",
            "drb_pct",
            "ftr_d",
            # Margins
            "efg_margin",
            "tov_edge",
            "reb_edge",
            "ftr_margin",
            # Four Factor Index (Z-scores and composite metric)
            "efg_margin_z",
            "tov_edge_z",
            "reb_edge_z",
            "ftr_margin_z",
            "four_factor_index_wz",
            "four_factor_index_100",
            # Shooting Splits
            "fg2_pct",
            "fg2_pct_d",
            "fg3_pct",
            "fg3_pct_d",
            "fg3_rate",
            "fg3_rate_d",
            "ft_pct",
            # Resume
            "wab",
            "sor",
            "barthag",
            "luck",
            "sos_adj_em",
            "ncsos_adj_em",
            # National Champion Checklist
            "national_champion_checklist",
            # Provenance
            "has_kenpom",
            "has_torvik",
            "has_cbb_analytics",
            "last_updated",
        ]

    def get_national_champion_checklist(self, obj):
        """Compute the national champion checklist for this team"""
        # Check if we have cached season context in the serializer context
        context = self.context.get("season_context")

        # If not cached, compute it (less efficient, but works)
        if context is None:
            context = compute_season_context(obj.season)

        return compute_national_champion_checklist(obj, context)


class RankingsSerializer(serializers.Serializer):
    """
    Simplified serializer for rankings table
    Combines data from TeamSeasonRatings and TeamSeasonMetrics
    """

    rank = serializers.IntegerField(source="d1_rank")
    team_name = serializers.CharField(source="team.name")
    team_slug = serializers.CharField(source="team.slug")
    team_logo = serializers.CharField(source="team.logo_url")
    season_display = serializers.CharField(source="season.display_name")
    conference = serializers.SerializerMethodField()
    record = serializers.SerializerMethodField()

    # Adjusted ratings from TeamSeasonRatings
    adj_em = serializers.FloatField()
    adj_o = serializers.FloatField()
    adj_d = serializers.FloatField()
    adj_tempo = serializers.FloatField()

    # Four Factor Index - Adjusted
    four_factor_index_100 = serializers.FloatField(source="ffi_raw")
    rank_four_factor_index_100 = serializers.SerializerMethodField()

    # Four Factor Index - Raw
    raw_four_factor_index_100 = serializers.FloatField(source="ffi_raw")

    # Raw Four Factors (from TeamSeasonMetrics)
    raw_efg_pct = serializers.SerializerMethodField()
    raw_tov_pct = serializers.SerializerMethodField()
    raw_orb_pct = serializers.SerializerMethodField()
    raw_ftr = serializers.SerializerMethodField()
    raw_efg_pct_d = serializers.SerializerMethodField()
    raw_tov_pct_d = serializers.SerializerMethodField()
    raw_orb_pct_d = serializers.SerializerMethodField()  # Opponent ORB%
    raw_ftr_d = serializers.SerializerMethodField()
    raw_efg_margin = serializers.SerializerMethodField()
    raw_tov_edge = serializers.SerializerMethodField()
    raw_reb_edge = serializers.SerializerMethodField()
    raw_ftr_margin = serializers.SerializerMethodField()

    # Adjusted Four Factors (from TeamSeasonRatings)
    efg_pct = serializers.FloatField(source="adj_efg_pct")
    tov_pct = serializers.FloatField(source="adj_tov_pct")
    orb_pct = serializers.FloatField(source="adj_orb_pct")
    ftr = serializers.FloatField(source="adj_ftr")
    efg_pct_d = serializers.FloatField(source="adj_opp_efg_pct")
    tov_pct_d = serializers.FloatField(source="adj_opp_tov_pct")
    orb_pct_d = serializers.FloatField(source="adj_opp_orb_pct")  # Opponent ORB%
    ftr_d = serializers.FloatField(source="adj_opp_ftr")

    # Adjusted Four Factor Margins
    efg_margin = serializers.FloatField(source="adj_efg_margin")
    tov_edge = serializers.FloatField(source="adj_tov_edge")
    reb_edge = serializers.FloatField(source="adj_reb_edge")
    ftr_margin = serializers.FloatField(source="adj_ftr_margin")

    # Shooting Splits (from TeamSeasonMetrics)
    fg2_pct = serializers.SerializerMethodField()
    fg3_pct = serializers.SerializerMethodField()
    ft_pct = serializers.SerializerMethodField()
    fg3_rate = serializers.SerializerMethodField()

    # Resume Metrics
    wab = serializers.FloatField()
    sor_rank = serializers.IntegerField()
    net_rank = serializers.IntegerField()
    sos_rank = serializers.IntegerField()
    sos_win_pct = serializers.FloatField()
    ap_poll_week6 = serializers.IntegerField(allow_null=True, required=False)

    # NCAA Tournament
    tournament_seed = serializers.IntegerField(allow_null=True, required=False)
    tournament_region = serializers.CharField(allow_null=True, required=False)
    tournament_finish = serializers.CharField(allow_null=True, required=False)

    # Legacy fields for compatibility
    aor_100 = serializers.FloatField(source="adj_o")
    adr_100 = serializers.FloatField(source="adj_d")
    net_100 = serializers.FloatField(source="adj_em")

    def get_conference(self, obj):
        """Get conference - try multiple sources"""
        # Try TeamSeasonMetrics first (might have been set from past scrapers)
        # Use cached metrics if available (set in view with prefetch_related)
        try:
            if hasattr(obj, '_metrics_cache'):
                metrics = obj._metrics_cache
            else:
                metrics = TeamSeasonMetrics.objects.filter(
                    team=obj.team, season=obj.season
                ).first()
            if metrics and hasattr(metrics, "conference") and metrics.conference:
                return metrics.conference.code
        except:
            pass

        # Comprehensive conference mappings for ALL D1 teams (2025-26 season)
        conf_map = {
            # Big Ten (B10) - 18 teams
            "michigan": "B10",
            "michigan-state": "B10",
            "michigan-st": "B10",
            "ohio-state": "B10",
            "ohio-st": "B10",
            "purdue": "B10",
            "illinois": "B10",
            "indiana": "B10",
            "iowa": "B10",
            "wisconsin": "B10",
            "maryland": "B10",
            "penn-state": "B10",
            "penn-st": "B10",
            "rutgers": "B10",
            "nebraska": "B10",
            "minnesota": "B10",
            "northwestern": "B10",
            "ucla": "B10",
            "usc": "B10",
            "oregon": "B10",
            "washington": "B10",
            # ACC - Atlantic Coast Conference
            "duke": "ACC",
            "north-carolina": "ACC",
            "unc": "ACC",
            "virginia": "ACC",
            "louisville": "ACC",
            "syracuse": "ACC",
            "florida-state": "ACC",
            "florida-st": "ACC",
            "nc-state": "ACC",
            "clemson": "ACC",
            "wake-forest": "ACC",
            "miami": "ACC",
            "miami-fl": "ACC",
            "miami-(fl)": "ACC",
            "georgia-tech": "ACC",
            "boston-college": "ACC",
            "virginia-tech": "ACC",
            "pitt": "ACC",
            "pittsburgh": "ACC",
            "notre-dame": "ACC",
            "california": "ACC",
            "stanford": "ACC",
            "smu": "ACC",
            # Big 12 (B12)
            "kansas": "B12",
            "baylor": "B12",
            "iowa-st": "B12",
            "iowa-state": "B12",
            "texas-tech": "B12",
            "tcu": "B12",
            "oklahoma-state": "B12",
            "oklahoma-st": "B12",
            "west-virginia": "B12",
            "kansas-state": "B12",
            "kansas-st": "B12",
            "houston": "B12",
            "cincinnati": "B12",
            "ucf": "B12",
            "byu": "B12",
            "colorado": "B12",
            "arizona": "B12",
            "arizona-state": "B12",
            "arizona-st": "B12",
            "utah": "B12",
            # SEC - Southeastern Conference
            "kentucky": "SEC",
            "florida": "SEC",
            "tennessee": "SEC",
            "arkansas": "SEC",
            "alabama": "SEC",
            "auburn": "SEC",
            "lsu": "SEC",
            "mississippi-state": "SEC",
            "mississippi-st": "SEC",
            "georgia": "SEC",
            "missouri": "SEC",
            "south-carolina": "SEC",
            "vanderbilt": "SEC",
            "texas": "SEC",
            "texas-am": "SEC",
            "texas-a-m": "SEC",
            "texas-a&m": "SEC",
            "ole-miss": "SEC",
            "mississippi": "SEC",
            "oklahoma": "SEC",
            # Big East (BE)
            "connecticut": "BE",
            "uconn": "BE",
            "villanova": "BE",
            "creighton": "BE",
            "marquette": "BE",
            "st-johns": "BE",
            "st-john-s": "BE",
            "st-john's": "BE",
            "providence": "BE",
            "xavier": "BE",
            "butler": "BE",
            "seton-hall": "BE",
            "depaul": "BE",
            "georgetown": "BE",
            # WCC - West Coast Conference
            "gonzaga": "WCC",
            "saint-marys": "WCC",
            "saint-mary-s": "WCC",
            "saint-mary's": "WCC",
            "st-marys": "WCC",
            "san-francisco": "WCC",
            "santa-clara": "WCC",
            "loyola-marymount": "WCC",
            "pepperdine": "WCC",
            "portland": "WCC",
            "pacific": "WCC",
            "san-diego": "WCC",
            "oregon-st": "WCC",
            "washington-st": "WCC",
            "seattle": "WCC",
            "seattle-u": "WCC",
            # Mountain West (MWC)
            "utah-st": "MWC",
            "utah-state": "MWC",
            "san-diego-state": "MWC",
            "san-diego-st": "MWC",
            "sdsu": "MWC",
            "nevada": "MWC",
            "unlv": "MWC",
            "colorado-state": "MWC",
            "colorado-st": "MWC",
            "new-mexico": "MWC",
            "boise-state": "MWC",
            "boise-st": "MWC",
            "wyoming": "MWC",
            "fresno-state": "MWC",
            "fresno-st": "MWC",
            "air-force": "MWC",
            "san-jose-state": "MWC",
            "san-jose-st": "MWC",
            "grand-canyon": "MWC",
            # Atlantic 10 (A10)
            "saint-louis": "A10",
            "st-louis": "A10",
            "dayton": "A10",
            "vcu": "A10",
            "richmond": "A10",
            "st-bonaventure": "A10",
            "saint-bonaventure": "A10",
            "davidson": "A10",
            "rhode-island": "A10",
            "george-mason": "A10",
            "fordham": "A10",
            "st-josephs": "A10",
            "saint-josephs": "A10",
            "saint-joseph's": "A10",
            "la-salle": "A10",
            "duquesne": "A10",
            "george-washington": "A10",
            "loyola-chicago": "A10",
            # American Athletic Conference (Amer)
            "memphis": "Amer",
            "temple": "Amer",
            "wichita-state": "Amer",
            "wichita-st": "Amer",
            "east-carolina": "Amer",
            "south-florida": "Amer",
            "tulsa": "Amer",
            "tulane": "Amer",
            "north-texas": "Amer",
            "uab": "Amer",
            "charlotte": "Amer",
            "florida-atlantic": "Amer",
            "utsa": "Amer",
            "rice": "Amer",
            # Conference USA (CUSA)
            "louisiana-tech": "CUSA",
            "western-kentucky": "CUSA",
            "middle-tennessee": "CUSA",
            "jacksonville-state": "CUSA",
            "jacksonville-st": "CUSA",
            "kennesaw-state": "CUSA",
            "kennesaw-st": "CUSA",
            "liberty": "CUSA",
            "new-mexico-state": "CUSA",
            "new-mexico-st": "CUSA",
            "sam-houston-state": "CUSA",
            "sam-houston-st": "CUSA",
            "fiu": "CUSA",
            "utep": "CUSA",
            "delaware": "CUSA",
            "missouri-state": "CUSA",
            "missouri-st": "CUSA",
            # Missouri Valley (MVC)
            "illinois-state": "MVC",
            "illinois-st": "MVC",
            "indiana-state": "MVC",
            "indiana-st": "MVC",
            "drake": "MVC",
            "bradley": "MVC",
            "northern-iowa": "MVC",
            "southern-illinois": "MVC",
            "valparaiso": "MVC",
            "belmont": "MVC",
            "murray-state": "MVC",
            "murray-st": "MVC",
            "evansville": "MVC",
            "uic": "MVC",
            "illinois-chicago": "MVC",
            # Big West (BW)
            "hawaii": "BW",
            "uc-irvine": "BW",
            "uc-davis": "BW",
            "uc-santa-barbara": "BW",
            "ucsb": "BW",
            "cal-poly": "BW",
            "cal-state-northridge": "BW",
            "cal-st-northridge": "BW",
            "csun": "BW",
            "cal-state-fullerton": "BW",
            "cal-st-fullerton": "BW",
            "uc-riverside": "BW",
            "cal-state-bakersfield": "BW",
            "cal-st-bakersfield": "BW",
            "long-beach-state": "BW",
            "long-beach-st": "BW",
            "uc-san-diego": "BW",
            # Summit League (Sum)
            "south-dakota-state": "Sum",
            "south-dakota-st": "Sum",
            "sdsu": "Sum",
            "north-dakota-state": "Sum",
            "north-dakota-st": "Sum",
            "oral-roberts": "Sum",
            "south-dakota": "Sum",
            "north-dakota": "Sum",
            "denver": "Sum",
            "omaha": "Sum",
            "nebraska-omaha": "Sum",
            "kansas-city": "Sum",
            "umkc": "Sum",
            "st-thomas": "Sum",
            # WAC - Western Athletic Conference
            "utah-valley": "WAC",
            "abilene-christian": "WAC",
            "southern-utah": "WAC",
            "ut-arlington": "WAC",
            "tarleton-state": "WAC",
            "tarleton-st": "WAC",
            "cal-baptist": "WAC",
            "california-baptist": "WAC",
            "utah-tech": "WAC",
            # Horizon League (Horz)
            "wright-state": "Horz",
            "wright-st": "Horz",
            "northern-kentucky": "Horz",
            "cleveland-state": "Horz",
            "cleveland-st": "Horz",
            "oakland": "Horz",
            "youngstown-state": "Horz",
            "youngstown-st": "Horz",
            "milwaukee": "Horz",
            "robert-morris": "Horz",
            "iupui": "Horz",
            "iu-indy": "Horz",
            "purdue-fort-wayne": "Horz",
            "green-bay": "Horz",
            "detroit-mercy": "Horz",
            # MAAC - Metro Atlantic Athletic Conference
            "iona": "MAAC",
            "marist": "MAAC",
            "manhattan": "MAAC",
            "quinnipiac": "MAAC",
            "fairfield": "MAAC",
            "rider": "MAAC",
            "siena": "MAAC",
            "niagara": "MAAC",
            "canisius": "MAAC",
            "merrimack": "MAAC",
            "mount-st-marys": "MAAC",
            "mount-st-mary-s": "MAAC",
            "mount-st-mary's": "MAAC",
            "sacred-heart": "MAAC",
            "saint-peters": "MAAC",
            "saint-peter-s": "MAAC",
            "saint-peter's": "MAAC",
            "st-peters": "MAAC",
            # MAC - Mid-American Conference
            "toledo": "MAC",
            "akron": "MAC",
            "bowling-green": "MAC",
            "kent-state": "MAC",
            "kent-st": "MAC",
            "miami-oh": "MAC",
            "miami-(oh)": "MAC",
            "ohio": "MAC",
            "ball-state": "MAC",
            "ball-st": "MAC",
            "buffalo": "MAC",
            "central-michigan": "MAC",
            "eastern-michigan": "MAC",
            "eastern-mich": "MAC",
            "massachusetts": "MAC",
            "umass": "MAC",
            "northern-illinois": "MAC",
            "western-michigan": "MAC",
            "western-mich": "MAC",
            # NEC - Northeast Conference
            "central-connecticut": "NEC",
            "central-connecticut-st": "NEC",
            "liu": "NEC",
            "wagner": "NEC",
            "stonehill": "NEC",
            "le-moyne": "NEC",
            "fairleigh-dickinson": "NEC",
            "chicago-state": "NEC",
            "chicago-st": "NEC",
            "saint-francis": "NEC",
            "mercyhurst": "NEC",
            "new-haven": "NEC",
            # Big Sky (BSky)
            "montana": "BSky",
            "montana-state": "BSky",
            "montana-st": "BSky",
            "weber-state": "BSky",
            "weber-st": "BSky",
            "idaho": "BSky",
            "idaho-state": "BSky",
            "idaho-st": "BSky",
            "northern-colorado": "BSky",
            "portland-state": "BSky",
            "portland-st": "BSky",
            "eastern-washington": "BSky",
            "northern-arizona": "BSky",
            "sacramento-state": "BSky",
            "sacramento-st": "BSky",
            # OVC - Ohio Valley Conference
            "morehead-state": "OVC",
            "morehead-st": "OVC",
            "tennessee-state": "OVC",
            "tennessee-st": "OVC",
            "ut-martin": "OVC",
            "tennessee-martin": "OVC",
            "tennessee-tech": "OVC",
            "lindenwood": "OVC",
            "siu-edwardsville": "OVC",
            "little-rock": "OVC",
            "western-illinois": "OVC",
            "eastern-illinois": "OVC",
            "southeast-missouri-st": "OVC",
            "southern-indiana": "OVC",
            # CAA - Colonial Athletic Association
            "charleston": "CAA",
            "hofstra": "CAA",
            "drexel": "CAA",
            "towson": "CAA",
            "unc-wilmington": "CAA",
            "monmouth": "CAA",
            "stony-brook": "CAA",
            "elon": "CAA",
            "william-mary": "CAA",
            "william-&-mary": "CAA",
            "hampton": "CAA",
            "campbell": "CAA",
            "north-carolina-at": "CAA",
            "north-carolina-a&t": "CAA",
            "nc-at": "CAA",
            "nc-a&t": "CAA",
            "northeastern": "CAA",
            # Southern Conference (SC)
            "furman": "SC",
            "wofford": "SC",
            "unc-greensboro": "SC",
            "samford": "SC",
            "east-tennessee-state": "SC",
            "east-tennessee-st": "SC",
            "etsu": "SC",
            "chattanooga": "SC",
            "the-citadel": "SC",
            "citadel": "SC",
            "vmi": "SC",
            "western-carolina": "SC",
            "mercer": "SC",
            # Sun Belt (SB)
            "james-madison": "SB",
            "coastal-carolina": "SB",
            "troy": "SB",
            "georgia-state": "SB",
            "georgia-st": "SB",
            "georgia-southern": "SB",
            "app-state": "SB",
            "appalachian-state": "SB",
            "appalachian-st": "SB",
            "louisiana": "SB",
            "marshall": "SB",
            "old-dominion": "SB",
            "southern-miss": "SB",
            "southern-mississippi": "SB",
            "arkansas-state": "SB",
            "arkansas-st": "SB",
            "ulm": "SB",
            "louisiana-monroe": "SB",
            "texas-state": "SB",
            "texas-st": "SB",
            "south-alabama": "SB",
            # Southland (Slnd)
            "mcneese-state": "Slnd",
            "mcneese-st": "Slnd",
            "mcneese": "Slnd",
            "nicholls-state": "Slnd",
            "nicholls-st": "Slnd",
            "nicholls": "Slnd",
            "northwestern-state": "Slnd",
            "northwestern-st": "Slnd",
            "southeastern-louisiana": "Slnd",
            "texas-am-commerce": "Slnd",
            "east-texas-a&m": "Slnd",
            "east-texas-am": "Slnd",
            "stephen-f-austin": "Slnd",
            "houston-christian": "Slnd",
            "incarnate-word": "Slnd",
            "lamar": "Slnd",
            "new-orleans": "Slnd",
            "texas-a&m-corpus-chris": "Slnd",
            "texas-am-corpus-chris": "Slnd",
            "ut-rio-grande-valley": "Slnd",
            # ASUN (ASun)
            "lipscomb": "ASun",
            "jacksonville": "ASun",
            "fgcu": "ASun",
            "florida-gulf-coast": "ASun",
            "stetson": "ASun",
            "north-florida": "ASun",
            "queens": "ASun",
            "eastern-kentucky": "ASun",
            "austin-peay": "ASun",
            "central-arkansas": "ASun",
            "bellarmine": "ASun",
            "north-alabama": "ASun",
            "west-georgia": "ASun",
            # America East (AE)
            "vermont": "AE",
            "bryant": "AE",
            "umbc": "AE",
            "umass-lowell": "AE",
            "binghamton": "AE",
            "new-hampshire": "AE",
            "unh": "AE",
            "maine": "AE",
            "albany": "AE",
            "njit": "AE",
            # Ivy League (Ivy)
            "princeton": "Ivy",
            "yale": "Ivy",
            "harvard": "Ivy",
            "cornell": "Ivy",
            "penn": "Ivy",
            "pennsylvania": "Ivy",
            "brown": "Ivy",
            "columbia": "Ivy",
            "dartmouth": "Ivy",
            # Patriot League (Pat)
            "colgate": "Pat",
            "army": "Pat",
            "navy": "Pat",
            "bucknell": "Pat",
            "holy-cross": "Pat",
            "lehigh": "Pat",
            "lafayette": "Pat",
            "boston-university": "Pat",
            "american": "Pat",
            "loyola-maryland": "Pat",
            "loyola-md": "Pat",
            # MEAC - Mid-Eastern Athletic Conference
            "norfolk-state": "MEAC",
            "norfolk-st": "MEAC",
            "howard": "MEAC",
            "north-carolina-central": "MEAC",
            "nc-central": "MEAC",
            "morgan-state": "MEAC",
            "morgan-st": "MEAC",
            "south-carolina-state": "MEAC",
            "south-carolina-st": "MEAC",
            "coppin-state": "MEAC",
            "coppin-st": "MEAC",
            "delaware-state": "MEAC",
            "delaware-st": "MEAC",
            "maryland-eastern-shore": "MEAC",
            "umes": "MEAC",
            # SWAC - Southwestern Athletic Conference
            "alabama-state": "SWAC",
            "alabama-st": "SWAC",
            "alabama-a&m": "SWAC",
            "alabama-am": "SWAC",
            "alcorn-state": "SWAC",
            "alcorn-st": "SWAC",
            "arkansas-pine-bluff": "SWAC",
            "bethune-cookman": "SWAC",
            "florida-am": "SWAC",
            "florida-a&m": "SWAC",
            "famu": "SWAC",
            "grambling-state": "SWAC",
            "grambling-st": "SWAC",
            "jackson-state": "SWAC",
            "jackson-st": "SWAC",
            "mississippi-valley-state": "SWAC",
            "mississippi-valley-st": "SWAC",
            "prairie-view-am": "SWAC",
            "prairie-view-a&m": "SWAC",
            "southern": "SWAC",
            "texas-southern": "SWAC",
            # Big South (BSth)
            "high-point": "BSth",
            "radford": "BSth",
            "longwood": "BSth",
            "gardner-webb": "BSth",
            "winthrop": "BSth",
            "charleston-southern": "BSth",
            "presbyterian": "BSth",
            "unc-asheville": "BSth",
            "usc-upstate": "BSth",
        }

        slug = obj.team.slug.lower()
        return conf_map.get(slug, "Ind")

    def get_record(self, obj):
        """Get W-L record from stored wins/losses fields"""
        try:
            # Use stored wins/losses from TeamSeasonRatings (includes all games: D1 + non-D1)
            return f"{obj.wins}-{obj.losses}"
        except Exception as e:
            # Fallback to games played
            return f"{obj.games_played}-0"

    def get_rank_four_factor_index_100(self, obj):
        """Compute FFI rank on the fly"""
        # Use cached rank if available (can be set in view)
        if hasattr(obj, '_ffi_rank_cache'):
            return obj._ffi_rank_cache
        
        try:
            better_count = TeamSeasonRatings.objects.filter(
                season=obj.season, ffi_adj__gt=obj.ffi_adj
            ).count()
            return better_count + 1
        except:
            return None

    def _get_metrics(self, obj):
        """Helper to get TeamSeasonMetrics for this rating (with caching)"""
        from ncaa.models import TeamSeasonMetrics
        
        # Cache metrics on the object to avoid multiple queries
        if not hasattr(obj, '_cached_metrics'):
            # Check if we have prefetched metrics
            if hasattr(obj.team, '_metrics_for_season') and obj.team._metrics_for_season:
                obj._cached_metrics = obj.team._metrics_for_season[0] if obj.team._metrics_for_season else None
            else:
                try:
                    obj._cached_metrics = TeamSeasonMetrics.objects.get(team=obj.team, season=obj.season)
                except TeamSeasonMetrics.DoesNotExist:
                    obj._cached_metrics = None
        
        return obj._cached_metrics

    def get_raw_efg_pct(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.efg_pct if metrics else 0.0

    def get_raw_tov_pct(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.tov_pct if metrics else 0.0

    def get_raw_orb_pct(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.orb_pct if metrics else 0.0

    def get_raw_ftr(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.ftr if metrics else 0.0

    def get_raw_efg_pct_d(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.opp_efg_pct if metrics else 0.0

    def get_raw_tov_pct_d(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.opp_tov_pct if metrics else 0.0

    def get_raw_orb_pct_d(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.opp_orb_pct if metrics else 0.0

    def get_raw_ftr_d(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.opp_ftr if metrics else 0.0

    def get_raw_efg_margin(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.efg_margin if metrics else 0.0

    def get_raw_tov_edge(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.tov_edge if metrics else 0.0

    def get_raw_reb_edge(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.reb_edge if metrics else 0.0

    def get_raw_ftr_margin(self, obj):
        metrics = self._get_metrics(obj)
        return metrics.ftr_margin if metrics else 0.0

    # SHOOTING SPLITS - Calculated directly to avoid property caching issues
    def get_fg2_pct(self, obj):
        metrics = self._get_metrics(obj)
        if not metrics:
            return None
        fg2a = (metrics.total_fga or 0) - (metrics.total_fg3a or 0)
        fg2m = (metrics.total_fgm or 0) - (metrics.total_fg3m or 0)
        return round(fg2m / fg2a * 100, 1) if fg2a > 0 else None

    def get_fg3_pct(self, obj):
        metrics = self._get_metrics(obj)
        if not metrics:
            return None
        return (
            round((metrics.total_fg3m or 0) / (metrics.total_fg3a or 0) * 100, 1)
            if (metrics.total_fg3a or 0) > 0
            else None
        )

    def get_ft_pct(self, obj):
        metrics = self._get_metrics(obj)
        if not metrics:
            return None
        return (
            round((metrics.total_ftm or 0) / (metrics.total_fta or 0) * 100, 1)
            if (metrics.total_fta or 0) > 0
            else None
        )

    def get_fg3_rate(self, obj):
        metrics = self._get_metrics(obj)
        if not metrics:
            return None
        return (
            round((metrics.total_fg3a or 0) / (metrics.total_fga or 0) * 100, 1)
            if (metrics.total_fga or 0) > 0
            else None
        )


class TeamDetailSerializer(serializers.Serializer):
    """
    Combined serializer for team detail page
    Includes team info + stats across all available seasons
    """

    team = TeamSerializer()
    seasons = TeamSeasonStatsSerializer(many=True)
    current_season_stats = TeamSeasonStatsSerializer()


# ==================== GAME LOG PIPELINE SERIALIZERS ====================


class GameSerializer(serializers.ModelSerializer):
    """Game metadata serializer"""

    home_team_name = serializers.CharField(source="home_team.name", read_only=True)
    away_team_name = serializers.CharField(source="away_team.name", read_only=True)
    home_team_slug = serializers.CharField(source="home_team.slug", read_only=True)
    away_team_slug = serializers.CharField(source="away_team.slug", read_only=True)
    winner_name = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "id",
            "source_game_id",
            "season_year",
            "game_date",
            "start_time_utc",
            "home_team_name",
            "away_team_name",
            "home_team_slug",
            "away_team_slug",
            "home_score",
            "away_score",
            "status",
            "neutral_site",
            "venue_name",
            "venue_city",
            "venue_state",
            "period_count",
            "went_to_ot",
            "winner_name",
            "created_at",
            "updated_at",
        ]

    def get_winner_name(self, obj):
        winner = obj.winner
        return winner.name if winner else None


class TeamGameStatsSerializer(serializers.ModelSerializer):
    """Team box score stats for one game"""

    team_name = serializers.CharField(source="team.name", read_only=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True)
    opponent_name = serializers.CharField(source="opponent.name", read_only=True)
    opponent_slug = serializers.CharField(source="opponent.slug", read_only=True)
    game_date = serializers.DateField(source="game.game_date", read_only=True)
    game_status = serializers.CharField(source="game.status", read_only=True)

    # Computed fields
    possessions = serializers.SerializerMethodField()
    fg2m = serializers.SerializerMethodField()
    fg2a = serializers.SerializerMethodField()
    fg_pct = serializers.SerializerMethodField()
    fg3_pct = serializers.SerializerMethodField()
    ft_pct = serializers.SerializerMethodField()

    class Meta:
        model = TeamGameStats
        fields = [
            "id",
            "team_name",
            "team_slug",
            "opponent_name",
            "opponent_slug",
            "game_date",
            "game_status",
            "home_away",
            "pts",
            "fgm",
            "fga",
            "fg3m",
            "fg3a",
            "ftm",
            "fta",
            "fg2m",
            "fg2a",  # Computed
            "fg_pct",
            "fg3_pct",
            "ft_pct",  # Computed percentages
            "oreb",
            "dreb",
            "reb",
            "ast",
            "stl",
            "blk",
            "tov",
            "pf",
            "possessions",  # Computed
        ]

    def get_possessions(self, obj):
        return round(obj.possessions_est, 1)

    def get_fg2m(self, obj):
        return obj.fg2m

    def get_fg2a(self, obj):
        return obj.fg2a

    def get_fg_pct(self, obj):
        return round(100 * obj.fgm / obj.fga, 1) if obj.fga > 0 else 0.0

    def get_fg3_pct(self, obj):
        return round(100 * obj.fg3m / obj.fg3a, 1) if obj.fg3a > 0 else 0.0

    def get_ft_pct(self, obj):
        return round(100 * obj.ftm / obj.fta, 1) if obj.fta > 0 else 0.0


class GameLogSerializer(serializers.ModelSerializer):
    """
    Enhanced game log with comprehensive derived metrics
    """

    team_name = serializers.CharField(source="team.name", read_only=True)
    opponent_name = serializers.CharField(source="opponent.name", read_only=True)
    opponent_slug = serializers.CharField(source="opponent.slug", read_only=True)
    opponent_is_d1 = serializers.BooleanField(source="opponent.is_d1", read_only=True)
    opponent_net_rank = serializers.SerializerMethodField()
    quadrant = serializers.SerializerMethodField()
    game_date = serializers.DateField(source="game.game_date", read_only=True)
    went_to_ot = serializers.BooleanField(source="game.went_to_ot", read_only=True)
    game_id = serializers.IntegerField(source="game.id", read_only=True)

    # Possessions
    poss_team = serializers.FloatField(read_only=True)
    poss_opp = serializers.FloatField(read_only=True)
    poss_game = serializers.FloatField(read_only=True)

    # 2-point stats
    fg2m = serializers.IntegerField(read_only=True)
    fg2a = serializers.IntegerField(read_only=True)

    # Shooting percentages
    fg_pct = serializers.FloatField(read_only=True)
    fg2_pct = serializers.FloatField(read_only=True)
    fg3_pct = serializers.FloatField(read_only=True)
    ft_pct = serializers.FloatField(read_only=True)
    fg3_rate = serializers.FloatField(read_only=True)
    ts_pct = serializers.FloatField(read_only=True)

    # Four Factors (Offense)
    efg_pct = serializers.FloatField(read_only=True)
    orb_pct = serializers.FloatField(read_only=True)
    tov_pct = serializers.FloatField(read_only=True)
    ftr = serializers.FloatField(read_only=True)

    # Four Factors (Defense)
    opp_efg_pct = serializers.FloatField(read_only=True)
    opp_orb_pct = serializers.FloatField(read_only=True)
    opp_tov_pct = serializers.FloatField(read_only=True)
    opp_ftr = serializers.FloatField(read_only=True)

    # Margins / Edges
    efg_margin = serializers.FloatField(read_only=True)
    tov_edge = serializers.FloatField(read_only=True)
    reb_edge = serializers.FloatField(read_only=True)
    ftr_margin = serializers.FloatField(read_only=True)

    # Ratings
    ortg = serializers.FloatField(read_only=True)
    drtg = serializers.FloatField(read_only=True)
    net_rating = serializers.FloatField(read_only=True)

    # Assist metrics
    ast_pct = serializers.FloatField(read_only=True)
    ast_to_ratio = serializers.FloatField(read_only=True)
    ast_ratio = serializers.FloatField(read_only=True)

    # Pace
    pace = serializers.FloatField(read_only=True)

    # Defense metrics
    stl_pct = serializers.FloatField(read_only=True)
    blk_pct = serializers.FloatField(read_only=True)
    stl_to_ratio = serializers.FloatField(read_only=True)
    stocks_per_100 = serializers.FloatField(read_only=True)

    # Foul metrics
    pf_per_100 = serializers.FloatField(read_only=True)
    stl_per_pf = serializers.FloatField(read_only=True)
    blk_per_pf = serializers.FloatField(read_only=True)

    # Game result
    result = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()

    # Resume metrics
    game_value = serializers.FloatField(read_only=True)

    class Meta:
        model = TeamGameStats
        fields = [
            # Game info
            "id",
            "game_id",
            "game_date",
            "team_name",
            "opponent_name",
            "opponent_slug",
            "opponent_is_d1",
            "opponent_net_rank",
            "quadrant",
            "home_away",
            "went_to_ot",
            "result",
            "margin",
            "game_value",
            # Scoring
            "pts",
            # Shooting stats (raw)
            "fgm",
            "fga",
            "fg2m",
            "fg2a",
            "fg3m",
            "fg3a",
            "ftm",
            "fta",
            # Shooting percentages
            "fg_pct",
            "fg2_pct",
            "fg3_pct",
            "ft_pct",
            "fg3_rate",
            "ts_pct",
            # Rebounding
            "oreb",
            "dreb",
            "reb",
            # Other box score
            "ast",
            "stl",
            "blk",
            "tov",
            "pf",
            # Possessions
            "poss_team",
            "poss_opp",
            "poss_game",
            # Four Factors - Offense
            "efg_pct",
            "orb_pct",
            "tov_pct",
            "ftr",
            # Four Factors - Defense
            "opp_efg_pct",
            "opp_orb_pct",
            "opp_tov_pct",
            "opp_ftr",
            # Margins / Edges
            "efg_margin",
            "tov_edge",
            "reb_edge",
            "ftr_margin",
            # Ratings
            "ortg",
            "drtg",
            "net_rating",
            # Assist metrics
            "ast_pct",
            "ast_to_ratio",
            "ast_ratio",
            # Pace
            "pace",
            # Defense metrics
            "stl_pct",
            "blk_pct",
            "stl_to_ratio",
            "stocks_per_100",
            # Foul metrics
            "pf_per_100",
            "stl_per_pf",
            "blk_per_pf",
        ]

    def get_result(self, obj):
        opp_stats = obj._get_opp_stats()
        if opp_stats:
            return "W" if obj.pts > opp_stats.pts else "L"
        return "-"

    def get_margin(self, obj):
        opp_stats = obj._get_opp_stats()
        if opp_stats:
            return obj.pts - opp_stats.pts
        return 0

    def get_opponent_net_rank(self, obj):
        """Get opponent's NET rank (use rank_adj_em as proxy if net_rank not available)"""
        try:
            from ncaa.models import TeamSeasonRatings, Season

            # Get season from game
            season = Season.objects.get(year=obj.game.season_year)
            opp_ratings = TeamSeasonRatings.objects.get(
                team=obj.opponent, season=season
            )
            return opp_ratings.net_rank or opp_ratings.rank_adj_em
        except Exception as e:
            # Log exception for debugging
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to get opponent NET rank: {e}")
            return None

    def get_quadrant(self, obj):
        """Calculate NCAA quadrant for this game"""
        from api.resume_utils import get_quadrant

        opponent_rank = self.get_opponent_net_rank(obj)
        if opponent_rank is None:
            return None
        return get_quadrant(opponent_rank, obj.home_away)


class TeamSeasonMetricsSerializer(serializers.ModelSerializer):
    """Season aggregate metrics from game logs"""

    team_name = serializers.CharField(source="team.name", read_only=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True)
    season_year = serializers.IntegerField(source="season.year", read_only=True)

    class Meta:
        model = TeamSeasonMetrics
        fields = [
            "team_name",
            "team_slug",
            "season_year",
            "games",
            "ppg",
            "papg",
            "pace",
            "ortg",
            "drtg",
            "net_rtg",
            "efg_pct",
            "tov_pct",
            "orb_pct",
            "ftr",
            "opp_efg_pct",
            "opp_tov_pct",
            "drb_pct",
            "opp_ftr",
            "efg_margin",
            "tov_edge",
            "reb_edge",
            "ftr_margin",
            "kill_shots_for",
            "kill_shots_against",
            "kill_shots_pg",
            "kill_shots_conceded_pg",
            "kill_shot_margin_pg",
            "ast_g",
            "ast_pct",
            "blk_g",
            "blk_pct",
            "dpf_g",
            "last_updated",
        ]


class TeamSeasonRatingsSerializer(serializers.ModelSerializer):
    """Adjusted ratings from regression model"""

    team_name = serializers.CharField(source="team.name", read_only=True)
    team_slug = serializers.CharField(source="team.slug", read_only=True)
    season_year = serializers.IntegerField(source="season.year", read_only=True)

    class Meta:
        model = TeamSeasonRatings
        fields = [
            "team_name",
            "team_slug",
            "season_year",
            # Adjusted efficiency ratings
            "adj_o",
            "adj_d",
            "adj_em",
            "adj_tempo",
            "rank_adj_o",
            "rank_adj_d",
            "rank_adj_em",
            # Adjusted four factors - offense
            "adj_efg_pct",
            "adj_tov_pct",
            "adj_orb_pct",
            "adj_ftr",
            # Adjusted four factors - defense
            "adj_opp_efg_pct",
            "adj_opp_tov_pct",
            "adj_drb_pct",
            "adj_opp_ftr",
            # Adjusted margins
            "adj_efg_margin",
            "adj_tov_edge",
            "adj_reb_edge",
            "adj_ftr_margin",
            # Four Factor Index
            "ffi_raw",
            "ffi_adj",
            # Resume
            "wab",
            "sor_rank",
            "net_rank",
            "sos_rank",
            "sos_win_pct",
            # Metadata
            "games_played",
            "wins",
            "losses",
            "d1_games_played",
            "total_possessions",
            "hca_estimate",
            "computed_at",
        ]


class GameDetailSerializer(serializers.ModelSerializer):
    """Full game details with team stats"""

    home_team_name = serializers.CharField(source="home_team.name", read_only=True)
    away_team_name = serializers.CharField(source="away_team.name", read_only=True)
    home_team_slug = serializers.CharField(source="home_team.slug", read_only=True)
    away_team_slug = serializers.CharField(source="away_team.slug", read_only=True)
    home_stats = serializers.SerializerMethodField()
    away_stats = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "id",
            "source_game_id",
            "season_year",
            "game_date",
            "start_time_utc",
            "home_team_name",
            "away_team_name",
            "home_team_slug",
            "away_team_slug",
            "home_score",
            "away_score",
            "status",
            "neutral_site",
            "venue_name",
            "venue_city",
            "venue_state",
            "period_count",
            "went_to_ot",
            "home_stats",
            "away_stats",
            "updated_at",
        ]

    def get_home_stats(self, obj):
        stats = TeamGameStats.objects.filter(game=obj, team=obj.home_team).first()
        return TeamGameStatsSerializer(stats).data if stats else None

    def get_away_stats(self, obj):
        stats = TeamGameStats.objects.filter(game=obj, team=obj.away_team).first()
        return TeamGameStatsSerializer(stats).data if stats else None


class DataProcessingJobSerializer(serializers.ModelSerializer):
    """Serializer for data processing job tracking"""

    season_display = serializers.CharField(source="season.display_name", read_only=True)

    class Meta:
        model = DataProcessingJob
        fields = [
            "id",
            "job_id",
            "job_type",
            "get_job_type_display",
            "status",
            "get_status_display",
            "progress_percent",
            "season",
            "season_display",
            "parameters",
            "started_at",
            "completed_at",
            "duration_seconds",
            "logs",
            "error_message",
            "created_by",
            "is_running",
            "is_complete",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "job_id",
            "started_at",
            "updated_at",
            "logs",
            "error_message",
            "duration_seconds",
            "is_running",
            "is_complete",
        ]

    def get_job_type_display(self, obj):
        return obj.get_job_type_display()

    def get_status_display(self, obj):
        return obj.get_status_display()


class PipelineConfigSerializer(serializers.ModelSerializer):
    """
    Serializer for the singleton PipelineConfig model.
    All fields are writable; the view restricts access to admin users.
    """

    class Meta:
        model = PipelineConfig
        fields = [
            # Adjusted Ratings
            "adj_ratings_iterations",
            "adj_ratings_convergence",
            "adj_ratings_shrinkage_floor",
            "adj_ratings_shrinkage_ceiling",
            "adj_ratings_shrinkage_decay",
            # Adjusted Four Factors
            "adj_ff_iterations",
            "adj_ff_convergence",
            "adj_ff_shrinkage_floor",
            "adj_ff_shrinkage_ceiling",
            "adj_ff_shrinkage_decay",
            # Four Factor Index
            "ffi_weight_efg",
            "ffi_weight_tov",
            "ffi_weight_reb",
            "ffi_weight_ftr",
            "ffi_scale_midpoint",
            "ffi_scale_multiplier",
            # Strength of Record
            "sor_trials",
            "sor_baseline_rank_min",
            "sor_baseline_rank_max",
            "sor_fallback_rank_min",
            "sor_fallback_rank_max",
            # WAB / Game Value
            "wab_bubble_rank",
            # Strength of Schedule
            "sos_baseline_adjem",
            "sos_logistic_sigma",
            "sos_home_advantage",
            "sos_away_penalty",
            # Shared Fallbacks
            "fallback_hca",
            "fallback_sigma",
            "fallback_avg_ortg",
        ]



class PlayerSeasonStatsSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source="player.display_name", read_only=True)
    player_id = serializers.CharField(source="player.espn_athlete_id", read_only=True)
    position = serializers.CharField(source="player.position", read_only=True)
    jersey = serializers.CharField(source="player.jersey", read_only=True)
    headshot_url = serializers.CharField(source="player.headshot_url", read_only=True)
    team_name = serializers.SerializerMethodField()
    conference_name = serializers.CharField(allow_null=True, read_only=True)
    season_display = serializers.CharField(source="season.display_name", read_only=True)

    class Meta:
        model = PlayerSeasonStats
        fields = [
            "player_name", "player_id", "position", "jersey", "headshot_url",
            "team_name", "conference_name", "season_display",
            "gp", "mpg", "pts", "reb", "ast", "stl", "blk", "tov", "pf",
            "fg_pct", "fg3_pct", "ft_pct", "fga_pg", "fg3a_pg",
            "ftm_pg", "fta_pg", "oreb_pg", "dreb_pg",
            "efg_pct", "ts_pct", "ast_to",
            # On-court raw ratings (from ESPN PBP lineup reconstruction)
            "on_court_secs_pg", "on_court_pts_pg", "on_court_def_pg",
            "on_court_net_pg",
            "on_court_ortg", "on_court_drtg", "on_court_net",
            # On-court Four Factors (Phase D — populated after sync_ncaa_pbp --force)
            "on_court_efg_pct", "on_court_tov_pct", "on_court_orb_pct", "on_court_ftr",
            "on_court_opp_efg_pct", "on_court_opp_tov_pct", "on_court_drb_pct", "on_court_opp_ftr",
            "on_court_efg_margin", "on_court_tov_edge", "on_court_reb_edge", "on_court_ftr_margin",
            "on_court_ffi",
            "o_mpir", "d_mpir", "mpir",
            # BPR (Bayesian Performance Rating)
            "bpr", "obpr", "dbpr",
            "box_bpr", "box_obpr", "box_dbpr",
            "prior_mean_obpr", "prior_mean_dbpr", "prior_sd_obpr", "prior_sd_dbpr",
            "off_poss", "def_poss",
            "adj_team_off_eff_on", "adj_team_def_eff_on",
            # Phase E — possession-based adjusted on-court ratings
            "on_court_off_poss", "on_court_def_poss",
            "on_court_raw_oe", "on_court_raw_de",
            "on_court_adj_o", "on_court_adj_d", "on_court_adj_em",
            # Four Factor Impact (RAPM-based, player-specific)
            "off_efg_impact", "def_efg_impact",
            "off_tov_impact", "def_tov_impact",
            "off_orb_impact", "def_reb_impact",
            "off_ftr_impact", "def_ftr_impact",
            "efg_impact_margin", "tov_impact_margin",
            "reb_impact_margin", "ftr_impact_margin",
            "four_factor_impact_index",
            "baseline_obpr", "baseline_dbpr",
            "obpr_source", "dbpr_source", "bpr_source",
            "bpr_model_version",
        ]

    def get_team_name(self, obj):
        return obj.team.name if obj.team else ""


class PlaceholderArchetypeSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for PlaceholderArchetype.
    Returns all fields needed by the scenario editor.
    """

    class Meta:
        model = PlaceholderArchetype
        fields = [
            "key",
            "display_name",
            "conf_group",
            "conference",
            "role_bucket",
            "quality_tier",
            "projected_obpr",
            "projected_dbpr",
            "projected_bpr",
            "minutes_share",
            "mpg",
            "uncertainty",
            "efg_pct",
            "fg3_pct",
            "ts_pct",
            "ast_to",
            "oreb_pg",
            "dreb_pg",
            "tov",
            "sample_n",
            "source_season_year",
        ]

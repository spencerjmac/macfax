"""
Management command: backfill_tournament
Backfills historical NCAA Tournament seeds from Wikipedia and sets hardcoded
Champions, Runner-Ups, and Final Fours.

Usage:
    python manage.py backfill_tournament
    python manage.py backfill_tournament --season 2024
"""

import re
import sys
import time
import requests
import pandas as pd
from io import StringIO
from django.core.management.base import BaseCommand, CommandError
from ncaa.models import Season, TeamSeasonRatings
from ncaa.utils.team_mapping import TeamMapper


TOURNAMENT_RESULTS = {
    2005: {
        'Champ': ['North Carolina'],
        'Runner-Up': ['Illinois'],
        'Final Four': ['Louisville', 'Michigan State']
    },
    2006: {
        'Champ': ['Florida'],
        'Runner-Up': ['UCLA'],
        'Final Four': ['LSU', 'George Mason']
    },
    2007: {
        'Champ': ['Florida'],
        'Runner-Up': ['Ohio State'],
        'Final Four': ['UCLA', 'Georgetown']
    },
    2008: {
        'Champ': ['Kansas'],
        'Runner-Up': ['Memphis'],
        'Final Four': ['North Carolina', 'UCLA']
    },
    2009: {
        'Champ': ['North Carolina'],
        'Runner-Up': ['Michigan State'],
        'Final Four': ['UConn', 'Villanova']
    },
    2010: {
        'Champ': ['Duke'],
        'Runner-Up': ['Butler'],
        'Final Four': ['West Virginia', 'Michigan State']
    },
    2011: {
        'Champ': ['UConn'],
        'Runner-Up': ['Butler'],
        'Final Four': ['VCU', 'Kentucky']
    },
    2012: {
        'Champ': ['Kentucky'],
        'Runner-Up': ['Kansas'],
        'Final Four': ['Louisville', 'Ohio State']
    },
    2013: {
        'Champ': ['Louisville'],
        'Runner-Up': ['Michigan'],
        'Final Four': ['Syracuse', 'Wichita State']
    },
    2014: {
        'Champ': ['UConn'],
        'Runner-Up': ['Kentucky'],
        'Final Four': ['Florida', 'Wisconsin']
    },
    2015: {
        'Champ': ['Duke'],
        'Runner-Up': ['Wisconsin'],
        'Final Four': ['Kentucky', 'Michigan State']
    },
    2016: {
        'Champ': ['Villanova'],
        'Runner-Up': ['North Carolina'],
        'Final Four': ['Oklahoma', 'Syracuse']
    },
    2017: {
        'Champ': ['North Carolina'],
        'Runner-Up': ['Gonzaga'],
        'Final Four': ['Oregon', 'South Carolina']
    },
    2018: {
        'Champ': ['Villanova'],
        'Runner-Up': ['Michigan'],
        'Final Four': ['Loyola Chicago', 'Kansas']
    },
    2019: {
        'Champ': ['Virginia'],
        'Runner-Up': ['Texas Tech'],
        'Final Four': ['Michigan State', 'Auburn']
    },
    2021: {
        'Champ': ['Baylor'],
        'Runner-Up': ['Gonzaga'],
        'Final Four': ['Houston', 'UCLA']
    },
    2022: {
        'Champ': ['Kansas'],
        'Runner-Up': ['North Carolina'],
        'Final Four': ['Duke', 'Villanova']
    },
    2023: {
        'Champ': ['UConn'],
        'Runner-Up': ['San Diego State'],
        'Final Four': ['Miami (FL)', 'Florida Atlantic']
    },
    2024: {
        'Champ': ['UConn'],
        'Runner-Up': ['Purdue'],
        'Final Four': ['Alabama', 'NC State']
    },
    2025: {
        'Champ': ['Florida'],
        'Runner-Up': ['Houston'],
        'Final Four': ['Duke', 'Auburn']
    },
    2026: {
        'Champ': ['Michigan'],
        'Runner-Up': ['UConn'],
        'Final Four': ['Arizona', 'Illinois']
    }
}


# Wikipedia's 2005-2013 tournament pages use full/old school names that don't
# match the abbreviated NCAA.com naming convention used by
# mappings/ncaa_team_name_mappings.yml. Map those directly to the NCAA.com key.
WIKI_SCHOOL_OVERRIDES_2005_2013 = {
    'Southern Illinois': 'Southern Ill.',
    'UW-Milwaukee': 'Milwaukee',
    'Southeastern Louisiana': 'Southeastern La.',
    'Fairleigh Dickinson': 'FDU',
    'Louisiana-Lafayette': 'Louisiana',
    'Connecticut': 'UConn',
    'NC State': 'NC State',
    'Northern Iowa': 'UNI',
    'Central Florida': 'UCF',
    'Eastern Kentucky': 'Eastern Ky.',
    'UNC Wilmington': 'UNCW',
    'Pennsylvania': 'Penn',
    'Southern': 'Southern U.',
    'Albany': 'UAlbany',
    'Miami (Ohio)': 'Miami (OH)',
    'Texas A&M-Corpus Christi': 'A&M-Corpus Christi',
    'Brigham Young': 'BYU',
    'Central Connecticut': 'Central Conn. St.',
    'Texas-Arlington': 'UT Arlington',
    'Western Kentucky': 'Western Ky.',
    'Mississippi Valley State': 'Mississippi Val.',
    'East Tennessee State': 'ETSU',
    'Stephen F. Austin': 'SFA',
    'Cal State Northridge': 'CSUN',
    'Sam Houston State': 'Sam Houston',
    'Arkansas-Pine Bluff': 'Ark.-Pine Bluff',
    'Long Island': 'LIU',
    "St. John's": "St. John's (NY)",
    'Arkansas-Little Rock': 'Little Rock',
    'Boston University': 'Boston U.',
    'Northern Colorado': 'Northern Colo.',
    'Southern Miss': 'Southern Miss.',
    'Loyola': 'Loyola Maryland',
    'South Florida': 'South Fla.',
    'Lamar': 'Lamar University',
    'LIU-Brooklyn': 'LIU',
    'Florida Gulf Coast': 'FGCU',
    'Miami': 'Miami (FL)',
    'Middle Tennessee': 'Middle Tenn.',
    'North Carolina A&T': 'N.C. A&T',
}


def clean_school_2005_2013(school):
    """Normalize a 2005-2013 Wikipedia school name to an NCAA.com mapping key."""
    school = school.replace('–', '-')  # en dash -> hyphen
    school = re.sub(r'\(vacated\)', '', school)
    school = re.sub(r'\[\d+\]', '', school)
    school = school.replace('*', '').strip()

    if school in WIKI_SCHOOL_OVERRIDES_2005_2013:
        return WIKI_SCHOOL_OVERRIDES_2005_2013[school]

    school = school.replace(' State', ' St.')
    if school == 'UNC': school = 'North Carolina'
    if school == 'USC': school = 'Southern California'
    if school == "Saint Mary's": school = "Saint Mary's (CA)"
    if school == "Miami (Florida)": school = "Miami (FL)"
    if 'Loyola' in school and 'Chicago' in school: school = 'Loyola Chicago'
    return school


class Command(BaseCommand):
    help = "Backfill historical NCAA Tournament seeds and finish"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            help="Optional: specific season to backfill (e.g. 2024). Defaults to all past seasons.",
        )

    def handle(self, *args, **options):
        season_arg = options["season"]
        
        if season_arg:
            seasons = Season.objects.filter(year=season_arg)
        else:
            seasons = Season.objects.filter(year__gte=2005, year__lte=2026).exclude(year=2020).order_by('year')

        mapper = TeamMapper(source="ncaa")
        total_updated = 0
        total_missing = []

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("BACKFILLING HISTORICAL NCAA TOURNAMENTS")
        self.stdout.write(f"{'='*60}\n")

        for season in seasons:
            year = season.year
            self.stdout.write(f"Fetching {year} Tournament Seeds from Wikipedia...")
            
            url = f"https://en.wikipedia.org/wiki/{year}_NCAA_Division_I_men%27s_basketball_tournament"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            try:
                resp = requests.get(url, headers=headers)
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(f"  Failed to fetch {year}: {e}"))
                continue
            
            try:
                tables = pd.read_html(StringIO(resp.text), flavor='lxml')
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  Failed to parse {year}: {e}"))
                continue
                
            seed_tables = []
            for t in tables:
                cols = t.columns
                if isinstance(cols, pd.MultiIndex):
                    # 2005-2013 format: columns like (RegionName, 'Seed'), (RegionName, 'School'), ...
                    sub_cols = [c[-1] for c in cols]
                    if 'Seed' in sub_cols and 'School' in sub_cols:
                        flat = pd.DataFrame({c[-1]: t[c] for c in cols})
                        seed_tables.append((flat, True))
                elif 'Seed' in cols and 'School' in cols:
                    seed_tables.append((t, False))

            if not seed_tables:
                self.stderr.write(self.style.ERROR(f"  Could not find seed tables for {year}. Skipping seeds..."))
            else:
                season_updated = 0
                for t, is_multiindex in seed_tables:
                    for _, row in t.iterrows():
                        seed_raw = row.get('Seed')
                        school = str(row.get('School')).strip()

                        if pd.isna(seed_raw) or not school or school == 'nan':
                            continue

                        # Clean up seed (e.g. "11*" or "11a")
                        try:
                            seed_str = ''.join(c for c in str(seed_raw) if c.isdigit())
                            seed = int(seed_str)
                        except ValueError:
                            continue

                        # Apply overrides
                        if is_multiindex:
                            school = clean_school_2005_2013(school)
                        else:
                            school = school.replace('*', '').strip()
                            school = school.replace(' State', ' St.')
                            if school == 'UNC': school = 'North Carolina'
                            if school == 'USC': school = 'Southern California'
                            if school == "Saint Mary's": school = "Saint Mary's (CA)"
                            if school == "Miami (Florida)": school = "Miami (FL)"
                            if 'Loyola' in school and 'Chicago' in school: school = 'Loyola Chicago'

                        team, conf, is_override = mapper.find_team(school, min_confidence=0.85)
                        
                        if team:
                            qs = TeamSeasonRatings.all_objects.filter(season=season, team=team)
                            if qs.exists():
                                qs.update(tournament_seed=seed)
                                season_updated += 1
                        else:
                            self.stderr.write(self.style.ERROR(f"  UNMATCHED TEAM: Seed {seed} {school}"))
                            total_missing.append(f"{year} - {school}")

                self.stdout.write(self.style.SUCCESS(f"✓ Updated {season_updated} seeds for {year}"))
                total_updated += season_updated
            
            # Now set the hardcoded results for this year
            results = TOURNAMENT_RESULTS.get(year)
            if results:
                for finish, teams in results.items():
                    for team_name in teams:
                        if ' State' in team_name and team_name != 'NC State':
                            team_name = team_name.replace(' State', ' St.')
                        
                        team, _, _ = mapper.find_team(team_name, min_confidence=0.85)
                        if team:
                            qs = TeamSeasonRatings.all_objects.filter(season=season, team=team)
                            if qs.exists():
                                qs.update(tournament_finish=finish)
                                self.stdout.write(f"  → Set {finish}: {team.name}")
                        else:
                            self.stderr.write(self.style.ERROR(f"  UNMATCHED RESULT TEAM: {team_name}"))

            time.sleep(1) # Be polite

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Finished. Total seeds updated: {total_updated}"))
        if total_missing:
            self.stdout.write("Could not match these teams:")
            for m in set(total_missing):
                self.stdout.write(f"  - {m}")
        self.stdout.write(f"{'='*60}\n")

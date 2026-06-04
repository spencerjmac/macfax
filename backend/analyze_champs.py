import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ncaa.models import TeamSeasonRatings, TeamSeasonMetrics

print("Analyzing past Champions (Pre-Tournament)...")

champs = TeamSeasonRatings.all_objects.filter(tournament_finish="Champ", is_pre_tournament=False).select_related("team", "season").order_by("season__year")

print(f"{'Year':<5} {'Team':<20} {'eFG Marg':<10} {'TOV Edge':<10} {'REB Edge':<10} {'FTR Marg':<10} {'FFI Raw':<10}")
print("-" * 75)

for champ in champs:
    # Try to get pre-tournament metrics and ratings
    try:
        metrics = TeamSeasonMetrics.all_objects.get(
            team=champ.team,
            season=champ.season,
            is_pre_tournament=True
        )
        ratings = TeamSeasonRatings.all_objects.get(
            team=champ.team,
            season=champ.season,
            is_pre_tournament=True
        )
        print(f"{champ.season.year:<5} {champ.team.name:<20} {metrics.efg_margin:8.2f}% {metrics.tov_edge:8.2f}% {metrics.reb_edge:8.2f}% {metrics.ftr_margin:9.2f} {ratings.ffi_raw:9.1f}")
    except (TeamSeasonMetrics.DoesNotExist, TeamSeasonRatings.DoesNotExist):
        print(f"{champ.season.year:<5} {champ.team.name:<20} NOT FOUND")

"""
Data migration: update Team.logo_url from /logos/ to /static/logos/.

Logos were moved from web/public/logos to backend/static/logos and are now
served by WhiteNoise at /static/logos/. This migration updates any existing
DB records that still use the old /logos/ prefix.
"""

from django.db import migrations


def fix_logo_urls(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    teams = Team.objects.filter(logo_url__startswith="/logos/")
    count = 0
    for team in teams:
        # /logos/foo.png  →  /static/logos/foo.png
        team.logo_url = "/static" + team.logo_url
        team.save(update_fields=["logo_url"])
        count += 1
    print(f"  Updated {count} team logo URLs (/logos/ → /static/logos/)")


def reverse_fix_logo_urls(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    teams = Team.objects.filter(logo_url__startswith="/static/logos/")
    count = 0
    for team in teams:
        # /static/logos/foo.png  →  /logos/foo.png
        team.logo_url = team.logo_url[len("/static"):]
        team.save(update_fields=["logo_url"])
        count += 1
    print(f"  Reverted {count} team logo URLs (/static/logos/ → /logos/)")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_teamseasonmetrics_conference"),
    ]

    operations = [
        migrations.RunPython(fix_logo_urls, reverse_code=reverse_fix_logo_urls),
    ]

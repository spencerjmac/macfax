from django.db import migrations

# Conferences new in 2026-27. MAAC and WAC rows are kept for earlier seasons.
NEW_CONFERENCES = [
    ("P12", "Pac-12 Conference"),
    ("Metro", "Metro Conference"),
    ("UAC", "United Athletic Conference"),
]


def add_conferences(apps, schema_editor):
    Conference = apps.get_model("core", "Conference")
    for code, name in NEW_CONFERENCES:
        Conference.objects.get_or_create(code=code, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("core", "0069_playermarketvalue_and_more")]

    operations = [migrations.RunPython(add_conferences, migrations.RunPython.noop)]

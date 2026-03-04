from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_fix_logo_url_paths"),
    ]

    operations = [
        migrations.DeleteModel(
            name="DataIngestionRun",
        ),
    ]

from django.apps import AppConfig


class NcaaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ncaa'
    label = 'core'  # preserves DB table names (core_*) and migration history

"""
Management command to clear Django cache
Usage: python manage.py clear_cache
"""

from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Clear Django cache (useful after data updates)"

    def handle(self, *args, **options):
        cache.clear()
        self.stdout.write(self.style.SUCCESS("✓ Cache cleared successfully"))
        self.stdout.write("Rankings API will regenerate on next request")

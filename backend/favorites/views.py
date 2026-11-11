"""
/api/favorites/ - save and load a device's starred teams.

GET  ?device_id=<uuid>                          -> {"device_id", "team_slugs"}
POST {"device_id": <uuid>, "team_slugs": [...]} -> replaces the whole list

team_slugs are newest first (index 0 = newest).
"""

import uuid

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ncaa.models import Team

from .models import FavoriteTeam

MAX_TEAMS = 50


class FavoritesError(Exception):
    """Bad request input; the message is returned to the client."""


def _parse_device_id(value):
    if value is None or value == "":
        raise FavoritesError("device_id is required.")
    if not isinstance(value, str):
        raise FavoritesError("device_id must be a UUID string.")
    try:
        return uuid.UUID(value)
    except ValueError:
        raise FavoritesError(f"device_id is not a valid UUID: {value!r}.")


def _parse_team_slugs(value):
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise FavoritesError("team_slugs must be a list of strings.")
    if len(value) > MAX_TEAMS:
        raise FavoritesError(f"team_slugs has {len(value)} teams; the limit is {MAX_TEAMS}.")

    seen, dupes = set(), []
    for slug in value:
        if slug in seen and slug not in dupes:
            dupes.append(slug)
        seen.add(slug)
    if dupes:
        raise FavoritesError(f"team_slugs has duplicates: {', '.join(dupes)}.")

    known = set(Team.objects.filter(slug__in=value).values_list("slug", flat=True))
    unknown = [slug for slug in value if slug not in known]
    if unknown:
        raise FavoritesError(f"Unknown team slugs: {', '.join(unknown)}.")
    return value


def _payload(device_id):
    slugs = FavoriteTeam.objects.filter(device_id=device_id).order_by("position")
    return {
        "device_id": str(device_id),
        "team_slugs": list(slugs.values_list("team_slug", flat=True)),
    }


def _bad_request(message):
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


class FavoritesView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "favorites"

    def get(self, request):
        try:
            device_id = _parse_device_id(request.query_params.get("device_id"))
        except FavoritesError as exc:
            return _bad_request(str(exc))
        return Response(_payload(device_id))

    def post(self, request):
        try:
            data = request.data
        except ParseError:
            return _bad_request("Request body must be valid JSON.")
        if not isinstance(data, dict):
            return _bad_request("Request body must be a JSON object.")

        try:
            device_id = _parse_device_id(data.get("device_id"))
            if "team_slugs" not in data:
                raise FavoritesError("team_slugs is required.")
            slugs = _parse_team_slugs(data["team_slugs"])
        except FavoritesError as exc:
            return _bad_request(str(exc))

        with transaction.atomic():
            FavoriteTeam.objects.filter(device_id=device_id).delete()
            FavoriteTeam.objects.bulk_create(
                FavoriteTeam(device_id=device_id, team_slug=slug, position=i)
                for i, slug in enumerate(slugs)
            )
        return Response(_payload(device_id))

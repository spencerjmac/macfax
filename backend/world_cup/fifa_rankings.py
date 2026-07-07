import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

FIFA_RANKING_PAGE_URL = "https://inside.fifa.com/fifa-world-ranking/men"
FIFA_RANKINGS_BY_SCHEDULE_URL = (
    "https://api.fifa.com/api/v3/fifarankings/rankings/rankingsbyschedule"
)

DATA_DIR = Path(__file__).resolve().parent / "data"
TEAMS_PATH = DATA_DIR / "teams.json"

REQUEST_HEADERS = {
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (compatible; MacFaxWorldCupRankings/1.0; "
        "+https://macfax.com)"
    ),
}

TEAM_FIFA_COUNTRY_CODES = {
    "Algeria": "ALG",
    "Argentina": "ARG",
    "Australia": "AUS",
    "Austria": "AUT",
    "Belgium": "BEL",
    "Bosnia and Herzegovina": "BIH",
    "Brazil": "BRA",
    "Canada": "CAN",
    "Cape Verde": "CPV",
    "Colombia": "COL",
    "Croatia": "CRO",
    "Curaçao": "CUW",
    "Czechia": "CZE",
    "DR Congo": "COD",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "England": "ENG",
    "France": "FRA",
    "Germany": "GER",
    "Ghana": "GHA",
    "Haiti": "HAI",
    "Iran": "IRN",
    "Iraq": "IRQ",
    "Ivory Coast": "CIV",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Mexico": "MEX",
    "Morocco": "MAR",
    "Netherlands": "NED",
    "New Zealand": "NZL",
    "Norway": "NOR",
    "Panama": "PAN",
    "Paraguay": "PAR",
    "Portugal": "POR",
    "Qatar": "QAT",
    "Saudi Arabia": "KSA",
    "Scotland": "SCO",
    "Senegal": "SEN",
    "South Africa": "RSA",
    "South Korea": "KOR",
    "Spain": "ESP",
    "Sweden": "SWE",
    "Switzerland": "SUI",
    "Tunisia": "TUN",
    "Turkey": "TUR",
    "United States": "USA",
    "Uruguay": "URU",
    "Uzbekistan": "UZB",
}

TEAM_NAME_ALIASES = {
    "Cape Verde": ["Cabo Verde"],
    "DR Congo": ["Congo DR"],
    "Iran": ["IR Iran"],
    "Ivory Coast": ["Côte d'Ivoire", "Cote d'Ivoire"],
    "South Korea": ["Korea Republic"],
    "Turkey": ["Türkiye", "Turkiye"],
    "United States": ["USA"],
}


class FifaRankingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class FifaRankingMetadata:
    schedule_id: str
    published_date: str | None
    last_update_date: str | None
    next_update_date: str | None


@dataclass(frozen=True)
class FifaRanking:
    rank: int
    country_code: str
    name: str
    total_points: float
    previous_rank: int | None = None


@dataclass(frozen=True)
class TeamRankingChange:
    team_name: str
    old_rank: int | None
    new_rank: int
    old_points: float | None
    new_points: float


@dataclass(frozen=True)
class TeamConfigUpdateResult:
    teams: list[dict[str, Any]]
    changes: list[TeamRankingChange]
    missing_teams: list[str]
    metadata: FifaRankingMetadata


def fetch_latest_fifa_rankings(timeout: int = 30) -> tuple[FifaRankingMetadata, list[FifaRanking]]:
    metadata = fetch_latest_fifa_ranking_metadata(timeout=timeout)
    rankings = fetch_fifa_rankings_for_schedule(metadata.schedule_id, timeout=timeout)
    return metadata, rankings


def fetch_latest_fifa_ranking_metadata(timeout: int = 30) -> FifaRankingMetadata:
    try:
        response = requests.get(FIFA_RANKING_PAGE_URL, headers=REQUEST_HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FifaRankingsError("Could not fetch FIFA ranking page.") from exc
    return extract_latest_fifa_ranking_metadata(response.text)


def extract_latest_fifa_ranking_metadata(page_html: str) -> FifaRankingMetadata:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        page_html,
        flags=re.DOTALL,
    )
    if not match:
        raise FifaRankingsError("Could not find FIFA __NEXT_DATA__ payload.")

    try:
        next_data = json.loads(match.group(1))
        ranking_data = next_data["props"]["pageProps"]["pageData"]["ranking"]
        latest_date = ranking_data["allAvailableDates"][0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise FifaRankingsError("Could not read latest FIFA ranking metadata.") from exc

    schedule_id = latest_date.get("id")
    if not schedule_id:
        raise FifaRankingsError("FIFA latest ranking metadata did not include a schedule id.")

    return FifaRankingMetadata(
        schedule_id=schedule_id,
        published_date=latest_date.get("date"),
        last_update_date=ranking_data.get("lastUpdateDate"),
        next_update_date=ranking_data.get("nextUpdateDate"),
    )


def fetch_fifa_rankings_for_schedule(
    schedule_id: str,
    timeout: int = 30,
) -> list[FifaRanking]:
    try:
        response = requests.get(
            FIFA_RANKINGS_BY_SCHEDULE_URL,
            params={"rankingScheduleId": schedule_id, "language": "en", "count": 300},
            headers=REQUEST_HEADERS,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise FifaRankingsError(f"Could not fetch FIFA rankings for {schedule_id}.") from exc
    except ValueError as exc:
        raise FifaRankingsError(f"FIFA rankings for {schedule_id} were not valid JSON.") from exc

    return parse_fifa_rankings_response(payload)


def parse_fifa_rankings_response(payload: dict[str, Any]) -> list[FifaRanking]:
    rankings: list[FifaRanking] = []
    for row in payload.get("Results") or []:
        rank = row.get("Rank")
        country_code = row.get("IdCountry")
        total_points = row.get("DecimalTotalPoints")
        if total_points is None:
            total_points = row.get("TotalPoints")
        team_name = _localized_description(row.get("TeamName"))

        if not rank or not country_code or total_points is None or not team_name:
            continue

        rankings.append(
            FifaRanking(
                rank=int(rank),
                country_code=str(country_code).upper(),
                name=team_name,
                total_points=float(total_points),
                previous_rank=_int_or_none(row.get("PrevRank")),
            )
        )

    if not rankings:
        raise FifaRankingsError("FIFA ranking response did not include any ranking rows.")

    return rankings


def update_team_config_rankings(
    teams: list[dict[str, Any]],
    rankings: list[FifaRanking],
    metadata: FifaRankingMetadata,
) -> TeamConfigUpdateResult:
    rankings_by_code = {ranking.country_code.upper(): ranking for ranking in rankings}
    rankings_by_name = {_normalize_name(ranking.name): ranking for ranking in rankings}
    changes: list[TeamRankingChange] = []
    missing_teams: list[str] = []
    updated_teams: list[dict[str, Any]] = []

    for team in teams:
        updated_team = dict(team)
        ranking = _find_ranking_for_team(updated_team, rankings_by_code, rankings_by_name)
        if ranking is None:
            missing_teams.append(str(updated_team.get("name", "<unknown>")))
            updated_teams.append(updated_team)
            continue

        old_rank = _int_or_none(updated_team.get("fifa_rank"))
        old_points = _float_or_none(updated_team.get("fifa_points"))
        new_points = round(ranking.total_points, 2)

        updated_team["fifa_rank"] = ranking.rank
        updated_team["fifa_points"] = new_points

        if old_rank != ranking.rank or old_points != new_points:
            changes.append(
                TeamRankingChange(
                    team_name=str(updated_team["name"]),
                    old_rank=old_rank,
                    new_rank=ranking.rank,
                    old_points=old_points,
                    new_points=new_points,
                )
            )

        updated_teams.append(updated_team)

    return TeamConfigUpdateResult(
        teams=updated_teams,
        changes=changes,
        missing_teams=missing_teams,
        metadata=metadata,
    )


def refresh_teams_file_from_fifa(
    teams_path: Path = TEAMS_PATH,
    dry_run: bool = False,
    timeout: int = 30,
) -> TeamConfigUpdateResult:
    metadata, rankings = fetch_latest_fifa_rankings(timeout=timeout)
    teams = json.loads(teams_path.read_text(encoding="utf-8"))
    result = update_team_config_rankings(teams, rankings, metadata)

    if result.missing_teams:
        missing = ", ".join(result.missing_teams)
        raise FifaRankingsError(f"Could not match FIFA rankings for: {missing}")

    if not dry_run:
        teams_path.write_text(_format_teams_json(result.teams), encoding="utf-8")

    return result


def _find_ranking_for_team(
    team: dict[str, Any],
    rankings_by_code: dict[str, FifaRanking],
    rankings_by_name: dict[str, FifaRanking],
) -> FifaRanking | None:
    team_name = str(team.get("name", ""))
    country_code = TEAM_FIFA_COUNTRY_CODES.get(team_name)
    if country_code:
        ranking = rankings_by_code.get(country_code)
        if ranking:
            return ranking

    candidate_names = [
        team_name,
        str(team.get("dataset_name", "")),
        *TEAM_NAME_ALIASES.get(team_name, []),
    ]
    for candidate in candidate_names:
        ranking = rankings_by_name.get(_normalize_name(candidate))
        if ranking:
            return ranking
    return None


def _localized_description(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return ""
    for locale in ("en-GB", "en"):
        for value in values:
            if value.get("Locale") == locale and value.get("Description"):
                return str(value["Description"])
    return str(values[0].get("Description") or "")


def _format_teams_json(teams: list[dict[str, Any]]) -> str:
    text_fields = ["name", "dataset_name", "confederation", "group"]
    widths = {
        field: max(len(json.dumps(str(team[field]), ensure_ascii=False)) for team in teams)
        for field in text_fields
    }
    lines = ["["]
    previous_group = None

    for index, team in enumerate(teams):
        group = str(team["group"])
        if index > 0 and group != previous_group:
            lines.append("")

        row = (
            "  {"
            f'"name": {_json_string(team["name"]):<{widths["name"]}}, '
            f'"dataset_name": {_json_string(team["dataset_name"]):<{widths["dataset_name"]}}, '
            f'"confederation": {_json_string(team["confederation"]):<{widths["confederation"]}}, '
            f'"group": {_json_string(group):<{widths["group"]}}, '
            f'"fifa_rank": {int(team["fifa_rank"]):<3}, '
            f'"fifa_points": {float(team.get("fifa_points", 0.0)):>7.2f}, '
            f'"is_host": {_json_bool(team.get("is_host")):<5}, '
            f'"flag_emoji": {_json_string(team.get("flag_emoji", ""))}'
            "}"
        )
        if index < len(teams) - 1:
            row += ","
        lines.append(row)
        previous_group = group

    lines.append("]")
    return "\n".join(lines) + "\n"


def _json_string(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _json_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None

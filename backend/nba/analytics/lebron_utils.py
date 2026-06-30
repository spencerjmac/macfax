from datetime import datetime
from pathlib import Path

NBA_SEASON_START_MONTH = 10   # October
NBA_SEASON_END_MONTH   = 6    # June (covers playoffs)
STALE_THRESHOLD_DAYS   = 14   # warn if this old during active season
OFFSEASON_WARNING_DAYS = 90   # warn if this old even in offseason


def is_nba_season_active() -> bool:
    month = datetime.now().month
    return month >= NBA_SEASON_START_MONTH or month <= NBA_SEASON_END_MONTH


def check_lebron_freshness(year: int, csv_path: str) -> dict:
    """
    Check a single LEBRON CSV for existence and staleness.

    Returns a dict with keys:
        exists, path, last_modified, age_days, season_active,
        status ("ok" | "warning" | "error"), message
    """
    path = Path(csv_path)
    season_active = is_nba_season_active()

    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "last_modified": None,
            "age_days": None,
            "season_active": season_active,
            "status": "error",
            "message": f"LEBRON CSV missing: {path}",
        }

    stat = path.stat()
    last_modified = datetime.fromtimestamp(stat.st_mtime)
    age_days = (datetime.now() - last_modified).total_seconds() / 86400

    if season_active and age_days > STALE_THRESHOLD_DAYS:
        status = "warning"
        message = (
            f"LEBRON data is {age_days:.0f} days old during active season "
            f"(threshold: {STALE_THRESHOLD_DAYS} days)"
        )
    elif not season_active and age_days > OFFSEASON_WARNING_DAYS:
        status = "warning"
        message = (
            f"LEBRON data is {age_days:.0f} days old "
            f"(threshold: {OFFSEASON_WARNING_DAYS} days for offseason)"
        )
    else:
        status = "ok"
        message = f"LEBRON data OK ({age_days:.1f} days old)"

    return {
        "exists": True,
        "path": str(path),
        "last_modified": last_modified,
        "age_days": age_days,
        "season_active": season_active,
        "status": status,
        "message": message,
    }


def check_all_lebron_files(data_dir: str, current_year: int) -> list[dict]:
    """
    Check current and prior season LEBRON CSVs.
    Returns list of check_lebron_freshness results with 'year' and 'is_current' added.
    """
    results = []
    for year in [current_year, current_year - 1]:
        csv_path = Path(data_dir) / f"lebron-data-{year}.csv"
        result = check_lebron_freshness(year, str(csv_path))
        result["year"] = year
        result["is_current"] = year == current_year
        results.append(result)
    return results

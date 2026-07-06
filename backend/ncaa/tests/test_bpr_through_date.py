"""
Static anti-leak guards for ncaa.analytics.player_value.bpr.through_date.

Every ORM query in through_date.py must carry a game-date bound, otherwise a
"date-bounded" rebuild silently reads full-season data — the exact defect this
module exists to fix (docs/bpr_audit/03_weakness_report.md item 3.1).

Data-dependent acceptance (season-end parity vs stored values, mid-season
divergence) runs against the live DB via:
    python manage.py validate_bpr_through_date --season YYYY
"""

import ast
import inspect

from ncaa.analytics.player_value.bpr import through_date

DATE_FILTER_TOKENS = ("game_date__lte", "game__game_date__lte")


def _filter_calls(tree: ast.AST):
    """Yield (lineno, kwarg_names) for every .filter(...) call in the module."""
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "filter"):
            kwargs = [kw.arg for kw in node.keywords if kw.arg]
            yield node.lineno, kwargs


def test_every_orm_filter_is_date_bounded():
    source = inspect.getsource(through_date)
    tree = ast.parse(source)
    offenders = []
    for lineno, kwargs in _filter_calls(tree):
        if not any(any(tok in (k or "") for tok in DATE_FILTER_TOKENS) for k in kwargs):
            offenders.append((lineno, kwargs))
    assert not offenders, (
        "through_date.py has .filter() calls without a game-date bound "
        f"(line, kwargs): {offenders}"
    )


def test_module_never_reads_playerseasonstats_or_teamseasonratings():
    # The whole point: rebuild from per-game sources, never from the
    # full-season aggregate tables. Check code identifiers (AST), not
    # docstring prose.
    source = inspect.getsource(through_date)
    tree = ast.parse(source)
    banned = {"PlayerSeasonStats", "TeamSeasonRatings"}
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in banned:
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in banned:
            used.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name in banned:
                    used.add(alias.name)
    assert not used, f"through_date.py must not read full-season tables: {used}"

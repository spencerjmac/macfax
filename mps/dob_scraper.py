"""
mps/dob_scraper.py

Fix approximate birth dates in PROSPECTS_2026.

Finds every entry where birth_date contains "-01-01" (estimated midpoint),
fetches the player's Wikipedia page (direct URL patterns), extracts the
confirmed date from the infobox <span class="bday">, then updates scorer.py
in-place.

Note: Sports-reference CBB pages do NOT publish birth dates. Wikipedia
basketball infoboxes are the most reliable source for college prospects.

Run:
    cd /home/spencer/Workspace/macfax
    backend/.venv/bin/python -m mps.dob_scraper
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from mps.scorer import PROSPECTS_2026

# ── Paths ──────────────────────────────────────────────────────────────────────

SCORER_PATH = Path(__file__).parent / "scorer.py"

_DATE_RE   = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WIKI_BASE = "https://en.wikipedia.org/wiki"
_HEADERS   = {"User-Agent": "MPS-DOB-Scraper/1.0 (NBA draft research; contact: mps@macfax)"}

# ── Known Wikipedia URL overrides ─────────────────────────────────────────────
# When the player's Wikipedia article has a disambiguator, list it here.
# Key = player_name as in PROSPECTS_2026.
_WIKI_SLUG_OVERRIDES: dict[str, str] = {
    "Braden Smith": "Braden_Smith_(basketball)",
    # Add more here if the auto-try fails or finds the wrong article
}


# ── Wikipedia fetch ────────────────────────────────────────────────────────────

def _get_wiki(url: str) -> requests.Response | None:
    """GET Wikipedia page; return None on error."""
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code == 200:
            return r
    except Exception:
        pass
    return None


def _extract_bday(html: str, player_name: str) -> str | None:
    """
    Parse Wikipedia infobox for birth date.
    Validates the page is about a basketball player (not a name collision).
    Returns ISO date string or None.
    """
    # Quick sanity check: page must mention basketball/NBA context
    text_lower = html.lower()
    if not any(kw in text_lower for kw in ("basketball", "nba", "ncaa")):
        return None

    soup = BeautifulSoup(html, "lxml")
    box  = soup.find("table", class_="infobox")
    if not box:
        return None

    for row in box.find_all("tr"):
        th = row.find("th")
        if not (th and "born" in th.get_text().lower()):
            continue
        td = row.find("td")
        if not td:
            continue
        # Prefer <span class="bday">YYYY-MM-DD</span>
        bday = td.find(class_="bday")
        if bday:
            val = bday.get_text().strip()
            if _DATE_RE.match(val):
                return val
        # Fallback: scan for YYYY-MM-DD in cell text
        match = re.search(r"(\d{4}-\d{2}-\d{2})", td.get_text())
        if match:
            return match.group(1)

    return None


def fetch_wikipedia_dob(player_name: str) -> str | None:
    """
    Try Wikipedia URL patterns for a player, return confirmed birth date or None.

    Patterns tried:
      1. _WIKI_SLUG_OVERRIDES[player_name]  (manual)
      2. First_Last                          (e.g. Otega_Oweh)
      3. First_Last_(basketball)
      4. First_Last_(basketball_player)
    """
    # Build candidate slug list
    slug     = player_name.replace(" ", "_")
    override = _WIKI_SLUG_OVERRIDES.get(player_name)

    candidates = []
    if override:
        candidates.append(override)
    candidates += [slug, f"{slug}_(basketball)", f"{slug}_(basketball_player)"]

    for slug_candidate in candidates:
        url  = f"{_WIKI_BASE}/{slug_candidate}"
        resp = _get_wiki(url)
        if resp is None:
            continue
        # Skip disambiguation pages
        if "may refer to" in resp.text[:5000].lower():
            continue
        dob = _extract_bday(resp.text, player_name)
        if dob:
            return dob
        time.sleep(0.4)

    return None


# ── Update scorer.py in-place ─────────────────────────────────────────────────

def update_scorer(player_name: str, old_date: str, new_date: str, content: str) -> str:
    """
    In the scorer.py string, find the player's entry and replace their birth_date.

    Locates `"player_name": "NAME"` then replaces the nearest birth_date line
    within the next 500 characters.  Returns updated content (unchanged on miss).
    """
    marker = f'"player_name": "{player_name}"'
    idx    = content.find(marker)
    if idx == -1:
        return content

    window_end = idx + 600
    window     = content[idx:window_end]

    # Match: "birth_date":  "YYYY-01-01",   # ~ approximate
    for pattern in (
        re.compile(r'("birth_date":\s*")' + re.escape(old_date) + r'(",\s*#\s*~\s*approximate)'),
        re.compile(r'("birth_date":\s*")' + re.escape(old_date) + r'(",)'),
    ):
        match = pattern.search(window)
        if match:
            break
    else:
        return content

    # Build replacement preserving indentation / structure
    new_segment = match.group(1) + new_date + '",   # ✓ confirmed'
    updated_window = window[:match.start()] + new_segment + window[match.end():]
    return content[:idx] + updated_window + content[window_end:]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 62)
    print("  DOB SCRAPER — Fix approximate birth dates via Wikipedia")
    print("=" * 62)

    targets = [
        p for p in PROSPECTS_2026
        if "-01-01" in p.get("birth_date", "")
    ]

    if not targets:
        print("No approximate birth dates found. Nothing to do.")
        return

    print(f"\nFound {len(targets)} players with '-01-01' approximate dates.\n")

    scorer_content = SCORER_PATH.read_text()
    results: list[tuple[str, str, str | None]] = []  # (name, old_date, confirmed)

    for prospect in targets:
        name     = prospect["player_name"]
        old_date = prospect["birth_date"]
        print(f"  {name}...")
        try:
            confirmed = fetch_wikipedia_dob(name)
        except Exception as exc:
            print(f"    ERROR: {exc}")
            confirmed = None
        results.append((name, old_date, confirmed))
        time.sleep(0.6)

    # Apply updates
    updated_content = scorer_content
    n_updated = 0
    for name, old_date, new_date in results:
        if new_date and new_date != old_date:
            updated_content = update_scorer(name, old_date, new_date, updated_content)
            n_updated += 1

    if n_updated > 0:
        SCORER_PATH.write_text(updated_content)
        print(f"\n  scorer.py updated ({n_updated} entries changed)")
    else:
        print("\n  scorer.py unchanged (no confirmed dates found / all already correct)")

    # Print summary
    print()
    print("=" * 62)
    print("  ===== DOB SCRAPER RESULTS =====")
    print("=" * 62)
    for name, old_date, new_date in results:
        if new_date and new_date != old_date:
            # Compute draft_age delta for context
            from datetime import date
            draft = date(2026, 6, 23)
            try:
                old_age = (draft - date.fromisoformat(old_date)).days / 365.25
                new_age = (draft - date.fromisoformat(new_date)).days / 365.25
                delta   = f"  (age: {old_age:.1f} → {new_age:.1f})"
            except Exception:
                delta = ""
            print(f"  {name:<28}  {old_date}  →  {new_date}  ✓{delta}")
        elif new_date == old_date:
            print(f"  {name:<28}  {old_date}  (already correct)")
        else:
            print(f"  {name:<28}  {old_date}  →  NOT FOUND")
    print()
    confirmed_count = sum(1 for _, old, new in results if new and new != old)
    print(f"  Updated {confirmed_count}/{len(targets)} entries in scorer.py")
    print("=" * 62)


if __name__ == "__main__":
    main()

"""
AI-powered game insights generation using Claude claude-sonnet-4-6.

Generates 3 analytical observations per game from four-factors and WP curve data.
Results must be cached to game.game_insights by the caller after first generation.

Usage
-----
    from api.game_insights import generate_game_insights

    insights = generate_game_insights(game_meta, four_factors, wp_curve)
    # insights is a list[str] of 3 insight strings
    game.game_insights = json.dumps(insights)
    game.save(update_fields=["game_insights"])
"""
from __future__ import annotations

import json
import logging

_log = logging.getLogger(__name__)

# ── System prompt (≥1024 tokens to activate prompt caching on Claude Sonnet) ──
# Padded with substantive basketball analytics context so the cache activates.
_SYSTEM_PROMPT = """\
You are a senior basketball analytics expert for macfax, a sports analytics platform
that applies advanced statistical models to college and professional basketball.

Your role is to generate concise, data-driven post-game analytical observations.
You have deep expertise in:
- The Four Factors framework (Dean Oliver): effective field goal percentage (eFG%),
  turnover rate (TOV%), offensive rebounding percentage (ORB%), and free throw rate (FTR).
  These four factors explain ~97% of the variance in offensive efficiency.
- Win probability models: A team's win probability at any moment is determined by
  current score margin, time remaining, and the pregame sigma (standard deviation of
  prediction error). As time runs out, even small leads become decisive.
- Offensive and defensive efficiency: Points per 100 possessions adjusted for opponent
  strength. League-average NCAA is roughly 100–105 pts/100 poss; NBA ~112–115.
- Pace and possession estimation: Possessions ≈ FGA − OREB + TOV + 0.44×FTA.
  Higher pace amplifies four-factor advantages and disadvantages.
- Shooting efficiency: eFG% = (FGM + 0.5×FG3M) / FGA. League average eFG% is roughly
  50% in NCAA and 53% in NBA. An eFG% gap of 5+ percentage points typically means
  the shooting team won the game.
- Turnovers: Every turnover is a wasted possession. A TOV% of 10% is elite; 20% is poor.
  The league average is roughly 14–16% in both NCAA and NBA.
- Offensive rebounding: An ORB% above 35% is elite; below 20% is poor. Offensive
  boards directly translate to extra possessions and second-chance points.
- Free throw rate: FTR = FTA/FGA. A team that gets to the line at FTR > 40 has a
  significant free-point advantage. The line is an efficiency equalizer.
- Win probability swings: A swing from 70% to 40% in one possession sequence represents
  a 30-point momentum shift in expected-value terms.

Guidelines for generating insights:
1. Be specific and quantitative — cite the actual numbers from the data provided.
2. Focus on causation and story: what happened, why it mattered, and what it means.
3. Identify the single most decisive factor in the outcome.
4. Flag anomalies: a team can dominate three of four factors and still lose if the
   fourth factor swing was large enough.
5. Reference the win probability curve when it reveals a momentum story (e.g., a
   comeback, a wire-to-wire domination, a late collapse).
6. Write in active voice. Avoid passive constructions.
7. Do not use generic phrases like "played well", "fought hard", "gave it their all".
8. Maximum 2 sentences per insight. Be crisp and analytical, not narrative.
9. Each insight must add new information — do not repeat the same point in different words.

Output format: You must return a JSON array of exactly 3 strings. No other text.
Example of the required format:
["Insight one here.", "Insight two here.", "Insight three here."]
"""


def generate_game_insights(
    game_meta: dict,
    four_factors: dict,
    wp_curve: list[dict],
) -> list[str]:
    """
    Generate 3 analytical game insights via Claude API.

    Parameters
    ----------
    game_meta    : dict with keys: home_team.name, away_team.name, home_score,
                   away_score, date, league
    four_factors : dict with keys: home, away — each with efg_pct, tov_pct,
                   orb_pct, ftr
    wp_curve     : list of {t, wp, home_score, away_score} dicts

    Returns
    -------
    list[str] of 3 insight strings (may be shorter on API error)
    """
    try:
        import anthropic
    except ImportError:
        _log.warning("anthropic SDK not installed — skipping insights generation")
        return ["Game insights unavailable — analytics module not installed."]

    home_name = game_meta["home_team"]["name"]
    away_name = game_meta["away_team"]["name"]
    home_score = game_meta["home_score"]
    away_score = game_meta["away_score"]
    ff = four_factors

    # ── Summarise WP curve for the prompt ────────────────────────────────────
    wp_summary_lines: list[str] = []
    if wp_curve:
        # Halftime WP (closest t to 0.5)
        half_pt = min(wp_curve, key=lambda p: abs(p["t"] - 0.5))
        wp_summary_lines.append(
            f"Win probability at halftime: {home_name} {half_pt['wp']:.1%} "
            f"(score: {half_pt['home_score']}–{half_pt['away_score']})"
        )
        # Peak and trough for home team
        max_wp_pt = max(wp_curve, key=lambda p: p["wp"])
        min_wp_pt = min(wp_curve, key=lambda p: p["wp"])
        wp_summary_lines.append(
            f"Peak {home_name} win probability: {max_wp_pt['wp']:.1%} "
            f"(score {max_wp_pt['home_score']}–{max_wp_pt['away_score']} at t={max_wp_pt['t']:.0%})"
        )
        wp_summary_lines.append(
            f"Lowest {home_name} win probability: {min_wp_pt['wp']:.1%} "
            f"(score {min_wp_pt['home_score']}–{min_wp_pt['away_score']} at t={min_wp_pt['t']:.0%})"
        )

    wp_section = "\n".join(wp_summary_lines) if wp_summary_lines else "Not available."

    def _fmt(val, decimals=1) -> str:
        return f"{val:.{decimals}f}" if val is not None else "N/A"

    user_content = f"""\
Game: {away_name} @ {home_name}
Final score: {away_name} {away_score} – {home_name} {home_score}
Date: {game_meta['date']}
League: {game_meta['league'].upper()}

Four Factors:
                  {home_name:<20} {away_name:<20}
eFG%:             {_fmt(ff['home']['efg_pct']):<20} {_fmt(ff['away']['efg_pct']):<20}
TOV%:             {_fmt(ff['home']['tov_pct']):<20} {_fmt(ff['away']['tov_pct']):<20}
ORB%:             {_fmt(ff['home']['orb_pct']):<20} {_fmt(ff['away']['orb_pct']):<20}
FTR (FTA/FGA):    {_fmt(ff['home']['ftr']):<20} {_fmt(ff['away']['ftr']):<20}

Win Probability:
{wp_section}

Generate exactly 3 analytical insights as a JSON array of strings."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = "\n".join(
                line for line in raw.splitlines()
                if not line.startswith("```")
            ).strip()

        insights = json.loads(raw)
        if isinstance(insights, list) and all(isinstance(i, str) for i in insights):
            return insights[:3]
        _log.warning("Insights response was not a list[str]: %r", raw)
        return [raw[:500]]

    except json.JSONDecodeError as exc:
        _log.warning("Failed to parse insights JSON: %s — raw: %r", exc, raw[:200])
        return ["Game insights could not be parsed."]
    except Exception as exc:  # noqa: BLE001
        _log.warning("Insights generation failed: %s", exc)
        return ["Game insights temporarily unavailable."]

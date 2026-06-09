# Ideas & Backlog

## Analytics / Ratings

- Improve BPR ratings by backtesting and trying to match Evan Miya (Claude)
- Analyze BPR ratings for NBA players, compare to RAPTOR or LEBRON to see improvements (Claude)
- Explore adding Injury Adjustment to ratings — if a player is injured, adjust the team's rating accordingly (Claude)
- Explore adding a pre-tournament filter for NCAA Player stats and Team Rankings
- Backtest the Cinderella Index to verify formula and weights are optimal (Claude)
- Check team migrations for historical seasons since some teams go in/out of Division I (Claude)
- Explore adding pace adjustment to matchup model — teams that play better in faster/slower games (Claude)
- Explore adding a "clutch" factor to the Matchup Model based on close-game performance (Claude)
- Do a deep dive into the NCAA Basketball Matchup Model — accuracy, missing adjustments (after adjusted ratings work)
- Get all historical player data from past seasons to improve current data (Chat)
- Explore if we should change/add/remove any criteria for the NCAA Champion Checklist (Claude)
- Explore the Trapezoid of Excellence formula — is there a better shape formula? (Claude or Chat)

## Stats & Metrics to Add to Database

**NCAA:**
- BPR (have it, needs improvement)
- Four Factor Player stats (have it, needs improvement)
- USG% (Usage Percentage)
- FTA Rate (Free Throw Attempt Rate)
- 3PA Rate (Three Point Attempt Rate)
- Proj NBA 3P% (Projected NBA Three Point Percentage)
- AST/USG (Assist to Usage Ratio)
- AST/TO (Assist to Turnover Ratio)
- PER (Player Efficiency Rating)
- OWS and OWS/40
- DWS and DWS/40
- WS and WS/40
- BPM, OBPM, DBPM

**NBA:**
- BPR (have it, needs improvement)
- Four Factor Player stats (have it, needs improvement)
- RAPM (Regularized Adjusted Plus-Minus)
- LEBRON
- RAPTOR
- DARKO

## Design System

- Work on design system to upgrade look and feel of website (Claude)
- Home Page — better layout, better graphics on NBA and NCAA cards
- Change the subtitle on the NCAA Basketball Homepage
- Remove "Teams 365 Conferences 32 Games modeled 5.4k" from NCAA homepage
- Remove "30 teams 2 conferences 1.2k games modeled" from NBA homepage
- Update NCAA Rankings page to match Claude design; add red back to heatmap
- Update ranking tables — Efficiency, Four Factors, Adjusted Four Factor, Traditional/Impact/Four Factor player tables
- Make design and format consistent between NCAA and NBA (rankings, team profile, visualizations)
- Fix Bracket Simulator icon on NCAA Visualizations homepage
- Change Viz Builder icon on Viz Homepage
- Highlight historical season champions on Visualizations (gold highlight?)
- Highlight champions on Trapezoid of Excellence

## Team Profile

- Update Game Log page format — include best stats for games (Chat)
- Update format and design of Off/Def tab
- Explore filling in the Charts tab

## Visualizations (NBA)

- Add visualizations to NBA web app (Claude)
- Explore Trapezoid of Excellence for NBA (30 teams — could work)
- Add Efficiency Landscape to NBA Visualizations
- Add NBA Crystal Ball (like NCAA Crystal Ball)

## Features

- Explore adding Team Breakdown to Team Profile for NCAA and NBA (like Evan Miya's team report) (Claude)
- Explore adding Keys to Victory to NCAA and NBA matchups (Claude)
- Explore NIL value for players — incorporate player monetary value for front office insights (Claude)
- NBA Awards scores: MVP Score, DPOY Score, ROY Score, etc. (Claude)
- Roster Outlook fixes:
  - Fix Offensive and Defensive Ranks in Scenario
  - Add incoming freshmen to database or make freshman recruiting archetypes (Claude)
  - Fix ranges to be more realistic (currently too wide)
  - Fix logic when adding newcomer/transfer — All-Conference player added should slightly lower projected rating since not retained
  - Review Offensive Fit and Defensive Fit grades

## NBA Draft / Prospects

- Switch Prospect Score and Profiles from scraper to our own database (Claude)
- Social media content templates (Claude):
  - NBA Draft Prospect Rankings
  - Draft Prospect Profiles (grades, measurements, comps)
  - Roster Outlook pages for teams
  - Way-too-early Top 25 for NCAA
  - Offseason analysis for NBA teams (draft, free agency, coaching changes)
  - Transfer Portal Rankings
  - NBA Mock Draft
  - NBA Trade Analysis with trade score

## World Cup

- Explore adding a full World Cup web app with advanced soccer analytics — team rankings, player profiles, matchups, visualizations (Claude)
- Social media: World Cup game predictions, World Cup rankings

## Infrastructure

- Update the update-all commands for both NBA and NCAA so all data is current
- Update NBA players and teams command to have the missing steps

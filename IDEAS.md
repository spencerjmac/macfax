
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
- Update ranking tables — Efficiency, Four Factors, Adjusted Four Factor, Traditional/Impact/Four Factor player tables
- Make design and format consistent between NCAA and NBA (rankings, team profile, visualizations)
- Fix Bracket Simulator icon on NCAA Visualizations homepage
- Change Viz Builder icon on Viz Homepage
- Highlight historical season champions on Visualizations (gold highlight?)
- Highlight champions on Trapezoid of Excellence
- Tone down overall design — less loud, more understated; target FiveThirtyEight aesthetic
- Preserve graphic structure, simplify visual noise
- Audit team rankings table — verify correct stats shown, clean up layout and structure
- Audit NCAA player stats tables — right stats, intentional column selection, clean presentation; no data blobs

## Macfax Home Page

## NCAA Homepage
- Take out the part where it says 365 teams and amound of games modeled and stuff thats pointless
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like
- Should we display the number 1 team in the model?
- Change the subtitle on the NCAA Basketball Homepage

## NCAA Rankings
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like
- Update the design on the rankings table like how claude design has it or at least update the look so it looks better and nicer
- Update the player stats table to be consistent with the team rankings table in terms of design and stuff
- Make sure for team and player ratings that the stats that we are showing on the correct ones we want to show and are desinged, formatted and structured right
- Make sure all the seasons for team ratings and player ratings are updated with the changes we have made
- Improve and backtest the NCAA BPR so that it is as accurate as possible (we need to deep dive into this)
- Should the name be NCAA Rankings or Ratings
- Should we have seperate tabs and entire pages for Team and Player ratings?
- Fix the Four Factor Player Stats
- Make sure on the raw four factors page the FFI stat is showing the raw FFI not adjsuted FFI
- Go over the Adjusted Ratings and go over it with claude code and backtesting to make sure its as accurate as it can be and adjust it or add things to it. We should compare it to KenPom and Evan Miya if we haven't already and compare it truly
- Western Michigan and Eastern Michigan are both missing their logos
- Update NCAA Rankings page to match Claude design; add red back to heatmap

## NCAA Matchup Tool
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like
- Make sure the Game Forcast Calculations are all correct for everything
- Go over the Four Factor Breakdown and make sure all of the math is accurate and the translation to points is all correct as well
- Go over the Volatility score deeply and make sure this all makes sense

## NCAA Roster Outlook
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like
- We need to get the Incoming Freshman data in for big name prospects somehow and calculate the correct impact they would have like specific names
- We need to go over all the ranks and ranges and math and code of everything to make sure its accurate (The ranks and ranges of things seem to be off)
- This could also maybe be for player stats, but we should find a way to incorporate NIL money into this like how much a player is worth vs how much they are getting paid and add budgets to this and for teams 

## NCAA Visualization Homepage
- We need to change the icons of the visulizations that we have for Efficiency Landscape, Crystal Ball Kinda, Cinderella Index, Bracket Simulator, Viz Builder, And Killshot
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like
- We need to change the Titles and subtitles of Viz pages so that its not sounding AI generated

## Trapezoid of Excellence
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like (Its honestly pretty good just putting it on here just in case)

## NCAA Efficiency Landscape
- We have made changes in Our Crystal Ball in our Title Favorite Tier to capture all past champions and we might need to update that in our viz. So orginally this Title Favorite Tier was based off the last 6 champions which would make sense since the game changes a lot but we need to make sure that the math in our viz matches the crystal ball math
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like 
- And just refine all of the tier on the Efficiency Landscape

## NCAA Crystall Ball
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like 
- Change up the Tiers and Tier names so that it makes more sense, like for example the Championship Tier should be only teams that are 15/15
- There is still some errors in accuracy meaning some past champions still dont pass some criteria except for the Uconn rule those champions are Baylor 2020-21: Balanced Dominance
O: 119.9 / D: 94.8((O ≥ 112.2 & D ≤ 94.7) or EM ≥ 25.9), Louisville 2012-13: 
3-Point %
32.2%(≥ 32.2%), 
- Fix so that when you click on a team on the Crystal Ball like the name itself, it either takes you to their team profile page or the drop down right now it comes up with a 404 error

## Cinderella Index
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like 
- We need to fix the tiers so that it is more rerpresentative
- Backtest all the code and math and make sure its as accurate as possible

## NBA Homepage
- Claude Overview of it, give screenshots of the homepage and tell whats wrong with it in terms of the content of whats on there like words and placement and reference what its suppoesed to look like
- Should we display the number 1 team in the model?
- Take out the part where it says 30 teams, 2 conferences and games modeled

## NBA Crystal Ball
- We are missing the seed data for the crystal ball so that criteria is left blank for every team
- We need pre-playoff data for this we might already have that though
- we need historical season data as well

## Content

- Top 10 NBA Players right now
- Top 10 NBA Players of All Time
- G.O.A.T post
- Trade Analysis Post (Grade, Winners, Losers)
- Top 10 PGs
- Top 10 SGs
- Top 10 SFs
- Top 10 PFs
- Top 10 Cs
- Top 10 Teams of all time
- Top 10 Clutchest Players of all time
- Way Too early Rankings for NCAA and NBA
- NBA Award Rankings, (MVP DPOY ROY and others)
- Roster Outlook Analysis for NCAA
- Top 10 College Basketball Teams of all time
- NBA Top 10 Fastest Players of All time
- One-and-Done vs. 4-Year Players: Who's Actually Better in the NBA?" Metric: Average MPS by years played. This is a research piece disguised as a list. The answer is probably more nuanced than the conventional wisdom.
- Anatomy of a Dynasty" — Pick a championship team, show the Crystal Ball criteria they met. Build toward an explanation of why they won.
- Head-to-Heads — Jordan vs. LeBron, not vibes. Pick 4–5 measurable dimensions, score each, render a verdict. The specific methodology is the content.
- 1. “The Truth Score”

This is the broadest and probably best umbrella series.

Concept: Take a common sports debate and create a composite score to answer it.

Examples:

Top 10 NBA Players Right Now
Top 10 Best Players Under 25
Top 10 Most Overrated NBA Players
Top 10 Most Underrated NBA Players
Top 10 Best NCAA Transfer Portal Adds
Top 10 Best NBA Draft Fits
Top 10 Best World Cup Teams
Top 10 Most Dangerous March Madness Teams
Top 10 Best Two-Way Players
Top 10 Best Winning Players

How to measure it:

For NBA players:

Truth Score =
35% impact metrics
25% box production
15% efficiency
15% role difficulty
10% team context / winning impact

For college teams:

Truth Score =
35% adjusted efficiency margin
20% offense
20% defense
10% schedule strength
10% recent form
5% roster stability

For World Cup teams:

Truth Score =
30% market/team rating
25% recent form
20% attacking quality
15% defensive quality
10% squad depth

TikTok hook examples:

“I built a score to find the actual top 10 NBA players right now.”
“This ranking is going to make people mad, but the numbers are the numbers.”
“I ranked every World Cup team using a Mac Facts score. One favorite is way too high.”

This is the easiest series to repeat forever.

- 4. “Player Archetype Rankings”

This fits your basketball brain and gives you a ton of repeatable content.

Concept: Don’t just rank overall players. Rank specific player types.

Examples:

Top 10 Playmakers
Top 10 Rim Pressure Guards
Top 10 Pure Shooters
Top 10 Shot Creators
Top 10 Off-Ball Stars
Top 10 Defensive Anchors
Top 10 3-and-D Wings
Top 10 Connector Players
Top 10 Chaos Defenders
Top 10 Transition Weapons
Top 10 Half-Court Creators
Top 10 “Playoff Players”

How to measure it:

Example: Shot Creator Score

Shot Creator Score =
30% self-created scoring volume
20% isolation / pick-and-roll efficiency
15% pull-up shooting
15% rim pressure
10% turnover control
10% late-clock usage

Example: 3-and-D Score

3-and-D Score =
30% defensive matchup difficulty
25% defensive impact
20% 3PT volume
15% 3PT efficiency
10% low-usage offensive value

Example: Playmaker Score

Playmaker Score =
30% assist creation
20% passing efficiency
20% turnover control
15% creation burden
15% teammate shot quality

This would be great because every player fanbase can argue.

- 15. “The Player Stock Market”

This could be a recurring weekly series.

Concept: Players are stocks. Buy, sell, hold.

Examples:

NBA player stocks I’m buying
College basketball teams I’m selling
Draft prospects rising/falling
World Cup teams to buy before everyone else notices
Transfer portal stock watch
Sophomore breakout stock watch

How to measure it:

Stock Score =
30% recent performance trend
20% underlying metrics
20% role opportunity
15% sustainability
15% public perception gap

Labels:

Strong Buy
Buy
Hold
Sell
Crash Warning

This format is easy, fun, and repeatable.

- Next season outlooks for the NCAA College Teams, since there are like 365 teams in College Basketball I say we go through each conference and then we have like the homepage be the title with the conference and then like the projected standings for next season for that conference, then each slide go through each team with like their projected record, seed in the tournament if they make it, lineup and starting five and just like all the different things and insights we would want to show an audience for each team in that conferece. Like Im thinking expected record, seed, and all that stuff i might help with ideas on what content to put on each slide

- Next season outlooks for NBA teams, I really wanna do this one and maybe for all NBA teams, maybe starting after the NBA draft we can go through each team and have slides for offseason outlook, maybe a capspace thing idk if we can, projected starting five, and then projected record and help me with other ideas in what to also put on there


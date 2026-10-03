import type { MethodologyContent, MethodologySectionConfig } from './methodologyTypes';

export const methodologyContent: MethodologyContent[] = [
  {
    slug: 'adjusted-ratings',
    section: 'core-ratings',
    title: 'Macfax Adjusted Ratings',
    subtitle: 'How Macfax estimates team strength',
    description: 'How Macfax estimates team strength using opponent-adjusted offensive, defensive, net, and tempo ratings.',
    bestUsedFor: 'Comparing overall team quality across unequal schedules',
    summary:
      'Adjusted Ratings are the backbone of Macfax team strength estimates. They measure how efficiently a team scores and prevents scoring per possession, then correct those raw numbers for opponent quality, game location, and sample size. The result is a fairer, more stable basis for comparing teams across wildly unequal schedules.',
    whatItMeasures:
      'Four values, all expressed per 100 possessions on a neutral-site basis against an average Division I opponent. AdjO (Adjusted Offensive Efficiency) measures points scored. AdjD (Adjusted Defensive Efficiency) measures points allowed — lower is better. AdjEM (Adjusted Efficiency Margin) is AdjO minus AdjD, the single best summary of overall team quality. AdjTempo is projected possessions per 40 minutes.',
    whyItMatters:
      'Points per game lies. A team scoring 80 against a weak non-conference schedule is not the same as one scoring 80 against elite opponents every night. Raw win-loss records suffer from the same distortion. Adjusted Ratings remove schedule context, letting you ask a more honest question: how good is this team on a neutral floor against equal competition?',
    howToInterpret:
      'AdjEM is the number to watch. Positive means the team outscores opponents per possession; negative means they get outscored. National average is 0 by definition — it is a margin above or below the mean. AdjO and AdjD are centered around the national scoring average — roughly 100 points per 100 possessions in a typical season. An AdjO of 118 is elite offense. An AdjD of 94 is elite defense.',
    basicFormula: {
      latex:
        '\\text{Poss} = \\text{FGA} - \\text{OREB} + \\text{TOV} + 0.475 \\times \\text{FTA}',
      prose:
        'Raw OE = 100 × Points / Possessions\nRaw DE = 100 × Opp Points / Opp Possessions\nAdjEM = AdjO − AdjD',
    },
    interpretationBands: [
      { label: 'Title Contender', range: '+30 and above', color: 'success', description: 'Historically among the best teams in the country. Deep tournament run expected.' },
      { label: 'Tournament Team', range: '+15 to +25', color: 'brand', description: 'At-large quality. Strong enough to win games in the tournament.' },
      { label: 'Bubble', range: '+10 to +15', color: 'secondary', description: 'Competitive but dependent on schedule and resume for selection.' },
      { label: 'Average', range: '0 to +10', color: 'warning', description: 'Near the national mean. Tournament bid unlikely without dramatic improvement.' },
      { label: 'Struggling', range: 'below 0', color: 'negative', description: 'Gets outscored per possession on average. Structural team quality concerns.' },
    ],
    technicalNotes: [
      'Opponent adjustment is iterative — each team\'s rating depends on opponents\' ratings, which depend on their opponents\' ratings, and so on. The process runs until ratings converge.',
      'Location normalization adjusts home and away games to a neutral-site baseline using site factors derived from league-wide patterns. The exact calibration is internal to Macfax.',
      'Bayesian shrinkage pulls early-season ratings toward the national average. The pull weakens as games accumulate — ratings stabilize meaningfully after around 15–20 games.',
      'More recent games carry somewhat more weight to reflect current form. The model does not discard earlier results, but recency is factored in throughout the season.',
      'Extreme mismatches receive less weight than close, competitive games. Games that are unexpectedly close relative to the expected gap receive modestly more weight.',
      'Only games against Division I opponents count toward ratings.',
      'Exact calibration values for shrinkage, recency decay, and site adjustment are internal and may be recalibrated as validation data accumulates.',
    ],
    knownLimitations: [
      'Early-season ratings (first 10–15 games) carry high uncertainty. Treat them as directional, not definitive.',
      'Injuries, suspensions, and lineup changes are not automatically reflected — the model only knows what happened on the court.',
      'Non-conference schedule imbalance persists in adjusted ratings when a team has very few crossover games against diverse opponents.',
      'Possession estimates from box-score data are approximations. Play-by-play counts are more precise but not always available.',
      'Public box-score data occasionally contains errors. Corrections are applied on the next update cycle.',
    ],
    example:
      'A team with AdjO 118.5 and AdjD 94.2 has AdjEM +24.3 — they outscore opponents by 24.3 points per 100 possessions on a neutral floor against average Division I competition. In a typical season, this places them among the top five or ten teams nationally. A team with AdjO 105.0 and AdjD 104.8 has AdjEM +0.2 — barely above average, outscoring opponents by less than one possession per 100. These numbers live on the same scale, making cross-conference comparison direct.',
    relatedMetrics: [
      { label: 'The Four Factors', slug: 'four-factors' },
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'Matchup Model', slug: 'matchup-model' },
      { label: 'Efficiency Landscape', slug: 'efficiency-landscape' },
      { label: 'Trapezoid of Excellence', slug: 'trapezoid-of-excellence' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'four-factors',
    section: 'core-ratings',
    title: 'The Four Factors',
    subtitle: 'The four ways a team wins or loses possessions',
    description: 'The basketball foundation behind shooting efficiency, turnovers, rebounding, and free throw pressure.',
    bestUsedFor: 'Understanding how a team wins possessions, not just whether they do',
    summary:
      'The Four Factors — Effective Field Goal Percentage, Turnover Rate, Offensive Rebounding Rate, and Free Throw Rate — describe the four possession-level dimensions that determine basketball efficiency. Originally identified by basketball statistician Dean Oliver, they remain the most useful framework for understanding why teams win or lose without reducing everything to a single number. Macfax computes both raw and opponent-adjusted versions of each factor.',
    whatItMeasures:
      'Four rate statistics, each with an offensive and defensive version. eFG% measures shooting quality, with three-pointers weighted appropriately for their extra scoring value. TOV% measures ball security as turnovers per possession. ORB% measures second-chance creation as a share of available offensive rebounds. FTR measures free throw generation relative to field goal attempts. Margins compare the offensive and defensive versions of each — positive margin always means your team has the structural edge on that dimension.',
    whyItMatters:
      'Raw box-score stats reward pace and ignore context. A team that plays fast generates more raw points and rebounds — that does not mean they are better per possession. The Four Factors strip pace out and isolate how a team wins possessions, which is more actionable than a single efficiency number. Two teams can have the same AdjEM through completely different profiles — one through elite shooting, one through elite defense and rebounding. The Four Factors make that difference visible and comparable.',
    howToInterpret:
      'Look at margins first. A team with eFG% 54% is good; that same team holding opponents to 46% eFG% has an +8 eFG Margin, which is excellent. The margin direction is consistent: positive is always advantageous. eFG Margin = your eFG% minus opponent eFG%. Turnover Edge = opponent TOV% minus your TOV% (reversed so positive means you protect the ball and force turnovers). Rebounding Edge = your ORB% minus opponent ORB%. FTR Margin = your FTR minus opponent FTR.',
    basicFormula: {
      prose:
        'eFG% = (FGM + 0.5 × 3PM) / FGA\nTOV% = TOV / Possessions\nORB% = OREB / (OREB + Opp DREB)\nFTR = FTA / FGA\n\neFG Margin = Team eFG% − Opp eFG%\nTurnover Edge = Opp TOV% − Team TOV%\nRebounding Edge = Team ORB% − Opp ORB%\nFTR Margin = Team FTR − Opp FTR',
    },
    technicalNotes: [
      'eFG% weights three-pointers at 1.5× because a made three scores 50% more than a made two, making it a fair per-shot comparison across different shot selection profiles.',
      'Possessions are estimated using the standard formula: FGA − OREB + TOV + 0.475 × FTA. The 0.475 multiplier accounts for and-one plays and technical fouls where free throws do not end a possession.',
      'Macfax displays adjusted Four Factors by default. Each game-level factor is normalized against the opponent\'s capability on that specific dimension and to a neutral-site baseline. Exact calibration is consistent with the adjusted efficiency rating methodology.',
      'Turnover Edge is intentionally inverted from raw TOV% so that positive values are uniformly favorable across all four margins.',
      'Raw (unadjusted) versions of all Four Factors are also available for reference.',
    ],
    knownLimitations: [
      'eFG% does not distinguish shot quality within make type — a corner three and a mid-range two count the same if both go in.',
      'FTR does not separate intentional end-of-game fouling, technical fouls, or clear-path fouls from genuine offensive free throw generation.',
      'Offensive rebounding rates can reflect team philosophy as much as capability — teams that emphasize transition defense may intentionally sacrifice offensive boards.',
      'Adjusted Four Factors stabilize more slowly than adjusted efficiency for teams early in the season.',
      'Box-score data captures outcomes but not decision quality — a team can have a high ORB% while taking poor shots that create more rebound opportunities.',
    ],
    example:
      'Illustrative example: Team A posts an adjusted eFG Margin of +7.8, Turnover Edge of +6.3, Rebounding Edge of +5.3, and FTR Margin of +9.5 — positive on all four. This is an unusual and highly favorable Four Factor profile that typically correlates with elite adjusted efficiency margin. In practice, most strong teams dominate one or two factors and are average or slightly negative on the others. A team with +8 eFG Margin but −3 Rebounding Edge is still very dangerous — they just win differently.',
    relatedMetrics: [
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Matchup Model', slug: 'matchup-model' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'four-factor-index',
    section: 'core-ratings',
    title: 'Macfax Four Factor Index',
    subtitle: 'One standardized score from four possession-level margins',
    description: 'How Macfax combines Four Factor performance into one standardized 0–100 team profile score.',
    bestUsedFor: 'Quick comparison of overall possession-efficiency profile across teams and seasons',
    summary:
      'The Four Factor Index (FFI) converts the four possession-level margins into a single 0–100 score. Each margin is standardized relative to the national Division I distribution for that season, then combined using weights derived from foundational basketball research and refined empirically for college basketball. FFI exists in both raw and adjusted forms — the adjusted version accounts for opponent quality and is the primary metric displayed on Macfax.',
    whatItMeasures:
      'FFI measures a team\'s composite possession-efficiency advantage across all four margins — shooting quality, ball security, offensive rebounding, and free throw rate pressure — weighted by how much each dimension historically drives team performance. A higher score means a more dominant overall possession profile. Both a raw version (from unadjusted margins) and an adjusted version (from opponent-adjusted margins) are computed. The adjusted FFI is the primary value shown on Macfax.',
    whyItMatters:
      'Individual Four Factor margins require context to interpret. A +4 eFG margin is excellent; a −2 rebounding edge might not matter much if the team has elite shooting and turnover advantages. FFI removes that friction by collapsing all four margins into a single number on a consistent scale, with shooting weighted most heavily because it predicts outcomes most reliably. It is easier to compare two teams\' overall possession profiles at a glance than to mentally weigh four separate margins.',
    howToInterpret:
      'FFI is centered at 50, which represents exactly average national Four Factor performance for that season. Scores above 60 are strong. Scores above 80 are elite. Scores below 40 indicate structural possession-level disadvantages. The scale is capped at 0 and 100. One important caveat: FFI is season-relative. A score of 68 in 2025–26 reflects performance relative to 2025–26 Division I averages, not a universal standard. Scores are not directly comparable across different seasons.',
    basicFormula: {
      latex:
        'FFI = \\text{clamp}(50 + 20 \\times \\text{Weighted Z-Score},\\ 0,\\ 100)',
      prose: 'Weighted Z-Score = w₁·z_eFG + w₂·z_TOV + w₃·z_REB + w₄·z_FTR\n\nEach z-score is computed relative to the current season\'s national Division I distribution.',
    },
    weights: [
      { label: 'eFG% Margin', value: '47%', pct: '47' },
      { label: 'Turnover Edge', value: '24%', pct: '24' },
      { label: 'Rebounding Edge', value: '21%', pct: '21' },
      { label: 'Free Throw Rate Margin', value: '8%', pct: '8' },
    ],
    interpretationBands: [
      { label: 'Elite', range: '80–100', color: 'success', description: 'Top national possession profile. Dominant on multiple factors.' },
      { label: 'Strong', range: '60–79', color: 'brand', description: 'Above average across most factors. Consistent possession-level advantage.' },
      { label: 'Average', range: '45–59', color: 'secondary', description: 'Near national mean. Competitive but no clear structural edge.' },
      { label: 'Below Average', range: '35–44', color: 'warning', description: 'Possession-level disadvantages present. Tends to lose close games.' },
      { label: 'Weak', range: '0–34', color: 'negative', description: 'Significant possession-level deficits. Structural team quality concerns.' },
    ],
    technicalNotes: [
      'Weights were inspired by Dean Oliver\'s foundational Four Factors research and empirically refined for college basketball. College basketball differs from the NBA data Oliver originally analyzed, particularly in the relative importance of shooting vs. other factors.',
      'eFG% margin carries the highest weight because shooting quality is the single strongest predictor of possession-level success at the college level in the current version.',
      'Z-scores are computed relative to the full Division I national distribution for the current season. This means FFI scores shift year to year as the national baseline shifts.',
      'The 20× scale multiplier controls the spread of the 0–100 distribution. The exact calibration is internal to Macfax.',
      'Individual component z-scores (eFG, TOV, REB, FTR) are available separately to show where a team\'s FFI is coming from.',
      'Weights may be recalibrated between seasons as additional validation data accumulates.',
    ],
    knownLimitations: [
      'FFI scores are not comparable across seasons — a 68 in 2025–26 and a 68 in 2026–27 are relative to different national baselines.',
      'Two teams can have identical FFI scores through very different factor profiles. Check individual margins to understand how a team achieves their score.',
      'Early-season FFI is directional only. Adjusted margins stabilize more slowly than adjusted efficiency, and the national z-score distribution is noisier with fewer games played.',
      'Adjusted FFI depends on the accuracy of opponent-adjusted four factors, which carry the same schedule-imbalance limitations as adjusted efficiency ratings.',
      'Weights may be recalibrated between seasons, which means a score of 65 in one season may be weighted slightly differently internally than a 65 in the prior season.',
    ],
    example:
      'Illustrative: Team A and Team B both have FFI 64. Team A gets there through dominant shooting (+7 eFG margin, +2 TOV edge, −1 rebounding edge, +3 FTR margin). Team B gets there through elite defense and rebounding (+3 eFG margin, +4 TOV edge, +6 rebounding edge, +1 FTR margin). Both score 64 — but they are stylistically very different teams, and their profiles match up differently against specific opponents. FFI tells you the overall possession quality level; the individual margins tell you the story.',
    relatedMetrics: [
      { label: 'The Four Factors', slug: 'four-factors' },
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Matchup Model', slug: 'matchup-model' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'bayesian-performance-rating',
    section: 'player-evaluation',
    title: 'Macfax Bayesian Performance Rating',
    subtitle: 'Player impact in points per 100 possessions above Division I average',
    description: 'How Macfax estimates offensive, defensive, and total player impact using box-score signals and lineup data.',
    bestUsedFor: 'Evaluating how much a player improves or hurts their team when on the court',
    summary:
      'Macfax Bayesian Performance Rating (BPR) is a player impact estimate expressed in points per 100 possessions above the Division I average. It combines what a player\'s box-score production predicts about their value with what actual on-court lineup data reveals, then uses Bayesian regularization to produce stable estimates even for players with limited minutes. BPR separates into an offensive component (OBPR) and a defensive component (DBPR).',
    whatItMeasures:
      'BPR measures how many points per 100 possessions a player adds to their team\'s scoring margin when on the court, relative to a Division I average player. Positive values mean the player improves the team; negative values mean the team performs worse with that player on the court. OBPR measures offensive contribution, DBPR measures defensive contribution, and total BPR is their sum. This is fundamentally different from counting stats — a player scoring 18 points per game on poor shooting can have a negative OBPR, while a player scoring 8 on elite efficiency with good decision-making can have a high OBPR.',
    whyItMatters:
      'Volume stats reward usage, not efficiency. A player who takes more shots generates more raw points regardless of whether those shots help the team. BPR controls for pace and playing time by measuring per possession, and incorporates actual on-court lineup results to capture contributions that box scores miss entirely — spacing, off-ball defense, screening, communication. It also adjusts for schedule strength, so a player putting up big numbers against weak competition is not rated the same as one doing the same against elite opponents.',
    howToInterpret:
      'BPR is centered at 0, representing replacement level — the typical contribution of a player who can fill a roster spot but does not meaningfully improve the team. Positive BPR means the player adds value; negative means they subtract it in the current model. A player with OBPR +5 and DBPR −1 is a strong offensive contributor who is slightly below average defensively. Always check the source label: RAPM-based estimates (from lineup data) are more reliable than box-only estimates for players with limited minutes.',
    basicFormula: {
      prose: 'BPR = OBPR + DBPR\n\nBoth OBPR and DBPR expressed in points per 100 possessions above D1 average.',
    },
    interpretationBands: [
      { label: 'Elite / All-American', range: '+8 and above', color: 'success', description: 'Transformative impact. Among the best individual contributors in Division I.' },
      { label: 'High-Impact Starter', range: '+4 to +7', color: 'brand', description: 'Clear positive impact on both efficiency dimensions. Tournament-quality contributor.' },
      { label: 'Solid Contributor', range: '+1 to +3', color: 'secondary', description: 'Above replacement. Helps the team without being a primary driver.' },
      { label: 'Replacement Level', range: '−1 to 0', color: 'warning', description: 'Near neutral impact. Team roughly as good without this player.' },
      { label: 'Below Replacement', range: 'below −1', color: 'negative', description: 'Team performs measurably worse with this player on the court in the current model.' },
    ],
    technicalNotes: [
      'BPR combines two sources: box-score predictions (what production patterns predict about value) and lineup-based RAPM (what actually happens on the court with this player in). The two are blended using Bayesian regularization.',
      'Players with sufficient on-court lineup data receive RAPM-based estimates. Players with limited minutes receive box-score-based estimates. Each BPR value is labeled by its primary data source.',
      'Multi-year lineup data is pooled where available to improve stability for returning players. Prior seasons contribute context without overriding current-season performance.',
      'Schedule strength is factored in — players whose teams face stronger opponents are adjusted relative to those producing similar stats against weaker competition.',
      'On-court performance is compared against the team\'s overall level to separate individual contribution from team-quality effects.',
      'Defensive BPR carries materially more uncertainty than offensive BPR. Defensive impact is harder to isolate from box scores and lineup data. DBPR should be interpreted with appropriate caution.',
      'Exact feature weights, regularization parameters, and calibration values are internal to Macfax and may be recalibrated as additional validation data accumulates.',
    ],
    knownLimitations: [
      'Player ratings are noisier than team ratings by design. College basketball sample sizes are small and lineup combinations repeat infrequently.',
      'DBPR is particularly uncertain. Most box-score defensive indicators are weak proxies for actual defensive contribution.',
      'Freshmen and low-minute players lack lineup data — their ratings rely more heavily on box-score priors, which carry their own uncertainty.',
      'Transfer players have a break in on-court data continuity. First-season transfer estimates carry more uncertainty than returning players.',
      'Injuries, foul trouble, and mid-season role changes affect lineup data quality but are not explicitly modeled.',
      'BPR should not be the sole basis for player evaluation. Role, system fit, and usage context matter in ways the model cannot fully capture.',
    ],
    example:
      'Illustrative — not based on a specific live season. Guard A: OBPR +5.8, DBPR +1.4, BPR +7.2. Scores efficiently, protects the ball, draws fouls, and on-court lineup data confirms the team scores more with him on the floor. Source: RAPM-based. Guard B on the same team: OBPR +6.1, DBPR −2.3, BPR +3.8. Higher raw offensive production, but opponents score more when he defends. Box stats alone would overrate Guard B — BPR separates the two clearly. Same team, same playing time, very different actual impact.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'matchup-model',
    section: 'prediction-tools',
    title: 'Macfax Matchup Model',
    subtitle: 'Game projections, spreads, totals, and win probability',
    description: 'How Macfax projects scores, spreads, totals, win probabilities, and Four Factor matchup edges.',
    bestUsedFor: 'Understanding what Macfax expects from a specific upcoming game',
    summary:
      'The Macfax Matchup Model projects game outcomes by combining each team\'s opponent-adjusted offensive and defensive efficiency, estimated game pace, and site factors into a projected score, spread, total, and win probability. It also computes per-dimension Four Factor edges for the specific matchup. The model is built on multiplicative efficiency interaction — how one team\'s offense interacts with the opponent\'s defense, normalized to the national average.',
    whatItMeasures:
      'The Matchup Model estimates the most likely score and outcome for a specific game. It produces a projected score for each team, a projected spread, a projected total, and a win probability. Separately, it computes Four Factor matchup edges — showing which team has the structural efficiency advantage on shooting, turnovers, rebounding, and free throw rate for that specific pairing.',
    whyItMatters:
      'Game previews without quantitative projection rely on narrative. The Matchup Model converts team ratings into specific, falsifiable predictions that can be evaluated after the game. Because the projection is built on opponent-adjusted inputs, it correctly accounts for schedule strength — a high-scoring team facing an elite defense is projected differently than when they faced an average defense.',
    howToInterpret:
      'Projected spread is the model\'s best estimate of the margin on a neutral or home-site basis. Win probability is expressed as a percentage — 70% means the model expects the favored team to win roughly 7 out of 10 times under similar conditions. A 70% win probability is not a lock; basketball variance is high enough that the underdog wins 3 in 10. Do not treat any probability under 90% as certain. Four Factor edges show which team has the advantage on each possession dimension — useful for understanding why the model favors one team.',
    basicFormula: {
      latex:
        '\\text{Proj OE}_A = \\frac{\\text{AdjO}_A \\times \\text{AdjD}_B}{\\text{NatAvg}}',
      prose:
        'Proj OE_A = (AdjO_A × AdjD_B) / NatAvg\nProj OE_B = (AdjO_B × AdjD_A) / NatAvg\n\nSite factors applied symmetrically to home and away teams.\nExpected pace = weighted blend of both teams\' adjusted tempos.\nExpected Score = Proj OE × (Expected Possessions / 100)\nProjected Spread = Expected Score_A − Expected Score_B',
    },
    technicalNotes: [
      'Efficiency interaction is multiplicative: projected offense is the product of the offensive team\'s AdjO and the defensive team\'s AdjD, divided by the national average. This naturally scales with both teams\' quality rather than treating efficiency as additive.',
      'Game pace is estimated as a weighted blend of both teams\' adjusted tempos, producing a game-specific possession estimate rather than using either team\'s tempo alone.',
      'Home court factors are applied symmetrically — a split of the total advantage is applied to the home team\'s offense and removed from the away team\'s offense. The exact calibration is internal to Macfax.',
      'Win probability is derived from the projected spread using a Normal CDF with a calibrated standard deviation that reflects typical game-to-game variance in Division I basketball.',
      'Four Factor matchup edges are also computed multiplicatively per dimension — projecting the eFG%, turnover, rebounding, and FTR margins expected for this specific game given both teams\' adjusted factor profiles.',
      'A volatility score is computed separately for each matchup to indicate how much more uncertain this game is relative to the average projection. Volatility reflects factors like game pace, three-point volume, and recent performance consistency.',
      'Recent form trends are displayed in the matchup context as supplemental information. They are not inputs to the projected spread or win probability calculation.',
    ],
    knownLimitations: [
      'Recent form does not affect the projected spread. The model\'s projection is based on season-to-date adjusted ratings. Recent form is shown alongside but does not shift the number.',
      'The model does not adjust for injuries, suspensions, or roster availability unless ratings already reflect those absences from prior games.',
      'Travel, rest, altitude, and other logistical factors are not currently modeled.',
      'Late lineup changes or game-time decisions before tip-off are not reflected.',
      'Early-season projections carry more uncertainty because adjusted ratings have higher variance with fewer games played.',
      'Win probability assumes a calibrated variance around the projection. Neutral-site tournament games may have different variance characteristics than regular-season games.',
    ],
    example:
      'Illustrative: Team A (AdjO 116.2, AdjD 95.1) hosts Team B (AdjO 108.4, AdjD 99.7), national average 100.0. Proj OE_A = (116.2 × 99.7) / 100.0 ≈ 115.8. Proj OE_B = (108.4 × 95.1) / 100.0 ≈ 103.1. With expected 68 possessions and home court applied, model projects Team A 78 – Team B 70, spread −8, total 148, win probability 77% for Team A.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'The Four Factors', slug: 'four-factors' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'trapezoid-of-excellence',
    section: 'visual-frameworks',
    title: 'The Trapezoid of Excellence',
    subtitle: 'The efficiency-tempo zone where elite teams cluster',
    description: 'How Macfax identifies the national efficiency-tempo region where championship-caliber teams historically appear.',
    bestUsedFor: 'Identifying whether a team\'s efficiency-tempo combination sits in the nationally elite zone',
    summary:
      'The Trapezoid of Excellence is a scatter plot visualization that maps every Division I team by two axes: Adjusted Efficiency Margin (how much a team outscores opponents per possession) and Adjusted Tempo (pace of play). The concept was originated by Ryan Hammer, whose framework identified the efficiency-tempo region where elite teams cluster. The Macfax implementation applies Hammer\'s concept using opponent-adjusted efficiency and tempo data with a dynamically computed boundary calibrated to each season\'s national distribution. Teams inside the trapezoid occupy a nationally competitive profile; teams outside may still be strong, but their combination of pace and efficiency is less typical of deep tournament contenders.',
    whatItMeasures:
      'The visualization plots each team\'s adjusted efficiency margin on the vertical axis and adjusted tempo on the horizontal axis. The trapezoid boundary marks the national zone where teams that combine elite efficiency with competitive pace tend to appear. Being inside the trapezoid is not a guarantee of tournament success — it is a visual signal that a team\'s efficiency-tempo profile resembles historical contenders.',
    whyItMatters:
      'AdjEM alone tells you how good a team is. Tempo alone tells you how fast they play. But the combination matters. A team that plays at an extreme pace and achieves high efficiency is doing something different than a team that achieves the same efficiency at a moderate pace. The Trapezoid captures both dimensions simultaneously, making it easy to see at a glance whether a team\'s overall profile — not just their rating — puts them in the national elite zone.',
    howToInterpret:
      'Teams are plotted as points (or logos when available). Teams inside the trapezoid region are highlighted; teams outside appear with reduced emphasis. Average lines cross the chart at the national mean tempo and mean efficiency margin, giving reference points for where the typical D1 team sits. Teams in the upper portion of the trapezoid are the strongest nationally. The trapezoid shape is intentional: the top edge is wider, capturing the full range of tempos found among peak-efficiency teams. The bottom edge is narrower, meaning teams at the efficiency floor of the elite zone tend to play at a more typical pace. Very fast or very slow teams need higher efficiency margins to sit inside — extreme pace strategies carry more execution risk and this is reflected in where the boundary sits.',
    technicalNotes: [
      'Trapezoid boundaries are computed dynamically each season from the full Division I national distribution — not from tournament-qualifying teams only. This ensures the reference zone reflects the true national baseline for that season.',
      'The trapezoid is a fixed national reference. Applying a conference filter or top-N filter changes which teams are displayed but does not change the trapezoid shape. This is intentional — the trapezoid should remain a stable national benchmark regardless of the viewing context.',
      'The bottom boundary of the trapezoid is anchored at a high-percentile threshold of national AdjEM, meaning only teams with elite efficiency margins can anchor the bottom corners. The exact percentile is internal to Macfax.',
      'The slanted sides of the trapezoid use linear interpolation between corner points. Teams at extreme tempos (very slow or very fast) face a higher efficiency threshold to be considered inside — the slant reflects the elevated execution required at pace extremes.',
      'National average lines for both tempo and efficiency margin are overlaid on the visualization for reference. These represent the typical D1 team, not a competitive threshold.',
      'The trapezoid boundary is one of 15 benchmarks evaluated in the Crystal Ball championship checklist.',
    ],
    knownLimitations: [
      'Being inside the trapezoid is descriptive, not predictive. Strong teams outside the trapezoid can and do win championships.',
      'The trapezoid is a snapshot based on current adjusted ratings. Early-season placements carry more uncertainty because adjusted ratings are noisier with fewer games played.',
      'Teams at the boundary of the trapezoid are not meaningfully different from teams just outside it. The boundary is not a hard threshold.',
      'Adjusted tempo reflects how fast a team plays on average — it does not capture whether that pace is by design or forced by opponents.',
      'The trapezoid captures two dimensions of team quality. It does not directly reflect Four Factor strengths, resume, or matchup-specific advantages.',
    ],
    example:
      'Illustrative: a team with AdjEM +22 and Adjusted Tempo 68.5 (moderately paced) sits comfortably inside the trapezoid — their efficiency margin is elite and their pace is well within the typical range for strong teams. A team with the same AdjEM +22 but Adjusted Tempo 59 (very slow) may sit outside or on the border — not because they are worse, but because their efficiency-tempo combination is less common among historical contenders. The trapezoid does not penalize them; it simply notes that their profile is atypical. A third team with AdjEM +16 and Tempo 68.5 sits below the trapezoid — their pace is fine but their efficiency margin does not clear the elite zone threshold.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Efficiency Landscape', slug: 'efficiency-landscape' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'efficiency-landscape',
    section: 'visual-frameworks',
    title: 'The Efficiency Landscape',
    subtitle: 'Mapping teams by adjusted offense and adjusted defense simultaneously',
    description: 'How Macfax maps every Division I team by adjusted offensive and defensive efficiency to show both team strength and team style.',
    bestUsedFor: 'Seeing how teams are strong — offensively, defensively, or both — at a glance',
    summary:
      'The Efficiency Landscape maps every Division I team on a scatter plot with Adjusted Offensive Efficiency on the vertical axis and Adjusted Defensive Efficiency on the horizontal axis. Three diagonal tier lines divide the chart into zones based on each team\'s net efficiency margin relative to the season\'s top team. The result is a visual where both overall strength and stylistic profile are immediately visible — which teams are balanced, which are offense-first, which are defense-first.',
    whatItMeasures:
      'The landscape plots each team\'s offensive and defensive efficiency on the same chart, making it possible to see both how good a team is and how they achieve that quality. Net efficiency (AdjEM = AdjO − AdjD) is captured by the diagonal tier lines — teams above a given tier line have a stronger net rating than teams below it. Two teams with identical AdjEM can have very different profiles: one through elite offense and average defense, the other through the opposite.',
    whyItMatters:
      'AdjEM summarizes overall quality but erases the distinction between offense-driven and defense-driven teams. That distinction matters for matchup analysis, tournament projections, and stylistic understanding. The Efficiency Landscape makes the composition visible — a scout, analyst, or fan can see at a glance where a team sits on both dimensions and how unusual or typical their profile is compared to the rest of Division I.',
    howToInterpret:
      'The vertical axis (Y) is Adjusted Offensive Efficiency — higher is better. The horizontal axis (X) is Adjusted Defensive Efficiency, oriented so that lower (better) defensive ratings appear toward the right side of the chart. Teams that combine elite offense and elite defense cluster in the upper-right corner of the plot, which is the championship-caliber zone. Three diagonal tier lines divide the chart based on net efficiency margins relative to the season\'s best team. Title Favorites are above the top tier line. Final Four Potential teams fall between the top and second lines. Hit or Miss teams fall between the second and third lines. The Rest fall below the third line. Clicking any team logo navigates to their full team profile.',
    technicalNotes: [
      'Tier lines are diagonal because they represent constant Adjusted Efficiency Margin values — AdjO minus AdjD equals a fixed number. Teams anywhere along a given diagonal line have the same net rating, regardless of how they divide that margin between offense and defense.',
      'Tier thresholds are computed relative to the season\'s top team\'s AdjEM, not as fixed absolute values. This means the tier lines shift position each season as the national top-end changes, keeping the tiers calibrated to the actual competitive landscape each year.',
      'The national baseline (the top team\'s AdjEM used to anchor tier lines) is computed from all Division I teams before any conference or tournament filter is applied. Applying a conference or region filter changes which teams are displayed but does not move the tier lines — they remain a stable national reference.',
      'The defensive axis is reversed relative to its numerical direction: as you move right on the chart, adjusted defensive efficiency numbers decrease (i.e., fewer points allowed per 100 possessions). This orientation places elite defenders on the right side, consistent with the standard convention that rightward or upward always means better on both axes.',
      'Average lines for both AdjO and AdjD are overlaid on the chart, representing the national Division I mean for that season.',
    ],
    knownLimitations: [
      'The landscape is a snapshot, not a projection. Teams can shift significantly as the season progresses and adjusted ratings stabilize.',
      'Being in the Title Favorites zone does not guarantee a title — it means the team\'s efficiency profile is among the strongest relative to the current national field.',
      'Early-season placements carry more uncertainty because adjusted ratings are less stable before 15+ games are played.',
      'The landscape captures two efficiency dimensions but does not directly reflect Four Factor style, resume strength, or tournament matchup dynamics.',
      'Teams with unusual stylistic profiles (extreme tempo, heavy zone, high foul-rate play) may sit in atypical chart positions relative to their win-loss record.',
    ],
    example:
      'Illustrative: Team A has AdjO 120.0 and AdjD 94.0, placing them in the upper-right corner above the Title Favorites tier line. Team B has AdjO 115.0 and AdjD 94.0 — same defense, less offense — placing them slightly lower on the chart, in the Final Four Potential zone. Team C has AdjO 120.0 and AdjD 101.0 — same offense as Team A but weaker defense — placing them to the left and below. All three are strong teams, but the landscape makes their stylistic and quality differences immediately readable.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Trapezoid of Excellence', slug: 'trapezoid-of-excellence' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'the-crystal-ball',
    section: 'prediction-tools',
    title: 'The Crystal Ball',
    subtitle: 'Championship profile benchmarks, not a projection',
    description: 'How Macfax evaluates every team against 15 historical championship benchmarks to score championship readiness.',
    bestUsedFor: 'Identifying which teams have the profile of a legitimate national contender right now',
    summary:
      'The Crystal Ball evaluates every Division I team against 15 benchmarks derived from historical championship and deep-tournament-run profiles. It is not a projection of what will happen — it is a snapshot of how closely a team\'s current profile matches the dimensions that have historically separated true contenders from the field. Teams are scored by how many benchmarks they clear and grouped into four tiers.',
    whatItMeasures:
      'Championship profile alignment: how many of the indicators that historically characterize national contenders does this team currently satisfy? The 15 checks span offensive and defensive efficiency quality, possession-level performance across the Four Factors, win percentage, schedule resume strength, shooting quality, and external validation signals like poll recognition. Each check is pass or fail based on thresholds calibrated from historical championship-caliber team data.',
    whyItMatters:
      'A single efficiency number can be built through a weak schedule. A gaudy win percentage can be manufactured through non-conference scheduling. The Crystal Ball forces a multi-dimensional test — a team must pass checks across efficiency, shot-making, ball control, resume, and validation simultaneously to earn a high score. Teams that check many boxes independently are exhibiting the same patterns as historical contenders, regardless of name recognition or media narrative.',
    howToInterpret:
      'Each team\'s score is shown as X/15 — how many of the 15 benchmarks they currently clear. Click any team row to see the full breakdown: which checks passed, which failed, and the supporting values. Tiers are assigned based on total passed checks. Championship Tier (12–15 passed): profiles that closely match historical national contenders. Contender (9–11): strong profiles with one or two meaningful gaps. Threat (6–8): real but incomplete — could make noise in a favorable bracket. Pretender (0–5): current profile does not align with contender history. The checks are not weighted — each benchmark contributes equally to the score.',
    technicalNotes: [
      'The 15 benchmarks span six categories: efficiency profile (2 checks), rank-based quality (3 checks), Four Factor margins (4 checks), composite scores (2 checks), resume signals (2 checks), and shooting quality (2 checks).',
      'Thresholds are calibrated against historical championship and deep-tournament-run team data and are season-specific — the exact cutoffs shift slightly each year as the national baseline shifts.',
      'Season context (national rankings, trapezoid boundaries, max AdjEM baseline) is pre-computed once per request and held constant whether filtering to all teams or tournament-only teams. This prevents rank-based checks from shifting when the visible team set changes.',
      'The score (0–100) is derived directly from the passed check count: passed ÷ 15 × 100. It is an alignment score, not a win probability.',
      'Checks that reference national rank use a stable season-wide ranking that does not shift when filtering by conference or tournament status.',
    ],
    knownLimitations: [
      'The Crystal Ball measures current profile alignment, not future performance. A team that passes 14 checks today can still lose in the first round.',
      'Each check is binary — pass or fail. A team that narrowly misses a threshold is treated the same as one that misses badly. The score does not reflect how close a team is to each benchmark.',
      'Early-season ratings are noisier, which makes early-season Crystal Ball scores less meaningful. The visualization is most useful after 15+ games.',
      'Injuries, lineup changes, and transfers are not directly modeled — the checks respond only to what the underlying ratings reflect.',
      'The checklist is designed for identifying historical contender patterns, not for predicting upsets, Cinderella runs, or late-season trajectories.',
      'Some checks depend on external validation data (AP Poll rankings), which may lag or be unavailable early in the season.',
    ],
    example:
      'Illustrative: a team with AdjEM +31, elite adjusted offense and defense, eFG margin +7, Rebounding Edge positive, FFI above 80, WAB over 5, and strong shooting percentages might pass 13 of 15 checks — earning a Championship Tier designation. A team with similar AdjEM but average shooting percentages and a thin resume might pass only 9, landing in Contender. Same adjusted margin, very different contender profile.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
      { label: 'Trapezoid of Excellence', slug: 'trapezoid-of-excellence' },
      { label: 'Cinderella Index', slug: 'cinderella-index' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'cinderella-index',
    section: 'prediction-tools',
    title: 'Macfax Cinderella Index',
    subtitle: 'Upset danger relative to seed and expectation',
    description: 'How Macfax identifies teams more dangerous than their seed or reputation suggests across five structural dimensions.',
    bestUsedFor: 'Finding teams more dangerous than their seed or reputation suggests',
    summary:
      'The Cinderella Index is not a ranking of the best teams. It is a ranking of upset danger relative to expectation — how dangerous a team is when their seed, public perception, or resume understates their actual quality or stylistic threat in a single-elimination context. It combines five structural dimensions into a 0–100 profile score, with higher scores indicating greater misalignment between perceived and actual threat.',
    whatItMeasures:
      'The Cinderella Index scores teams on five dimensions: underseeded strength (how much better the team is than their seed implies), defensive disruption capability, possession control and ball security, performance variance (reliance on three-point shooting and pace), and resume legitimacy relative to schedule. Teams with a large gap between perceived strength and actual measured quality score highest. When the bracket is set, a separate P(Sweet 16) probability is also computed using bracket simulation.',
    whyItMatters:
      'Tournament seeding is partially based on perception, selection committee criteria, and conference record — not purely on adjusted efficiency. A team that is measurably better than their seed suggests, plays high-variance basketball, and has a defensively disruptive style represents structural upset danger regardless of name recognition. The Cinderella Index quantifies that gap, making it easier to identify dangerous matchups before they happen.',
    howToInterpret:
      'Scores run from 0 to 100. Higher means more structural upset danger relative to expectation. Four tiers: Elite Threat (65–100) — strong across multiple dimensions, genuine seed/perception gap present; Notable Threat (50–64) — real upset potential, at least one or two significant factors working in their favor; Moderate Risk (35–49) — profile broadly matches expectation, limited structural edge; Low Threat (0–34) — profile does not suggest meaningful upset risk above seeding. This is not a quality ranking — a top seed can score high if their true strength far exceeds even a top seed. The metric is most meaningful for mid-major and mid-seeded teams. When tournament seeds are loaded, a P(Sweet 16) probability is shown separately as a bracket-path-aware supplement to the profile score.',
    weights: [
      { label: 'Underseeded Strength', value: '28%', pct: '28' },
      { label: 'Defensive Disruption', value: '27%', pct: '27' },
      { label: 'Possession Control', value: '21%', pct: '21' },
      { label: 'Performance Variance', value: '14%', pct: '14' },
      { label: 'Resume Legitimacy', value: '10%', pct: '10' },
    ],
    interpretationBands: [
      { label: 'Elite Threat', range: '65–100', color: 'success', description: 'Strong structural upset threat. Multiple dimensions point to a meaningful seed or perception gap.' },
      { label: 'Notable Threat', range: '50–64', color: 'brand', description: 'Real upset potential. At least one or two significant factors working in their favor.' },
      { label: 'Moderate Risk', range: '35–49', color: 'secondary', description: 'Profile broadly matches expectation. Limited structural upset edge.' },
      { label: 'Low Threat', range: '0–34', color: 'negative', description: 'Profile does not suggest meaningful upset risk above seeding.' },
    ],
    technicalNotes: [
      'All five component scores are computed as percentiles against the full Division I population for that season — not just seeded or tournament-qualifying teams. This keeps scores stable and comparable regardless of how teams are filtered in the UI.',
      'Underseeded Strength is anchored by adjusted efficiency margin. When the bracket is set, a seed residual — the gap between a team\'s actual seed and the seed their efficiency rank would imply — is incorporated as a secondary signal.',
      'Defensive Disruption combines adjusted defensive efficiency, shooting suppression, and turnover-forcing ability into a single defensive sub-score.',
      'Possession Control combines ball security (own turnover rate), turnover-forcing, and offensive rebounding into a possession-leverage sub-score.',
      'Performance Variance reflects the structural volatility of a team\'s style — teams with higher three-point shot volume and slower pace tend to produce more variable game-to-game outcomes, which works both ways in a single-elimination game.',
      'P(Sweet 16) probability, when shown, uses bracket simulation based on adjusted efficiency ratings and the team\'s actual seed and bracket region. It is a bracket-path estimate, not a general upset indicator.',
      'Component weights and sub-weights may be recalibrated between seasons as additional tournament validation data accumulates.',
    ],
    knownLimitations: [
      'Cinderella Index is most meaningful during tournament time, when seeds are assigned. In-season use is directional only.',
      'Tournament randomness is real — even a low-scoring team can pull an upset through variance alone. The index identifies structural threat, not guaranteed outcomes.',
      'The metric works best for mid-major and bubble teams. Extreme seeds (1, 2, 15, 16) have less meaningful scores because the seed/perception gap logic is most informative in the middle of the bracket.',
      'Injuries, late lineup changes, and mid-season role shifts are not directly modeled — the index responds only to what the underlying ratings reflect.',
      'Early-season scores carry more uncertainty because adjusted ratings are noisier before 15+ games are played.',
      'Component weights are still evolving with each additional tournament season of data.',
    ],
    example:
      'Illustrative: a 12-seed with an adjusted efficiency margin that would typically imply a 5-seed, combined with an elite defense that suppresses shooting and forces turnovers, a high three-point attempt rate, and a legitimate road-game resume — that profile scores in the Elite Threat range. The seed gap is large, the style is high-variance and defensively disruptive, and the resume is real. That is the structural Cinderella profile. A 12-seed with a profile that genuinely matches a 12-seed — average efficiency, average defense, low variance — scores low regardless of seed.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'The Four Factors', slug: 'four-factors' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'resume-metrics',
    section: 'resume-data',
    title: 'Macfax Resume Metrics',
    subtitle: 'What a team has earned, not just how good they are',
    description: 'How Macfax evaluates schedule strength, quality wins, WAB, SOR, SOS, NET rank, and full tournament resume.',
    bestUsedFor: 'Evaluating what a team has accomplished against their actual schedule',
    summary:
      'Adjusted Ratings estimate how good a team is. Resume Metrics estimate what a team has actually earned. These are different questions — a team can build strong adjusted ratings through a weak schedule without validating that strength in competition. Resume Metrics capture the achievement profile: Wins Above Bubble, Strength of Record, Strength of Schedule, NET rank, and quadrant-by-quadrant records against the full game log.',
    whatItMeasures:
      'Resume Metrics cover four primary indicators and a full game-log breakdown. WAB (Wins Above Bubble) measures how many more wins a team has than a typical bubble-quality team would be expected to produce against the same schedule. SOR (Strength of Record) measures how difficult it would be for a reference-level team to match the same record against the same opponents. SOS (Strength of Schedule) measures how hard the schedule is, expressed as the expected win percentage for an average Division I team playing that exact slate. NET Rank is the official NCAA Evaluation Tool ranking used by the selection committee. Quadrant records break the game log into four tiers based on opponent quality and game location, following the NCAA Committee\'s official framework.',
    whyItMatters:
      'NCAA Tournament selection committees use achievement-based criteria alongside predictive ratings. A team that goes 28–3 against a weak schedule may rate well in adjusted efficiency but have a weak resume. Resume Metrics close that gap — they answer the question the committee is actually asking: given the games this team played, did they win the ones that matter? WAB and SOR are the most directly committee-relevant numbers on Macfax.',
    howToInterpret:
      'WAB is the clearest single resume number. Positive means the team has won more games than a bubble-level team would be expected to win on the same schedule — strong positive WAB is direct evidence for an at-large bid. SOR rank is lower-is-better (1 = best) — a low rank means few reference-quality teams would have matched this team\'s record against the same opponents. SOS rank is also lower-is-better (1 = hardest schedule). Best Wins and Worst Losses show the five most significant wins and five most costly losses by opponent quality, with quadrant labels showing context. Quadrant records summarize the full season by tier: Q1 is the hardest category, Q4 the easiest.',
    basicFormula: {
      prose: 'WAB = Σ (Actual Game Result − Probability a Bubble-Quality Team Wins That Same Game)\n\nSummed across all completed games. Positive = more wins than expected. Negative = fewer.',
    },
    technicalNotes: [
      'WAB uses the Macfax matchup model to compute, for each game, the win probability a representative bubble-quality team would have against that opponent in that location. WAB is the sum of actual results minus those probabilities across all games. The bubble baseline is calibrated to represent a team on the fringe of at-large consideration.',
      'SOS is computed using a logistic win-probability model applied to an average Division I team baseline against the full schedule. The output — shown as an expected win percentage — represents how hard the schedule was: a lower expected win percentage means a harder schedule. The exact calibration values are internal to Macfax.',
      'SOR uses a Monte Carlo simulation approach: it estimates how often a reference-level team (drawn from the upper-middle of the national field) would achieve the same or better win-loss record against the same opponents. A lower SOR rank means the actual record is harder to replicate, which is better.',
      'NET Rank is the official NCAA Evaluation Tool ranking as published by the NCAA. Macfax displays it for reference alongside its own metrics; Macfax does not compute or control the NET.',
      'Quadrant definitions follow the NCAA Committee\'s official criteria, using opponent NET rank and game location. Home Q1 (1–30), Neutral Q1 (1–50), Away Q1 (1–75). Home Q2 (31–75), Neutral Q2 (51–100), Away Q2 (76–135). Home Q3 (76–160), Neutral Q3 (101–200), Away Q3 (136–240). Q4 covers all remaining games.',
      'Best Wins and Worst Losses are sorted by opponent quality, with game location and game value used as tiebreakers. Game value reflects the importance of each result relative to the bubble baseline.',
    ],
    knownLimitations: [
      'Resume metrics are backward-looking and do not predict future performance.',
      'WAB is sensitive to the bubble team calibration, which is recalibrated annually. Small changes to the baseline can shift WAB values slightly across all teams.',
      'Early-season resume metrics are unstable before 15+ games are played. Early WAB and SOR should be treated as directional only.',
      'Conference tournament performance affects resume metrics significantly in March — a conference tournament run can shift quadrant records, WAB, and SOR substantially in a short window.',
      'NET rank is an external metric that Macfax does not compute. Discrepancies between NET and Macfax-computed metrics are expected — they use different methodologies.',
      'Strength of Schedule reflects opponents faced, not opponents\' actual quality at game time. A schedule that appeared hard at the time of scheduling can look weaker if opponents underperform.',
    ],
    example:
      'Illustrative: a team with WAB +4.8, SOR rank #22, Q1 record 7–3, and two away wins over top-10 teams has built a genuinely strong tournament resume. They have won significantly more games than a bubble team would be expected to on that schedule, and their record would be difficult to replicate even for a reference-level team. The Q1 record alone — seven wins against the hardest game category — makes a compelling case. A team with WAB +1.2 and Q1 record 2–8 has played a hard schedule but has not validated it with results.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Cinderella Index', slug: 'cinderella-index' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },

  {
    slug: 'roster-outlook',
    section: 'roster-projections',
    title: 'Macfax Roster Outlook',
    subtitle: 'Next-season team projections built from the roster up',
    description: 'How Macfax projects next-season team performance using player talent, minutes, roster fit, continuity, and recruiting.',
    bestUsedFor: 'Understanding what a team\'s roster is likely to produce next season and where the roster has structural strengths or gaps',
    summary:
      'The Roster Outlook builds a forward-looking team projection from the ground up — starting with each player\'s individual talent estimate, then layering in expected playing time, how well the roster\'s styles fit together, and how much continuity or roster turnover introduces uncertainty. The result is a projected efficiency rating with a national ranking estimate, uncertainty bands, roster fit grades, and continuity diagnostics for the upcoming season.',
    whatItMeasures:
      'The Roster Outlook estimates what a team\'s current roster is likely to produce next season in terms of adjusted offensive efficiency, adjusted defensive efficiency, and net efficiency margin. It separates talent from fit — a roster with individually strong players can still have structural weaknesses if the pieces do not complement each other. The feature also measures roster continuity (how much production is returning versus transferred in or newly added), and flags where transfer dependence or roster composition creates meaningful projection uncertainty.',
    whyItMatters:
      'In-season ratings tell you what a team has done. The Roster Outlook tells you what a team is likely to become. Transfer portal activity, recruiting classes, and roster turnover make next-season projections fundamentally different from extrapolating current ratings. By building the projection player by player — incorporating each player\'s talent estimate, minutes, and fit contribution — the Roster Outlook captures the actual mechanism by which rosters translate into team performance, rather than assuming the current team quality persists unchanged.',
    howToInterpret:
      'The projected AdjEM, AdjO, and AdjD are the model\'s central estimates for next season. The national ranking estimate shows where that efficiency profile would rank among Division I teams in a typical season. Uncertainty bands (shown as a projected rank range) reflect how wide the realistic distribution of outcomes is — a team with a narrow range has a more predictable outlook, while a team with a wide range has more variance in either direction. Fit grades run from A+ (elite roster composition) to F (significant structural weaknesses), separated into offensive fit and defensive fit. A team can have strong individual talent but a B- fit grade if the roster lacks spacing, playmaking, or defensive structure. Player tiers — All-American, All-Conference, Starter, Reserve, Bench — reflect the projected quality level for each player relative to Division I averages. Recruitment type labels (Returner, Transfer, Newcomer) show where projected production is coming from and where it carries more uncertainty.',
    technicalNotes: [
      'Player talent estimates use Bayesian Performance Rating (BPR) as the core input. For returning players, BPR is based on prior college performance with appropriate regression toward the mean. For transfers, prior college BPR is adjusted for the change in competition level and role. For freshmen and other newcomers, recruiting rank and star rating serve as priors where college performance data is unavailable.',
      'Minutes allocation is projected using a minutes model that accounts for role, quality tier, roster depth, and historical minutes patterns. Minutes projections are a key uncertainty source — a player whose role expands or contracts significantly will produce differently than the model expects.',
      'Roster fit is evaluated separately for offensive and defensive dimensions. Offensive fit assesses playmaking coverage, spacing distribution, ball security, finishing quality, and free-throw pressure. Defensive fit assesses rim protection, defensive rebounding, perimeter coverage, and structural composition. Each dimension receives a letter grade. The exact subcomponent weights and structural penalty logic are internal to Macfax.',
      'Contextual adjustments incorporate the team\'s stylistic identity — pace tendency and offensive and defensive scheme — to assess whether the projected roster aligns with how the coaching staff has historically deployed talent.',
      'Continuity is measured as both a minutes fraction (how much of projected playing time comes from returners) and a talent-weighted score (how much of projected BPR production is retained). High transfer dependence without strong fit scores increases projection uncertainty.',
      'Team-level projected ratings are derived by translating the aggregate talent and fit signals into an efficiency margin estimate, calibrated against the historical relationship between roster quality and on-court performance. The translation is not linear — fit matters, and the same aggregate talent level produces better ratings when the pieces complement each other.',
      'Uncertainty bands represent roughly a ±2 standard deviation range around the central projection, reflecting player projection variance, minutes uncertainty, and continuity risk. The central estimate is more likely than any outcome at the edges of the range, but outcomes outside the range are possible.',
      'The scenario editor on the Roster Outlook page allows users to modify the projected roster — adding, removing, or swapping players — and see how those changes would shift the projection. Scenario results use the same model as the baseline projection.',
    ],
    knownLimitations: [
      'The Roster Outlook is a projection, not a guarantee. Basketball roster construction involves significant uncertainty — injuries, role changes, player development, and coaching adjustments can all cause actual outcomes to diverge from the projection.',
      'Transfer portal movement is ongoing throughout the offseason. The projection reflects roster information available at the time of the most recent pipeline run; subsequent transfers, decommitments, or additions are not automatically reflected.',
      'Minutes projections are a major source of uncertainty, especially for freshmen and transfer players whose college roles are inherently difficult to predict.',
      'The model does not account for coaching changes unless they are already reflected in the team\'s current coaching profile.',
      'Defensive projection carries more uncertainty than offensive projection at the player level, which propagates to the team-level defensive fit and projected AdjD estimates.',
      'Early offseason projections (before most transfer portal decisions are finalized) carry wider uncertainty than late-offseason projections with a more complete roster picture.',
      'The scenario editor produces estimates, not predictions. Manually constructed rosters may include combinations that the model has limited data to evaluate confidently.',
    ],
    example:
      'Illustrative: a team projects AdjEM +18.5 with a national rank estimate of #22, but with a rank range of #14–#35. Their offensive fit is B+ (strong spacing and playmaking, slight ball-security concern from a high-usage transfer) and defensive fit is B (solid rim protection, but limited perimeter stopper in the backcourt rotation). Continuity score is 62 — meaning roughly 62% of projected production comes from returners, with the rest dependent on two transfers. If the transfers perform to projection, the upper end of the range is realistic. If they underperform their college history, the team slides toward the lower end.',
    relatedMetrics: [
      { label: 'Bayesian Performance Rating', slug: 'bayesian-performance-rating' },
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'The Four Factors', slug: 'four-factors' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '1.0',
  },

  {
    slug: 'data-sources-updates',
    section: 'resume-data',
    title: 'Data Sources and Update Timing',
    subtitle: 'Where Macfax data comes from and how the pipeline works',
    description: 'Where Macfax data comes from, how it is processed through the computation pipeline, and when ratings update.',
    bestUsedFor: 'Understanding data freshness, what is and is not tracked, and the reliability of current ratings',
    summary:
      'Macfax collects box-score data for every Division I men\'s basketball game from public NCAA and ESPN data sources. That raw data flows through a multi-stage computation pipeline — from possession estimates and four-factor aggregation through iterative opponent adjustment, resume metrics, and player evaluation — before ratings are published. This page explains the pipeline, what data is and is not available, and the current update cadence.',
    whatItMeasures:
      'This page covers data provenance and process, not a specific metric. It explains what inputs power Macfax, how games are ingested and validated, what stages the computation pipeline runs through, and when and how often ratings are updated.',
    whyItMatters:
      'Analytics are only as reliable as the data and processes behind them. Understanding where data comes from, what gets included and excluded, and how recently ratings were last computed helps users interpret Macfax numbers with appropriate confidence — and know when to treat a number as stable versus provisional.',
    howToInterpret:
      'Each metric on Macfax reflects the most recently completed pipeline run. If a game was played very recently, it may not yet be incorporated — ratings do not update in real time. During tournament stretches, the pipeline is typically run more frequently. The computation pipeline runs in sequential stages, so all metrics on the site reflect the same common data snapshot from the most recent update.',
    technicalNotes: [
      'Box score data is collected from public NCAA and ESPN data sources, with ESPN used as a secondary source when the primary source is unavailable for a given game.',
      'Team name matching uses fuzzy matching to reconcile naming variations between data sources. Canonical team identifiers are maintained across all external sources.',
      'The pipeline runs in sequential stages: game ingestion → raw four-factor aggregation → national averages → iterative opponent adjustment → adjusted four factors and FFI → resume metrics (NET, SOR, SOS, WAB) → player evaluation. Each stage depends on the output of prior stages.',
      'Possession calculations use the standard formula: FGA − OREB + TOV + 0.475 × FTA. The 0.475 multiplier accounts for and-one plays and technical fouls.',
      'Opponent adjustment runs iteratively — each team\'s ratings depend on their opponents\' ratings, which depend on their opponents\' ratings, and so on. The process runs until ratings converge.',
      'AP Poll Week 6 rankings are loaded separately and incorporated as a reference signal in applicable metrics.',
      'NCAA NET Rankings are fetched from the NCAA\'s published data and displayed for reference. Macfax does not compute or control the NET.',
      'Tournament bracket information (seeds and regions) is loaded separately when the selection committee releases the bracket.',
      'All ingestion and computation passes are idempotent — re-running the pipeline for a given day does not double-count games or corrupt prior results.',
    ],
    knownLimitations: [
      'Macfax does not collect injury data, roster availability, or lineup changes. The pipeline only knows what happened on the court in completed games.',
      'Play-by-play data beyond scoring sequences is not currently stored. Box-score-level efficiency calculations are estimates; possession counts from play-by-play would be more precise.',
      'Data from exhibition games and scrimmages is excluded from ratings.',
      'Forfeit and administrative results may be handled differently from normal game results.',
      'Source data occasionally contains errors — incorrect scores, missing players, or misidentified teams. Corrections are applied on the next pipeline run when the source corrects the data.',
      'Ratings do not update in real time. They reflect the most recently completed pipeline run. Very recently completed games may not be incorporated yet.',
      'Non-Division I opponents are excluded from all rating computations. Games against non-D1 opponents do not count toward adjusted ratings, WAB, or SOR.',
    ],
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
      { label: 'The Four Factors', slug: 'four-factors' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.1',
  },
];

export const METHODOLOGY_SECTIONS: {
  id: string;
  title: string;
  slugs: string[];
}[] = [
  {
    id: 'core-ratings',
    title: 'Core Team Ratings',
    slugs: ['adjusted-ratings', 'four-factors', 'four-factor-index'],
  },
  {
    id: 'player-evaluation',
    title: 'Player Evaluation',
    slugs: ['bayesian-performance-rating'],
  },
  {
    id: 'roster-projections',
    title: 'Roster Projections',
    slugs: ['roster-outlook'],
  },
  {
    id: 'prediction-tools',
    title: 'Prediction Tools',
    slugs: ['matchup-model', 'the-crystal-ball', 'cinderella-index'],
  },
  {
    id: 'visual-frameworks',
    title: 'Visual Frameworks',
    slugs: ['trapezoid-of-excellence', 'efficiency-landscape'],
  },
  {
    id: 'resume-data',
    title: 'Résumé and Data',
    slugs: ['resume-metrics', 'data-sources-updates'],
  },
];

export function getMethodologyBySlug(slug: string): MethodologyContent | undefined {
  return methodologyContent.find((m) => m.slug === slug);
}

export function getAllMethodologySlugs(): string[] {
  return methodologyContent.map((m) => m.slug);
}

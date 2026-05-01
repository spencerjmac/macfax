import type { MethodologyContent, MethodologySectionConfig } from './methodologyTypes';

export const methodologyContent: MethodologyContent[] = [
  {
    slug: 'adjusted-ratings',
    section: 'core-ratings',
    title: 'Macfax Adjusted Ratings',
    subtitle: 'How Macfax estimates team strength',
    description: 'How Macfax estimates team strength using opponent-adjusted offensive, defensive, net, and tempo ratings.',
    bestUsedFor: 'Comparing overall team quality across the full season',
    summary:
      'Adjusted Ratings are the backbone of Macfax team strength estimates. They measure how efficiently a team scores and prevents scoring on a per-possession basis, then adjust those raw numbers for opponent quality, game site, and sample size. The result is a more stable, fair comparison of team strength than raw box-score statistics.',
    whatItMeasures:
      'Adjusted Ratings measure four core team qualities: offensive efficiency (AdjO), defensive efficiency (AdjD), net efficiency margin (AdjEM), and pace of play (AdjTempo). Each is expressed per 100 possessions and adjusted to remove the effect of opponent strength and game location.',
    whyItMatters:
      'Raw points per game and win-loss records are poor team quality signals in college basketball because of dramatic schedule imbalance. A team that scores 80 points against weak opponents every night is not the same as one that scores 80 against Top-25 defenses. Adjusted ratings account for this, making cross-conference and cross-schedule comparisons meaningful.',
    howToInterpret:
      'AdjO and AdjD are expressed as points per 100 possessions adjusted to a neutral-site game against an average Division I opponent. AdjEM is the difference: AdjO minus AdjD. Positive AdjEM means the team outscores opponents; higher is better. AdjTempo is projected possessions per 40 minutes. National average is roughly 100 for efficiency and 68–70 for tempo in a typical season.',
    basicFormula: {
      latex:
        '\\text{Poss} = \\text{FGA} - \\text{OREB} + \\text{TOV} + 0.475 \\times \\text{FTA}',
      prose:
        'Raw OE = 100 × Points / Possessions\nRaw DE = 100 × Opp Points / Opp Possessions\nAdjEM = AdjO − AdjD',
    },
    technicalNotes: [
      'Possession formula uses the 0.475 free throw multiplier, a standard estimate for and-one and technical foul scenarios.',
      'Opponent adjustments are iterative — each team\'s rating depends on who they played, which depends on those teams\' ratings.',
      'Site adjustment applies a home court advantage factor (current version estimates ~3 points per 100 possessions).',
      'Sample-size stabilization (shrinkage) pulls early-season ratings toward the national mean. Ratings become more reliable after 8–10 games.',
      'Recency weighting may be applied in-season to reflect recent form over full-season averages.',
    ],
    knownLimitations: [
      'Adjusted ratings do not account for injuries, travel fatigue, or back-to-back scheduling.',
      'Early-season ratings (first 5 games) carry high uncertainty and should be interpreted cautiously.',
      'Conference strength estimates depend on cross-conference games; teams with few non-conference games against power opponents have noisier adjustments.',
      'Possession estimates from box scores are approximations, not play-by-play counts.',
    ],
    example:
      'A team with AdjO 118.5, AdjD 94.2 has AdjEM +24.3 — meaning they outscore opponents by 24.3 points per 100 possessions on a neutral court against average competition. This would rank among the top teams nationally in a typical season.',
    relatedMetrics: [
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'Matchup Model', slug: 'matchup-model' },
      { label: 'Efficiency Landscape', slug: 'efficiency-landscape' },
      { label: 'Trapezoid of Excellence', slug: 'trapezoid-of-excellence' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'four-factors',
    section: 'core-ratings',
    title: 'The Four Factors',
    subtitle: 'The basketball foundation of possession-level analysis',
    description: 'The basketball foundation behind shooting efficiency, turnovers, rebounding, and free throw pressure.',
    bestUsedFor: 'Understanding why a team wins or loses possessions',
    summary:
      'The Four Factors — Effective Field Goal Percentage, Turnover Rate, Offensive Rebounding Rate, and Free Throw Rate — describe the four ways a team can win or lose individual possessions. Introduced by Dean Oliver, they remain the most useful framework for understanding possession-level basketball without reducing teams to raw box-score totals.',
    whatItMeasures:
      'Each factor captures a different dimension of possession efficiency. eFG% measures shooting quality. TOV% measures ball security. ORB% measures second-chance creation. FTR measures free throw generation. Offensive and defensive versions exist for each, enabling margin analysis.',
    whyItMatters:
      'Raw box-score stats (points, rebounds, assists) are volume stats that reward pace and ignore context. Rate stats per possession are more informative. A team that shoots 55% eFG and forces 22% turnover rate has a clear structural advantage over one that scores more raw points through pace alone.',
    howToInterpret:
      'Look at margins, not just absolute values. A team with eFG% 54% is good in isolation; a team with eFG% 54% while holding opponents to 46% has a +8 eFG% margin, which is elite. The same logic applies to all four factors. On defense, lower opponent values are better for eFG%, TOV (higher is better — more opponent turnovers), ORB% (lower opponent ORB% is better), and FTR (lower opponent FTR is better).',
    basicFormula: {
      prose:
        'eFG% = (FGM + 0.5 × 3PM) / FGA\nTOV% = TOV / (FGA + 0.475 × FTA + TOV)\nORB% = OREB / (OREB + Opp DREB)\nFTR = FTA / FGA',
    },
    technicalNotes: [
      'eFG% gives three-pointers 1.5× weight because a made three scores 50% more than a made two.',
      'TOV% uses possessions as denominator (approximated), not raw game count.',
      'ORB% is bounded by opponent defensive rebounding — a team cannot have 100% ORB% unless the opponent secures no defensive rebounds.',
      'FTR is a rate of free throw attempts relative to field goal attempts, not a success rate. FTMR (made rate) is sometimes used alternatively.',
    ],
    knownLimitations: [
      'Four Factors do not capture shot quality within eFG% (e.g., corner three vs. mid-range).',
      'FTR does not distinguish intentional fouls, technical fouls, or end-of-game fouling situations.',
      'Rebounding rates from play-by-play vs. box score can differ slightly.',
    ],
    example:
      'A team with eFG% 53.1%, TOV% 14.2%, ORB% 32.4%, FTR 0.38 has a strong but not elite shooting profile, excellent ball security, good offensive rebounding, and high free throw generation. Together these suggest a balanced, high-efficiency offense.',
    relatedMetrics: [
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'four-factor-index',
    section: 'core-ratings',
    title: 'Macfax Four Factor Index',
    subtitle: 'One standardized score from four possession-level margins',
    description: 'How Macfax combines Four Factor performance into one standardized 0–100 team profile score.',
    bestUsedFor: 'Quick comparison of how teams perform across all four possession dimensions',
    summary:
      'The Four Factor Index (FFI) converts the four possession-level margins into a single 0–100 score. Each factor is standardized to a z-score relative to the national distribution, then weighted by its historical predictive importance. The resulting composite describes overall possession-efficiency profile on a consistent scale.',
    whatItMeasures:
      'FFI measures the composite advantage a team holds across all four possession margins — shooting, turnover, rebounding, and free throw pressure — weighted by how much each factor explains team success.',
    whyItMatters:
      'Individual Four Factor values require context to interpret. FFI removes that friction by expressing everything relative to a national baseline, making it easy to compare two teams or track how a team\'s overall possession profile changes over a season.',
    howToInterpret:
      'FFI is centered at 50, which represents exactly average national Four Factor performance. Scores above 60 are strong. Scores above 70 are elite. Scores below 40 are weak. The scale is capped at 0 and 100.',
    basicFormula: {
      latex:
        'FFI = \\text{clamp}(50 + 20 \\times \\text{Weighted FFI Z-Score},\\ 0,\\ 100)',
      prose: 'Weighted FFI Z-Score = 0.47·z_eFG + 0.24·z_TOV + 0.21·z_REB + 0.08·z_FTR',
    },
    weights: [
      { label: 'eFG% Margin', value: '47%', pct: '47' },
      { label: 'Turnover Edge', value: '24%', pct: '24' },
      { label: 'Rebounding Edge', value: '21%', pct: '21' },
      { label: 'Free Throw Rate Margin', value: '8%', pct: '8' },
    ],
    interpretationBands: [
      { label: 'Elite', range: '70–100', color: 'success', description: 'Top national possession profile. Dominant on multiple factors.' },
      { label: 'Strong', range: '60–69', color: 'brand', description: 'Above average across most factors. Consistent possession-level advantage.' },
      { label: 'Average', range: '45–59', color: 'secondary', description: 'Near national mean. Competitive but no clear edge.' },
      { label: 'Below Average', range: '35–44', color: 'warning', description: 'Possession-level disadvantages present. Tends to lose close games.' },
      { label: 'Weak', range: '0–34', color: 'negative', description: 'Significant possession-level deficits. Structural team quality concerns.' },
    ],
    technicalNotes: [
      'Z-scores are computed relative to the full Division I national distribution for the current season.',
      'The 15× multiplier calibrates the standard deviation so that one z-unit ≈ 15 FFI points.',
      'eFG% margin receives the highest weight (47%) as the single strongest predictor. Turnover edge is second at 24%, reflecting its direct impact on possession count.',
      'Rebounding and free throw rate have lower weights reflecting their lower predictive power relative to shooting and turnovers.',
    ],
    knownLimitations: [
      'FFI is a composite — two teams can have the same score through very different factor profiles.',
      'Early-season FFI is noisy; treat it as directional until 8+ games.',
      'FFI does not capture opponent quality directly — a high FFI against a weak schedule may overstate team quality.',
      'Weights may be recalibrated between seasons as new data accumulates.',
    ],
    example:
      'A team with +3.1 eFG% margin, +4.2 turnover edge, +1.8 rebounding edge, −0.3 FTR margin computes a weighted z-score of approximately +1.2, yielding FFI ≈ 68. This places them in the strong tier — above average in most factors.',
    relatedMetrics: [
      { label: 'The Four Factors', slug: 'four-factors' },
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Matchup Model', slug: 'matchup-model' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'bayesian-performance-rating',
    section: 'player-evaluation',
    title: 'Macfax Bayesian Performance Rating',
    subtitle: 'Player impact through offensive, defensive, and total value estimates',
    description: 'How Macfax estimates offensive, defensive, and total player impact.',
    bestUsedFor: 'Evaluating individual player value above or below replacement level',
    summary:
      'Macfax Bayesian Performance Rating, or BPR, is Macfax\'s player impact estimate. It separates offensive, defensive, and total player value using box-score production, on-court impact signals, teammate and opponent context, and sample-size stabilization. BPR is expressed as points added or subtracted per 100 team possessions.',
    whatItMeasures:
      'BPR measures the net effect a player has on team scoring margin per 100 possessions. Offensive BPR (OBPR) measures offensive contribution; Defensive BPR (DBPR) measures defensive contribution. Total BPR is their sum. Positive values mean the player improves the team; negative means the team plays worse with that player on the court.',
    whyItMatters:
      'Raw stats (points, rebounds, assists) measure what a player does, not whether those actions help the team win. A player who scores 20 points on 34% shooting hurts their team. BPR attempts to separate positive contribution from volume.',
    howToInterpret:
      'BPR of 0.0 represents a replacement-level player — a player with no meaningful impact on team performance. Positive BPR players improve the team above this baseline. Elite players typically have BPR of +4 or higher. Negative BPR players are below replacement in the current model framework.',
    basicFormula: {
      prose: 'BPR = OBPR + DBPR',
    },
    interpretationBands: [
      { label: 'Star / All-American', range: '+5.0 and above', color: 'success', description: 'Transformative impact. Significant team improvement on court.' },
      { label: 'High Contributor', range: '+2.0 to +4.9', color: 'brand', description: 'Clear positive impact. Reliable above-replacement value.' },
      { label: 'Replacement Level', range: '-1.0 to +1.9', color: 'secondary', description: 'Near neutral impact. Team roughly as good with or without.' },
      { label: 'Below Replacement', range: 'below -1.0', color: 'negative', description: 'Team performs worse with this player on court in current model.' },
    ],
    technicalNotes: [
      'Box-score priors provide the initial signal from traditional statistics adjusted for pace and opponent strength.',
      'On-court adjusted impact uses lineup data where available to capture effects beyond box-score counting.',
      'Teammate context adjusts for playing alongside strong or weak teammates to isolate individual contribution.',
      'Opponent context adjusts for the strength of players defended, improving DBPR reliability.',
      'Sample-size stabilization (Bayesian shrinkage) pulls estimates toward the position mean early in a season. Ratings become more reliable after 15+ games.',
      'Player-season identity tracks each player within their current season context.',
      'Multi-year prior logic may be incorporated where career data helps stabilize small-sample seasons.',
    ],
    knownLimitations: [
      'Player ratings are inherently noisier than team ratings. College basketball sample sizes are small.',
      'DBPR is particularly uncertain — defense is difficult to measure from box scores alone.',
      'Players in unusual roles (backup center who rarely plays) have high uncertainty intervals.',
      'BPR does not capture leadership, communication, or off-ball positioning that never shows up in any box score.',
      'Early-season BPR for freshmen has no prior year data, making shrinkage pull strongly toward the mean.',
    ],
    example:
      'A guard with OBPR +3.2 and DBPR +1.1 has Total BPR +4.3 — a high-impact player who contributes meaningfully on both ends. A center with OBPR +2.8 and DBPR −0.4 has Total BPR +2.4 — strong offensively but slightly below average defensively in the current model.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'matchup-model',
    section: 'prediction-tools',
    title: 'Macfax Matchup Model',
    subtitle: 'Game projections, spreads, totals, and win probability',
    description: 'How Macfax projects scores, spreads, totals, win probabilities, and matchup edges.',
    bestUsedFor: 'Understanding what Macfax expects from a specific upcoming game',
    summary:
      'The Macfax Matchup Model projects game outcomes using each team\'s adjusted offensive and defensive efficiency, expected possessions, site factors, and Four Factor profile edges. It produces a projected score, projected spread, projected total, and win probability for each team.',
    whatItMeasures:
      'The Matchup Model estimates the most likely score and outcome for a given game. It uses the opponent interaction between one team\'s adjusted offense and the other\'s adjusted defense to project raw scoring, then applies a site adjustment and tempo estimate to produce concrete predictions.',
    whyItMatters:
      'Game previews without quantitative projection rely on narrative. The Matchup Model converts team ratings into specific, falsifiable predictions, which can be evaluated after the game to improve the model over time.',
    howToInterpret:
      'Projected spread is the model\'s best estimate of the margin. Win probability is expressed as a percentage — 70% means the model expects the favored team to win roughly 7 out of 10 times under similar conditions. A 70% win probability game is not a lock; basketball is volatile enough that the underdog wins 3 in 10. Do not treat any probability under 90% as certain.',
    basicFormula: {
      prose:
        'Projected OE (Team A) = AdjO_A adjusted for AdjD_B and site\nProjected DE (Team A) = AdjD_A adjusted for AdjO_B and site\nExpected Score = Projected OE × (Expected Possessions / 100)\nProjected Spread = Expected Score_A − Expected Score_B',
    },
    technicalNotes: [
      'Site adjustment applies home court advantage factor to the projecting team.',
      'Expected possessions uses each team\'s adjusted tempo to estimate game pace.',
      'Four Factor edges may adjust projected scoring to account for specific style matchups.',
      'Win probability is derived from the projected spread using a normal distribution with a calibrated standard deviation representing typical game-to-game volatility.',
      'Projected total is the sum of both teams\' expected scores.',
    ],
    knownLimitations: [
      'The model does not adjust for injuries unless roster data is updated.',
      'Travel, rest advantage, and altitude are not currently in the model.',
      'Late lineup changes before tip-off are not reflected.',
      'Win probability assumes a typical variance around the projection — actual variance can be higher in neutral-site tournament games.',
      'The model improves with more games played; early-season projections carry more uncertainty.',
    ],
    example:
      'Team A (AdjO 116.2, AdjD 95.1) hosts Team B (AdjO 108.4, AdjD 99.7). Model projects Team A 74 – Team B 66, spread −8, total 140, win probability 78% for Team A.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Four Factor Index', slug: 'four-factor-index' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'trapezoid-of-excellence',
    section: 'visual-frameworks',
    title: 'The Trapezoid of Excellence',
    subtitle: 'A visual framework for elite efficiency-tempo profiles',
    description: 'How Macfax visualizes the national efficiency-tempo region where elite teams tend to appear.',
    bestUsedFor: 'Identifying whether a team\'s efficiency-tempo profile is nationally competitive',
    summary:
      'The Trapezoid of Excellence is a Macfax visualization that identifies the national efficiency-tempo region where elite team profiles tend to appear. It is not a separate rating. It is a visual framework for understanding where teams sit relative to high-performing national profiles. Teams inside the trapezoid occupy a zone associated with tournament-caliber performance.',
    whatItMeasures:
      'The trapezoid plots teams on two axes: Adjusted Efficiency Margin (AdjEM) on the vertical and Adjusted Tempo on the horizontal. The trapezoid region marks the efficiency-tempo combinations historically associated with at-large tournament bids and deep tournament runs.',
    whyItMatters:
      'Teams can be strong in different ways — a high-tempo team and a low-tempo team can both have strong adjusted efficiency margins. The trapezoid visualizes whether a team\'s particular efficiency-tempo combination places them in a nationally competitive zone, or whether their profile has structural concerns.',
    howToInterpret:
      'Teams inside the trapezoid have efficiency-tempo profiles that historically match tournament-caliber teams. Teams outside may still be strong (a team can have elite AdjEM outside the trapezoid region), but their profile is less common among tournament participants. The region is based on national distribution — it should not change when filtering by conference.',
    technicalNotes: [
      'Trapezoid boundaries are derived from the national distribution of tournament-qualifying teams, not manually set.',
      'The reference region is season-specific and recalculates when new season data is available.',
      'Conference filter on the visualization changes which teams are shown but should not change the trapezoid region itself — it is a national reference.',
      'AdjEM on the vertical axis is plotted on a logarithmic-friendly scale to prevent extreme outliers from compressing the central region.',
    ],
    knownLimitations: [
      'The trapezoid is descriptive, not predictive — being inside it does not guarantee a tournament bid.',
      'Early-season plots are less meaningful because adjusted ratings have high uncertainty.',
      'Teams at the boundary of the trapezoid are not meaningfully different from teams just outside it.',
    ],
    example:
      'A team with AdjEM +18.5 and AdjTempo 70.2 falls inside the trapezoid. A team with AdjEM +16.0 but AdjTempo 59.0 (very slow pace) may fall outside even with a strong margin, because their efficiency-tempo combination is less common among at-large tournament teams.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Efficiency Landscape', slug: 'efficiency-landscape' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'efficiency-landscape',
    section: 'visual-frameworks',
    title: 'The Efficiency Landscape',
    subtitle: 'Mapping teams by adjusted offense and defense',
    description: 'How Macfax maps teams by adjusted offense and adjusted defense to show team style and strength.',
    bestUsedFor: 'Understanding how teams are strong — offensively, defensively, or both',
    summary:
      'The Efficiency Landscape maps teams by their Adjusted Offensive Efficiency (AdjO) on one axis and Adjusted Defensive Efficiency (AdjD) on the other. It shows not only which teams are strong overall, but how they are strong — helping distinguish offense-driven, defense-driven, and balanced teams.',
    whatItMeasures:
      'The landscape plots each team\'s offensive and defensive efficiency on a two-axis scatter. Net rating (AdjEM) is the diagonal — teams in the upper-left quadrant (high offense, low opponent scoring allowed) are the strongest. Teams can be compared visually on both dimensions simultaneously.',
    whyItMatters:
      'AdjEM alone describes how good a team is but not how. Two teams with identical AdjEM +15 can have very different profiles — one through elite offense and average defense, one through elite defense and average offense. The landscape makes that distinction visible and actionable for matchup analysis.',
    howToInterpret:
      'Upper-left quadrant (high AdjO, low AdjD) = best teams. Lower-right = weakest. Teams near the top of the upper-left cluster are title contenders. Teams in the mid-range may be bubble or tournament fringe. Specific tier lines on the plot mark approximate thresholds for title contender, Final Four, Sweet 16, and at-large quality based on current season distribution.',
    technicalNotes: [
      'Tier lines are based on adjusted efficiency thresholds from historical tournament outcomes and are recalibrated per season.',
      'Defensive efficiency axis is typically inverted (lower = better) so that "up and left" consistently means better.',
      'The landscape is intended for visual comparison — small differences between adjacent teams are not meaningful.',
    ],
    knownLimitations: [
      'The landscape is a snapshot, not a projection. Strong teams early may regress; weak teams may improve.',
      'Teams with unusual defensive styles (e.g., extreme zone) may cluster differently than pace-adjusted models expect.',
    ],
    example:
      'A team with AdjO 118.0 and AdjD 94.5 sits in the upper-left, inside the title contender zone. A team with AdjO 110.0 and AdjD 94.5 has the same defense but weaker offense — they would sit slightly right of center in the Final Four zone. The landscape shows this difference immediately.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Trapezoid of Excellence', slug: 'trapezoid-of-excellence' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'the-crystal-ball',
    section: 'prediction-tools',
    title: 'The Crystal Ball',
    subtitle: 'Forward-looking team outlooks and projection confidence',
    description: 'How Macfax summarizes forward-looking team outlooks, expected outcomes, and projection confidence.',
    bestUsedFor: 'Getting a probabilistic read on what Macfax expects from a team going forward',
    summary:
      'The Crystal Ball is a forward-looking Macfax tool that uses adjusted ratings, matchup projections, schedule context, and volatility indicators to estimate what may happen next. It is probabilistic, not prophetic. The Crystal Ball estimates likely outcomes based on available data, but basketball remains rude enough to ignore spreadsheets.',
    whatItMeasures:
      'The Crystal Ball summarizes Macfax\'s forward-looking projections, including expected future performance, probability-weighted outcomes, and confidence levels for teams based on their current rating and remaining schedule.',
    whyItMatters:
      'Past ratings describe what a team has done. The Crystal Ball attempts to translate that into what is likely to happen next — useful for tournament seeding projections, game previews, and understanding which teams have favorable or unfavorable remaining schedules.',
    howToInterpret:
      'Probabilities in the Crystal Ball represent the model\'s estimate of likelihood under current conditions. A 65% probability does not mean a team will win — it means that under similar conditions, they would be expected to win roughly 65% of the time. Treat all Crystal Ball outputs as estimates, not certainties. Confidence indicators signal how stable the projection is relative to model uncertainty.',
    technicalNotes: [
      'Crystal Ball projections use current adjusted ratings as the primary input, combined with schedule and site context.',
      'Probability estimates use normal distribution modeling with calibrated variance.',
      'Tournament projection logic, where included, applies bracket simulation over remaining schedule.',
      'The tool is still evolving. Specific logic and weighting may be recalibrated in the current version.',
    ],
    knownLimitations: [
      'Projections do not account for injuries, suspensions, or roster changes.',
      'Uncertainty increases with longer projection horizons — next-game projections are more reliable than season-end estimates.',
      'The model cannot anticipate coaching changes, transfer portal moves, or player development mid-season.',
      'All projections should be read as conditional estimates, not guarantees.',
    ],
    example:
      'A team with AdjEM +20.5 facing a schedule of mostly below-average opponents projects a strong remaining record with high confidence. The same team facing three Top-10 road games projects a similar raw rating with wider probability intervals around each game outcome.',
    relatedMetrics: [
      { label: 'Matchup Model', slug: 'matchup-model' },
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Cinderella Index', slug: 'cinderella-index' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'cinderella-index',
    section: 'prediction-tools',
    title: 'Macfax Cinderella Index',
    subtitle: 'Upset danger relative to seed and expectation',
    description: 'How Macfax identifies teams with dangerous upset and tournament profiles relative to their seed or reputation.',
    bestUsedFor: 'Finding teams more dangerous than their seed or reputation suggests',
    summary:
      'The Cinderella Index is not a ranking of the best teams. It is a ranking of upset danger relative to expectation. It measures how dangerous a team is when their seed, public perception, or resume understates their actual quality or stylistic threat in a single-elimination context.',
    whatItMeasures:
      'The Cinderella Index scores teams on five dimensions: underseeded strength relative to their seed line, defensive disruption capability, possession control and ball security, performance variance (ability to go cold or get hot), and resume quality relative to reputation. Teams with a large gap between perceived strength and actual strength score highest.',
    whyItMatters:
      'Tournament seeding is partially based on perception and selection committee criteria, not purely on adjusted ratings. A team that is better than their seed suggests, plays high-variance basketball, and has a matchup-portable style represents structural upset danger regardless of their name recognition.',
    howToInterpret:
      'Higher Cinderella Index scores mean more upset potential relative to expectation. A #12 seed with score 72 is more dangerous than a #12 seed with score 40. This is not a quality ranking — a #1 seed could theoretically score high on Cinderella Index if their true strength far exceeds even their top seed perception, but the metric is most meaningful for mid-major and mid-seeded teams.',
    interpretationBands: [
      { label: 'High Danger', range: '65–100', color: 'success', description: 'Strong structural upset threat. Multiple factors point to seed/perception gap.' },
      { label: 'Elevated Danger', range: '50–64', color: 'brand', description: 'Real upset potential. At least one or two significant factors present.' },
      { label: 'Average', range: '35–49', color: 'secondary', description: 'Profile matches expectation. Limited structural upset edge.' },
      { label: 'Low Danger', range: '0–34', color: 'negative', description: 'Team profile does not suggest upset risk above their seeding.' },
    ],
    technicalNotes: [
      'Component weights in the current version: Underseeded Strength 28%, Defense 27%, Possession/Turnover 21%, Variance 14%, Resume Gap 10%.',
      'Exact component weights may be recalibrated as tournament data accumulates.',
      'Scores are standardized within the at-large and auto-bid field, not the full Division I population.',
    ],
    knownLimitations: [
      'Cinderella Index is most meaningful during the tournament; in-season use is directional only.',
      'Tournament randomness is real — even a low Cinderella Index team can pull an upset through variance alone.',
      'The metric works best for mid-major and bubble teams; extreme seeds (1, 2, 16) have less meaningful scores.',
      'Component weights are still evolving with each additional tournament season of data.',
    ],
    example:
      'A 12-seed with Cinderella Index 71 has strong adjusted efficiency (underseeded by 2+ seed lines), elite turnover rate, high variance profile, and an eFG% defense that matches poorly against their likely 5-seed opponent. This is the structural Cinderella profile.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
      { label: 'The Crystal Ball', slug: 'the-crystal-ball' },
      { label: 'Four Factor Index', slug: 'four-factor-index' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'resume-metrics',
    section: 'resume-data',
    title: 'Macfax Resume Metrics',
    subtitle: 'What a team has earned, not just how good they are',
    description: 'How Macfax evaluates schedule strength, quality wins, WAB, SOR, and tournament resume.',
    bestUsedFor: 'Evaluating what a team has accomplished against their actual schedule',
    summary:
      'Adjusted Ratings estimate how good a team is. Resume Metrics estimate what a team has accomplished. These are different questions. A team can have strong adjusted ratings through a weak schedule; resume metrics capture whether they have validated that strength by winning the right games.',
    whatItMeasures:
      'Resume Metrics cover: Strength of Schedule (SOS), Strength of Record (SOR), Wins Above Bubble (WAB), Quadrant records, best wins, worst losses, and road/neutral site context. Together they describe the achievement profile — the evidence a team has for an at-large tournament selection.',
    whyItMatters:
      'NCAA Tournament selection committees use achievement-based criteria, not just predictive ratings. A team that goes 28-3 with a weak schedule may rate well in adjusted efficiency but have poor resume metrics — which reflects the selection risk accurately. Resume Metrics serve as the committee-facing complement to predictive ratings.',
    howToInterpret:
      'WAB is the most useful single resume number: it measures wins above what a typical bubble-quality team would be expected to produce against the same schedule. Positive WAB means better than expected; negative means worse. SOR measures the probability that a team\'s record would be produced by a top-25 team. Quadrant records follow NCAA Committee quadrant definitions based on opponent rank and game location.',
    basicFormula: {
      prose: 'WAB = Actual Wins − Expected Bubble-Team Wins Against Same Schedule',
    },
    technicalNotes: [
      'Quadrant definitions follow NCAA Committee criteria: Q1 = home vs. 1–75, neutral vs. 1–50, away vs. 1–30; Q2 = home 76–100, neutral 51–75, away 31–50; Q3 = home 101–160, neutral 76–125, away 51–100; Q4 = home 161+, neutral 126+, away 101+.',
      'Strength of Schedule uses opponent adjusted efficiency margin weighted by game location.',
      'Expected wins for WAB use a bubble-team efficiency profile to simulate expected outcomes against the actual schedule.',
    ],
    knownLimitations: [
      'Resume metrics are backward-looking and do not predict future performance.',
      'WAB is sensitive to the bubble team efficiency baseline, which is recalibrated annually.',
      'Early-season resume metrics are not stable until 15+ games are played.',
      'Conference tournament performance affects resume metrics significantly in March.',
    ],
    example:
      'A team with WAB +4.2 and Q1 record 7-3 has a strong tournament resume. They have beaten four more teams than expected and have winning records in the hardest game category. This supports an at-large bid even without a dominant efficiency margin.',
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Cinderella Index', slug: 'cinderella-index' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
  },

  {
    slug: 'data-sources-updates',
    section: 'resume-data',
    title: 'Data Sources and Update Timing',
    subtitle: 'Where Macfax data comes from and when ratings update',
    description: 'Where Macfax data comes from, how it is processed, and when ratings update.',
    bestUsedFor: 'Understanding data freshness and the reliability of current ratings',
    summary:
      'Macfax data is collected from public game data sources, standardized through consistent possession and efficiency calculation, and validated before ratings are updated. This page describes the data pipeline, update cadence, and known limitations of the underlying data.',
    whatItMeasures:
      'This page covers data provenance, not a metric. It explains what data sources power Macfax, how game data is processed into possession-level statistics, how ratings are computed and validated, and when updates occur.',
    whyItMatters:
      'Analytics are only as reliable as the data behind them. Macfax is committed to consistent, transparent data handling. Users should understand the current update timing to avoid misreading stale ratings, and should know which types of games or situations introduce data quality limitations.',
    howToInterpret:
      'Ratings reflect games processed through the most recent update cycle. If a game was played very recently, it may not yet be reflected. During tournament periods, updates occur more frequently. Known data limitations (listed below) are situations where the underlying box score data is less reliable or unavailable.',
    technicalNotes: [
      'Game box score data is collected from public sources covering all Division I men\'s basketball games.',
      'Possession calculations use the standard formula: FGA − OREB + TOV + 0.475 × FTA.',
      'Efficiency values are computed per 100 possessions before opponent adjustment.',
      'Opponent adjustment is iterative — each team\'s ratings depend on their opponents\' ratings, converging over multiple passes.',
      'Data validation checks for statistical outliers, missing box scores, and format inconsistencies before inclusion.',
      'Ratings typically update within 24 hours of game completion during the regular season. Tournament period updates are more frequent.',
    ],
    knownLimitations: [
      'Box score data from early November (Exhibition games, scrimmages) is excluded from ratings.',
      'Forfeit or administrative wins may appear differently from box-score counts.',
      'Missing or corrected box scores are incorporated on the next update cycle.',
      'The possession formula is an estimate — play-by-play possession counts, where available, are more precise.',
      'Data corrections to historical games occur occasionally and may cause small retroactive rating changes.',
    ],
    relatedMetrics: [
      { label: 'Adjusted Ratings', slug: 'adjusted-ratings' },
      { label: 'Resume Metrics', slug: 'resume-metrics' },
    ],
    lastUpdated: '2025-11',
    methodologyVersion: '2.0',
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

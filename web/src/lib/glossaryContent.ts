import type { GlossaryTerm } from './glossaryTypes';

export const GLOSSARY_TERMS: GlossaryTerm[] = [
  // ─── Efficiency Ratings ───────────────────────────────────────────────────

  {
    id: 'adj_o',
    term: 'Adjusted Offensive Efficiency',
    aliases: ['AdjO', 'Adj O', 'Offensive Efficiency'],
    category: 'efficiency',
    shortDefinition: 'Points scored per 100 possessions, adjusted for opponent defensive quality.',
    detailedDefinition:
      'AdjO estimates how many points a team would score per 100 possessions against an average D1 defense. Raw offensive efficiency is iteratively adjusted based on the strength of defenses faced, giving a more accurate picture of offensive quality than unadjusted points-per-possession.',
    formula: {
      display: '\\text{Raw OE} = \\frac{\\text{Points}}{\\text{Possessions}} \\times 100',
      prose: 'Raw offensive efficiency is then adjusted via iterative opponent strength calculation.',
    },
    howToInterpret:
      'National average is roughly 100–105. Elite offenses exceed 120. Below 90 is poor. Scores above ~115 put a team in the top tier nationally.',
    methodologySlug: 'adjusted-ratings',
    relatedTerms: ['adj_d', 'adj_em', 'tempo'],
    isHigherBetter: true,
  },

  {
    id: 'adj_d',
    term: 'Adjusted Defensive Efficiency',
    aliases: ['AdjD', 'Adj D', 'Defensive Efficiency'],
    category: 'efficiency',
    shortDefinition: 'Points allowed per 100 possessions, adjusted for opponent offensive quality.',
    detailedDefinition:
      'AdjD estimates how many points a team would allow per 100 possessions against an average D1 offense. Raw defensive efficiency is iteratively adjusted for the strength of offenses faced. Lower is better — elite defenses allow fewer points per possession.',
    formula: {
      display: '\\text{Raw DE} = \\frac{\\text{Opp Points}}{\\text{Possessions}} \\times 100',
      prose: 'Then adjusted via iterative opponent strength calculation.',
    },
    howToInterpret:
      'National average is roughly 100–105. Elite defenses are below 90. Above 115 is poor. Scores below ~92 put a team in the top tier defensively.',
    methodologySlug: 'adjusted-ratings',
    relatedTerms: ['adj_o', 'adj_em', 'tempo'],
    isHigherBetter: false,
  },

  {
    id: 'adj_em',
    term: 'Adjusted Efficiency Margin',
    aliases: ['AdjEM', 'Adj EM', 'Efficiency Margin'],
    category: 'efficiency',
    shortDefinition: 'Net efficiency rating — the difference between adjusted offense and defense.',
    detailedDefinition:
      'AdjEM is the single most predictive measure of overall team quality on Macfax. It captures both offensive and defensive performance adjusted for opponent strength. A positive number means the team scores more efficiently than it allows; a larger number means a wider quality gap.',
    formula: {
      display: '\\text{AdjEM} = \\text{AdjO} - \\text{AdjD}',
    },
    howToInterpret:
      'Top-10 teams often exceed +30. Bubble teams cluster around 0 to +10. Negative values indicate below-average teams. AdjEM is the primary driver of Macfax matchup predictions.',
    methodologySlug: 'adjusted-ratings',
    relatedTerms: ['adj_o', 'adj_d', 'tempo'],
    isHigherBetter: true,
  },

  {
    id: 'tempo',
    term: 'Adjusted Tempo',
    aliases: ['Tempo', 'Pace'],
    category: 'efficiency',
    shortDefinition: 'Estimated possessions per 40 minutes, adjusted for opponent pace.',
    detailedDefinition:
      'Tempo measures how fast a team plays, expressed as possessions per 40-minute game after adjusting for opponent pace tendencies. Possessions are estimated from box-score statistics using the standard approximation. Tempo is an independent dimension from efficiency — fast teams are not inherently better or worse.',
    formula: {
      display: '\\text{Possessions} \\approx \\text{FGA} - \\text{OREB} + \\text{TOV} + 0.475 \\times \\text{FTA}',
      prose: 'Tempo is then estimated as possessions per 40 minutes, adjusted for opponent pace.',
    },
    howToInterpret:
      'National average is roughly 68–70 possessions per game. Slowest teams are around 60; fastest push past 75. Tempo matters for predicting total scores but not outcomes on its own.',
    methodologySlug: 'adjusted-ratings',
    relatedTerms: ['adj_o', 'adj_d', 'adj_em'],
    isHigherBetter: null,
  },

  // ─── Four Factors ─────────────────────────────────────────────────────────

  {
    id: 'efg_pct',
    term: 'Effective Field Goal %',
    aliases: ['eFG%', 'eFG', 'effective FG'],
    category: 'four-factors',
    shortDefinition: 'Field goal percentage adjusted to give 3-pointers 1.5× the weight of 2-pointers.',
    detailedDefinition:
      'eFG% is the most important of the Four Factors. It adjusts raw field goal percentage to account for the extra value of 3-point shots. A made 3-pointer counts as 1.5 field goals in the formula, making eFG% a fairer measure of shooting efficiency across teams with different shot distributions.',
    formula: {
      display: '\\text{eFG\\%} = \\frac{\\text{FG} + 0.5 \\times \\text{3P}}{\\text{FGA}}',
    },
    howToInterpret:
      'National average is around 50–52%. Elite offenses exceed 57%; struggling offenses fall below 47%. In Macfax, the eFG margin (team eFG% minus opponent eFG%) is the strongest predictor of game outcomes among the four factors.',
    methodologySlug: 'four-factors',
    relatedTerms: ['tov_rate', 'orb_pct', 'ftr', 'ffi'],
    isHigherBetter: true,
  },

  {
    id: 'tov_rate',
    term: 'Turnover Rate',
    aliases: ['TOV%', 'TOV Rate', 'Turnover %'],
    category: 'four-factors',
    shortDefinition: 'Turnovers committed per 100 possessions.',
    detailedDefinition:
      'TOV% measures how often a team gives the ball away. Lower is better for offense; higher is better for defense. On the margin, what matters is forcing more turnovers than you commit — a positive TOV edge means the team benefits from this factor.',
    formula: {
      display: '\\text{TOV\\%} = \\frac{\\text{TOV}}{\\text{Possessions}} \\times 100',
    },
    howToInterpret:
      'Average is around 17–19%. Below 15% is excellent ball security; above 22% is problematic. On defense, forcing a high turnover rate is a major advantage.',
    methodologySlug: 'four-factors',
    relatedTerms: ['efg_pct', 'orb_pct', 'ftr', 'ffi'],
    isHigherBetter: false,
  },

  {
    id: 'orb_pct',
    term: 'Offensive Rebound %',
    aliases: ['ORB%', 'OREB%', 'Offensive Rebounding'],
    category: 'four-factors',
    shortDefinition: 'Percentage of available offensive rebounds a team secures.',
    detailedDefinition:
      'ORB% measures a team\'s ability to extend possessions by recovering their own misses. It\'s calculated relative to available rebounds — only rebounds the offense could have gotten. Defensive rebound rate (DRB%) is the same concept from the other end, measuring how well a team limits opponent offensive rebounds.',
    formula: {
      display: '\\text{ORB\\%} = \\frac{\\text{ORB}}{\\text{ORB} + \\text{Opp DRB}} \\times 100',
    },
    howToInterpret:
      'Average ORB% is around 28–30%. Elite offensive rebounding teams exceed 35%; elite defensive rebounding teams hold opponents below 24%. The rebound edge (team ORB% − opponent ORB%) is the four-factor component with the third-highest weight in FFI.',
    methodologySlug: 'four-factors',
    relatedTerms: ['efg_pct', 'tov_rate', 'ftr', 'ffi'],
    isHigherBetter: true,
  },

  {
    id: 'ftr',
    term: 'Free Throw Rate',
    aliases: ['FTR', 'FT Rate'],
    category: 'four-factors',
    shortDefinition: 'Free throws attempted per field goal attempt — measures getting to the line.',
    detailedDefinition:
      'FTR captures a team\'s ability to draw fouls and convert from the stripe. On offense, a high FTR means earning extra scoring opportunities at the foul line. On defense, a low FTR allowed means not fouling often. The FTR margin compares how often a team gets to the line versus how often it sends opponents there.',
    formula: {
      display: '\\text{FTR} = \\frac{\\text{FTA}}{\\text{FGA}}',
    },
    howToInterpret:
      'Average FTR is around 0.28–0.33. Above 0.40 is aggressive; below 0.20 means rarely getting to the line. FTR carries the smallest weight of the four factors in FFI (8%), but can matter in low-possession games.',
    methodologySlug: 'four-factors',
    relatedTerms: ['efg_pct', 'tov_rate', 'orb_pct', 'ffi'],
    isHigherBetter: true,
  },

  {
    id: 'ffi',
    term: 'Four Factor Index',
    aliases: ['FFI'],
    category: 'four-factors',
    shortDefinition: 'Weighted composite of all four factors, scaled 0–100 relative to the national average.',
    detailedDefinition:
      'FFI combines eFG% margin, TOV edge, rebounding edge, and FTR margin into a single 0–100 score. Each factor is converted to a z-score against the national distribution for that season, weighted by its importance, and scaled to a 50-point baseline. A score of 50 is exactly average; higher is better. Scores are season-relative and not directly comparable across seasons.',
    formula: {
      display: '\\text{FFI} = \\text{clamp}\\left(50 + 20 \\times Z_{\\text{weighted}},\\ 0,\\ 100\\right)',
      prose: 'Weights: eFG margin 47%, TOV edge 24%, rebounding edge 21%, FTR margin 8%.',
    },
    howToInterpret:
      'FFI 70+ is elite; 60–70 is good; 40–60 is average; below 40 is struggling. A team with FFI 75 on offense and 30 on defense has a dominant four-factor advantage. FFI is available in both raw (unadjusted) and adjusted (opponent-adjusted) versions.',
    methodologySlug: 'four-factor-index',
    relatedTerms: ['efg_pct', 'tov_rate', 'orb_pct', 'ftr', 'adj_em'],
    isHigherBetter: true,
  },

  // ─── Player Ratings ───────────────────────────────────────────────────────

  {
    id: 'bpr',
    term: 'Bayesian Performance Rating',
    aliases: ['BPR'],
    category: 'player-ratings',
    shortDefinition: 'Overall player impact rating combining box-score contributions and on-court influence.',
    detailedDefinition:
      'BPR is Macfax\'s primary player evaluation metric. It combines box-score contributions (scoring, rebounding, assists, steals, blocks, turnovers) with on-court lineup impact to estimate a player\'s net effect on team performance per 100 possessions, adjusted for teammates, opponents, and schedule. The Bayesian component stabilizes estimates for players with limited minutes. BPR = OBPR + DBPR. Each rating carries a source label — On-court (lineup data drives it), Box-based (box-score model fills in when lineup sample is thin), or Mixed — and a confidence level that reflects sample size, not player quality. College note: play-by-play before the 2024-25 season contains no substitution data, so pre-2025 college ratings are driven by box score and team context rather than true lineup impact; ratings from 2025 onward use full lineup data and are validated out-of-sample against the strongest public college metrics.',
    formula: {
      display: '\\text{BPR} = \\text{OBPR} + \\text{DBPR}',
    },
    howToInterpret:
      'Positive BPR means the player helps the team. Above +5 is All-Conference caliber; above +10 is elite. Negative BPR suggests the player hurts performance when on the court. Context matters — a BPR of +3 on a top-10 team means something different than on a bottom-50 team. BPR answers "how good is this player, in context, right now" — team forecasts may separately use a blended projection value where it predicts future results better out of sample.',
    methodologySlug: 'bayesian-performance-rating',
    relatedTerms: ['obpr', 'dbpr'],
    isHigherBetter: true,
  },

  {
    id: 'obpr',
    term: 'Offensive BPR',
    aliases: ['OBPR'],
    category: 'player-ratings',
    shortDefinition: 'Offensive component of BPR — estimated offensive contribution per 100 possessions.',
    detailedDefinition:
      'OBPR isolates a player\'s offensive impact: scoring efficiency, assist creation, offensive rebounding, and avoiding turnovers. It is normalized per 100 possessions and adjusted for teammate and opponent quality. Higher OBPR means the player meaningfully improves the offense when on the court.',
    howToInterpret:
      'Elite offensive players typically post OBPR above +6. Average contributors are around 0 to +3. Negative OBPR suggests the player is a net drain offensively.',
    methodologySlug: 'bayesian-performance-rating',
    relatedTerms: ['bpr', 'dbpr'],
    isHigherBetter: true,
  },

  {
    id: 'dbpr',
    term: 'Defensive BPR',
    aliases: ['DBPR'],
    category: 'player-ratings',
    shortDefinition: 'Defensive component of BPR — estimated defensive contribution per 100 possessions.',
    detailedDefinition:
      'DBPR captures defensive impact through steal rates, block rates, defensive rebounding, and defensive on-court influence. It is harder to measure than offensive impact because defense shows up less clearly in box scores. The Bayesian component is especially important for stabilizing defensive estimates with limited data.',
    howToInterpret:
      'Elite defenders post DBPR above +4. Average is near 0. Negative DBPR means the player is being exploited defensively. High DBPR players often anchor a team\'s defensive system without showing up in traditional stat lines.',
    methodologySlug: 'bayesian-performance-rating',
    relatedTerms: ['bpr', 'obpr'],
    isHigherBetter: true,
  },

  // ─── Resume Metrics ────────────────────────────────────────────────────────

  {
    id: 'wab',
    term: 'Wins Above Bubble',
    aliases: ['WAB'],
    category: 'resume',
    shortDefinition: 'Wins accumulated above what a bubble-level team would be expected to win against the same schedule.',
    detailedDefinition:
      'WAB measures resume quality by comparing a team\'s actual results to what would be expected from a hypothetical bubble-caliber team playing that exact schedule. A positive WAB means the team outperformed bubble-level expectations; negative means they underperformed. WAB accounts for location (home/away/neutral) and the strength of each opponent.',
    formula: {
      display: '\\text{WAB} = \\sum \\left(\\text{Actual Result} - P_{\\text{bubble wins game}}\\right)',
    },
    howToInterpret:
      'Teams with WAB above +5 have strong at-large résumés. WAB near 0 is bubble territory. Negative WAB teams need conference tournament wins to make the field. WAB complements efficiency ratings by focusing on results rather than process.',
    methodologySlug: 'resume-metrics',
    relatedTerms: ['sos', 'sor'],
    isHigherBetter: true,
  },

  {
    id: 'sos',
    term: 'Strength of Schedule',
    aliases: ['SOS'],
    category: 'resume',
    shortDefinition: 'Expected win percentage for an average D1 team against this team\'s schedule.',
    detailedDefinition:
      'SOS expresses schedule difficulty as the expected winning percentage of an average D1 team if they played that exact slate of games, accounting for home/away/neutral location for each contest. A lower SOS percentage means harder opponents — an average team would struggle to win many of those games. Higher SOS means easier competition.',
    howToInterpret:
      'An average schedule has SOS around 40–45%. Below 35% is a brutal schedule; above 55% means notably weak competition. SOS alone doesn\'t measure a team\'s quality — only the difficulty of games they played.',
    methodologySlug: 'resume-metrics',
    relatedTerms: ['wab', 'sor'],
    isHigherBetter: null,
  },

  {
    id: 'sor',
    term: 'Strength of Record',
    aliases: ['SOR'],
    category: 'resume',
    shortDefinition: 'Probability that a reference-quality team would achieve this team\'s same record against the same schedule.',
    detailedDefinition:
      'SOR evaluates resume quality: given this team\'s exact win-loss record and schedule, what is the probability that a strong reference team would match or exceed it? A high SOR rank means the team\'s record is impressive relative to schedule difficulty. SOR rewards beating tough opponents and penalizes losses to weak ones.',
    howToInterpret:
      'Higher SOR rank (lower number) is better. A team ranked #1 in SOR has the most impressive record-relative-to-schedule combination in the country. SOR is particularly useful as a tiebreaker when teams have similar efficiency ratings but different records.',
    methodologySlug: 'resume-metrics',
    relatedTerms: ['wab', 'sos'],
    isHigherBetter: true,
  },

  // ─── Prediction ───────────────────────────────────────────────────────────

  {
    id: 'win_probability',
    term: 'Win Probability',
    aliases: ['Win Prob', 'Home Win %'],
    category: 'prediction',
    shortDefinition: 'Model probability that each team wins the game before tip-off.',
    detailedDefinition:
      'Win probability is generated from Macfax\'s efficiency-based matchup model before each game. It incorporates both teams\' adjusted offensive and defensive ratings, home-court advantage, and tempo context. The model outputs a probability for each outcome — not a guarantee — and reflects uncertainty in the prediction.',
    howToInterpret:
      '50% means a coin flip. 60% is a moderate favorite. 75%+ is a heavy favorite. Even 90% favorites lose 1-in-10 times. Win probability is calibrated so that 70% favorites should win about 70% of the time over a large sample.',
    methodologySlug: 'matchup-model',
    relatedTerms: ['projected_spread', 'projected_total', 'brier_score'],
    isHigherBetter: null,
  },

  {
    id: 'projected_spread',
    term: 'Projected Spread',
    aliases: ['Projected Margin', 'Point Spread'],
    category: 'prediction',
    shortDefinition: 'Model-predicted point margin for the game (positive = home team favored).',
    detailedDefinition:
      'The projected spread is the expected margin of victory based on the efficiency matchup. Positive values favor the home team; negative values favor the away team. The spread is derived from efficiency differentials and adjusted for home-court advantage. It is not intended as a betting line — it\'s a model estimate with inherent uncertainty.',
    howToInterpret:
      'A spread of +7 means the home team is expected to win by 7 points. Spread accuracy is measured by Spread MAE. College basketball spreads typically have an average error of 9–10 points.',
    methodologySlug: 'matchup-model',
    relatedTerms: ['projected_total', 'win_probability'],
    isHigherBetter: null,
  },

  {
    id: 'projected_total',
    term: 'Projected Total',
    aliases: ['Projected Score', 'O/U'],
    category: 'prediction',
    shortDefinition: 'Model-predicted combined score for both teams.',
    detailedDefinition:
      'The projected total is the expected combined final score of both teams. It is calculated from each team\'s offensive efficiency and the opponent\'s defensive efficiency, scaled by the expected number of possessions (determined by both teams\' tempo ratings). A higher tempo game generates more possessions and a higher projected total.',
    howToInterpret:
      'College basketball totals typically fall between 120 and 165 combined points. Low-tempo defensive games often fall below 130; high-tempo offensive games can exceed 160.',
    methodologySlug: 'matchup-model',
    relatedTerms: ['projected_spread', 'win_probability', 'tempo'],
    isHigherBetter: null,
  },

  // ─── Validation ───────────────────────────────────────────────────────────

  {
    id: 'winner_accuracy',
    term: 'Winner Accuracy',
    aliases: ['Pick Accuracy', 'Pick %'],
    category: 'validation',
    shortDefinition: 'Percentage of games where the model correctly predicted the winner before tip-off.',
    detailedDefinition:
      'Winner accuracy tracks how often the team with the higher predicted win probability actually won the game. All predictions are locked as snapshots before games are played — no postgame adjustments. A coin flip would yield ~50%. Good college basketball models typically land in the 68–74% range over a full season.',
    howToInterpret:
      '68%+ is solid for college basketball. 72%+ is excellent. Below 60% suggests a model problem. Single-game outcomes are noisy — accuracy stabilizes over 200+ games. Check this metric seasonally, not weekly.',
    methodologySlug: 'matchup-model',
    relatedTerms: ['spread_mae', 'brier_score'],
    isHigherBetter: true,
  },

  {
    id: 'spread_mae',
    term: 'Spread MAE',
    aliases: ['Margin Error', 'Spread Error'],
    category: 'validation',
    shortDefinition: 'Mean Absolute Error of predicted point margins — average miss in points.',
    detailedDefinition:
      'Spread MAE measures how far off the projected margin was on average, in absolute value. An MAE of 9.5 means the model was off by 9.5 points on average. Vegas lines on college basketball typically run 8.5–9.5 MAE. Signed margin error (positive or negative) reveals directional bias — whether the model systematically over- or under-predicts margins.',
    formula: {
      display: '\\text{MAE} = \\frac{1}{N} \\sum |\\text{Projected Margin} - \\text{Actual Margin}|',
    },
    howToInterpret:
      'Below 9.0 is competitive with Vegas lines. Below 8.0 is very good. Above 11.0 suggests systematic miscalibration. This is the most actionable accuracy metric for evaluating model quality.',
    methodologySlug: 'matchup-model',
    relatedTerms: ['winner_accuracy', 'brier_score'],
    isHigherBetter: false,
  },

  {
    id: 'brier_score',
    term: 'Brier Score',
    aliases: ['Brier'],
    category: 'validation',
    shortDefinition: 'Probability calibration metric — measures how well predicted win probabilities match actual outcomes.',
    detailedDefinition:
      'Brier score measures the accuracy of probability predictions, not just win/loss picks. It is calculated as the squared difference between the predicted probability and the actual outcome (1 = win, 0 = loss). Lower Brier scores mean better-calibrated probabilities. A perfect predictor scores 0.0; a coin flip scores 0.25.',
    formula: {
      display: '\\text{Brier} = \\left(p_{\\text{predicted}} - \\text{outcome}\\right)^2',
      prose: 'Averaged across all evaluated games. Outcome = 1 if predicted team wins, 0 otherwise.',
    },
    howToInterpret:
      'Below 0.20 indicates well-calibrated win probabilities. Above 0.25 is no better than a coin flip. Brier score penalizes overconfident wrong predictions more than modest wrong predictions — predicting 90% for a team that loses is much worse than predicting 55%.',
    methodologySlug: 'matchup-model',
    relatedTerms: ['winner_accuracy', 'spread_mae'],
    isHigherBetter: false,
  },

  // ─── Visual Frameworks ────────────────────────────────────────────────────

  {
    id: 'trapezoid',
    term: 'Trapezoid of Excellence',
    aliases: ['Trapezoid', 'Trap'],
    category: 'visual-frameworks',
    shortDefinition: 'A 2D scatter plot mapping teams by offensive and defensive efficiency with contextual regions.',
    detailedDefinition:
      'The Trapezoid of Excellence plots every team simultaneously using AdjO on the X-axis and AdjD on the Y-axis (inverted, so better defense is higher). Teams are color-coded by their bracket seeding or tier. The "trapezoid" shape outlines the realistic envelope of team quality — very few teams are both elite offensively and defensively, creating the characteristic shape.',
    howToInterpret:
      'Top-right quadrant: elite teams with great offense and defense. Top-left: defensive teams with weaker offense. Bottom-right: offensive teams that can\'t stop anyone. Bottom-left: teams struggling on both ends. Position relative to the national average lines shows overall quality.',
    methodologySlug: 'trapezoid-of-excellence',
    relatedTerms: ['adj_o', 'adj_d', 'adj_em'],
    isHigherBetter: null,
  },

  {
    id: 'efficiency_landscape',
    term: 'Efficiency Landscape',
    aliases: ['Landscape'],
    category: 'visual-frameworks',
    shortDefinition: 'A team-level breakdown showing all four efficiency components visualized together.',
    detailedDefinition:
      'The Efficiency Landscape provides a comprehensive visual snapshot of a team\'s offensive and defensive profile across the Four Factors. Each factor is displayed as a bar relative to the national average, making it easy to see where a team excels or struggles. It\'s designed to answer: "How does this team win games?" at a glance.',
    howToInterpret:
      'Bars extending to the right of center indicate above-average performance; left of center is below average. A team with all bars strongly right is a dominant all-around team; uneven bars reveal specific strengths and weaknesses.',
    methodologySlug: 'efficiency-landscape',
    relatedTerms: ['efg_pct', 'tov_rate', 'orb_pct', 'ftr', 'ffi'],
    isHigherBetter: null,
  },

  {
    id: 'crystal_ball',
    term: 'Crystal Ball',
    aliases: ['Bracket Simulation'],
    category: 'visual-frameworks',
    shortDefinition: 'A Monte Carlo tournament simulation that estimates each team\'s probability of reaching each bracket round.',
    detailedDefinition:
      'The Crystal Ball simulates the NCAA tournament thousands of times, using Macfax\'s matchup model to determine game-by-game probabilities. Each simulation produces a bracket winner; aggregating across simulations yields each team\'s probability of reaching the Round of 32, Sweet 16, Elite Eight, Final Four, and winning the championship.',
    howToInterpret:
      'Championship probability above 10% is very high — top seeds in a wide-open field. Sweet 16 probability above 50% is expected for top-4 seeds. First-round upset probability above 30% signals a dangerous 12-or-lower seed. These are probabilities, not predictions.',
    methodologySlug: 'the-crystal-ball',
    relatedTerms: ['win_probability', 'adj_em', 'projected_spread'],
    isHigherBetter: null,
  },

  {
    id: 'cinderella_index',
    term: 'Cinderella Index',
    aliases: ['Cinderella Score'],
    category: 'visual-frameworks',
    shortDefinition: 'A score measuring how likely a team is to be a tournament surprise — combining upset potential and narratives.',
    detailedDefinition:
      'The Cinderella Index combines statistical factors (efficiency ratings, seeding gap, recent performance) with contextual signals to estimate how likely a team is to make a surprising run in the NCAA tournament. Higher scores mean a team has the profile of a historical Cinderella: respectable efficiency, underseeding, and a favorable path.',
    howToInterpret:
      'Scores above 70 indicate strong Cinderella potential. Below 40 means the team is seeded appropriately relative to their efficiency metrics. The index is most meaningful for 9–15 seeds — it\'s not meant to evaluate 1-seeds.',
    methodologySlug: 'cinderella-index',
    relatedTerms: ['adj_em', 'win_probability', 'crystal_ball'],
    isHigherBetter: true,
  },
];

export function getGlossaryTerm(id: string): GlossaryTerm | undefined {
  return GLOSSARY_TERMS.find(t => t.id === id);
}

export const GLOSSARY_TERM_MAP: Record<string, GlossaryTerm> = Object.fromEntries(
  GLOSSARY_TERMS.map(t => [t.id, t])
);

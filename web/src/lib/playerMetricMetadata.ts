/**
 * Player metric metadata — shared definitions for NCAA and NBA player ranking tables.
 *
 * Mirrors the shape of metricMetadata.ts (for team metrics) so the same
 * heatmap, formatting, and rank-badge logic can be reused.
 */

export type Better = 'higher' | 'lower' | 'neutral';
// 'pct4' = multiply by 100 and show 1 decimal (e.g. fg_pct = 0.456 → "45.6%")
// 'pct_raw' = already a percent-point value, just show with 1 decimal + %
// 'number1' = show 1 decimal as-is
// 'number2' = show 2 decimals
// 'int' = show as integer
export type PlayerMetricFormat = 'pct4' | 'pct_raw' | 'number1' | 'number2' | 'int';

export interface PlayerMetricMeta {
  key: string;
  label: string;
  tooltip: string;
  format: PlayerMetricFormat;
  better: Better;
  showRank?: boolean;
  heatmap?: boolean;
  group?: string; // column group label
  tier?: 'primary' | 'secondary' | 'optional'; // default visibility tier
}

// ─── Traditional ─────────────────────────────────────────────────────────────

export const PLAYER_TRADITIONAL_METRICS: PlayerMetricMeta[] = [
  { key: 'pts',     label: 'PPG',   tooltip: 'Points per game.',                format: 'number1', better: 'neutral', showRank: true,  heatmap: true,  tier: 'primary'   },
  { key: 'reb',     label: 'RPG',   tooltip: 'Total rebounds per game.',         format: 'number1', better: 'neutral', showRank: false, heatmap: true,  tier: 'primary'   },
  { key: 'ast',     label: 'APG',   tooltip: 'Assists per game.',                format: 'number1', better: 'neutral', showRank: false, heatmap: true,  tier: 'primary'   },
  { key: 'stl',     label: 'SPG',   tooltip: 'Steals per game.',                 format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'primary'   },
  { key: 'blk',     label: 'BPG',   tooltip: 'Blocks per game.',                 format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'primary'   },
  { key: 'tov',     label: 'TOV',   tooltip: 'Turnovers per game.',              format: 'number1', better: 'lower',   showRank: false, heatmap: false, tier: 'primary'   },
  { key: 'oreb_pg', label: 'ORB',   tooltip: 'Offensive rebounds per game.',     format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'secondary' },
  { key: 'dreb_pg', label: 'DRB',   tooltip: 'Defensive rebounds per game.',     format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'secondary' },
  { key: 'fga_pg',  label: 'FGA',   tooltip: 'Field goal attempts per game.',    format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'optional'  },
  { key: 'fg3a_pg', label: '3PA',   tooltip: '3-point attempts per game.',       format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'optional'  },
  { key: 'fta_pg',  label: 'FTA',   tooltip: 'Free throw attempts per game.',    format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'optional'  },
  { key: 'ftm_pg',  label: 'FTM',   tooltip: 'Free throw makes per game.',       format: 'number1', better: 'neutral', showRank: false, heatmap: false, tier: 'optional'  },
  { key: 'fg_pct',  label: 'FG%',   tooltip: 'Field goal percentage.',           format: 'pct4',    better: 'higher',  showRank: false, heatmap: true,  tier: 'secondary' },
  { key: 'fg3_pct', label: '3P%',   tooltip: '3-point field goal percentage.',   format: 'pct4',    better: 'higher',  showRank: false, heatmap: true,  tier: 'secondary' },
  { key: 'ft_pct',  label: 'FT%',   tooltip: 'Free throw percentage.',           format: 'pct4',    better: 'higher',  showRank: false, heatmap: true,  tier: 'secondary' },
  { key: 'efg_pct', label: 'eFG%',  tooltip: 'Effective FG% = (FGM + 0.5×FG3M) / FGA. Adjusts for 3-pointers being worth more.', format: 'pct4', better: 'higher', showRank: false, heatmap: true,  tier: 'primary'   },
  { key: 'ts_pct',  label: 'TS%',   tooltip: 'True Shooting% = PTS / (2 × (FGA + 0.44 × FTA)). Most complete single shooting efficiency stat.', format: 'pct4', better: 'higher', showRank: true, heatmap: true, tier: 'primary' },
  { key: 'ast_to',  label: 'AST/TO', tooltip: 'Assist-to-turnover ratio. Higher is better.', format: 'number2', better: 'higher', showRank: false, heatmap: true, tier: 'primary' },
];

// ─── NCAA Impact (on-court raw from PBP) ─────────────────────────────────────

export const NCAA_IMPACT_METRICS: PlayerMetricMeta[] = [
  // ── BPR (Bayesian Performance Rating) ──────────────────────────────────────
  {
    key: 'bpr',    label: 'BPR',    group: 'BPR',
    tooltip: 'Bayesian Performance Rating = OBPR + DBPR. Prior-informed RAPM estimate of total impact in pts/100 poss above average D1 player.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'obpr',   label: 'OBPR',   group: 'BPR',
    tooltip: 'Offensive BPR — estimated pts/100 poss added when the player is on offense, relative to an average D1 player.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'dbpr',   label: 'DBPR',   group: 'BPR',
    tooltip: 'Defensive BPR — estimated pts/100 poss prevented when the player is on defense, relative to an average D1 player. Higher = better defender.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'box_bpr',  label: 'Box BPR',  group: 'BPR',
    tooltip: 'Box-score-only BPR estimate (no lineup data required). Trained to predict RAPM from per-100-poss box stats.',
    format: 'number2', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'box_obpr', label: 'Box OBPR', group: 'BPR',
    tooltip: 'Offensive Box BPR (box-score model only).',
    format: 'number2', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'box_dbpr', label: 'Box DBPR', group: 'BPR',
    tooltip: 'Defensive Box BPR (box-score model only).',
    format: 'number2', better: 'higher', showRank: false, heatmap: true,
  },
  // ── MPIR (legacy) ────────────────────────────────────────────────────────────
  {
    key: 'mpir',   label: 'MPIR',   group: 'Macfax Impact',
    tooltip: 'Macfax Player Impact Rating = O-MPIR + D-MPIR. Blends on-court efficiency with box-score prior weighted by minutes played.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'o_mpir', label: 'O-MPIR', group: 'Macfax Impact',
    tooltip: 'Offensive MPIR — blend of on-court offensive impact (ORtg vs league avg) and box-score scoring prior, weighted by minutes.',
    format: 'number2', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'd_mpir', label: 'D-MPIR', group: 'Macfax Impact',
    tooltip: 'Defensive MPIR — blend of on-court defensive impact (DRtg vs league avg) and box-score defensive prior (stl+blk), weighted by minutes.',
    format: 'number2', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_ortg',  label: 'On-Ct ORtg', group: 'On-Court Ratings',
    tooltip: 'Team points scored per 40 minutes with player on court (raw, from PBP).',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'on_court_drtg',  label: 'On-Ct DRtg', group: 'On-Court Ratings',
    tooltip: 'Team points allowed per 40 minutes with player on court (raw, from PBP).',
    format: 'number1', better: 'lower', showRank: true, heatmap: true,
  },
  {
    key: 'on_court_net',   label: 'On-Ct Net', group: 'On-Court Ratings',
    tooltip: 'On-court net rating per 40 minutes (ORtg − DRtg). Positive = net positive impact.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'on_court_pts_pg', label: 'Pts On-Ct/G', group: 'Per-Game',
    tooltip: 'Average team points scored per game while this player is on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_def_pg', label: 'Def On-Ct/G', group: 'Per-Game',
    tooltip: 'Average opponent points per game while this player is on court.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_net_pg', label: 'Net On-Ct/G', group: 'Per-Game',
    tooltip: 'Average net points per game while this player is on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_secs_pg', label: 'Min On-Ct', group: 'Playing Time',
    tooltip: 'Average minutes on court per game (converted from seconds in PBP data).',
    format: 'number1', better: 'neutral', showRank: false, heatmap: false,
  },
  // ── Possession count + adjusted lineup context ──────────────────────────────
  {
    key: 'off_poss', label: 'Poss', group: 'Lineup Context',
    tooltip: 'Offensive possessions played during the season (from PBP lineup segments). Used for BPR qualification threshold.',
    format: 'int', better: 'neutral', showRank: false, heatmap: false,
  },
  {
    key: 'adj_team_off_eff_on', label: 'Adj Off Eff', group: 'Lineup Context',
    tooltip: 'Adjusted team offensive efficiency (pts/100 poss) while this player is on court. Adjusted for opponent strength.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'adj_team_def_eff_on', label: 'Adj Def Eff', group: 'Lineup Context',
    tooltip: 'Adjusted team defensive efficiency (pts/100 poss allowed) while this player is on court. Lower is better.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true,
  },
];

// ─── NCAA On-Court Four Factors ───────────────────────────────────────────────

export const NCAA_FF_METRICS: PlayerMetricMeta[] = [
  {
    key: 'four_factor_impact_index', label: 'FFII',  group: 'Four Factor Impact',
    tooltip: 'Four Factor Impact Index (0-100). RAPM-based: estimates how much this player individually moves each Four Factor, adjusted for teammates and opponents. Higher = better.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  // ── RAPM-based impact components (positive-good) ─
  {
    key: 'off_efg_impact', label: 'Off eFG', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on team eFG% when on offense vs average (percentage points). Positive = boosts team eFG.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'def_efg_impact', label: 'Def eFG', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on opponent eFG% when on defense vs average (pp, positive-good). Positive = reduces opp eFG.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'off_tov_impact', label: 'Off TOV', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on team TOV% when on offense vs average (pp, positive-good). Positive = fewer turnovers.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'def_tov_impact', label: 'Def TOV', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on opponent TOV% when on defense vs average (pp). Positive = forces more turnovers.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'off_orb_impact', label: 'Off ORB', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on team ORB% when on offense vs average (pp). Positive = better offensive rebounding.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'def_reb_impact', label: 'Def REB', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on opponent ORB% when on defense vs average (pp, positive-good). Positive = limits opp offensive rebounding.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'off_ftr_impact', label: 'Off FTR', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on team FTR when on offense vs average (pp). Positive = draws more fouls.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'def_ftr_impact', label: 'Def FTR', group: 'Factor Impact',
    tooltip: 'Player\'s estimated effect on opponent FTR when on defense vs average (pp, positive-good). Positive = limits opponent free throws.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  // ── Combined two-way margins ─
  {
    key: 'efg_impact_margin', label: 'eFG Margin', group: 'Impact Margins',
    tooltip: 'Two-way eFG impact: off_efg_impact + def_efg_impact.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'tov_impact_margin', label: 'TOV Margin', group: 'Impact Margins',
    tooltip: 'Two-way TOV impact: off_tov_impact + def_tov_impact.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'reb_impact_margin', label: 'REB Margin', group: 'Impact Margins',
    tooltip: 'Two-way rebounding impact: off_orb_impact + def_reb_impact.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'ftr_impact_margin', label: 'FTR Margin', group: 'Impact Margins',
    tooltip: 'Two-way FTR impact: off_ftr_impact + def_ftr_impact.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true,
  },
  // ── Old on-court lineup environment (kept for context) ─
  {
    key: 'on_court_ffi',        label: 'On-Ct FFI',   group: 'Lineup Environment',
    tooltip: 'On-court Four Factor Index (0-100). Measures team Four Factor profile while this player is on court — reflects lineup environment, not individual player impact.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  // ── Offensive Four Factors ─
  {
    key: 'on_court_efg_pct',    label: 'On-Ct eFG%',  group: 'On-Court Offense',
    tooltip: 'Team effective FG% = (FGM + 0.5×FG3M) / FGA while player is on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_tov_pct',    label: 'On-Ct TOV%',  group: 'On-Court Offense',
    tooltip: 'Team turnover rate = TOV / (FGA + 0.44×FTA + TOV) × 100 while player is on court. Lower is better.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_orb_pct',    label: 'On-Ct ORB%',  group: 'On-Court Offense',
    tooltip: 'Team offensive rebounding% = OREB / (OREB + opp DREB) × 100 while player is on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_ftr',        label: 'On-Ct FTR',   group: 'On-Court Offense',
    tooltip: 'Team free throw rate = FTA / FGA × 100 while player is on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  // ── Defensive Four Factors ─
  {
    key: 'on_court_opp_efg_pct', label: 'Opp eFG%',  group: 'On-Court Defense',
    tooltip: 'Opponent effective FG% while player is on court. Lower is better.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_opp_tov_pct', label: 'Opp TOV%',  group: 'On-Court Defense',
    tooltip: 'Opponent turnover rate while player is on court. Higher is better (forcing turnovers).',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_drb_pct',     label: 'On-Ct DRB%', group: 'On-Court Defense',
    tooltip: 'Team defensive rebounding% = 100 - opp ORB% while player is on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true,
  },
  {
    key: 'on_court_opp_ftr',     label: 'Opp FTR',    group: 'On-Court Defense',
    tooltip: 'Opponent free throw rate while player is on court. Lower is better.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true,
  },
  // ── Margins ─
  {
    key: 'on_court_efg_margin',  label: 'eFG Margin',  group: 'Margins',
    tooltip: 'Team eFG% minus opponent eFG% while player is on court. Positive = team advantage.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'on_court_tov_edge',    label: 'TOV Edge',    group: 'Margins',
    tooltip: 'Opp TOV% minus team TOV% while player is on court. Positive = team advantage (fewer turnovers, more forced).',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'on_court_reb_edge',    label: 'Reb Edge',    group: 'Margins',
    tooltip: 'Team ORB% minus opp ORB% while player is on court. Positive = team rebounding advantage.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
  {
    key: 'on_court_ftr_margin',  label: 'FTR Margin',  group: 'Margins',
    tooltip: 'Team FTR minus opp FTR while player is on court. Positive = team gets to the line more.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true,
  },
];

// ─── NBA Impact ───────────────────────────────────────────────────────────────

export const NBA_ADVANCED_METRICS: PlayerMetricMeta[] = [
  { key: 'ts_pct',   label: 'TS%',    tooltip: 'True Shooting%.',                       format: 'pct4',    better: 'higher', showRank: true,  heatmap: true,  tier: 'primary'  },
  { key: 'efg_pct',  label: 'eFG%',   tooltip: 'Effective Field Goal%.',                format: 'pct4',    better: 'higher', showRank: false, heatmap: true,  tier: 'primary'  },
  { key: 'usg_pct',  label: 'USG%',   tooltip: 'Usage rate — share of team possessions used by this player.', format: 'pct4', better: 'neutral', showRank: false, heatmap: false, tier: 'primary' },
  { key: 'oreb_pct', label: 'ORB%',   tooltip: 'Offensive rebound rate while on court.', format: 'pct4',   better: 'higher', showRank: false, heatmap: true,  tier: 'primary'  },
  { key: 'dreb_pct', label: 'DRB%',   tooltip: 'Defensive rebound rate while on court.', format: 'pct4',  better: 'higher', showRank: false, heatmap: true,  tier: 'primary'  },
  { key: 'ast_pct',  label: 'AST%',   tooltip: 'Assist rate — % of team FGM assisted while on court.', format: 'pct4', better: 'higher', showRank: false, heatmap: true,  tier: 'primary' },
  { key: 'tov_pct',  label: 'TOV%',   tooltip: 'Turnover rate per 100 plays.',           format: 'pct4',   better: 'lower',  showRank: false, heatmap: true,  tier: 'primary'  },
  { key: 'ast_to',   label: 'AST/TO', tooltip: 'Assist-to-turnover ratio.',              format: 'number2', better: 'higher', showRank: false, heatmap: true,  tier: 'primary' },
  { key: 'pie',      label: 'PIE',    tooltip: 'Player Impact Estimate — share of positive game events contributed.', format: 'pct4', better: 'higher', showRank: true, heatmap: true, tier: 'primary' },
  { key: 'stl_pct',  label: 'STL%',   tooltip: 'Steal rate while on court.',             format: 'pct4',   better: 'higher', showRank: false, heatmap: false, tier: 'optional' },
  { key: 'blk_pct',  label: 'BLK%',   tooltip: 'Block rate — % of opponent 2PA blocked while on court.', format: 'pct4', better: 'higher', showRank: false, heatmap: false, tier: 'optional' },
];

export const NBA_IMPACT_METRICS: PlayerMetricMeta[] = [
  // ── BPR (prior-informed RAPM — primary displayed rating) ─────────────────────
  {
    key: 'bpr',   label: 'BPR',   group: 'BPR',
    tooltip: 'Bayesian Performance Rating (OBPR + DBPR). Career-stabilized box stats regularized toward single-season RAPM. Context-adjusted impact in pts/100 poss above league average — reflects role and team quality, not pure skill in isolation.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true, tier: 'primary',
  },
  {
    key: 'obpr',  label: 'OBPR',  group: 'BPR',
    tooltip: 'Offensive BPR — estimated offensive pts/100 poss added above league average.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true, tier: 'primary',
  },
  {
    key: 'dbpr',  label: 'DBPR',  group: 'BPR',
    tooltip: 'Defensive BPR — estimated defensive pts/100 poss prevented above league average. Higher = better defender.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true, tier: 'primary',
  },
  // ── Box BPR (intermediate — available but not primary) ────────────────────────
  {
    key: 'box_bpr',   label: 'Box BPR',   group: 'Box BPR',
    tooltip: 'Box-score-only BPR — Ridge regression on per-100-poss box stats. Intermediate signal used as prior for final BPR.',
    format: 'number2', better: 'higher', showRank: false, heatmap: false, tier: 'optional',
  },
  {
    key: 'box_obpr',  label: 'Box OBPR',  group: 'Box BPR',
    tooltip: 'Offensive Box BPR (box-score model only).',
    format: 'number2', better: 'higher', showRank: false, heatmap: false, tier: 'optional',
  },
  {
    key: 'box_dbpr',  label: 'Box DBPR',  group: 'Box BPR',
    tooltip: 'Defensive Box BPR (box-score model only).',
    format: 'number2', better: 'higher', showRank: false, heatmap: false, tier: 'optional',
  },
  // ── MPIR ─────────────────────────────────────────────────────────────────────
  {
    key: 'mpir',          label: 'MPIR',      group: 'Macfax Impact',
    tooltip: 'Macfax Player Impact Rating (O-MPIR + D-MPIR). Combines box production and on-court team efficiency into a single impact score.',
    format: 'number2', better: 'higher', showRank: true, heatmap: true, tier: 'primary',
  },
  {
    key: 'o_mpir',        label: 'O-MPIR',    group: 'Macfax Impact',
    tooltip: 'Offensive MPIR — blend of on-court offensive impact and box-score offensive prior.',
    format: 'number2', better: 'higher', showRank: false, heatmap: true, tier: 'primary',
  },
  {
    key: 'd_mpir',        label: 'D-MPIR',    group: 'Macfax Impact',
    tooltip: 'Defensive MPIR — blend of on-court defensive impact and box-score defensive prior.',
    format: 'number2', better: 'higher', showRank: false, heatmap: true, tier: 'primary',
  },
  {
    key: 'on_court_adj_o', label: 'On-Ct Adj O', group: 'Adj On-Court',
    tooltip: 'Bayesian-stabilised adjusted offensive efficiency with player on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true, tier: 'secondary',
  },
  {
    key: 'on_court_adj_d', label: 'On-Ct Adj D', group: 'Adj On-Court',
    tooltip: 'Bayesian-stabilised adjusted defensive efficiency with player on court.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true, tier: 'secondary',
  },
  {
    key: 'on_court_adj_em', label: 'On-Ct Adj EM', group: 'Adj On-Court',
    tooltip: 'On-court adjusted net efficiency (Adj O – Adj D) with player on court.',
    format: 'number1', better: 'higher', showRank: true, heatmap: true, tier: 'secondary',
  },
  {
    key: 'on_court_ortg',  label: 'Raw ORtg',   group: 'Raw On-Court',
    tooltip: 'Raw team offensive rating (pts per 100 poss) with player on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true, tier: 'optional',
  },
  {
    key: 'on_court_drtg',  label: 'Raw DRtg',   group: 'Raw On-Court',
    tooltip: 'Raw team defensive rating (pts allowed per 100 poss) with player on court.',
    format: 'number1', better: 'lower', showRank: false, heatmap: true, tier: 'optional',
  },
  {
    key: 'on_court_net',   label: 'Raw Net',     group: 'Raw On-Court',
    tooltip: 'Raw on-court net rating (ORtg − DRtg) with player on court.',
    format: 'number1', better: 'higher', showRank: false, heatmap: true, tier: 'optional',
  },
  {
    key: 'on_court_poss',  label: 'Poss',        group: 'Playing Time',
    tooltip: 'Estimated possessions played on court this season.',
    format: 'int', better: 'neutral', showRank: false, heatmap: false, tier: 'primary',
  },
];

// ─── Lookup helpers ───────────────────────────────────────────────────────────

export const PLAYER_METRIC_LOOKUP: Record<string, PlayerMetricMeta> = Object.fromEntries(
  [
    ...PLAYER_TRADITIONAL_METRICS,
    ...NCAA_IMPACT_METRICS,
    ...NBA_ADVANCED_METRICS,
    ...NBA_IMPACT_METRICS,
  ].map((m) => [m.key, m])
);

/**
 * Format a raw numeric value according to PlayerMetricFormat.
 *   pct4     — value in [0,1] → "45.6%"
 *   pct_raw  — value already in pct-points → "45.6%"
 *   number1  — "12.3"
 *   number2  — "12.34"
 *   int      — "12"
 */
export function formatPlayerMetric(value: number | null | undefined, format: PlayerMetricFormat): string {
  if (value == null) return '—';
  switch (format) {
    case 'pct4':    return `${(value * 100).toFixed(1)}%`;
    case 'pct_raw': return `${value.toFixed(1)}%`;
    case 'number1': return value.toFixed(1);
    case 'number2': return value.toFixed(2);
    case 'int':     return Math.round(value).toString();
  }
}

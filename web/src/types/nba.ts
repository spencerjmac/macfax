/**
 * NBA TypeScript types — macfax NBA app
 *
 * These are NBA-specific and intentionally separate from the NCAA types in types/index.ts.
 */

import type { ChecklistItem } from '@/types';

// ─────────────────────────────────────────────────────────────────────────────
// Domain models
// ─────────────────────────────────────────────────────────────────────────────

export interface NBASeasonInfo {
  id: number;
  year: number;
  display_name: string;
  is_current: boolean;
}

export interface NBATeam {
  id: number;
  nba_team_id: number;
  slug: string;
  name: string;
  abbreviation: string;
  city: string;
  conference: 'East' | 'West';
  division: string;
  logo_url: string | null;
}

export interface NBAGame {
  id: number;
  game_id: string;
  date: string;
  season_type: string;
  competition: string;
  counts_toward_regular_season: boolean;
  status: string;
  home_team: number;
  home_team_abbr: string;
  home_team_slug: string;
  home_score: number | null;
  away_team: number;
  away_team_abbr: string;
  away_team_slug: string;
  away_score: number | null;
  rest_days_home: number | null;
  rest_days_away: number | null;
  home_b2b: boolean;
  away_b2b: boolean;
  box_score_synced: boolean;
}

export interface NBATeamGameStats {
  id: number;
  game: number;
  team: number;
  team_name: string;
  team_abbreviation: string;
  is_home: boolean;
  pts: number | null;
  opp_pts: number | null;
  fgm: number | null;
  fga: number | null;
  fg3m: number | null;
  fg3a: number | null;
  ftm: number | null;
  fta: number | null;
  oreb: number | null;
  dreb: number | null;
  tov: number | null;
  poss: number | null;
  raw_ortg: number | null;
  raw_drtg: number | null;
  adj_ortg: number | null;
  adj_drtg: number | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Season-level ratings — the main ranking model
// ─────────────────────────────────────────────────────────────────────────────

export interface NBATeamSeasonRatings {
  id: number;
  team: number;
  team_name: string;
  team_slug: string;
  team_abbreviation: string;
  team_logo_url: string | null;
  team_conference: string;
  season: number;
  season_display: string;

  games: number;

  // Adjusted efficiency
  adj_off: number | null;
  adj_def: number | null;
  adj_net: number | null;
  pace: number | null;

  // Four Factors (raw season averages)
  efg_pct: number | null;
  opp_efg_pct: number | null;
  tov_rate: number | null;
  opp_tov_rate: number | null;
  oreb_pct: number | null;
  opp_oreb_pct: number | null;
  fta_rate: number | null;
  opp_fta_rate: number | null;

  // Four Factor margins (offense advantage)
  efg_margin: number | null;
  tov_edge: number | null;
  oreb_edge: number | null;
  fta_margin: number | null;

  // FFI (PROVISIONAL — see ratings_config.py)
  ffi: number | null;

  // Derived ranks (presentation only, not source of truth)
  rank_adj_net: number | null;
  rank_ffi: number | null;

  updated_at: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Efficiency Landscape
// ─────────────────────────────────────────────────────────────────────────────

export interface NBALandscapeTeam {
  team_name: string;
  team_slug: string;
  team_abbreviation: string;
  conference: 'East' | 'West';
  logo_url: string | null;
  o_rate: number;
  d_rate: number;
  net: number;
  rank: number | null;
  record: string;
  playoff_finish: string | null;
}

export interface NBALandscapeData {
  season: number;
  season_display: string;
  max_net: number;
  tier_lines: {
    champion_net: number;
    contender_net: number;
    playoff_net: number;
  };
  teams: NBALandscapeTeam[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Crystal Ball
// ─────────────────────────────────────────────────────────────────────────────

export interface NBACrystalBallTeam {
  team_name: string;
  team_slug: string;
  team_logo: string | null;
  conference: 'East' | 'West';
  record: string;
  rank: number | null;
  adj_net: number;
  adj_off: number;
  adj_def: number;
  conference_seed: number | null;
  playoff_finish: string | null;
  checklist: {
    passedCount: number;
    totalCount: number;
    score: number;
    items: ChecklistItem[];
  };
}

export interface NBACrystalBallData {
  season: number;
  season_display: string;
  total_teams: number;
  teams: NBACrystalBallTeam[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Luck Chart
// ─────────────────────────────────────────────────────────────────────────────

export interface NBALuckChartTeam {
  team_name: string;
  team_slug: string;
  team_abbreviation: string;
  conference: 'East' | 'West';
  logo_url: string | null;
  net_rating: number;
  ortg: number;
  drtg: number;
  actual_wins: number;
  actual_losses: number;
  games_played: number;
  expected_wins: number;
  wins_above_expected: number;
  quadrant: 'hot' | 'overachieving' | 'hidden_value' | 'struggling';
}

export interface NBALuckChartData {
  season: number;
  season_display: string;
  league_avg_net_rating: number;
  teams: NBALuckChartTeam[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Player
// ─────────────────────────────────────────────────────────────────────────────

export interface NBAPlayer {
  id: number;
  player_id: number;
  name: string;
  is_active: boolean;
  current_team: number | null;
  current_team_name: string | null;
  current_team_slug: string | null;
  // Career-level BPR aggregates (written by nba_compute_career_bpr)
  peak_bpr: number | null;
  career_bpr: number | null;
}

export interface TeamRosterValueResponse {
  team: string;
  team_slug: string;
  season: number;
  season_display: string;
  team_wins_added_total: number;
  players: NBAPlayerSeasonStats[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Health endpoint
// ─────────────────────────────────────────────────────────────────────────────

export interface NBAHealthData {
  status: string;
  phase: string;
  counts: {
    seasons: number;
    teams: number;
    games: number;
    games_with_box_scores: number;
    team_season_ratings: number;
    players: number;
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Team detail page
// ─────────────────────────────────────────────────────────────────────────────

export interface NBATeamDetailResponse {
  team: NBATeam;
  season: NBASeasonInfo | null;
  ratings: NBATeamSeasonRatings | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Model Calibration (Phase 3)
// ─────────────────────────────────────────────────────────────────────────────

export interface NBAModelCalibration {
  id: number;
  season: number;
  season_display: string;
  season_year: number;
  computed_at: string;

  // Analysis 1 — prediction accuracy
  games_predicted: number | null;
  correct_predictions: number | null;
  straight_up_accuracy: number | null;
  brier_score: number | null;
  log_loss: number | null;

  // Analysis 2+3 — HCA + B2B via OLS
  ols_games: number | null;
  ols_r_squared: number | null;
  empirical_hca: number | null;
  configured_hca: number | null;
  ols_model_scale: number | null;
  empirical_home_b2b_penalty: number | null;
  empirical_away_b2b_penalty: number | null;
  configured_b2b_penalty: number | null;

  // Analysis 4 — FFI weight regression
  ffi_teams_used: number | null;
  ffi_adj_net_r_squared: number | null;
  ffi_proposed_weight_efg: number | null;
  ffi_proposed_weight_tov: number | null;
  ffi_proposed_weight_oreb: number | null;
  ffi_proposed_weight_fta: number | null;
  ffi_current_weight_efg: number | null;
  ffi_current_weight_tov: number | null;
  ffi_current_weight_oreb: number | null;
  ffi_current_weight_fta: number | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Matchup
// ─────────────────────────────────────────────────────────────────────────────

export interface NBAMatchupTeam {
  id: number;
  name: string;
  slug: string;
  logo_url: string | null;
  conference: 'East' | 'West';
  division: string;
  rank: number | null;
  record: string;
  adj_em: number;
  adj_o: number;
  adj_d: number;
  adj_tempo: number;
  ffi: number;
}

export interface NBAMatchupForecast {
  pace: number;
  pts_a_neutral: number;
  pts_b_neutral: number;
  pts_a: number;
  pts_b: number;
  margin: number;
  spread: number;
  spread_team: 'a' | 'b';
  total: number;
  prob_a: number;
  prob_b: number;
  // Score projection range: margin ± prediction_sigma (game outcome spread in raw points)
  margin_low: number;
  margin_high: number;
  // Model confidence band: prob if spread estimate is off by ±1.5 pts (NOT game variance)
  prob_a_low: number;
  prob_a_high: number;
}

export interface NBAFourFactorEdges {
  efg_edge: number;
  tov_edge: number;
  orb_edge: number;
  ftr_edge: number;
  exp_efg_a: number;
  exp_efg_b: number;
  exp_tov_a: number;
  exp_tov_b: number;
  exp_orb_a: number;
  exp_orb_b: number;
  exp_ftr_a: number;
  exp_ftr_b: number;
}

export interface NBAShotProfile {
  fg3_rate_edge: number;
  fg3_pct_edge: number;
  fg2_pct_edge: number;
  fg3_rate_a: number;
  fg3_rate_b: number;
  fg3_pct_a: number;
  fg3_pct_b: number;
  fg2_pct_a: number;
  fg2_pct_b: number;
}

export interface NBAVolatility {
  volatility_score: number;
  pace_component: number;
  three_pt_component: number;
  variance_component: number;
  reasons: string[];
  upset_warning: string | null;
}

export interface NBARecentGame {
  date: string;
  opponent: string;
  result: 'W' | 'L';
  score: string;
  margin: number;
}

export interface NBARecentForm {
  games_analyzed: number;
  record: string;
  avg_margin: number;
  variance: number;
  games: NBARecentGame[];
}

export interface NBAMatchupMetadata {
  hca_points: number;
  prediction_sigma: number;
  nat_avg_ortg: number;
  coefficients: {
    efg: number | null;
    tov: number | null;
    orb: number | null;
    ftr: number | null;
    r_squared: number | null;
  };
}

export interface NBASeriesGame {
  game: number;
  site: 'home' | 'away';
  label: string;
}

export interface NBASeriesPrediction {
  prob_a_series: number;
  prob_b_series: number;
  prob_sweep_a: number;
  prob_a_in_5: number;
  prob_a_in_6: number;
  prob_a_in_7: number;
  prob_sweep_b: number;
  prob_b_in_5: number;
  prob_b_in_6: number;
  prob_b_in_7: number;
  series_home: 'a' | 'b';
  game_schedule: NBASeriesGame[];
}

export interface NBAMatchupResult {
  season: string;
  site: 'neutral' | 'home' | 'away';
  mode: 'game' | 'series';
  teamA: NBAMatchupTeam;
  teamB: NBAMatchupTeam;
  forecast: NBAMatchupForecast;
  four_factor_edges: NBAFourFactorEdges;
  ffi_edge: number;
  points_breakdown: {
    pts_from_efg: number;
    pts_from_tov: number;
    pts_from_orb: number;
    pts_from_ftr: number;
    baseline: number;
    total_margin: number;
  } | null;
  top_drivers: Array<{
    factor: string;
    edge: number;
    points: number;
    team: 'a' | 'b';
  }> | null;
  shot_profile: NBAShotProfile | null;
  volatility: NBAVolatility;
  recent_form_a: NBARecentForm;
  recent_form_b: NBARecentForm;
  series_prediction: NBASeriesPrediction | null;
  metadata: NBAMatchupMetadata;
}

export interface NBATeamColors {
  primary: string;
  secondary: string;
}

export interface NBAPlayerSeasonStats {
  id: number;
  player: number;
  player_id: number;
  player_name: string;
  team: number | null;
  team_name: string | null;
  team_slug: string | null;
  season: number;
  season_display: string;
  // Traditional
  gp: number;
  mpg: number | null;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  stl: number | null;
  blk: number | null;
  tov: number | null;
  plus_minus: number | null;
  fg_pct: number | null;
  fg3_pct: number | null;
  ft_pct: number | null;
  fga_pg: number | null;
  fg3a_pg: number | null;
  oreb_pg: number | null;
  dreb_pg: number | null;
  fta_pg: number | null;
  ftm_pg: number | null;
  // Advanced efficiency
  efg_pct: number | null;
  ts_pct: number | null;
  usg_pct: number | null;
  oreb_pct: number | null;
  dreb_pct: number | null;
  ast_pct: number | null;
  tov_pct: number | null;
  ast_to: number | null;
  pie: number | null;
  // On-court raw ratings
  on_court_ortg: number | null;
  on_court_drtg: number | null;
  on_court_net: number | null;
  on_court_poss: number | null;
  // Bayesian-stabilised on-court
  on_court_adj_o: number | null;
  on_court_adj_d: number | null;
  on_court_adj_em: number | null;
  // MPIR
  mpir: number | null;
  o_mpir: number | null;
  d_mpir: number | null;
  // Defense rates
  stl_pct: number | null;
  blk_pct: number | null;
  // Final BPR (prior-informed RAPM — displayed)
  obpr: number | null;
  dbpr: number | null;
  bpr: number | null;
  // Replacement-adjusted BPR — 0 = replacement level, computed at API time, never stored
  bpr_replacement_adjusted: number | null;
  obpr_replacement_adjusted: number | null;
  dbpr_replacement_adjusted: number | null;
  // Wins above replacement player — derived at compute time
  wins_added: number | null;
  // Box BPR (intermediate)
  box_obpr: number | null;
  box_dbpr: number | null;
  box_bpr: number | null;
  // Baseline RAPM
  baseline_obpr: number | null;
  baseline_dbpr: number | null;
  nba_archetype: string | null;
  bpr_last_updated: string | null;
  updated_at: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Season Outlook types
// ─────────────────────────────────────────────────────────────────────────────

export type OutlookTier =
  | 'title_contender'
  | 'playoff_contender'
  | 'bubble'
  | 'lottery'
  | 'rebuilding';

export interface TeamOutseasonMove {
  id: number;
  move_type: 'signed' | 'lost' | 'drafted' | 'traded_in' | 'traded_out' | 'extended' | 'waived';
  player_name: string;
  detail: string;
  impact_rating: 'high' | 'medium' | 'low';
}

export interface ProjectedStarter {
  id: number;
  position: string;
  player_name: string;
  position_order: number;
  role_note: string;
  bpr_rating: number | null;
  key_question: string;
}

export interface TeamSeasonOutlookSummary {
  team_name: string;
  team_abbr: string;
  team_slug: string;
  conference: 'East' | 'West';
  primary_color: string;
  secondary_color: string;
  logo_url: string | null;
  wins: number | null;
  losses: number | null;
  adj_offensive_rating: number | null;
  adj_defensive_rating: number | null;
  adj_net_rating: number | null;
  ffi: number | null;
  outlook_tier: OutlookTier | null;
  projected_wins: number | null;
  season_headline: string;
  league_rank: number;
}

export interface TeamSeasonOutlookDetail extends TeamSeasonOutlookSummary {
  projected_losses: number | null;
  projected_adj_net: number | null;
  pace: number | null;
  efg_pct: number | null;
  opp_efg_pct: number | null;
  tov_pct: number | null;
  opp_tov_pct: number | null;
  oreb_pct: number | null;
  opp_oreb_pct: number | null;
  fta_rate: number | null;
  opp_fta_rate: number | null;
  macfax_take: string;
  development_spotlight_player: string;
  development_spotlight_text: string;
  season_defining_variable: string;
  offseason_moves: TeamOutseasonMove[];
  projected_starters: ProjectedStarter[];
}

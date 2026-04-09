/**
 * NBA TypeScript types — macfax NBA app
 *
 * These are NBA-specific and intentionally separate from the NCAA types in types/index.ts.
 */

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
  updated_at: string;
}

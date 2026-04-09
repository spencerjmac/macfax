// Core data types for the application

export interface Team {
  id: number;
  slug: string;
  name: string;
  aliases: string[];
  logo_url: string | null;
}

export interface TeamSeason {
  // Identity
  teamId: string;
  teamName: string;
  teamNameAlt: string[];
  conference: string;
  logoUrl: string;
  
  // Season Context
  season: string;
  lastUpdated: string;
  games: number;
  record: string;
  
  // Core Ratings
  rank: number;
  adjEM: number;
  adjO: number;
  adjD: number;
  adjTempo: number;
  
  // Four Factors - Offense
  eFG: number;
  tov: number;
  orb: number;
  ftr: number;
  
  // Four Factors - Defense
  eFG_d: number;
  tov_d: number;
  drb: number;
  ftr_d: number;
  
  // Four Factors - Margins (derived)
  eFG_margin: number;
  tov_edge: number;
  reb_edge: number;
  ftr_margin: number;
  
  // Raw Four Factors - Offense
  raw_eFG: number | null;
  raw_tov: number | null;
  raw_orb: number | null;
  raw_ftr: number | null;
  
  // Raw Four Factors - Defense
  raw_eFG_d: number | null;
  raw_tov_d: number | null;
  raw_orb_d: number | null;
  raw_drb: number | null;
  raw_ftr_d: number | null;
  
  // Raw Four Factors - Margins
  raw_eFG_margin: number | null;
  raw_tov_edge: number | null;
  raw_reb_edge: number | null;
  raw_ftr_margin: number | null;
  
  // Four Factor Index
  four_factor_index_100: number | null;
  raw_four_factor_index_100: number | null;
  rank_four_factor_index_100: number | null;
  
  // Shooting Splits
  fg2_pct: number | null;
  fg2_pct_d: number | null;
  fg3_pct: number | null;
  fg3_pct_d: number | null;
  fg3_rate: number | null;
  fg3_rate_d: number | null;
  ft_pct: number | null;
  
  // Resume Metrics
  wab: number | null;
  sor_rank: number | null;
  net_rank: number | null;
  sos_rank: number | null;
  sos_win_pct: number | null;
  ap_poll_week6: number | null;
  sor: number | null;
  luck: number | null;
  sos_adjEM: number | null;
  ncsos_adjEM: number | null;
  barthag: number | null;

  // NCAA Tournament
  tournament_seed: number | null;
  tournament_region: string | null;
  
  // Source metadata
  sources: {
    kenpom: boolean;
    torvik: boolean;
    cbbAnalytics: boolean;
  };
}

export interface DatasetMetadata {
  lastUpdated: string;
  season: string;
  teamCount: number;
  sources: {
    kenpom: number;
    torvik: number;
    cbbAnalytics: number;
  };
}

export interface TeamsData {
  metadata: DatasetMetadata;
  teams: TeamSeason[];
}

export interface MetricDefinition {
  id: string;
  name: string;
  category: string;
  definition: string;
  formula: string; // LaTeX
  interpretation: string;
  range?: string;
  higherIsBetter: boolean;
}

// Conference types
export interface Conference {
  id: number;
  code: string;
  name: string;
}

export interface SeasonInfo {
  id: number;
  year: number;
  display_name: string;
  is_current: boolean;
}

// Trapezoid types
export interface TrapezoidBoundaries {
  x_left_top: number;
  x_right_top: number;
  x_left_bot: number;
  x_right_bot: number;
  y_top: number;
  y_bot: number;
}

export interface TrapezoidTeam {
  team_id: number;
  team_name: string;
  team_slug: string;
  adj_tempo: number;
  adj_em: number;
  conference: string;
  conference_name: string;
  logo_url: string | null;
  rank: number | null;
  record: string;
  inside_trapezoid: boolean;
}

export interface TrapezoidData {
  meta: {
    season: number;
    season_display: string;
    conference: string;
    top: number;
    total_teams: number;
    quantiles_used: {
      x_left_top: number;
      x_right_top: number;
      x_left_bot: number;
      x_right_bot: number;
      y_top: number;
      y_bot: number;
      method: string;
    };
  };
  trapezoid: TrapezoidBoundaries;
  averages: {
    avg_tempo: number;
    avg_em: number;
  };
  teams: TrapezoidTeam[];
}

// Efficiency Landscape types
export interface EfficiencyLandscapeTeam {
  team_name: string;
  team_slug: string;
  conference: string;
  conference_name: string;
  o_rate: number;
  d_rate: number;
  net: number;
  logo_url: string | null;
  rank: number | null;
  record: string;
}

export interface EfficiencyLandscapeData {
  season: number;
  season_display: string;
  conference: string;
  top: number;
  max_net: number;
  defaults: {
    title_delta: number;
    final4_delta: number;
    hit_miss_delta: number;
  };
  teams: EfficiencyLandscapeTeam[];
}

// ==================== Crystal Ball ====================

export interface ChecklistItem {
  key: string;
  label: string;
  pass: boolean;
  value: string;
  threshold: string;
  details: string;
}

export interface CrystalBallTeam {
  team_name: string;
  team_slug: string;
  team_logo: string | null;
  conference: string;
  record: string;
  rank: number | null;
  adj_em: number;
  adj_o: number;
  adj_d: number;
  tournament_seed: number | null;
  tournament_region: string | null;
  checklist: {
    passedCount: number;
    totalCount: number;
    score: number;
    items: ChecklistItem[];
  };
}

export interface CrystalBallData {
  season: number;
  season_display: string;
  filter: string;
  total_teams: number;
  teams: CrystalBallTeam[];
}

// ==================== Cinderella Index ====================

export interface CinderellaComponents {
  adj_em_pct: number;
  adj_d_pct: number;
  opp_efg_pct: number;
  opp_tov_pct: number;
  tov_avoid_pct: number;
  orb_pct: number;
  fg3_rate_pct: number;
  fg3_pct_pct: number;
  slow_tempo_pct: number;
  wab_pct: number;
  sos_pct: number;
}

export interface CinderellaScore {
  profile_score: number;
  underseeded_strength: number;
  defense_score: number;
  possession_score: number;
  variance_score: number;
  resume_score: number;
  seed_residual: number | null;
  p_sweet16: number | null;
  components: CinderellaComponents;
}

export interface CinderellaTeam {
  team_name: string;
  team_slug: string;
  team_logo: string | null;
  conference: string;
  record: string;
  rank: number | null;
  adj_em: number;
  adj_d: number;
  adj_tempo: number;
  tournament_seed: number | null;
  tournament_region: string | null;
  cinderella: CinderellaScore;
}

export interface CinderellaData {
  season: number;
  season_display: string;
  has_tournament: boolean;
  total_teams: number;
  teams: CinderellaTeam[];
}

// ==================== Bracket Simulator ====================

export interface BracketTeamData {
  team_id: number;
  name: string;
  slug: string;
  logo_url: string | null;
  seed: number;
  region: string;
  adj_em: number;
  record: string;
  is_first_four: boolean;
}

export interface BracketSlot {
  seed: number;
  is_first_four: boolean;
  teams: BracketTeamData[];
}

export interface TeamRoundProbs {
  p_r64: number;     // P(appears in R64) — 1.0 for non-FF teams
  p_r32: number;     // P(advances to R32, i.e., wins R64)
  p_s16: number;     // P(advances to Sweet 16)
  p_e8: number;      // P(advances to Elite 8)
  p_ff: number;      // P(advances to Final Four)
  p_final: number;   // P(appears in Championship game)
  p_champion: number;
}

export interface BracketData {
  season: number;
  season_label: string;
  n_sims: number;
  ff_pairings: [string, string][];
  r64_pods: [number, number][];
  regions: {
    East: BracketSlot[];
    West: BracketSlot[];
    South: BracketSlot[];
    Midwest: BracketSlot[];
  };
  probabilities: Record<string, TeamRoundProbs>;
}

// ==================== Matchup Prediction ====================

export interface MatchupTeam {
  id: number;
  name: string;
  slug: string;
  logo_url: string | null;
  conference: string | null;
  rank: number;
  record: string;
  adj_em: number;
  adj_o: number;
  adj_d: number;
  adj_tempo: number;
  ffi: number;
}

export interface MatchupForecast {
  pace: number;
  pts_a_neutral: number;
  pts_b_neutral: number;
  pts_a: number;
  pts_b: number;
  margin: number;
  spread: number;
  spread_team: string;
  total: number;
  prob_a: number;
  prob_b: number;
  prob_a_low: number;
  prob_a_high: number;
  margin_low: number;
  margin_high: number;
}

export interface FourFactorEdges {
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

export interface PointsBreakdown {
  pts_from_efg: number;
  pts_from_tov: number;
  pts_from_orb: number;
  pts_from_ftr: number;
  baseline: number;
  total_margin: number;
}

export interface TopDriver {
  factor: string;
  edge: number;
  points: number;
  team: string;
}

export interface ShotProfile {
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

export interface Volatility {
  volatility_score: number;
  pace_component: number;
  three_pt_component: number;
  variance_component: number;
  reasons: string[];
}

export interface RecentGame {
  date: string;
  opponent: string;
  result: 'W' | 'L';
  score: string;
  margin: number;
}

export interface RecentForm {
  games_analyzed: number;
  record: string;
  avg_margin: number;
  avg_ortg: number | null;
  variance: number;
  games: RecentGame[];
}

export interface MatchupMetadata {
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

export interface MatchupResult {
  season: string;
  site: 'neutral' | 'home' | 'away';
  teamA: MatchupTeam;
  teamB: MatchupTeam;
  forecast: MatchupForecast;
  four_factor_edges: FourFactorEdges;
  ffi_edge: number;
  points_breakdown: PointsBreakdown | null;
  top_drivers: TopDriver[] | null;
  shot_profile: ShotProfile | null;
  volatility: Volatility;
  recent_form_a: RecentForm;
  recent_form_b: RecentForm;
  metadata: MatchupMetadata;
}

// Viz Builder types
export interface StatMetadata {
  key: string;
  label: string;
  group: string;
  description: string;
  format: string;
  decimals: number;
  higher_is_better: boolean;
}

export interface VizStats {
  groups: {
    [groupName: string]: StatMetadata[];
  };
  count: number;
  season?: string;
}

export interface VizScatterPoint {
  team: string;
  slug: string;
  conference: string;
  logo_url: string | null;
  x: number;
  y: number;
}

export interface VizScatterData {
  season: string;
  x: StatMetadata;
  y: StatMetadata;
  stats: {
    n: number;
    pearson_r: number | null;
    r2: number | null;
    slope: number | null;
    intercept: number | null;
    p_value: number | null;
  };
  points: VizScatterPoint[];
  last_updated: string | null;
}

export interface NCAAPlayerSeasonStats {
  player_name: string;
  player_id: string;
  position: string | null;
  jersey: string | null;
  headshot_url: string | null;
  team_name: string;
  season_display: string;
  // Traditional
  gp: number;
  mpg: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  pf: number;
  fg_pct: number | null;
  fg3_pct: number | null;
  ft_pct: number | null;
  fga_pg: number;
  fg3a_pg: number;
  ftm_pg: number;
  fta_pg: number;
  oreb_pg: number;
  dreb_pg: number;
  efg_pct: number | null;
  ts_pct: number | null;
  ast_to: number | null;
  // On-court impact (from ESPN PBP)
  on_court_secs_pg: number | null;
  on_court_pts_pg: number | null;
  on_court_def_pg: number | null;
  on_court_net_pg: number | null;
  on_court_ortg: number | null;
  on_court_drtg: number | null;
  on_court_net: number | null;
  // On-court Four Factors (Phase D)
  on_court_efg_pct: number | null;
  on_court_tov_pct: number | null;
  on_court_orb_pct: number | null;
  on_court_ftr: number | null;
  on_court_opp_efg_pct: number | null;
  on_court_opp_tov_pct: number | null;
  on_court_drb_pct: number | null;
  on_court_opp_ftr: number | null;
  on_court_efg_margin: number | null;
  on_court_tov_edge: number | null;
  on_court_reb_edge: number | null;
  on_court_ftr_margin: number | null;
  on_court_ffi: number | null;
  o_mpir: number | null;
  d_mpir: number | null;
  mpir: number | null;
  // BPR (Bayesian Performance Rating)
  bpr: number | null;
  obpr: number | null;
  dbpr: number | null;
  box_bpr: number | null;
  box_obpr: number | null;
  box_dbpr: number | null;
  prior_mean_obpr: number | null;
  prior_mean_dbpr: number | null;
  prior_sd_obpr: number | null;
  prior_sd_dbpr: number | null;
  off_poss: number | null;
  def_poss: number | null;
  adj_team_off_eff_on: number | null;
  adj_team_def_eff_on: number | null;
  bpr_model_version: string | null;
}

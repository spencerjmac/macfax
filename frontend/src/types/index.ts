/**
 * TypeScript types for CBB Analytics API
 * These mirror the Django models and API responses
 */

export interface Season {
  id: number;
  year: number;
  display_name: string;
  is_current: boolean;
}

export interface Conference {
  id: number;
  code: string;
  name: string;
}

export interface Team {
  id: number;
  slug: string;
  name: string;
  aliases: string[];
  logo_url: string | null;
}

export interface TeamSeasonStats {
  // Identifiers
  id: number;
  team_name: string;
  team_slug: string;
  team_logo: string | null;
  conference_code: string;
  conference_name: string;
  season_year: number;
  
  // Record
  games: number;
  wins: number;
  losses: number;
  record: string;
  
  // Rankings
  rank: number | null;
  rank_adj_em: number | null;
  rank_adj_o: number | null;
  rank_adj_d: number | null;
  rank_aor: number | null;
  rank_adr: number | null;
  rank_aem: number | null;
  t_rank: number | null;
  ap_poll_week6: number | null;
  
  // Core Metrics
  adj_em: number;
  adj_o: number;
  adj_d: number;
  adj_tempo: number;
  
  // Game-Level Adjusted Ratings (NEW)
  aor: number | null;
  adr: number | null;
  aem: number | null;
  aor_100: number | null;
  adr_100: number | null;
  net_100: number | null;
  
  // Four Factors - Offense
  efg_pct: number;
  tov_pct: number;
  orb_pct: number;
  ftr: number;
  
  // Four Factors - Defense
  efg_pct_d: number;
  tov_pct_d: number;
  drb_pct: number;
  ftr_d: number;
  
  // Margins
  efg_margin: number;
  tov_edge: number;
  reb_edge: number;
  ftr_margin: number;
  
  // Four Factor Index
  efg_margin_z: number | null;
  tov_edge_z: number | null;
  reb_edge_z: number | null;
  ftr_margin_z: number | null;
  four_factor_index_wz: number | null;
  four_factor_index_100: number | null;
  rank_four_factor_index_100: number | null;
  
  // Shooting Splits
  fg2_pct: number | null;
  fg2_pct_d: number | null;
  fg3_pct: number | null;
  fg3_pct_d: number | null;
  fg3_rate: number | null;
  fg3_rate_d: number | null;
  ft_pct: number | null;
  
  // Resume
  wab: number | null;
  sor: number | null;
  barthag: number | null;
  luck: number | null;
  sos_adj_em: number | null;
  ncsos_adj_em: number | null;
  
  // National Champion Checklist
  national_champion_checklist: NationalChampionChecklist | null;
  
  // Provenance
  has_kenpom: boolean;
  has_torvik: boolean;
  has_cbb_analytics: boolean;
  last_updated: string;
}

// ==================== National Champion Checklist ====================

export interface ChecklistItem {
  key: string;
  label: string;
  pass: boolean;
  value: string | number;
  threshold: string;
  details: string;
}

export interface NationalChampionChecklist {
  passedCount: number;
  totalCount: number;
  items: ChecklistItem[];
}

export interface RankingsRow {
  rank: number;
  team_name: string;
  team_slug: string;
  team_logo: string | null;
  conference: string;
  record: string;
  adj_em: number;
  adj_o: number;
  adj_d: number;
  adj_tempo: number;
  // New adjusted rating fields
  aor: number | null;
  adr: number | null;
  aem: number | null;
  aor_100: number | null;
  adr_100: number | null;
  net_100: number | null;
  rank_aor: number | null;
  rank_adr: number | null;
  rank_aem: number | null;
  // Four Factor Index
  four_factor_index_100: number | null;
  rank_four_factor_index_100: number | null;
  efg_pct: number;
  tov_pct: number;
  orb_pct: number;
  ftr: number;
  efg_pct_d: number;
  tov_pct_d: number;
  drb_pct: number;
  ftr_d: number;
}

export interface TeamProfile {
  team: Team;
  current_season_stats: TeamSeasonStats | null;
  seasons: TeamSeasonStats[];
}

export interface MatchupEdges {
  efficiency: number;
  offensive: number;
  defensive: number;
  tempo: number;
  efg: number;
  tov: number;
  reb: number;
  ftr: number;
}

export interface MatchupResult {
  teamA: TeamSeasonStats;
  teamB: TeamSeasonStats;
  matchup: {
    site: 'neutral' | 'home' | 'away';
    win_probability_a: number;
    win_probability_b: number;
    predicted_margin: number;
    edges: MatchupEdges;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ==================== Trapezoid of Excellence ====================

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

// ==================== Efficiency Landscape ====================

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

// ==================== Viz Builder ====================

export interface StatMetadata {
  key: string;
  label: string;
  group: string;
  description: string;
  format: string;
  decimals: number;
  higher_is_better?: boolean;
}

export interface VizStats {
  groups: Record<string, StatMetadata[]>;
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

export interface VizScatterStats {
  n: number;
  pearson_r: number | null;
  r2: number | null;
  slope: number | null;
  intercept: number | null;
  p_value: number | null;
}

export interface VizScatterData {
  season: string;
  x: {
    key: string;
    label: string;
    format: string;
    decimals: number;
  };
  y: {
    key: string;
    label: string;
    format: string;
    decimals: number;
  };
  stats: VizScatterStats;
  points: VizScatterPoint[];
  last_updated: string | null;
}

/**
 * TypeScript type definitions for API responses
 */

export interface Team {
  id: number;
  slug: string;
  name: string;
  aliases: string[];
  logo_url: string | null;
}

export interface Season {
  id: number;
  year: number;
  display_name: string;
  is_current: boolean;
}

export interface Game {
  id: number;
  source_game_id: string;
  season_year: number;
  game_date: string;
  start_time_utc: string | null;
  home_team_name: string;
  away_team_name: string;
  home_team_slug: string;
  away_team_slug: string;
  home_score: number | null;
  away_score: number | null;
  status: 'scheduled' | 'in_progress' | 'final' | 'canceled' | 'postponed';
  neutral_site: boolean;
  venue_name: string | null;
  venue_city: string | null;
  venue_state: string | null;
  period_count: number | null;
  went_to_ot: boolean;
  winner_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TeamGameStats {
  id: number;
  team_name: string;
  team_slug: string;
  opponent_name: string;
  opponent_slug: string;
  game_date: string;
  game_status: string;
  home_away: 'H' | 'A' | 'N';
  pts: number;
  fgm: number;
  fga: number;
  fg3m: number;
  fg3a: number;
  ftm: number;
  fta: number;
  fg2m: number;
  fg2a: number;
  fg_pct: number;
  fg3_pct: number;
  ft_pct: number;
  oreb: number;
  dreb: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  pf: number;
  possessions: number;
}

export interface GameLogEntry {
  id: number;
  game_date: string;
  team_name: string;
  opponent_name: string;
  opponent_slug: string;
  home_away: 'H' | 'A' | 'N';
  result: 'W' | 'L' | '-';
  margin: number;
  went_to_ot: boolean;
  
  // Scoring
  pts: number;
  opp_pts: number;
  
  // Shooting stats
  fgm: number;
  fga: number;
  fg_pct: number | null;
  fg2m: number;
  fg2a: number;
  fg2_pct: number | null;
  fg3m: number;
  fg3a: number;
  fg3_pct: number | null;
  fg3_rate: number | null;
  ftm: number;
  fta: number;
  ft_pct: number | null;
  ts_pct: number | null;
  
  // Rebounding
  oreb: number;
  dreb: number;
  reb: number;
  
  // Other box score
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  pf: number;
  
  // Possessions (3 types)
  poss_team: number | null;
  poss_opp: number | null;
  poss_game: number | null;
  
  // Ratings
  ortg: number | null;
  drtg: number | null;
  net_rating: number | null;
  pace: number | null;
  
  // Four Factors - Offense
  efg_pct: number | null;
  tov_pct: number | null;
  orb_pct: number | null;
  ftr: number | null;
  
  // Four Factors - Defense
  opp_efg_pct: number | null;
  opp_tov_pct: number | null;
  opp_orb_pct: number | null;
  opp_ftr: number | null;
  
  // Margins
  efg_margin: number | null;
  tov_edge: number | null;
  reb_edge: number | null;
  ftr_margin: number | null;
  
  // Assist metrics
  ast_pct: number | null;
  ast_to_ratio: number | null;
  ast_ratio: number | null;
  
  // Defense metrics
  stl_pct: number | null;
  blk_pct: number | null;
  stl_to_ratio: number | null;
  stocks_per_100: number | null;
  
  // Foul metrics
  pf_per_100: number | null;
  stl_per_pf: number | null;
  blk_per_pf: number | null;
}

export interface TeamSeasonMetrics {
  team_name: string;
  team_slug: string;
  season_year: number;
  games: number;
  ppg: number;
  papg: number;
  pace: number;
  ortg: number;
  drtg: number;
  net_rtg: number;
  efg_pct: number;
  tov_pct: number;
  orb_pct: number;
  ftr: number;
  opp_efg_pct: number;
  opp_tov_pct: number;
  drb_pct: number;
  opp_ftr: number;
  efg_margin: number;
  tov_edge: number;
  reb_edge: number;
  ftr_margin: number;
  kill_shots_for: number;
  kill_shots_against: number;
  kill_shots_pg: number;
  kill_shots_conceded_pg: number;
  kill_shot_margin_pg: number;
  ast_g: number;
  ast_pct: number | null;
  blk_g: number;
  blk_pct: number | null;
  dpf_g: number;
  last_updated: string;
}

export interface TeamSeasonRatings {
  team_name: string;
  team_slug: string;
  season_year: number;
  // Adjusted efficiency ratings
  adj_o: number;
  adj_d: number;
  adj_em: number;
  adj_tempo: number;
  rank_adj_o: number | null;
  rank_adj_d: number | null;
  rank_adj_em: number | null;
  // Adjusted four factors - offense
  adj_efg_pct: number;
  adj_tov_pct: number;
  adj_orb_pct: number;
  adj_ftr: number;
  // Adjusted four factors - defense
  adj_opp_efg_pct: number;
  adj_opp_tov_pct: number;
  adj_drb_pct: number;
  adj_opp_ftr: number;
  // Adjusted margins
  adj_efg_margin: number;
  adj_tov_edge: number;
  adj_reb_edge: number;
  adj_ftr_margin: number;
  // Four Factor Index
  ffi_raw: number;
  ffi_adj: number;
  // Metadata
  games_played: number;
  total_possessions: number;
  hca_estimate: number | null;
  computed_at: string;
}

export interface TeamSeasonStats {
  id: number;
  team_name: string;
  team_slug: string;
  team_logo: string | null;
  conference_code: string | null;
  conference_name: string | null;
  season_year: number;
  games: number;
  wins: number;
  losses: number;
  record: string;
  rank: number | null;
  rank_adj_em: number | null;
  rank_adj_o: number | null;
  rank_adj_d: number | null;
  adj_em: number;
  adj_o: number;
  adj_d: number;
  adj_tempo: number;
  efg_pct: number;
  tov_pct: number;
  orb_pct: number;
  ftr: number;
  efg_pct_d: number;
  tov_pct_d: number;
  drb_pct: number;
  ftr_d: number;
  efg_margin: number;
  tov_edge: number;
  reb_edge: number;
  ftr_margin: number;
  last_updated: string;
}

export interface GameLogResponse {
  team: Team;
  season_year: number;
  game_log: GameLogEntry[];
  total_games: number;
  last_updated: string | null;
}

export interface GamesResponse {
  team: Team;
  season_year: number;
  games: Game[];
  last_updated: string | null;
}

export interface SeasonStatsResponse {
  team: Team;
  season_year: number;
  metrics: TeamSeasonMetrics | null;
  ratings: TeamSeasonRatings | null;
}

export interface GameDetailResponse extends Game {
  home_stats: TeamGameStats | null;
  away_stats: TeamGameStats | null;
}

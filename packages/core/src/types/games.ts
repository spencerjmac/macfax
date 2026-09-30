// Types for game detail page — shared between NCAA and NBA

export interface GameTeamRef {
  name: string;
  abbr: string;
  slug: string;
}

export interface WPPoint {
  t: number;          // elapsed fraction of total game time (0.0 = tipoff, 1.0 = final buzzer)
  wp: number;         // home team win probability (0–1)
  home_score: number;
  away_score: number;
}

export interface FourFactorsTeam {
  efg_pct: number | null;
  tov_pct: number | null;
  orb_pct: number | null;
  ftr: number | null;
}

export interface PlayerBoxRow {
  name: string;
  min: string;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  stl: number | null;
  blk: number | null;
  tov: number | null;
  fg: string;
  fg3: string;
  ft: string;
  plus_minus: number | null;
}

export interface GameMeta {
  id: number;
  league: 'ncaa' | 'nba';
  date: string;           // ISO date: "2025-01-18"
  home_team: GameTeamRef;
  away_team: GameTeamRef;
  home_score: number | null;
  away_score: number | null;
  venue: string | null;
  status: string;
}

export interface GameDetailResponse {
  game_meta: GameMeta;
  wp_curve: WPPoint[];
  four_factors: {
    home: FourFactorsTeam;
    away: FourFactorsTeam;
  };
  box_score: {
    home: PlayerBoxRow[];
    away: PlayerBoxRow[];
  };
  insights: string[];
}

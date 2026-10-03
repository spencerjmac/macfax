export interface WorldCupTeam {
  elo_rank: number;
  name: string;
  flag_emoji: string;
  confederation: 'UEFA' | 'CONMEBOL' | 'CAF' | 'CONCACAF' | 'AFC' | 'OFC';
  group: string;
  is_host: boolean;
  elo_rating: number;
  fifa_rank: number;
  fifa_points: number;
  elo_vs_fifa: number;
  updated_at: string;
}

export interface WorldCupMatchupResult {
  teamA: WorldCupTeam;
  teamB: WorldCupTeam;
  win_pct_a: number;
  draw_pct: number;
  win_pct_b: number;
  elo_diff: number;
}

export interface WorldCupFixtureProb {
  team_a: string;
  team_b: string;
  p_a_win: number;
  p_draw: number;
  p_b_win: number;
}

export interface WorldCupGroupTeamResult extends WorldCupTeam {
  win_group_pct: number;
  advance_pct: number;
}

export interface WorldCupGroupResult {
  group: string;
  teams: WorldCupGroupTeamResult[];
  fixtures: WorldCupFixtureProb[];
}

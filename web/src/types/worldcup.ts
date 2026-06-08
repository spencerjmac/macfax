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

export interface ValidationSummaryEntry {
  period_type: 'season' | 'last_7' | 'last_30' | 'all_time';
  period_start: string | null;
  period_end: string | null;
  games_evaluated: number;
  winner_accuracy: number; // 0.0–1.0
  spread_mae: number;
  score_mae: number;
  total_mae: number;
  average_margin_bias: number;
  brier_score: number;
  log_loss: number | null;
  upset_predictions: number;
  upset_hits: number;
  upset_precision: number | null;
  updated_at: string;
}

export interface ValidationSummaryResponse {
  season: number;
  model_version: string;
  summaries: ValidationSummaryEntry[];
}

export interface ValidationWeekEntry {
  week_start: string;
  games: number;
  winner_accuracy: number;
  spread_mae: number;
  score_mae: number;
}

export interface ValidationWeeklyResponse {
  season: number;
  weeks: ValidationWeekEntry[];
}

export interface ValidationRecentGame {
  game_date: string;
  home_team: string;
  away_team: string;
  actual_home_score: number;
  actual_away_score: number;
  projected_home_score: number;
  projected_away_score: number;
  projected_home_margin: number;
  actual_home_margin: number;
  margin_error: number;
  home_win_probability: number;
  winner_correct: boolean;
  brier_score: number;
}

export interface ValidationRecentGamesResponse {
  season: number;
  games: ValidationRecentGame[];
}

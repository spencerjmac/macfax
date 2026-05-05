/**
 * Phase 7: Roster Outlook type definitions.
 *
 * These types mirror the shapes returned by the backend outlook API:
 *   GET  /api/outlook/<slug>/
 *   POST /api/outlook/scenario/
 *   GET  /api/outlook/player-search/
 */

export type RecruitmentType = 'returner' | 'transfer' | 'newcomer';
export type RoleBucket = 'G' | 'Wing' | 'Big' | null;

export interface FitGrade {
  letter: string;   // e.g. "A", "B+", "C"
  label: string;    // e.g. "Elite", "Strong", "Solid"
  score: number | null;
}

// ── Player ───────────────────────────────────────────────────────────────────

export interface OutlookPlayer {
  player_id: number;
  player_name: string;
  player_short_name: string;
  position: string;
  headshot_url: string | null;
  projected_obpr: number | null;
  projected_dbpr: number | null;
  projected_bpr: number | null;
  minutes_share_p2: number | null;
  mpg_p2: number | null;
  role_bucket: RoleBucket;
  recruitment_type: RecruitmentType;
  projection_uncertainty: number | null;
  rotation_rank: number | null;
  n_prior_seasons: number;
  /**
   * True when this player was created from a PlaceholderArchetype rather than
   * a real PlayerSeasonProjection.  Synthetic additions are treated as
   * 'newcomer' in the scenario engine — they have no prior DB history and
   * represent external additions to the roster.
   */
  is_placeholder?: boolean;
  /** The archetype key that generated this player, e.g. 'high_mid_starter_g'. */
  placeholder_key?: string;
}

/**
 * Player search result — extends OutlookPlayer with the source team info
 * returned by GET /api/outlook/player-search/.
 */
export interface PlayerSearchResult extends OutlookPlayer {
  team_name: string;
  team_slug: string | null;
}

// ── Team projection ───────────────────────────────────────────────────────────

export interface TeamOutlookProjection {
  projected_adj_o: number | null;
  projected_adj_d: number | null;
  projected_adj_em: number | null;
  projected_adj_o_low: number | null;
  projected_adj_o_high: number | null;
  projected_adj_d_low: number | null;
  projected_adj_d_high: number | null;
  projected_adj_em_low: number | null;
  projected_adj_em_high: number | null;

  projected_national_rank: number | null;
  national_rank_range_low: number | null;
  national_rank_range_high: number | null;
  projected_offense_rank: number | null;
  offense_rank_range_low: number | null;
  offense_rank_range_high: number | null;
  projected_defense_rank: number | null;
  defense_rank_range_low: number | null;
  defense_rank_range_high: number | null;

  team_projection_uncertainty: number | null;
  returner_minutes_fraction: number | null;
  continuity_score: number | null;
  continuity_value_score: number | null;
  transfer_dependence_score: number | null;
  transfer_fit_risk_score: number | null;
}

// ── Fit data ──────────────────────────────────────────────────────────────────

export interface TeamOutlookFit {
  offensive_fit_score: number | null;
  defensive_fit_score: number | null;
  overall_fit_score: number | null;
  adjusted_off_fit: number | null;
  adjusted_def_fit: number | null;
  adjusted_overall_fit: number | null;
  has_team_style_data: boolean;
  off_grade: FitGrade;
  def_grade: FitGrade;
  offensive_strengths: string[];
  offensive_weaknesses: string[];
  defensive_strengths: string[];
  defensive_weaknesses: string[];
}

// ── Full baseline response ────────────────────────────────────────────────────

export interface RosterOutlookData {
  team: {
    id: number;
    name: string;
    slug: string;
    logo_url: string | null;
  };
  season: {
    year: number;
    display_name: string;
    projected_season_year: number;
  };
  projection: TeamOutlookProjection;
  players: OutlookPlayer[];
  fit: TeamOutlookFit | null;
}

// ── Scenario ──────────────────────────────────────────────────────────────────

/**
 * A player row in the scenario editor.  Extends OutlookPlayer with a few
 * scenario-specific fields that exist only on the client.
 */
export interface ScenarioPlayer extends OutlookPlayer {
  /** 'baseline' = unchanged, 'removed' = user excluded, 'added' = user added */
  scenarioState: 'baseline' | 'removed' | 'added';
  /** Optional manual minutes override (0-1, fraction of pool) */
  minutesOverride?: number | null;
}

/** Request body sent to POST /api/outlook/scenario/ */
export interface ScenarioRequest {
  from_season_year: number;
  team_slug: string;
  players: Array<{
    player_id: number | null;
    player_name: string;
    projected_obpr: number;
    projected_dbpr: number;
    projected_bpr: number;
    minutes_share: number;
    recruitment_type: RecruitmentType;
    projection_uncertainty: number;
  }>;
}

/** Response from POST /api/outlook/scenario/ */
export interface ScenarioProjectionResult {
  projected_adj_o: number;
  projected_adj_d: number;
  projected_adj_em: number;
  projected_adj_o_low: number;
  projected_adj_o_high: number;
  projected_adj_d_low: number;
  projected_adj_d_high: number;
  projected_adj_em_low: number;
  projected_adj_em_high: number;
  approx_national_rank: number;
  n_teams_in_pool: number;
  national_rank_range_low: number | null;
  national_rank_range_high: number | null;
  projected_offense_rank: number | null;
  projected_defense_rank: number | null;
  team_projection_uncertainty: number;
  returner_minutes_fraction: number;
  continuity_score: number;
  continuity_value_score: number;
  transfer_dependence_score: number;
  transfer_fit_risk_score: number;
}

// ── Placeholder archetypes ────────────────────────────────────────────────────

export type ConfGroup = 'national' | 'power' | 'high_mid' | 'mid_major';
export type QualityTier = 'elite' | 'all_conference' | 'starter' | 'rotation' | 'bench';

/**
 * Pre-built archetype player built from real cohort medians.
 * Returned by GET /api/outlook/placeholders/.
 */
export interface PlaceholderArchetype {
  key: string;               // e.g. 'power_starter_g'
  display_name: string;      // e.g. 'Power Conf Guard (Starter)'
  conf_group: ConfGroup;
  role_bucket: RoleBucket;
  quality_tier: QualityTier;
  projected_obpr: number;
  projected_dbpr: number;
  projected_bpr: number;
  minutes_share: number;
  mpg: number;
  uncertainty: number;
  efg_pct: number | null;
  fg3_pct: number | null;
  ts_pct: number | null;
  ast_to: number | null;
  oreb_pg: number | null;
  dreb_pg: number | null;
  tov: number | null;
  sample_n: number;
  source_season_year: number;
}

export interface PlaceholderListResponse {
  archetypes: PlaceholderArchetype[];
}

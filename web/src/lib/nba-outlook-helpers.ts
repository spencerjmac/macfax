import type {
  DevelopmentWatchPlayer,
  NBAProjectedRosterSlot,
  OutlookTier,
  TeamOutseasonMove,
  TeamSeasonOutlookSummary,
} from '@/types/nba';

export type OutlookTierLabel =
  | 'Title Favorite'
  | 'Contender'
  | 'Playoff Lock'
  | 'Playoff Mix'
  | 'Play-In Range'
  | 'Rebuild'
  | 'Deep Rebuild';

export type EfficiencyKind = 'offense' | 'defense' | 'net';
export type FourFactorKey = 'shooting' | 'ball-security' | 'glass' | 'free-throws';

const TIER_ORDER: Record<OutlookTierLabel, number> = {
  'Title Favorite': 0,
  Contender: 1,
  'Playoff Lock': 2,
  'Playoff Mix': 3,
  'Play-In Range': 4,
  Rebuild: 5,
  'Deep Rebuild': 6,
};

const TEAM_NAME_OVERRIDES: Record<string, string> = {
  'los-angeles-lakers': 'Los Angeles Lakers',
  'la-lakers': 'Los Angeles Lakers',
  'los-angeles-clippers': 'Los Angeles Clippers',
  'la-clippers': 'Los Angeles Clippers',
  'new-york-knicks': 'New York Knicks',
  'oklahoma-city-thunder': 'Oklahoma City Thunder',
  'san-antonio-spurs': 'San Antonio Spurs',
  'golden-state-warriors': 'Golden State Warriors',
  'new-orleans-pelicans': 'New Orleans Pelicans',
  'portland-trail-blazers': 'Portland Trail Blazers',
};

export function normalizeNegativeZero(value: number, decimals = 1): number {
  const scale = 10 ** decimals;
  const rounded = Math.round(value * scale) / scale;
  return Object.is(rounded, -0) ? 0 : rounded;
}

export function formatSignedNumber(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  const normalized = normalizeNegativeZero(value, decimals);
  const rendered = normalized.toFixed(decimals);
  return normalized > 0 ? `+${rendered}` : rendered;
}

export function formatRating(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return normalizeNegativeZero(value, decimals).toFixed(decimals);
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `${normalizeNegativeZero(value, decimals).toFixed(decimals)}%`;
}

export function formatRecord(
  wins: number | null | undefined,
  losses: number | null | undefined,
): string {
  if (wins === null || wins === undefined) return '-';
  if (losses === null || losses === undefined) return `${wins}W`;
  return `${wins}-${losses}`;
}

export function formatProjectedRecord(team: TeamSeasonOutlookSummary): string {
  return formatRecord(team.projected_wins ?? team.wins, team.projected_losses ?? team.losses);
}

export function formatTeamNameFromSlug(slug: string | null | undefined): string {
  if (!slug) return '';
  const normalized = slug.trim().toLowerCase();
  if (TEAM_NAME_OVERRIDES[normalized]) return TEAM_NAME_OVERRIDES[normalized];
  return normalized
    .split('-')
    .filter(Boolean)
    .map((part) => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ');
}

function asPercent(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  return Math.abs(value) <= 1 ? value * 100 : value;
}

export function getDisplayAdjNet(team: TeamSeasonOutlookSummary): number | null {
  return team.projected_adj_net ?? team.adj_net_rating;
}

export function getDisplayAdjO(team: TeamSeasonOutlookSummary): number | null {
  return team.projected_adj_o ?? team.adj_offensive_rating;
}

export function getDisplayAdjD(team: TeamSeasonOutlookSummary): number | null {
  return team.projected_adj_d ?? team.adj_defensive_rating;
}

export function getOutlookTier(adjNet: number | null | undefined, wins?: number | null): OutlookTierLabel {
  const net = adjNet ?? 0;
  if (net >= 6 || (wins !== null && wins !== undefined && wins >= 56)) return 'Title Favorite';
  if (net >= 3.5 || (wins !== null && wins !== undefined && wins >= 50)) return 'Contender';
  if (net >= 1.5 || (wins !== null && wins !== undefined && wins >= 45)) return 'Playoff Lock';
  if (net >= 0.5 || (wins !== null && wins !== undefined && wins >= 42)) return 'Playoff Mix';
  if (net >= -1 || (wins !== null && wins !== undefined && wins >= 38)) return 'Play-In Range';
  if (net >= -5) return 'Rebuild';
  return 'Deep Rebuild';
}

export function getOutlookTierLabel(
  backendTier: OutlookTier | null | undefined,
  adjNet: number | null | undefined,
  wins?: number | null,
): OutlookTierLabel {
  const modelTier = getOutlookTier(adjNet, wins);
  if (!backendTier) return modelTier;
  if (backendTier === 'title_contender') return modelTier === 'Title Favorite' ? 'Title Favorite' : 'Contender';
  if (backendTier === 'playoff_contender') return modelTier === 'Title Favorite' ? 'Title Favorite' : 'Contender';
  if (backendTier === 'bubble') return modelTier === 'Playoff Lock' ? 'Playoff Mix' : modelTier;
  if (backendTier === 'lottery') return modelTier === 'Deep Rebuild' ? 'Deep Rebuild' : 'Rebuild';
  return modelTier === 'Rebuild' ? 'Deep Rebuild' : modelTier;
}

export function getOutlookTierRank(label: OutlookTierLabel): number {
  return TIER_ORDER[label];
}

export function getTierClass(label: OutlookTierLabel): string {
  if (label === 'Title Favorite') return 'bg-yellow-500/15 text-yellow-700 border border-yellow-500/25';
  if (label === 'Contender') return 'bg-brand/15 text-brand border border-brand/25';
  if (label === 'Playoff Lock' || label === 'Playoff Mix') return 'bg-brandBlue/15 text-brandBlue border border-brandBlue/25';
  if (label === 'Play-In Range') return 'bg-slate-500/10 text-slate-600 border border-slate-300';
  if (label === 'Rebuild') return 'bg-orange-500/10 text-orange-600 border border-orange-500/25';
  return 'bg-negative/10 text-negative border border-negative/25';
}

export function getTierDotClass(label: OutlookTierLabel): string {
  if (label === 'Title Favorite') return 'bg-yellow-500';
  if (label === 'Contender') return 'bg-brand';
  if (label === 'Playoff Lock' || label === 'Playoff Mix') return 'bg-brandBlue';
  if (label === 'Play-In Range') return 'bg-slate-400';
  if (label === 'Rebuild') return 'bg-orange-500';
  return 'bg-negative';
}

export function getTeamRiskSignal(team: {
  top2_bpr_concentration?: number | null;
  continuity_score?: number | null;
  weighted_effective_age?: number | null;
  projected_adj_d?: number | null;
  projected_adj_o?: number | null;
  adj_defensive_rating?: number | null;
  adj_offensive_rating?: number | null;
}): string {
  const concentration = asPercent(team.top2_bpr_concentration);
  const continuity = team.continuity_score;
  const age = team.weighted_effective_age;
  const adjD = team.projected_adj_d ?? team.adj_defensive_rating;
  const adjO = team.projected_adj_o ?? team.adj_offensive_rating;

  if (concentration !== null && concentration >= 65) return 'Star health';
  if (continuity !== null && continuity !== undefined && continuity < 45) return 'Chemistry';
  if (age !== null && age !== undefined && age <= 24.5) return 'Development curve';
  if (age !== null && age !== undefined && age >= 30) return 'Aging curve';
  if (adjD !== null && adjD !== undefined && adjD > 116) return 'Defensive floor';
  if (adjO !== null && adjO !== undefined && adjO < 112) return 'Shot creation';
  return 'Normal variance';
}

export function getAgeLabel(age: number | null | undefined): { label: string; text: string; className: string; barClass: string } {
  if (age === null || age === undefined) {
    return { label: 'Unknown', text: 'Rotation age is not available yet.', className: 'text-text-muted', barClass: 'bg-slate-300' };
  }
  if (age <= 24) {
    return { label: 'Young / ascending', text: 'The core is still before the typical NBA peak window.', className: 'text-brandBlue', barClass: 'bg-brandBlue' };
  }
  if (age <= 29) {
    return { label: 'Prime window', text: 'The rotation sits in the NBA peak-age band.', className: 'text-positive', barClass: 'bg-positive' };
  }
  return { label: 'Aging curve', text: 'The projection carries more veteran age risk.', className: 'text-orange-600', barClass: 'bg-orange-500' };
}

export function getContinuityLabel(value: number | null | undefined): { label: string; text: string; className: string; barClass: string } {
  if (value === null || value === undefined) {
    return { label: 'Unknown', text: 'Continuity is not available yet.', className: 'text-text-muted', barClass: 'bg-slate-300' };
  }
  if (value >= 75) {
    return { label: 'Very stable', text: 'High continuity usually gives good teams a regular-season floor.', className: 'text-positive', barClass: 'bg-positive' };
  }
  if (value >= 55) {
    return { label: 'Mostly stable', text: 'Enough of last season returns for the model to trust the baseline.', className: 'text-brand', barClass: 'bg-brand' };
  }
  if (value >= 35) {
    return { label: 'New mix', text: 'The rotation has meaningful integration risk.', className: 'text-orange-600', barClass: 'bg-orange-500' };
  }
  return { label: 'Low continuity', text: 'The team has to rebuild chemistry and role clarity.', className: 'text-negative', barClass: 'bg-negative' };
}

export function getStarConcentrationLabel(value: number | null | undefined): { label: string; text: string; className: string; barClass: string; percent: number | null } {
  const pct = asPercent(value);
  if (pct === null) {
    return { label: 'Unknown', text: 'Star concentration is not available yet.', className: 'text-text-muted', barClass: 'bg-slate-300', percent: null };
  }
  if (pct <= 45) {
    return { label: 'Balanced', text: 'Value is spread across more of the rotation.', className: 'text-brandBlue', barClass: 'bg-brandBlue', percent: pct };
  }
  if (pct <= 65) {
    return { label: 'Normal', text: 'The roster has a typical top-end value shape.', className: 'text-brand', barClass: 'bg-brand', percent: pct };
  }
  return { label: 'Top-heavy', text: 'A large share of value comes from the top two players.', className: 'text-orange-600', barClass: 'bg-orange-500', percent: pct };
}

export function getBprTier(bpr: number | null | undefined): { label: string; className: string } {
  if (bpr === null || bpr === undefined) return { label: 'Unknown', className: 'text-text-muted' };
  if (bpr >= 5) return { label: 'All-Star', className: 'text-positive' };
  if (bpr >= 2) return { label: 'Starter', className: 'text-brand' };
  if (bpr >= 0) return { label: 'Rotation', className: 'text-text-primary' };
  return { label: 'Drag', className: 'text-negative' };
}

export function getMpsTier(mps: number | null | undefined): { label: string; className: string } {
  if (mps === null || mps === undefined) return { label: 'Unknown', className: 'bg-ui-surface text-text-muted border border-ui-border' };
  if (mps >= 85) return { label: 'Elite', className: 'bg-positive/15 text-positive border border-positive/25' };
  if (mps >= 75) return { label: 'High', className: 'bg-brand/15 text-brand border border-brand/25' };
  if (mps >= 60) return { label: 'Mid', className: 'bg-brandBlue/15 text-brandBlue border border-brandBlue/25' };
  if (mps >= 45) return { label: 'Developmental', className: 'bg-orange-500/10 text-orange-600 border border-orange-500/25' };
  return { label: 'Long shot', className: 'bg-ui-surface text-text-muted border border-ui-border' };
}

export function getEfficiencyInterpretation(
  value: number | null | undefined,
  kind: EfficiencyKind,
): { label: string; className: string } {
  if (value === null || value === undefined) return { label: 'Unknown', className: 'text-text-muted' };
  if (kind === 'defense') {
    if (value <= 110) return { label: 'Elite', className: 'text-positive' };
    if (value <= 113) return { label: 'Above average', className: 'text-brand' };
    if (value <= 116) return { label: 'Average', className: 'text-text-muted' };
    if (value <= 119) return { label: 'Below average', className: 'text-orange-600' };
    return { label: 'Poor', className: 'text-negative' };
  }
  if (kind === 'offense') {
    if (value >= 118) return { label: 'Elite', className: 'text-positive' };
    if (value >= 115) return { label: 'Above average', className: 'text-brand' };
    if (value >= 112) return { label: 'Average', className: 'text-text-muted' };
    if (value >= 109) return { label: 'Below average', className: 'text-orange-600' };
    return { label: 'Poor', className: 'text-negative' };
  }
  if (value >= 6) return { label: 'Elite', className: 'text-positive' };
  if (value >= 3) return { label: 'Above average', className: 'text-brand' };
  if (value >= -1) return { label: 'Average', className: 'text-text-muted' };
  if (value >= -5) return { label: 'Below average', className: 'text-orange-600' };
  return { label: 'Poor', className: 'text-negative' };
}

export function getMetricColor(value: number | null | undefined, kind: EfficiencyKind): string {
  if (value === null || value === undefined) return 'text-text-muted';
  if (kind === 'defense') {
    if (value <= 113) return 'text-positive';
    if (value >= 117) return 'text-negative';
    return 'text-text-primary';
  }
  if (kind === 'offense') {
    if (value >= 115) return 'text-positive';
    if (value <= 110) return 'text-negative';
    return 'text-text-primary';
  }
  if (value > 0) return 'text-positive';
  if (value < 0) return 'text-negative';
  return 'text-text-muted';
}

export function getFourFactorEdge(
  key: FourFactorKey,
  teamVal: number | null | undefined,
  oppVal: number | null | undefined,
): { label: 'Advantage' | 'Neutral' | 'Problem'; className: string; edge: number | null } {
  if (teamVal === null || teamVal === undefined || oppVal === null || oppVal === undefined) {
    return { label: 'Neutral', className: 'text-text-muted', edge: null };
  }
  const edge = key === 'ball-security' ? oppVal - teamVal : teamVal - oppVal;
  if (edge >= 1) return { label: 'Advantage', className: 'text-positive', edge };
  if (edge <= -1) return { label: 'Problem', className: 'text-negative', edge };
  return { label: 'Neutral', className: 'text-text-muted', edge };
}

export function formatArchetype(archetype: string | null | undefined): string {
  if (!archetype) return 'Rotation';
  return archetype
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function getPlayerRoleLabel(player: Pick<NBAProjectedRosterSlot, 'projected_bpr' | 'archetype'>): string {
  const bpr = player.projected_bpr;
  if (bpr !== null && bpr !== undefined) {
    if (bpr >= 5) return 'Primary engine';
    if (bpr >= 3) return 'Top-end starter';
    if (bpr >= 1.5) return 'Plus starter';
    if (bpr >= 0) return 'Rotation piece';
    return 'Depth swing';
  }
  return formatArchetype(player.archetype);
}

export function getDevelopmentRead(player: DevelopmentWatchPlayer): string {
  if (player.acquisition_type === 'drafted') return 'Development bet';
  const bpr = player.projected_bpr;
  if (bpr !== null && bpr !== undefined && bpr >= 2) return 'Core growth piece';
  if (bpr !== null && bpr !== undefined && bpr >= 0) return 'Rotation upside';
  return 'Needs a leap';
}

export function getPickLabel(round: number | null | undefined, pick: number | null | undefined): string {
  if (pick === null || pick === undefined) return 'Pick TBD';
  return `${round === 2 ? 'R2' : 'R1'} #${pick}`;
}

function cleanSlugFragments(text: string): string {
  return text
    .replace(/\b([a-z]+(?:-[a-z0-9]+)+)\b/g, (match) => formatTeamNameFromSlug(match))
    .replace(/\s+/g, ' ')
    .trim();
}

export function formatMoveDetail(move: TeamOutseasonMove): string {
  const detail = cleanSlugFragments(move.detail || '');
  if (move.move_type === 'drafted') {
    const pick = getPickLabel(move.round_number, move.overall_pick);
    return move.mps_score !== null && move.mps_score !== undefined
      ? `${pick} - MPS ${formatRating(move.mps_score)}`
      : pick;
  }
  if (!detail) {
    if (move.move_type === 'signed') return 'Free-agent addition';
    if (move.move_type === 'traded_in') return 'Trade addition';
    if (move.move_type === 'lost') return 'Departed in free agency';
    if (move.move_type === 'traded_out') return 'Moved by trade';
    if (move.move_type === 'extended') return 'Extension keeps continuity intact';
    return 'Roster move';
  }
  return detail
    .replace(/^left via offseason\s*[-:]\s*now on\s+/i, 'Signed with ')
    .replace(/^now on\s+/i, 'Signed with ')
    .replace(/^to\s+/i, 'To ')
    .replace(/^from\s+/i, 'From ');
}

export function getMoveVerb(move: TeamOutseasonMove): string {
  if (move.move_type === 'signed') return 'Signed';
  if (move.move_type === 'lost') return 'Departed';
  if (move.move_type === 'drafted') return 'Drafted';
  if (move.move_type === 'traded_in') return 'Acquired';
  if (move.move_type === 'traded_out') return 'Traded out';
  if (move.move_type === 'extended') return 'Extended';
  return 'Waived';
}

export function generateTeamSummary(team: TeamSeasonOutlookSummary): string {
  if (team.season_headline) return team.season_headline;
  const adjNet = getDisplayAdjNet(team);
  const tier = getOutlookTierLabel(team.outlook_tier, adjNet, team.projected_wins);
  const continuity = getContinuityLabel(team.continuity_score).label.toLowerCase();
  const age = getAgeLabel(team.weighted_effective_age).label.toLowerCase();
  const concentration = getStarConcentrationLabel(team.top2_bpr_concentration).label.toLowerCase();
  return `The model sees a ${tier.toLowerCase()} profile built around ${continuity} continuity, a ${age} rotation, and a ${concentration} value shape.`;
}

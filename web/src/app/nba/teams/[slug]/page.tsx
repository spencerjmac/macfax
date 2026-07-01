import { notFound } from 'next/navigation';
import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowLeft, ChevronDown } from 'lucide-react';
import TeamLogo from '@/components/TeamLogo';
import type {
  CapStatusTier,
  DevelopmentWatchPlayer,
  NBAProjectedRosterSlot,
  ProjectedStarter,
  TeamOutseasonMove,
  TeamSeasonOutlookDetail,
} from '@/types/nba';
import { nbaApi } from '@/lib/nba-api';
import {
  formatArchetype,
  formatMoveDetail,
  formatPercent,
  formatProjectedRecord,
  formatRating,
  formatRecord,
  formatSignedNumber,
  formatTeamNameFromSlug,
  getAgeLabel,
  getBprTier,
  getContinuityLabel,
  getDevelopmentRead,
  getDisplayAdjD,
  getDisplayAdjNet,
  getDisplayAdjO,
  getEfficiencyInterpretation,
  getFourFactorEdge,
  getMetricColor,
  getMoveVerb,
  getMpsTier,
  getOutlookTierLabel,
  getPickLabel,
  getPlayerRoleLabel,
  getStarConcentrationLabel,
  getTeamRiskSignal,
  getTierClass,
} from '@/lib/nba-outlook-helpers';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  return { title: `${formatTeamNameFromSlug(slug)} Team Outlook | macfax` };
}

const ADDITION_TYPES: TeamOutseasonMove['move_type'][] = ['signed', 'drafted', 'traded_in', 'extended'];

const IMPACT_CLASSES: Record<TeamOutseasonMove['impact_rating'], string> = {
  high: 'bg-positive/15 text-positive border border-positive/25',
  medium: 'bg-brand/15 text-brand border border-brand/25',
  low: 'bg-ui-surface text-text-muted border border-ui-border',
};

const ACQUISITION_LABELS: Record<NBAProjectedRosterSlot['acquisition_type'], string> = {
  returner: 'Returner',
  extended: 'Extended',
  signed: 'Signed',
  traded_in: 'Trade',
  drafted: 'Rookie',
};

const ACQUISITION_CLASSES: Record<NBAProjectedRosterSlot['acquisition_type'], string> = {
  returner: 'bg-brandBlue/10 text-brandBlue border border-brandBlue/20',
  extended: 'bg-brandBlue/10 text-brandBlue border border-brandBlue/20',
  signed: 'bg-positive/10 text-positive border border-positive/20',
  traded_in: 'bg-orange-500/10 text-orange-600 border border-orange-500/25',
  drafted: 'bg-brand/10 text-brand border border-brand/25',
};

const CAP_TIER_LABELS: Record<CapStatusTier, string> = {
  under_cap: 'Under Cap',
  over_cap: 'Over Cap',
  taxpayer: 'Tax',
  first_apron: 'First Apron',
  second_apron: 'Second Apron',
};

const CAP_TIER_TEXT: Record<CapStatusTier, string> = {
  under_cap: 'Cap room gives the front office more ways to reshape the roster.',
  over_cap: 'The team can still maneuver, but most upgrades have to come through exceptions or trades.',
  taxpayer: 'Tax pressure makes the current rotation more expensive to adjust.',
  first_apron: 'Apron rules reduce flexibility, so internal continuity matters more.',
  second_apron: 'Second-apron restrictions make major roster pivots harder.',
};

function sectionTitle(kicker: string, title: string, text?: string) {
  return (
    <div className="mb-4">
      <p className="kicker-sport text-brand mb-2">{kicker}</p>
      <h2 className="font-display text-[24px] font-bold uppercase leading-none tracking-[0.005em] text-text-primary m-0">
        {title}
      </h2>
      {text && <p className="mt-2 max-w-[760px] text-[14px] leading-relaxed text-text-muted m-0">{text}</p>}
    </div>
  );
}

function formatMinutesShare(value: number | null): string {
  if (value === null) return '-';
  if (value <= 1) return `${formatRating(value * 100, 0)}%`;
  if (value <= 5) return `${formatRating((value / 5) * 100, 0)}%`;
  return `${formatRating(value, 0)}%`;
}

function formatSalary(value: number): string {
  return `$${(value / 1_000_000).toFixed(0)}M`;
}

function generateMacFaxRead(detail: TeamSeasonOutlookDetail): string {
  const adjNet = getDisplayAdjNet(detail);
  const tier = getOutlookTierLabel(detail.outlook_tier, adjNet, detail.projected_wins ?? detail.wins);
  const continuity = getContinuityLabel(detail.continuity_score).label.toLowerCase();
  const age = getAgeLabel(detail.weighted_effective_age).label.toLowerCase();
  const risk = getTeamRiskSignal(detail).toLowerCase();

  if (tier === 'Title Favorite' || tier === 'Contender') {
    return `The model sees ${detail.team_name} as a real contender because the baseline is strong and the roster shape is ${continuity}. The question is less whether the team is good and more whether ${risk} keeps the ceiling from matching the regular-season profile.`;
  }
  if (tier === 'Playoff Lock' || tier === 'Playoff Mix') {
    return `${detail.team_name} lands in the playoff conversation because the model sees enough efficiency and roster value to clear the middle of the league. The swing comes from whether the ${age} pieces can turn a solid baseline into something sturdier.`;
  }
  if (tier === 'Play-In Range') {
    return `${detail.team_name} projects close to the league middle: good enough to matter, but not clean enough to separate. The projection is sensitive to ${risk} and small changes in two-way depth.`;
  }
  return `The model is skeptical of ${detail.team_name} because the current roster profile does not create enough bankable efficiency. The upside case needs development or roster movement to beat a low baseline.`;
}

function getSwingText(detail: TeamSeasonOutlookDetail): string {
  if (detail.season_defining_variable) return detail.season_defining_variable;
  const risk = getTeamRiskSignal(detail);
  if (risk === 'Star health') return 'The season turns on whether the top-end players stay available enough to support a top-heavy value profile.';
  if (risk === 'Chemistry') return 'The season turns on how quickly a changed rotation finds roles that make sense.';
  if (risk === 'Development curve') return 'The season turns on whether the under-25 core arrives ahead of the model curve.';
  if (risk === 'Aging curve') return 'The season turns on whether veteran production holds up over 82 games.';
  if (risk === 'Defensive floor') return 'The season turns on whether the defense can avoid becoming the limiting factor.';
  if (risk === 'Shot creation') return 'The season turns on whether the offense has enough reliable creation late in possessions.';
  return 'The season turns on normal health, shooting, and rotation variance.';
}

function WinRangeBar({
  floor,
  baseline,
  ceiling,
}: {
  floor: number | null;
  baseline: number | null;
  ceiling: number | null;
}) {
  if (floor === null || baseline === null || ceiling === null) return null;

  const scale = (wins: number) => Math.max(0, Math.min(100, ((wins - 10) / 65) * 100));
  const floorPct = scale(floor);
  const baselinePct = scale(baseline);
  const ceilingPct = scale(ceiling);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 text-[12px] text-text-muted">
        <span><span className="font-mono font-semibold text-text-primary">{floor}W</span> floor</span>
        <span><span className="font-mono font-semibold text-text-primary">{baseline}W</span> baseline</span>
        <span><span className="font-mono font-semibold text-text-primary">{ceiling}W</span> ceiling</span>
      </div>
      <div className="relative h-3 rounded-full bg-ui-border">
        <div
          className="absolute top-0 h-full rounded-full bg-brand/30"
          style={{ left: `${floorPct}%`, width: `${Math.max(2, ceilingPct - floorPct)}%` }}
        />
        <div
          className="absolute top-[-4px] h-5 w-1.5 rounded-full bg-brand shadow"
          style={{ left: `${baselinePct}%`, marginLeft: '-3px' }}
        />
      </div>
    </div>
  );
}

function TeamHero({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const adjNet = getDisplayAdjNet(detail);
  const tier = getOutlookTierLabel(detail.outlook_tier, adjNet, detail.projected_wins ?? detail.wins);
  const summary = detail.season_headline || generateMacFaxRead(detail);

  return (
    <header className="relative overflow-hidden border-b-4 border-brand bg-ink text-white">
      <div className="max-w-[1240px] mx-auto px-5 sm:px-8 py-10 sm:py-12">
        <Link
          href="/nba/teams"
          className="mb-7 inline-flex items-center gap-2 text-[13px] font-semibold text-ink-fg2 no-underline transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
          All Team Outlooks
        </Link>

        <div className="grid gap-7 lg:grid-cols-[1fr_320px] lg:items-end">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-xl bg-white p-3 shadow-[0_18px_50px_-28px_rgba(0,0,0,0.65)]">
              <TeamLogo
                src={detail.logo_url}
                alt={detail.team_abbr}
                width={72}
                height={72}
                className="max-h-[72px] max-w-[72px] object-contain"
                fallbackColor={detail.primary_color}
              />
            </div>
            <div className="min-w-0">
              <p className="kicker-sport text-brand2 mb-3">
                {detail.conference}ern Conference · {formatProjectedRecord(detail)} projected · #{detail.league_rank} in NBA
              </p>
              <h1 className="font-display text-[clamp(40px,6vw,76px)] font-bold uppercase leading-[0.94] tracking-[0.005em] text-white m-0">
                {detail.team_name}
              </h1>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <span className={`font-mono text-[32px] font-bold leading-none ${getMetricColor(adjNet, 'net')}`}>
                  {formatSignedNumber(adjNet)}
                  <span className="ml-2 text-[14px] font-normal text-ink-fg2">AdjNet</span>
                </span>
                <span className={`rounded px-2.5 py-1 text-[12px] font-semibold ${getTierClass(tier)}`}>
                  {tier}
                </span>
              </div>
              <p className="mt-5 max-w-[760px] text-[16px] leading-relaxed text-ink-fg m-0">
                {summary}
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-ink-line bg-ink/55 p-5">
            <p className="font-display text-[15px] font-bold uppercase tracking-wide text-brand2 m-0">
              Model Baseline
            </p>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-ink-fg2 m-0">Record</p>
                <p className="mt-1 font-mono text-[20px] font-bold text-white m-0">{formatProjectedRecord(detail)}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-ink-fg2 m-0">AdjO</p>
                <p className={`mt-1 font-mono text-[20px] font-bold m-0 ${getMetricColor(getDisplayAdjO(detail), 'offense')}`}>
                  {formatRating(getDisplayAdjO(detail))}
                </p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-ink-fg2 m-0">AdjD</p>
                <p className={`mt-1 font-mono text-[20px] font-bold m-0 ${getMetricColor(getDisplayAdjD(detail), 'defense')}`}>
                  {formatRating(getDisplayAdjD(detail))}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function SnapshotCard({
  label,
  value,
  detail,
  className = 'text-text-primary',
}: {
  label: string;
  value: string;
  detail: string;
  className?: string;
}) {
  return (
    <div className="rounded-lg border border-ui-border bg-ui-card p-5">
      <p className="table-header m-0 mb-3">{label}</p>
      <p className={`font-mono text-[28px] font-bold leading-none m-0 ${className}`}>{value}</p>
      <p className="mt-3 text-[12px] leading-snug text-text-muted m-0">{detail}</p>
    </div>
  );
}

function ProjectionSnapshot({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const adjNet = getDisplayAdjNet(detail);
  const adjO = getDisplayAdjO(detail);
  const adjD = getDisplayAdjD(detail);

  return (
    <section>
      {sectionTitle('10-second read', 'The Projection At A Glance')}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SnapshotCard
          label="Projected Record"
          value={formatProjectedRecord(detail)}
          detail="Baseline outcome from the roster projection."
        />
        <SnapshotCard
          label="AdjNet"
          value={formatSignedNumber(adjNet)}
          detail="Projected team strength per 100 possessions."
          className={getMetricColor(adjNet, 'net')}
        />
        <SnapshotCard
          label="Offensive Rating"
          value={formatRating(adjO)}
          detail={getEfficiencyInterpretation(adjO, 'offense').label}
          className={getMetricColor(adjO, 'offense')}
        />
        <SnapshotCard
          label="Defensive Rating"
          value={formatRating(adjD)}
          detail={`${getEfficiencyInterpretation(adjD, 'defense').label} - lower is better.`}
          className={getMetricColor(adjD, 'defense')}
        />
        <SnapshotCard
          label="Win Range"
          value={
            detail.projected_floor_wins !== null && detail.projected_ceil_wins !== null
              ? `${detail.projected_floor_wins}-${detail.projected_ceil_wins}W`
              : '-'
          }
          detail="Model floor-to-ceiling band."
        />
        <SnapshotCard
          label="Main Risk"
          value={getTeamRiskSignal(detail)}
          detail="The clearest variable that could move the projection."
        />
      </div>
    </section>
  );
}

function MacFaxReadCard({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const read = detail.macfax_take || generateMacFaxRead(detail);
  const swing = getSwingText(detail);

  return (
    <section>
      <div className="rounded-lg border border-brand/25 bg-brand/5 p-6 sm:p-7">
        <p className="kicker-sport text-brand mb-3">MacFax Read</p>
        <p className="max-w-[880px] text-[18px] leading-relaxed text-text-primary m-0">
          {read}
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="border-t border-brand/20 pt-4">
            <p className="font-display text-[15px] font-bold uppercase tracking-wide text-text-primary m-0">
              What would make this wrong?
            </p>
            <p className="mt-2 text-[14px] leading-relaxed text-text-muted m-0">
              {getTeamRiskSignal(detail)} moving more than the model expects.
            </p>
          </div>
          <div className="border-t border-brand/20 pt-4">
            <p className="font-display text-[15px] font-bold uppercase tracking-wide text-text-primary m-0">
              Season-defining variable
            </p>
            <p className="mt-2 text-[14px] leading-relaxed text-text-muted m-0">{swing}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function EfficiencyProfile({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const cards = [
    { label: 'Adjusted Offense', value: getDisplayAdjO(detail), kind: 'offense' as const },
    { label: 'Adjusted Defense', value: getDisplayAdjD(detail), kind: 'defense' as const },
    { label: 'Adjusted Net', value: getDisplayAdjNet(detail), kind: 'net' as const },
  ];

  return (
    <section>
      {sectionTitle('Efficiency', 'Efficiency Profile', 'Adjusted ratings summarize how the team projects possession by possession.')}
      <div className="grid gap-4 md:grid-cols-3">
        {cards.map((card) => {
          const interpretation = getEfficiencyInterpretation(card.value, card.kind);
          const value = card.kind === 'net' ? formatSignedNumber(card.value) : formatRating(card.value);
          return (
            <div key={card.label} className="rounded-lg border border-ui-border bg-ui-card p-5">
              <p className="table-header m-0 mb-3">{card.label}</p>
              <p className={`font-mono text-[34px] font-bold leading-none m-0 ${getMetricColor(card.value, card.kind)}`}>
                {value}
              </p>
              <p className={`mt-3 text-[13px] font-semibold m-0 ${interpretation.className}`}>
                {interpretation.label}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function FourFactorsCard({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const factors = [
    { key: 'shooting' as const, label: 'Shooting', stat: 'eFG%', team: detail.efg_pct, opp: detail.opp_efg_pct },
    { key: 'ball-security' as const, label: 'Ball Security', stat: 'Turnover%', team: detail.tov_pct, opp: detail.opp_tov_pct },
    { key: 'glass' as const, label: 'Offensive Glass', stat: 'OREB%', team: detail.oreb_pct, opp: detail.opp_oreb_pct },
    { key: 'free-throws' as const, label: 'Free Throws', stat: 'FTA/FGA', team: detail.fta_rate, opp: detail.opp_fta_rate },
  ];

  return (
    <section>
      {sectionTitle('Possession detail', 'Four Factors', 'The four factors show where the rating is coming from: shooting, turnovers, rebounding, and free throws.')}
      <div className="overflow-hidden rounded-lg border border-ui-border bg-ui-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead>
              <tr className="border-b border-ui-border">
                <th className="table-header px-5 py-3 text-left">Factor</th>
                <th className="table-header px-4 py-3 text-center">Team</th>
                <th className="table-header px-4 py-3 text-center">Opponent</th>
                <th className="table-header px-5 py-3 text-right">Edge</th>
              </tr>
            </thead>
            <tbody>
              {factors.map((factor) => {
                const edge = getFourFactorEdge(factor.key, factor.team, factor.opp);
                return (
                  <tr key={factor.key} className="border-b border-ui-border last:border-0">
                    <td className="px-5 py-4">
                      <p className="text-[14px] font-semibold text-text-primary m-0">{factor.label}</p>
                      <p className="mt-1 text-[12px] text-text-muted m-0">{factor.stat}</p>
                    </td>
                    <td className="px-4 py-4 text-center font-mono text-[14px] text-text-primary">
                      {formatPercent(factor.team)}
                    </td>
                    <td className="px-4 py-4 text-center font-mono text-[14px] text-text-primary">
                      {formatPercent(factor.opp)}
                    </td>
                    <td className={`px-5 py-4 text-right text-[13px] font-semibold ${edge.className}`}>
                      {edge.label}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {detail.pace !== null && (
          <div className="border-t border-ui-border px-5 py-3 text-[12px] text-text-muted">
            Pace: <span className="font-mono text-text-primary">{formatRating(detail.pace)}</span> possessions per 48 minutes.
          </div>
        )}
      </div>
    </section>
  );
}

function MoveCard({ move }: { move: TeamOutseasonMove }) {
  const mps = getMpsTier(move.mps_score);
  return (
    <div className="flex items-start justify-between gap-3 border-b border-ui-border py-3 last:border-0">
      <div className="min-w-0">
        <p className="text-[14px] font-semibold text-text-primary m-0">{move.player_name}</p>
        <p className="mt-1 text-[12px] leading-snug text-text-muted m-0">
          {getMoveVerb(move)} · {formatMoveDetail(move)}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${IMPACT_CLASSES[move.impact_rating]}`}>
          {move.impact_rating}
        </span>
        {move.mps_score !== null && (
          <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${mps.className}`}>
            {mps.label}
          </span>
        )}
      </div>
    </div>
  );
}

function OffseasonMovesSection({
  additions,
  departures,
}: {
  additions: TeamOutseasonMove[];
  departures: TeamOutseasonMove[];
}) {
  if (additions.length === 0 && departures.length === 0) return null;

  return (
    <section>
      {sectionTitle('Roster movement', 'Offseason Moves', 'The model weighs offseason movement by projected role, player value, and minutes likely to change hands.')}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-lg border border-ui-border bg-ui-card">
          <div className="border-b border-ui-border px-5 py-4">
            <p className="font-display text-[17px] font-bold uppercase tracking-wide text-positive m-0">Additions</p>
          </div>
          <div className="px-5">
            {additions.length > 0 ? additions.map((move) => <MoveCard key={move.id} move={move} />) : (
              <p className="py-4 text-[13px] text-text-muted m-0">No major additions listed.</p>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-ui-border bg-ui-card">
          <div className="border-b border-ui-border px-5 py-4">
            <p className="font-display text-[17px] font-bold uppercase tracking-wide text-negative m-0">Departures</p>
          </div>
          <div className="px-5">
            {departures.length > 0 ? departures.map((move) => <MoveCard key={move.id} move={move} />) : (
              <p className="py-4 text-[13px] text-text-muted m-0">No major departures listed.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function StatBar({
  value,
  max = 100,
  className = 'bg-brand',
}: {
  value: number;
  max?: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-2 overflow-hidden rounded-full bg-ui-border">
      <div className={`h-full rounded-full ${className}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function RosterConstructionSection({
  detail,
  slots,
}: {
  detail: TeamSeasonOutlookDetail;
  slots: NBAProjectedRosterSlot[];
}) {
  if (
    detail.continuity_score === null &&
    detail.weighted_effective_age === null &&
    detail.top2_bpr_concentration === null
  ) {
    return null;
  }

  const continuity = getContinuityLabel(detail.continuity_score);
  const age = getAgeLabel(detail.weighted_effective_age);
  const concentration = getStarConcentrationLabel(detail.top2_bpr_concentration);
  const topTwo = [...slots]
    .sort((a, b) => (b.projected_wins_added ?? -99) - (a.projected_wins_added ?? -99))
    .slice(0, 2)
    .map((slot) => slot.player_name);

  return (
    <section>
      {sectionTitle('Roster shape', 'Roster Construction')}
      <div className="grid gap-4 lg:grid-cols-3">
        {detail.continuity_score !== null && (
          <div className="rounded-lg border border-ui-border bg-ui-card p-5">
            <p className="table-header m-0 mb-3">Roster Continuity</p>
            <p className="font-mono text-[34px] font-bold leading-none text-text-primary m-0">{formatRating(detail.continuity_score, 0)}%</p>
            <div className="mt-4"><StatBar value={detail.continuity_score} className={continuity.barClass} /></div>
            <p className={`mt-4 text-[13px] font-semibold m-0 ${continuity.className}`}>{continuity.label}</p>
            <p className="mt-2 text-[12px] leading-snug text-text-muted m-0">{continuity.text}</p>
          </div>
        )}
        {detail.weighted_effective_age !== null && (
          <div className="rounded-lg border border-ui-border bg-ui-card p-5">
            <p className="table-header m-0 mb-3">Weighted Age</p>
            <p className="font-mono text-[34px] font-bold leading-none text-text-primary m-0">{formatRating(detail.weighted_effective_age)}</p>
            <div className="mt-4"><StatBar value={Math.max(0, detail.weighted_effective_age - 20)} max={14} className={age.barClass} /></div>
            <p className={`mt-4 text-[13px] font-semibold m-0 ${age.className}`}>{age.label}</p>
            <p className="mt-2 text-[12px] leading-snug text-text-muted m-0">{age.text}</p>
          </div>
        )}
        {concentration.percent !== null && (
          <div className="rounded-lg border border-ui-border bg-ui-card p-5">
            <p className="table-header m-0 mb-3">Star Concentration</p>
            <p className="font-mono text-[34px] font-bold leading-none text-text-primary m-0">{formatRating(concentration.percent, 0)}%</p>
            <div className="mt-4"><StatBar value={concentration.percent} className={concentration.barClass} /></div>
            <p className={`mt-4 text-[13px] font-semibold m-0 ${concentration.className}`}>{concentration.label}</p>
            <p className="mt-2 text-[12px] leading-snug text-text-muted m-0">
              {topTwo.length > 0 ? `Top two: ${topTwo.join(' + ')}.` : concentration.text}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

type CorePlayer = {
  id: string | number;
  name: string;
  position: string;
  bpr: number | null;
  archetype: string | null;
  roleNote: string;
  keyQuestion?: string;
};

function getCoreFive(detail: TeamSeasonOutlookDetail): { title: string; players: CorePlayer[] } {
  if (detail.projected_starters.length > 0) {
    return {
      title: 'Projected Starting Five',
      players: detail.projected_starters.map((starter: ProjectedStarter) => ({
        id: starter.id,
        name: starter.player_name,
        position: starter.position,
        bpr: starter.bpr_rating,
        archetype: null,
        roleNote: starter.role_note || getBprTier(starter.bpr_rating).label,
        keyQuestion: starter.key_question,
      })),
    };
  }

  return {
    title: 'Projected Core Five',
    players: [...detail.projected_roster_slots]
      .sort((a, b) => (b.projected_minutes_share ?? 0) - (a.projected_minutes_share ?? 0))
      .slice(0, 5)
      .map((slot) => ({
        id: slot.id,
        name: slot.player_name,
        position: slot.position || formatArchetype(slot.archetype),
        bpr: slot.projected_bpr,
        archetype: slot.archetype,
        roleNote: getPlayerRoleLabel(slot),
      })),
  };
}

function ProjectedCoreFiveSection({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const core = getCoreFive(detail);
  if (core.players.length === 0) return null;

  return (
    <section>
      {sectionTitle('Rotation core', core.title)}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {core.players.map((player) => (
          <div key={player.id} className="rounded-lg border border-ui-border bg-ui-card p-4">
            <div className="mb-4 flex items-center justify-between gap-2">
              <span className="kicker-sport text-brand text-[11px]">{player.position || 'Core'}</span>
              <span className={`font-mono text-[12px] font-semibold ${getBprTier(player.bpr).className}`}>
                {formatSignedNumber(player.bpr)} BPR
              </span>
            </div>
            <p className="text-[15px] font-semibold leading-tight text-text-primary m-0">{player.name}</p>
            <p className="mt-2 text-[12px] leading-snug text-text-muted m-0">{player.roleNote}</p>
            {player.keyQuestion && (
              <p className="mt-3 border-t border-ui-border pt-3 text-[12px] leading-snug text-brand m-0">
                {player.keyQuestion}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function RotationRow({ slot }: { slot: NBAProjectedRosterSlot }) {
  return (
    <tr className="border-b border-ui-border last:border-0 hover:bg-ui-surface/50">
      <td className="px-4 py-3">
        <p className="text-[13px] font-semibold text-text-primary m-0">{slot.player_name}</p>
        <p className="mt-1 text-[11px] text-text-muted m-0">{slot.position || 'Position TBD'}</p>
      </td>
      <td className="px-3 py-3 text-[12px] text-text-muted">{formatArchetype(slot.archetype)}</td>
      <td className={`px-3 py-3 text-center font-mono text-[13px] font-semibold ${getBprTier(slot.projected_bpr).className}`}>
        {formatSignedNumber(slot.projected_bpr)}
      </td>
      <td className={`px-3 py-3 text-center font-mono text-[13px] ${getBprTier(slot.projected_obpr).className}`}>
        {formatSignedNumber(slot.projected_obpr)}
      </td>
      <td className={`px-3 py-3 text-center font-mono text-[13px] ${getBprTier(slot.projected_dbpr).className}`}>
        {formatSignedNumber(slot.projected_dbpr)}
      </td>
      <td className="px-3 py-3 text-center font-mono text-[13px] text-text-muted">{formatMinutesShare(slot.projected_minutes_share)}</td>
      <td className="px-4 py-3 text-right">
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${ACQUISITION_CLASSES[slot.acquisition_type]}`}>
          {ACQUISITION_LABELS[slot.acquisition_type]}
        </span>
      </td>
    </tr>
  );
}

function RotationTable({ slots }: { slots: NBAProjectedRosterSlot[] }) {
  if (slots.length === 0) return null;
  const sorted = [...slots].sort((a, b) => (b.projected_minutes_share ?? 0) - (a.projected_minutes_share ?? 0));
  const top = sorted.slice(0, 12);
  const rest = sorted.slice(12);

  return (
    <section>
      {sectionTitle('Projected minutes', 'Projected Rotation', 'BPR scale: +5 All-Star, +2 starter, 0 replacement-level, negative rotation drag.')}
      <div className="overflow-hidden rounded-lg border border-ui-border bg-ui-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px]">
            <thead>
              <tr className="border-b border-ui-border">
                <th className="table-header px-4 py-3 text-left">Player</th>
                <th className="table-header px-3 py-3 text-left">Role</th>
                <th className="table-header px-3 py-3 text-center">BPR</th>
                <th className="table-header px-3 py-3 text-center">OBPR</th>
                <th className="table-header px-3 py-3 text-center">DBPR</th>
                <th className="table-header px-3 py-3 text-center">Min%</th>
                <th className="table-header px-4 py-3 text-right">Type</th>
              </tr>
            </thead>
            <tbody>
              {top.map((slot) => <RotationRow key={slot.id} slot={slot} />)}
            </tbody>
          </table>
        </div>
        {rest.length > 0 && (
          <details className="group border-t border-ui-border">
            <summary className="flex cursor-pointer list-none items-center justify-center gap-2 px-4 py-3 text-[13px] font-semibold text-brand">
              Show full roster ({rest.length} more)
              <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" strokeWidth={1.75} />
            </summary>
            <div className="overflow-x-auto border-t border-ui-border">
              <table className="w-full min-w-[760px]">
                <tbody>{rest.map((slot) => <RotationRow key={slot.id} slot={slot} />)}</tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </section>
  );
}

function DevelopmentWatchSection({ players }: { players: DevelopmentWatchPlayer[] }) {
  if (players.length === 0) return null;
  const drafted = players.filter((player) => player.acquisition_type === 'drafted');
  const under25 = players.filter((player) => player.acquisition_type !== 'drafted');

  return (
    <section>
      {sectionTitle('Next layer', 'Development Watch')}
      <div className="grid gap-5 lg:grid-cols-2">
        {drafted.length > 0 && (
          <div className="rounded-lg border border-ui-border bg-ui-card p-5">
            <p className="font-display text-[17px] font-bold uppercase tracking-wide text-brand m-0">Draft Class</p>
            <div className="mt-4 grid gap-3">
              {drafted.map((player) => {
                const mps = getMpsTier(player.mps_score);
                return (
                  <div key={player.player_name} className="rounded-lg border border-ui-border bg-ui-surface p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[14px] font-semibold text-text-primary m-0">{player.player_name}</p>
                        <p className="mt-1 text-[12px] text-text-muted m-0">
                          {getPickLabel(player.round_number, player.overall_pick)} · {formatArchetype(player.archetype)}
                        </p>
                      </div>
                      <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${mps.className}`}>
                        {mps.label}
                      </span>
                    </div>
                    <p className="mt-3 text-[12px] leading-snug text-text-muted m-0">
                      MPS {formatRating(player.mps_score)} · {getDevelopmentRead(player)}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {under25.length > 0 && (
          <div className="rounded-lg border border-ui-border bg-ui-card p-5">
            <p className="font-display text-[17px] font-bold uppercase tracking-wide text-brandBlue m-0">Under-25 Returners</p>
            <div className="mt-4 grid gap-3">
              {under25.map((player) => (
                <div key={player.player_name} className="rounded-lg border border-ui-border bg-ui-surface p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[14px] font-semibold text-text-primary m-0">{player.player_name}</p>
                      <p className="mt-1 text-[12px] text-text-muted m-0">
                        Age {player.age ?? '-'} · {formatArchetype(player.archetype)}
                      </p>
                    </div>
                    <span className={`font-mono text-[13px] font-semibold ${getBprTier(player.projected_bpr).className}`}>
                      {formatSignedNumber(player.projected_bpr)}
                    </span>
                  </div>
                  <p className="mt-3 text-[12px] leading-snug text-text-muted m-0">
                    {getDevelopmentRead(player)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function BottomLineOutlook({ detail }: { detail: TeamSeasonOutlookDetail }) {
  if (detail.projected_wins === null && !detail.macfax_take) return null;
  const adjNet = getDisplayAdjNet(detail);

  return (
    <section>
      {sectionTitle('Final read', 'Bottom Line')}
      <div className="rounded-lg border border-ui-border bg-ui-card p-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr] lg:items-center">
          <div>
            <p className="table-header m-0 mb-2">Projected Record</p>
            <p className="font-mono text-[34px] font-bold leading-none text-text-primary m-0">
              {formatRecord(detail.projected_wins, detail.projected_losses)}
            </p>
            <div className="mt-4 flex flex-wrap gap-4 text-[13px] text-text-muted">
              <span>AdjNet <span className={`font-mono font-semibold ${getMetricColor(adjNet, 'net')}`}>{formatSignedNumber(adjNet)}</span></span>
              <span>AdjO <span className={`font-mono font-semibold ${getMetricColor(getDisplayAdjO(detail), 'offense')}`}>{formatRating(getDisplayAdjO(detail))}</span></span>
              <span>AdjD <span className={`font-mono font-semibold ${getMetricColor(getDisplayAdjD(detail), 'defense')}`}>{formatRating(getDisplayAdjD(detail))}</span></span>
            </div>
          </div>
          <WinRangeBar
            floor={detail.projected_floor_wins}
            baseline={detail.projected_wins}
            ceiling={detail.projected_ceil_wins}
          />
        </div>
        <p className="mt-6 border-t border-ui-border pt-5 text-[15px] leading-relaxed text-text-primary m-0">
          {detail.macfax_take || generateMacFaxRead(detail)}
        </p>
        <blockquote className="mt-5 border-l-4 border-brand pl-4 text-[14px] leading-relaxed text-text-muted m-0">
          {getSwingText(detail)}
        </blockquote>
      </div>
    </section>
  );
}

function CapSnapshot({ detail }: { detail: TeamSeasonOutlookDetail }) {
  if (detail.cap_total_salary === null || detail.cap_status_tier === null) return null;
  const tier = detail.cap_status_tier;

  return (
    <section>
      {sectionTitle('Roster flexibility', 'Cap Snapshot')}
      <div className="rounded-lg border border-ui-border bg-ui-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded bg-ui-surface px-2.5 py-1 text-[11px] font-semibold text-text-primary border border-ui-border">
            {CAP_TIER_LABELS[tier]}
          </span>
          <span className="font-mono text-[24px] font-bold text-text-primary">{formatSalary(detail.cap_total_salary)}</span>
        </div>
        <p className="mt-3 text-[13px] leading-relaxed text-text-muted m-0">{CAP_TIER_TEXT[tier]}</p>
      </div>
    </section>
  );
}

export default async function TeamOutlookPage({ params }: Props) {
  const { slug } = await params;

  let detail: TeamSeasonOutlookDetail;
  try {
    detail = await nbaApi.getTeamOutlook(slug);
  } catch {
    notFound();
  }

  const additions = detail.offseason_moves.filter((move) => ADDITION_TYPES.includes(move.move_type));
  const departures = detail.offseason_moves.filter((move) => !ADDITION_TYPES.includes(move.move_type));

  return (
    <div>
      <TeamHero detail={detail} />

      <main className="max-w-[1240px] mx-auto px-5 sm:px-8 py-8 sm:py-10 pb-16 flex flex-col gap-10">
        <ProjectionSnapshot detail={detail} />
        <MacFaxReadCard detail={detail} />
        <EfficiencyProfile detail={detail} />
        <FourFactorsCard detail={detail} />
        <RosterConstructionSection detail={detail} slots={detail.projected_roster_slots} />
        <OffseasonMovesSection additions={additions} departures={departures} />
        <ProjectedCoreFiveSection detail={detail} />
        <RotationTable slots={detail.projected_roster_slots} />
        <DevelopmentWatchSection players={detail.development_watch} />
        <BottomLineOutlook detail={detail} />
        <CapSnapshot detail={detail} />

        <div className="border-t border-ui-border pt-6">
          <Link
            href="/nba/teams"
            className="inline-flex items-center gap-2 text-[13px] font-semibold text-brand no-underline transition-colors hover:text-brand-hover"
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
            All Team Outlooks
          </Link>
        </div>
      </main>
    </div>
  );
}

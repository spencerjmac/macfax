import { notFound } from 'next/navigation';
import Link from 'next/link';
import type { Metadata } from 'next';
import type {
  TeamSeasonOutlookDetail,
  TeamOutseasonMove,
  ProjectedStarter,
  NBAProjectedRosterSlot,
  CapStatusTier,
  OutlookTier,
} from '@/types/nba';
import { nbaApi } from '@/lib/nba-api';
import TeamLogo from '@/components/TeamLogo';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  return { title: `Team Outlook | macfax` };
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const TIER_LABELS: Record<OutlookTier, string> = {
  title_contender: 'Title Contender',
  playoff_contender: 'Playoff Contender',
  bubble: 'Bubble Team',
  lottery: 'Lottery Team',
  rebuilding: 'Rebuilding',
};

const TIER_CLASSES: Record<OutlookTier, string> = {
  title_contender: 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30',
  playoff_contender: 'bg-brand/20 text-brand border border-brand/30',
  bubble: 'bg-amber-500/20 text-amber-500 border border-amber-500/30',
  lottery: 'bg-orange-400/20 text-orange-400 border border-orange-400/30',
  rebuilding: 'bg-ui-surface text-text-muted border border-ui-border',
};

const MOVE_TYPE_LABELS: Record<TeamOutseasonMove['move_type'], string> = {
  signed: 'Signed',
  lost: 'Lost',
  drafted: 'Drafted',
  traded_in: 'Acquired',
  traded_out: 'Traded Away',
  extended: 'Extended',
  waived: 'Waived',
};

const IMPACT_CLASSES: Record<TeamOutseasonMove['impact_rating'], string> = {
  high: 'bg-positive/15 text-positive border border-positive/25',
  medium: 'bg-brand/15 text-brand border border-brand/25',
  low: 'bg-ui-surface text-text-muted border border-ui-border',
};

const ADDITION_TYPES: TeamOutseasonMove['move_type'][] = [
  'signed', 'drafted', 'traded_in', 'extended',
];

function fmtRating(v: number | null): string {
  if (v === null) return '—';
  return v.toFixed(1);
}

function netColor(v: number | null): string {
  if (v === null) return '';
  if (v > 0) return 'text-positive';
  if (v < 0) return 'text-negative';
  return 'text-text-muted';
}

function fmtNet(v: number | null): string {
  if (v === null) return '—';
  const s = v.toFixed(1);
  return v > 0 ? `+${s}` : s;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  rank,
  colorClass = '',
}: {
  label: string;
  value: string;
  rank?: number;
  colorClass?: string;
}) {
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg p-5 flex flex-col gap-2">
      <p className="table-header text-text-muted m-0">{label}</p>
      <p className={`font-mono text-[2.25rem] font-bold leading-none m-0 ${colorClass}`}>
        {value}
      </p>
      {rank !== undefined && (
        <p className="text-[12px] text-text-muted m-0">
          #{rank} <span className="text-text-muted/60">in league</span>
        </p>
      )}
    </div>
  );
}

function FourFactorRow({
  label,
  teamVal,
  oppVal,
}: {
  label: string;
  teamVal: number | null;
  oppVal: number | null;
}) {
  const teamLeads =
    teamVal !== null && oppVal !== null && teamVal > oppVal;
  const oppLeads =
    teamVal !== null && oppVal !== null && oppVal > teamVal;
  return (
    <tr className="border-b border-ui-border last:border-0">
      <td className="py-2.5 pr-4 text-[13px] text-text-muted w-1/3">{label}</td>
      <td
        className={`py-2.5 text-center font-mono text-[13px] font-medium ${
          teamLeads ? 'text-positive' : oppLeads ? 'text-negative' : 'text-text-primary'
        }`}
      >
        {teamVal !== null ? `${teamVal.toFixed(1)}%` : '—'}
      </td>
      <td
        className={`py-2.5 text-center font-mono text-[13px] font-medium ${
          oppLeads ? 'text-positive' : teamLeads ? 'text-negative' : 'text-text-primary'
        }`}
      >
        {oppVal !== null ? `${oppVal.toFixed(1)}%` : '—'}
      </td>
    </tr>
  );
}

function MoveCard({ move }: { move: TeamOutseasonMove }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-ui-border last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-[14px] font-medium text-text-primary m-0">{move.player_name}</p>
        {move.detail && (
          <p className="text-[12px] text-text-muted m-0 mt-0.5">{move.detail}</p>
        )}
      </div>
      <span
        className={`text-[11px] font-medium px-2 py-0.5 rounded flex-shrink-0 ${IMPACT_CLASSES[move.impact_rating]}`}
      >
        {move.impact_rating}
      </span>
    </div>
  );
}

function StarterCard({ starter }: { starter: ProjectedStarter }) {
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="kicker-sport text-brand text-[11px]">{starter.position}</span>
        {starter.bpr_rating !== null && (
          <span className="font-mono text-[12px] text-text-muted">
            {starter.bpr_rating > 0 ? '+' : ''}{starter.bpr_rating.toFixed(1)} BPR
          </span>
        )}
      </div>
      <p className="text-[15px] font-semibold text-text-primary m-0 leading-tight">
        {starter.player_name}
      </p>
      {starter.role_note && (
        <p className="text-[12px] text-text-muted m-0">{starter.role_note}</p>
      )}
      {starter.key_question && (
        <p className="text-[12px] text-brand/80 m-0 italic border-t border-ui-border pt-2 mt-1">
          {starter.key_question}
        </p>
      )}
    </div>
  );
}

// ── BPR color helper ─────────────────────────────────────────────────────────
function bprColor(v: number | null): string {
  if (v === null) return 'text-text-muted';
  if (v >= 5) return 'text-emerald-400';
  if (v >= 3) return 'text-teal-400';
  if (v >= 0) return 'text-text-primary';
  return 'text-negative';
}

function fmtBpr(v: number | null): string {
  if (v === null) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(1);
}

// ── Acquisition type badge ────────────────────────────────────────────────────
const ACQTYPE_STYLES: Record<NBAProjectedRosterSlot['acquisition_type'], string> = {
  returner: 'bg-blue-500/15 text-blue-400 border border-blue-500/25',
  extended: 'bg-blue-500/15 text-blue-400 border border-blue-500/25',
  signed: 'bg-positive/15 text-positive border border-positive/25',
  traded_in: 'bg-amber-500/15 text-amber-400 border border-amber-500/25',
  drafted: 'bg-purple-500/15 text-purple-400 border border-purple-500/25',
};
const ACQTYPE_LABELS: Record<NBAProjectedRosterSlot['acquisition_type'], string> = {
  returner: 'Rtr',
  extended: 'Ext',
  signed: 'FA',
  traded_in: 'Trd',
  drafted: 'Rk',
};

// ── Cap thresholds 2026-27 ────────────────────────────────────────────────────
const CAP_THRESHOLDS = [
  { label: 'Floor', value: 149_000_000, color: '#6b7280' },
  { label: 'Cap', value: 165_000_000, color: '#6b7280' },
  { label: 'Tax', value: 201_000_000, color: '#eab308' },
  { label: '1st Apron', value: 209_000_000, color: '#f97316' },
  { label: '2nd Apron', value: 222_000_000, color: '#ef4444' },
];
const CAP_MIN = 130_000_000;
const CAP_MAX = 240_000_000;
const CAP_TIER_LABELS: Record<CapStatusTier, string> = {
  under_cap: 'Under Cap',
  over_cap: 'Over Cap',
  taxpayer: 'Luxury Taxpayer',
  first_apron: 'First Apron',
  second_apron: 'Second Apron',
};
const CAP_TIER_CONSEQUENCES: Record<CapStatusTier, string> = {
  under_cap: 'Full cap room; can sign any player.',
  over_cap: 'Non-Taxpayer MLE (~$15M); sign-and-trade in/out.',
  taxpayer: 'Taxpayer MLE (~$6M); paying tax dollar-for-dollar.',
  first_apron: 'No BAE/Non-Taxpayer MLE; sign-and-trade restricted.',
  second_apron: 'Cannot aggregate salaries in trades; no buyout signings.',
};
const CAP_TIER_CLASSES: Record<CapStatusTier, string> = {
  under_cap: 'bg-ui-surface text-text-muted border border-ui-border',
  over_cap: 'bg-amber-500/15 text-amber-400 border border-amber-500/25',
  taxpayer: 'bg-orange-500/15 text-orange-400 border border-orange-500/25',
  first_apron: 'bg-orange-600/15 text-orange-500 border border-orange-600/25',
  second_apron: 'bg-negative/15 text-negative border border-negative/25',
};

function fmtSalaryM(v: number): string {
  return `$${(v / 1_000_000).toFixed(0)}M`;
}

// ── Projected Roster Table ────────────────────────────────────────────────────
function ProjectedRosterTable({ slots }: { slots: NBAProjectedRosterSlot[] }) {
  const sorted = [...slots].sort(
    (a, b) => (b.projected_minutes_share ?? 0) - (a.projected_minutes_share ?? 0),
  );
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-ui-border">
              <th className="table-header text-left py-2.5 px-4">Player</th>
              <th className="table-header text-center py-2.5 px-3">Arch</th>
              <th className="table-header text-center py-2.5 px-3">OBPR</th>
              <th className="table-header text-center py-2.5 px-3">DBPR</th>
              <th className="table-header text-center py-2.5 px-3">BPR</th>
              <th className="table-header text-center py-2.5 px-3">Min%</th>
              <th className="table-header text-center py-2.5 px-3">W+</th>
              <th className="table-header text-center py-2.5 px-3">Type</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((slot) => (
              <tr key={slot.id} className="border-b border-ui-border last:border-0 hover:bg-ui-surface/40">
                <td className="py-2 px-4">
                  <span className="text-[13px] font-medium text-text-primary">{slot.player_name}</span>
                </td>
                <td className="py-2 px-3 text-center">
                  {slot.archetype ? (
                    <span className="text-[11px] text-text-muted font-mono uppercase tracking-wide">
                      {slot.archetype.replace(/_/g, ' ')}
                    </span>
                  ) : (
                    <span className="text-[11px] text-text-muted">—</span>
                  )}
                </td>
                <td className={`py-2 px-3 text-center font-mono text-[13px] ${bprColor(slot.projected_obpr)}`}>
                  {fmtBpr(slot.projected_obpr)}
                </td>
                <td className={`py-2 px-3 text-center font-mono text-[13px] ${bprColor(slot.projected_dbpr)}`}>
                  {fmtBpr(slot.projected_dbpr)}
                </td>
                <td className={`py-2 px-3 text-center font-mono text-[13px] font-semibold ${bprColor(slot.projected_bpr)}`}>
                  {fmtBpr(slot.projected_bpr)}
                </td>
                <td className="py-2 px-3 text-center font-mono text-[13px] text-text-muted">
                  {slot.projected_minutes_share !== null
                    ? `${((slot.projected_minutes_share / 5) * 100).toFixed(0)}%`
                    : '—'}
                </td>
                <td className={`py-2 px-3 text-center font-mono text-[13px] ${slot.projected_wins_added !== null && slot.projected_wins_added >= 0 ? 'text-positive' : 'text-negative'}`}>
                  {slot.projected_wins_added !== null
                    ? (slot.projected_wins_added >= 0 ? '+' : '') + slot.projected_wins_added.toFixed(1)
                    : '—'}
                </td>
                <td className="py-2 px-3 text-center">
                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${ACQTYPE_STYLES[slot.acquisition_type]}`}>
                    {ACQTYPE_LABELS[slot.acquisition_type]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── StatBar ───────────────────────────────────────────────────────────────────
function StatBar({
  value,
  max = 100,
  colorClass = 'bg-brand',
}: {
  value: number;
  max?: number;
  colorClass?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="h-1.5 bg-ui-border rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Roster Construction Section ───────────────────────────────────────────────
function RosterConstructionSection({
  detail,
  slots,
}: {
  detail: TeamSeasonOutlookDetail;
  slots: NBAProjectedRosterSlot[];
}) {
  const continuity = detail.continuity_score;
  const age = detail.weighted_effective_age;
  const concentration = detail.top2_bpr_concentration;

  // Top-2 players by wins added for the concentration label
  const sorted = [...slots].sort(
    (a, b) => (b.projected_wins_added ?? -99) - (a.projected_wins_added ?? -99),
  );
  const top2Names = sorted.slice(0, 2).map((s) => s.player_name);

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* Continuity */}
      {continuity !== null && (
        <div className="bg-ui-card border border-ui-border rounded-lg p-5 flex flex-col gap-3">
          <p className="table-header text-text-muted m-0">Roster Continuity</p>
          <p className="font-mono text-[2rem] font-bold leading-none text-text-primary m-0">
            {continuity.toFixed(0)}
            <span className="text-[1rem] font-normal text-text-muted ml-1">%</span>
          </p>
          <StatBar
            value={continuity}
            colorClass={continuity >= 70 ? 'bg-positive' : continuity >= 40 ? 'bg-brand' : 'bg-amber-500'}
          />
          <p className="text-[11px] text-text-muted m-0">
            {continuity >= 70 ? 'High continuity — chemistry advantage' :
             continuity >= 40 ? 'Mixed returning core' :
             'Low continuity — new-roster integration risk'}
          </p>
        </div>
      )}

      {/* Weighted Age */}
      {age !== null && (
        <div className="bg-ui-card border border-ui-border rounded-lg p-5 flex flex-col gap-3">
          <p className="table-header text-text-muted m-0">Weighted Avg Age</p>
          <p className="font-mono text-[2rem] font-bold leading-none text-text-primary m-0">
            {age.toFixed(1)}
          </p>
          {/* Age spectrum: 20–36, peak window 27–29 highlighted */}
          <div className="relative h-1.5 bg-ui-border rounded-full overflow-visible">
            {/* Peak window band */}
            <div
              className="absolute top-0 h-full bg-positive/30 rounded"
              style={{ left: `${((27 - 20) / 16) * 100}%`, width: `${((29 - 27) / 16) * 100}%` }}
            />
            {/* Marker */}
            <div
              className="absolute top-[-3px] w-[3px] h-[9px] bg-brand rounded-full"
              style={{ left: `${Math.min(100, Math.max(0, ((age - 20) / 16) * 100))}%` }}
            />
          </div>
          <p className="text-[11px] text-text-muted m-0">
            {age < 25 ? 'Young — ascending' :
             age <= 29 ? 'Peak window (27–29)' :
             age <= 32 ? 'Aging window' :
             'Veteran core'}
          </p>
        </div>
      )}

      {/* Star Concentration */}
      {concentration !== null && (
        <div className="bg-ui-card border border-ui-border rounded-lg p-5 flex flex-col gap-3">
          <p className="table-header text-text-muted m-0">Star Concentration</p>
          <p className={`font-mono text-[2rem] font-bold leading-none m-0 ${concentration >= 0.65 ? 'text-amber-400' : 'text-text-primary'}`}>
            {(concentration * 100).toFixed(0)}
            <span className="text-[1rem] font-normal text-text-muted ml-1">%</span>
          </p>
          <StatBar
            value={concentration * 100}
            colorClass={concentration >= 0.65 ? 'bg-amber-500' : 'bg-brand'}
          />
          {top2Names.length > 0 && (
            <p className="text-[11px] text-text-muted m-0">
              Top 2: {top2Names.join(' + ')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Cap Snapshot ──────────────────────────────────────────────────────────────
function CapSnapshotSection({ detail }: { detail: TeamSeasonOutlookDetail }) {
  const total = detail.cap_total_salary;
  const tier = detail.cap_status_tier;
  if (total === null || tier === null) return null;

  const pct = (v: number) =>
    Math.min(100, Math.max(0, ((v - CAP_MIN) / (CAP_MAX - CAP_MIN)) * 100));
  const teamPct = pct(total);

  return (
    <section>
      <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
        Cap Snapshot
      </h2>
      <div className="bg-ui-card border border-ui-border rounded-lg p-6 flex flex-col gap-5">
        {/* Tier badge + total + consequence */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-[11px] font-medium px-2.5 py-1 rounded ${CAP_TIER_CLASSES[tier]}`}>
            {CAP_TIER_LABELS[tier]}
          </span>
          <span className="font-mono text-[18px] font-bold text-text-primary">
            {fmtSalaryM(total)}
          </span>
          <span className="text-[13px] text-text-muted">{CAP_TIER_CONSEQUENCES[tier]}</span>
        </div>

        {/* Cap meter bar */}
        <div className="relative h-3 bg-ui-border rounded-full overflow-visible">
          {/* Color zones */}
          <div className="absolute inset-0 flex rounded-full overflow-hidden">
            <div className="bg-positive/20" style={{ width: `${pct(165_000_000)}%` }} />
            <div className="bg-amber-500/20" style={{ width: `${pct(201_000_000) - pct(165_000_000)}%` }} />
            <div className="bg-orange-500/20" style={{ width: `${pct(209_000_000) - pct(201_000_000)}%` }} />
            <div className="bg-orange-700/20" style={{ width: `${pct(222_000_000) - pct(209_000_000)}%` }} />
            <div className="bg-negative/20 flex-1" />
          </div>
          {/* Threshold ticks */}
          {CAP_THRESHOLDS.map((t) => (
            <div
              key={t.label}
              className="absolute top-0 bottom-0 w-[2px]"
              style={{ left: `${pct(t.value)}%`, background: t.color }}
            />
          ))}
          {/* Team marker */}
          <div
            className="absolute top-[-4px] w-[4px] h-[19px] bg-brand rounded-full shadow"
            style={{ left: `${teamPct}%`, marginLeft: '-2px' }}
          />
        </div>

        {/* Threshold labels */}
        <div className="relative h-4">
          {CAP_THRESHOLDS.map((t) => (
            <div
              key={t.label}
              className="absolute text-[10px] text-text-muted"
              style={{ left: `${pct(t.value)}%`, transform: 'translateX(-50%)' }}
            >
              {t.label}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default async function TeamOutlookPage({ params }: Props) {
  const { slug } = await params;

  let detail: TeamSeasonOutlookDetail;
  try {
    detail = await nbaApi.getTeamOutlook(slug);
  } catch {
    notFound();
  }

  const additions = detail.offseason_moves.filter((m) =>
    ADDITION_TYPES.includes(m.move_type),
  );
  const departures = detail.offseason_moves.filter(
    (m) => !ADDITION_TYPES.includes(m.move_type),
  );

  return (
    <div>
      {/* ── Section 1: Header ─────────────────────────────────────────── */}
      <div
        className="relative overflow-hidden"
        style={{ background: `linear-gradient(135deg, ${detail.primary_color}22 0%, var(--ink) 60%)` }}
      >
        <div className="bg-ink/90 relative">
          <div className="max-w-[1240px] mx-auto px-8 py-10">
            <div className="flex items-start gap-6">
              {detail.logo_url && (
                <TeamLogo
                  src={detail.logo_url}
                  alt={detail.team_abbr}
                  width={72}
                  height={72}
                  className="object-contain flex-shrink-0 mt-1"
                  fallbackColor={detail.primary_color}
                />
              )}
              <div className="flex-1 min-w-0">
                <p className="kicker-sport text-brand mb-2">
                  {detail.conference}ern Conference · 2025-26 Season Outlook
                </p>
                <h1 className="font-display font-bold text-[clamp(28px,4vw,52px)] leading-none uppercase tracking-[0.005em] text-ink-fg m-0">
                  {detail.team_name}
                </h1>
                <div className="flex items-center gap-4 mt-3 flex-wrap">
                  {detail.wins !== null && detail.losses !== null && (
                    <span className="font-mono text-[15px] text-ink-fg2">
                      {detail.wins}–{detail.losses}
                    </span>
                  )}
                  <span
                    className={`font-mono text-[22px] font-bold ${netColor(detail.adj_net_rating)}`}
                  >
                    {fmtNet(detail.adj_net_rating)}
                    <span className="text-[13px] font-normal text-ink-fg2 ml-1">AdjNet</span>
                  </span>
                  <span className="font-mono text-[13px] text-ink-fg2">
                    #{detail.league_rank} in league
                  </span>
                  {detail.outlook_tier && (
                    <span
                      className={`text-[11px] font-medium px-2.5 py-1 rounded ${TIER_CLASSES[detail.outlook_tier]}`}
                    >
                      {TIER_LABELS[detail.outlook_tier]}
                    </span>
                  )}
                </div>
                {detail.season_headline && (
                  <p className="text-[16px] text-ink-fg/80 mt-4 m-0 leading-snug max-w-[640px]">
                    {detail.season_headline}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
        {/* 4px teal separator */}
        <div className="h-1 w-full bg-brand" />
      </div>

      {/* ── Content ─────────────────────────────────────────────────────── */}
      <div className="max-w-[1240px] mx-auto px-8 py-8 pb-16 flex flex-col gap-10">

        {/* ── Section 2: Efficiency Profile ─────────────────────────────── */}
        <section>
          <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
            Efficiency Profile
          </h2>

          {/* Three stat cards */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <StatCard
              label="ADJ OFFENSIVE RTG"
              value={fmtRating(detail.adj_offensive_rating)}
            />
            <StatCard
              label="ADJ DEFENSIVE RTG"
              value={fmtRating(detail.adj_defensive_rating)}
            />
            <StatCard
              label="ADJ NET RTG"
              value={fmtNet(detail.adj_net_rating)}
              rank={detail.league_rank}
              colorClass={netColor(detail.adj_net_rating)}
            />
          </div>

          {/* Four Factors table */}
          <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
            <div className="px-5 py-3 border-b border-ui-border">
              <p className="table-header text-text-muted m-0">Four Factors</p>
            </div>
            <div className="px-5">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ui-border">
                    <th className="table-header text-left py-2.5 w-1/3">Factor</th>
                    <th className="table-header text-center py-2.5">Team</th>
                    <th className="table-header text-center py-2.5">Opponent</th>
                  </tr>
                </thead>
                <tbody>
                  <FourFactorRow
                    label="Eff. Field Goal %"
                    teamVal={detail.efg_pct}
                    oppVal={detail.opp_efg_pct}
                  />
                  <FourFactorRow
                    label="Turnover %"
                    teamVal={
                      detail.tov_pct !== null ? -detail.tov_pct : null
                    }
                    oppVal={
                      detail.opp_tov_pct !== null ? -detail.opp_tov_pct : null
                    }
                  />
                  <FourFactorRow
                    label="Off. Rebound %"
                    teamVal={detail.oreb_pct}
                    oppVal={detail.opp_oreb_pct}
                  />
                  <FourFactorRow
                    label="FT Rate (FTA/FGA)"
                    teamVal={detail.fta_rate}
                    oppVal={detail.opp_fta_rate}
                  />
                </tbody>
              </table>
            </div>
            {detail.pace !== null && (
              <div className="px-5 py-3 border-t border-ui-border">
                <span className="text-[12px] text-text-muted">
                  Pace:{' '}
                  <span className="font-mono text-text-primary">
                    {detail.pace.toFixed(1)}
                  </span>{' '}
                  poss/48 min
                </span>
              </div>
            )}
          </div>
        </section>

        {/* ── Section 3: Offseason Moves (conditional) ──────────────────── */}
        {detail.offseason_moves.length > 0 && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              Offseason Moves
            </h2>
            <div className="grid grid-cols-2 gap-6">
              {additions.length > 0 && (
                <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
                  <div className="px-5 py-3 border-b border-ui-border">
                    <p className="table-header text-positive m-0">Additions</p>
                  </div>
                  <div className="px-5">
                    {additions.map((m) => (
                      <MoveCard key={m.id} move={m} />
                    ))}
                  </div>
                </div>
              )}
              {departures.length > 0 && (
                <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
                  <div className="px-5 py-3 border-b border-ui-border">
                    <p className="table-header text-negative m-0">Departures</p>
                  </div>
                  <div className="px-5">
                    {departures.map((m) => (
                      <MoveCard key={m.id} move={m} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── Section 3b: Roster Construction ──────────────────────────────── */}
        {(detail.continuity_score !== null ||
          detail.weighted_effective_age !== null ||
          detail.top2_bpr_concentration !== null) && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              Roster Construction
            </h2>
            <RosterConstructionSection detail={detail} slots={detail.projected_roster_slots} />
          </section>
        )}

        {/* ── Section 4: Projected Starting Five (conditional) ──────────── */}
        {detail.projected_starters.length > 0 && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              Projected Starting Five
            </h2>
            <div className="grid grid-cols-5 gap-3">
              {detail.projected_starters.map((s) => (
                <StarterCard key={s.id} starter={s} />
              ))}
            </div>
          </section>
        )}

        {/* ── Section 4b: Projected Roster ─────────────────────────────────── */}
        {detail.projected_roster_slots.length > 0 && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              2026-27 Projected Roster
            </h2>
            <ProjectedRosterTable slots={detail.projected_roster_slots} />
          </section>
        )}

        {/* ── Section 5: Development Spotlight (conditional) ────────────── */}
        {detail.development_spotlight_player && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              Development Spotlight
            </h2>
            <div className="bg-ui-card border border-ui-border rounded-lg p-6">
              <p className="kicker-sport text-brand mb-2">
                {detail.development_spotlight_player}
              </p>
              {detail.development_spotlight_text && (
                <p className="text-[15px] text-text-primary leading-relaxed m-0">
                  {detail.development_spotlight_text}
                </p>
              )}
            </div>
          </section>
        )}

        {/* ── Section 6: 2026-27 Outlook ────────────────────────────────────── */}
        {(detail.projected_wins !== null || detail.macfax_take) && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              2026-27 Outlook
            </h2>
            <div className="bg-ui-card border border-ui-border rounded-lg p-6 flex flex-col gap-5">
              {detail.projected_wins !== null && (
                <div className="flex flex-col gap-3">
                  {/* Projected record + ratings row */}
                  <div className="flex items-center gap-4 flex-wrap">
                    <div>
                      <p className="table-header text-text-muted m-0 mb-1">Projected Record</p>
                      <span className="font-mono text-[22px] font-bold text-text-primary">
                        {detail.projected_wins}–{detail.projected_losses ?? '?'}
                      </span>
                    </div>
                    {detail.projected_adj_net !== null && (
                      <div>
                        <p className="table-header text-text-muted m-0 mb-1">AdjEM</p>
                        <span className={`font-mono text-[18px] font-semibold ${netColor(detail.projected_adj_net)}`}>
                          {fmtNet(detail.projected_adj_net)}
                        </span>
                      </div>
                    )}
                    {detail.projected_adj_o !== null && (
                      <div>
                        <p className="table-header text-text-muted m-0 mb-1">AdjO</p>
                        <span className="font-mono text-[18px] font-semibold text-positive">
                          {fmtRating(detail.projected_adj_o)}
                        </span>
                      </div>
                    )}
                    {detail.projected_adj_d !== null && (
                      <div>
                        <p className="table-header text-text-muted m-0 mb-1">AdjD</p>
                        <span className="font-mono text-[18px] font-semibold text-negative">
                          {fmtRating(detail.projected_adj_d)}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Floor / ceiling range bar */}
                  {detail.projected_floor_wins !== null && detail.projected_ceil_wins !== null && (
                    <div className="flex flex-col gap-1.5">
                      <p className="table-header text-text-muted m-0">Win Range</p>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-[13px] text-text-muted w-8">
                          {detail.projected_floor_wins}W
                        </span>
                        <div className="flex-1 relative h-2 bg-ui-border rounded-full overflow-hidden">
                          {/* Fill from floor to ceil */}
                          {(() => {
                            const scale = (v: number) => ((v - 15) / 65) * 100;
                            const floorPct = Math.max(0, scale(detail.projected_floor_wins!));
                            const ceilPct  = Math.min(100, scale(detail.projected_ceil_wins!));
                            const midPct   = scale(detail.projected_wins!);
                            return (
                              <>
                                <div
                                  className="absolute top-0 h-full bg-brand/30 rounded"
                                  style={{ left: `${floorPct}%`, width: `${ceilPct - floorPct}%` }}
                                />
                                <div
                                  className="absolute top-[-1px] w-[3px] h-[10px] bg-brand rounded-full"
                                  style={{ left: `${midPct}%`, marginLeft: '-1.5px' }}
                                />
                              </>
                            );
                          })()}
                        </div>
                        <span className="font-mono text-[13px] text-text-muted w-8 text-right">
                          {detail.projected_ceil_wins}W
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}
              {detail.macfax_take && (
                <p className="text-[15px] text-text-primary leading-relaxed m-0 border-t border-ui-border pt-4">
                  {detail.macfax_take}
                </p>
              )}
              {detail.season_defining_variable && (
                <blockquote className="border-l-4 border-brand pl-4 m-0 italic text-[15px] text-text-primary/80">
                  {detail.season_defining_variable}
                </blockquote>
              )}
            </div>
          </section>
        )}

        {/* ── Section 7: Cap Snapshot (conditional) ─────────────────────── */}
        <CapSnapshotSection detail={detail} />

        {/* ── Footer ────────────────────────────────────────────────────── */}
        <div className="border-t border-ui-border pt-6">
          <Link
            href="/nba/teams"
            className="text-[13px] text-brand hover:text-brand/80 transition-colors"
          >
            ← All Team Outlooks
          </Link>
        </div>
      </div>
    </div>
  );
}

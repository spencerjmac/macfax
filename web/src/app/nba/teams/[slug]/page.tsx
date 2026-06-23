import { notFound } from 'next/navigation';
import Link from 'next/link';
import type { Metadata } from 'next';
import type {
  TeamSeasonOutlookDetail,
  TeamOutseasonMove,
  ProjectedStarter,
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

        {/* ── Section 6: 2026-27 Outlook (conditional) ──────────────────── */}
        {(detail.projected_wins !== null || detail.macfax_take) && (
          <section>
            <h2 className="font-display font-bold text-[18px] uppercase tracking-wide text-text-primary mb-4">
              2026-27 Outlook
            </h2>
            <div className="bg-ui-card border border-ui-border rounded-lg p-6 flex flex-col gap-4">
              {detail.projected_wins !== null && (
                <div className="flex items-center gap-3">
                  <span className="table-header text-text-muted">Projected Record</span>
                  <span className="font-mono text-[18px] font-bold text-text-primary">
                    {detail.projected_wins}–{detail.projected_losses ?? '?'}
                  </span>
                  {detail.projected_adj_net !== null && (
                    <span className={`font-mono text-[14px] font-semibold ${netColor(detail.projected_adj_net)}`}>
                      ({fmtNet(detail.projected_adj_net)} AdjNet)
                    </span>
                  )}
                </div>
              )}
              {detail.macfax_take && (
                <p className="text-[15px] text-text-primary leading-relaxed m-0">
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

        {/* ── Section 7: Footer ─────────────────────────────────────────── */}
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

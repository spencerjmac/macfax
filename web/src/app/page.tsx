import Link from 'next/link';
import { BarChart3, Swords, ScatterChart, BookOpen, Info, ArrowRight, Activity, Users } from 'lucide-react';
import { getAllTeams } from '@/lib/data';
import { nbaApi } from '@/lib/nba-api';
import type { TeamSeason } from '@/types';
import type { NBATeamSeasonRatings } from '@/types/nba';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

async function getLeaderboardData(): Promise<{
  ncaaTop5: TeamSeason[];
  nbaTop3: NBATeamSeasonRatings[];
}> {
  const [ncaaResult, nbaResult] = await Promise.allSettled([
    getAllTeams(),
    nbaApi.getRankings(),
  ]);

  const ncaaTop5 =
    ncaaResult.status === 'fulfilled'
      ? [...ncaaResult.value].sort((a, b) => a.rank - b.rank).slice(0, 5)
      : [];
  const nbaTop3 =
    nbaResult.status === 'fulfilled'
      ? [...nbaResult.value]
          .sort((a, b) => (a.rank_adj_net ?? 999) - (b.rank_adj_net ?? 999))
          .slice(0, 3)
      : [];

  return { ncaaTop5, nbaTop3 };
}

export default async function HomePage() {
  const { ncaaTop5, nbaTop3 } = await getLeaderboardData();

  const ncaaTop3 = ncaaTop5.slice(0, 3);

  return (
    <div>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <header className="bg-ink text-white border-b-4 border-brand relative overflow-hidden">
        {/* faint teal glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(900px 380px at 88% -8%, rgba(64,144,128,0.20), transparent 60%)',
          }}
        />
        <div className="max-w-[1240px] mx-auto px-8 relative">
          <div
            className="grid items-center gap-14 py-[72px] pb-[84px]"
            style={{ gridTemplateColumns: '1.15fr 0.85fr' }}
          >
            {/* Copy */}
            <div className="flex flex-col items-start gap-0">
              <p className="kicker-sport text-brand2 flex items-center gap-3 mb-6">
                <span className="w-1.5 h-1.5 rounded-full bg-brand2 shadow-[0_0_0_4px_rgba(112,192,112,0.18)]" />
                NCAA · NBA — Updated daily
              </p>
              <h1 className="display-sport text-white mb-6 max-w-[16ch]">
                The numbers behind the game.
              </h1>
              <p className="text-ink-fg text-[19px] leading-[1.55] max-w-[540px] mb-8">
                We run the numbers and share what we find. Dig in, check our work,
                and see what the data says.
              </p>
              <div className="flex gap-3 flex-wrap">
                <Link
                  href="/ncaa/rankings"
                  className="inline-flex items-center gap-2 bg-brand hover:bg-brand-hover border border-brand hover:border-brand-hover text-white font-display font-semibold text-[16px] tracking-[0.04em] uppercase rounded-lg px-6 py-3.5 transition-colors"
                >
                  View rankings <ArrowRight className="w-[18px] h-[18px]" strokeWidth={1.5} />
                </Link>
                <Link
                  href="/ncaa/matchup"
                  className="inline-flex items-center gap-2 bg-transparent hover:border-brand2 border border-[#2f3d59] text-white font-display font-semibold text-[16px] tracking-[0.04em] uppercase rounded-lg px-6 py-3.5 transition-colors"
                >
                  Matchup tool
                </Link>
              </div>
            </div>

            {/* Leaderboard card */}
            <div className="bg-gradient-to-b from-ink-2 to-ink border border-ink-line rounded-[14px] p-2 shadow-[0_30px_60px_-20px_rgba(0,0,0,0.6)]">
              <div className="flex items-center justify-between px-4 py-3.5">
                <span className="font-display font-semibold text-[15px] tracking-[0.1em] uppercase text-white">
                  NCAA · Top of the polls
                </span>
                <span className="font-mono text-[11px] tracking-[0.08em] uppercase text-brand2 flex items-center gap-1.5">
                  <span className="w-[7px] h-[7px] rounded-full bg-brand2" />
                  Live
                </span>
              </div>

              {ncaaTop5.length > 0 ? (
                ncaaTop5.map((team, i) => (
                  <Link
                    key={team.teamId}
                    href={`/ncaa/team/${team.teamId}`}
                    className="grid items-center gap-3 w-full px-4 py-2.5 rounded-[9px] text-white hover:bg-ink-3 transition-colors"
                    style={{ gridTemplateColumns: '30px 30px 1fr auto' }}
                  >
                    <span className="font-mono font-bold text-[15px] text-[#6f7d97]">{i + 1}</span>
                    {team.logoUrl ? (
                      <img src={team.logoUrl} alt="" className="w-[30px] h-[30px] object-contain" />
                    ) : (
                      <div className="w-[30px] h-[30px] rounded-full bg-ink-3 flex items-center justify-center text-xs font-bold text-ink-fg2">
                        {team.teamName.charAt(0)}
                      </div>
                    )}
                    <span>
                      <span className="block font-semibold text-[15px]">{team.teamName}</span>
                      <span className="block font-sans text-[12px] text-[#7b88a0] mt-0.5">
                        {team.conference}
                      </span>
                    </span>
                    <span className="font-mono font-bold text-[16px] text-brand2">
                      {team.adjEM > 0 ? '+' : ''}{team.adjEM.toFixed(2)}
                    </span>
                  </Link>
                ))
              ) : (
                <div className="px-4 py-6 text-ink-fg2 text-sm text-center">Rankings loading…</div>
              )}

              <div className="px-4 py-3">
                <Link
                  href="/ncaa/rankings"
                  className="text-[#b6c2d6] hover:text-brand2 font-display font-semibold text-[13px] tracking-[0.08em] uppercase inline-flex items-center gap-1.5 transition-colors"
                >
                  Full rankings <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── League cards ─────────────────────────────────────────────────── */}
      <section className="py-[76px]">
        <div className="max-w-[1240px] mx-auto px-8">
          <div className="flex items-end justify-between gap-6 mb-[30px]">
            <div>
              <p className="kicker-sport text-brand mb-2">Two leagues, one model</p>
              <h2 className="head-sport text-text-primary">Pick your league</h2>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-[22px]">
            {/* NCAA */}
            <LeagueCard
              title="College Basketball"
              sub="365 Division I teams · all conferences"
              feats={['Rankings', 'Matchup', 'Outlook', 'Visualizations']}
              href="/ncaa/rankings"
              btnLabel="Enter NCAA"
              teams={ncaaTop3.map(t => ({
                id: t.teamId,
                name: t.teamName,
                logoUrl: t.logoUrl,
                em: t.adjEM,
              }))}
            />

            {/* NBA */}
            <LeagueCard
              title="NBA"
              sub="30 teams · East &amp; West"
              feats={['Rankings', 'Player Stats', 'Visualizations']}
              href="/nba"
              btnLabel="Enter NBA"
              teams={nbaTop3.map(t => ({
                id: t.team_slug,
                name: t.team_name,
                logoUrl: t.team_logo_url ?? '',
                em: t.adj_net ?? 0,
              }))}
            />
          </div>
        </div>
      </section>

      {/* ── About ────────────────────────────────────────────────────────── */}
      <section className="py-12 border-t border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8">
          <Link
            href="/about"
            className="block p-6 bg-ui-card border border-ui-border rounded-lg hover:border-text-primary transition-all flex items-start gap-4 max-w-xl"
          >
            <Info className="w-8 h-8 text-text-primary shrink-0 mt-1" />
            <div>
              <h2 className="text-xl font-bold mb-1">About macfax</h2>
              <p className="text-text-muted">
                Independent data sources, methodology, and how we calculate our
                advanced metrics across both leagues.
              </p>
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}

// ── League card component ─────────────────────────────────────────────────────

function BasketballIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      {/* solid filled ball — currentColor (brand teal) */}
      <circle cx="12" cy="12" r="10.5" fill="currentColor" opacity="0.82" />
      {/* seam lines in white over the fill */}
      <line
        x1="1.5" y1="12" x2="22.5" y2="12"
        stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.75"
      />
      {/* left ) seam — control points stay left of center (x=11), arc peaks at x≈10.5 */}
      <path
        d="M9 2C11 6 11 18 9 22"
        fill="none" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.75"
      />
      {/* right ( seam — control points stay right of center (x=13), arc peaks at x≈13.5 */}
      <path
        d="M15 2C13 6 13 18 15 22"
        fill="none" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.75"
      />
    </svg>
  );
}

function LeagueCard({
  title,
  sub,
  feats,
  href,
  btnLabel,
  teams,
}: {
  title: string;
  sub: string;
  feats: string[];
  href: string;
  btnLabel: string;
  teams: { id: string; name: string; logoUrl: string; em: number }[];
}) {
  return (
    <div className="border border-ui-border rounded-[16px] bg-surface overflow-hidden flex flex-col hover:border-brand hover:shadow-lg hover:-translate-y-0.5 transition-all duration-150">
      {/* top */}
      <div className="flex items-start justify-between gap-4 px-[26px] py-[26px] pb-[22px] border-b border-ui-border">
        <div>
          <h3 className="font-display font-bold text-[23px] uppercase tracking-[0.01em] m-0 mb-[5px]">
            {title}
          </h3>
          <p className="text-sm text-muted m-0">{sub}</p>
        </div>
        <BasketballIcon className="w-16 h-16 text-brand shrink-0" />
      </div>

      {/* feature chips */}
      <div className="flex gap-[7px] px-[26px] pt-[18px] pb-[6px] flex-wrap">
        {feats.map(f => (
          <span
            key={f}
            className="font-semibold text-[12px] text-muted bg-ui-surface border border-ui-border px-[11px] py-[7px] rounded-full"
          >
            {f}
          </span>
        ))}
      </div>

      {/* team list */}
      <div className="px-[18px] py-[12px]">
        {teams.map((tm, i) => (
          <div
            key={tm.id}
            className="grid items-center gap-3 px-2 py-[9px] rounded-lg hover:bg-ui-surface"
            style={{ gridTemplateColumns: '22px 26px 1fr auto' }}
          >
            <span className="font-mono font-bold text-[13px] text-muted-2">{i + 1}</span>
            {tm.logoUrl ? (
              <img src={tm.logoUrl} alt="" className="w-[26px] h-[26px] object-contain" />
            ) : (
              <div className="w-[26px] h-[26px] rounded-full bg-ui-surface flex items-center justify-center text-xs font-bold text-text-muted">
                {tm.name.charAt(0)}
              </div>
            )}
            <span className="font-semibold text-[14px]">{tm.name}</span>
            <span className="font-mono font-bold text-[14px] text-brand">
              {tm.em > 0 ? '+' : ''}{tm.em.toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* CTA */}
      <div className="mt-auto px-[26px] pb-[24px] pt-[16px]">
        <Link
          href={href}
          className="w-full flex items-center justify-center gap-2 bg-brand hover:bg-brand-hover text-white font-display font-semibold text-[16px] tracking-[0.04em] uppercase rounded-lg px-6 py-3.5 transition-colors"
        >
          {btnLabel} <ArrowRight className="w-[18px] h-[18px]" strokeWidth={1.5} />
        </Link>
      </div>
    </div>
  );
}

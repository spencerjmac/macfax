import { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { nbaApi } from '@/lib/nba-api';
import NBATeamPageTabs from '@/components/NBATeamPageTabs';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface NBATeamPageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ season?: string }>;
}

export async function generateMetadata({ params }: NBATeamPageProps): Promise<Metadata> {
  const { slug } = await params;
  return {
    title: `NBA Team | macfax`,
    description: `NBA team analytics for ${slug}.`,
  };
}

export default async function NBATeamPage({ params, searchParams }: NBATeamPageProps) {
  const { slug } = await params;
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;

  let teamDetail = null;
  let games: import('@/types/nba').NBAGame[] = [];
  let error: string | null = null;

  try {
    [teamDetail, games] = await Promise.all([
      nbaApi.getTeamDetail(slug, seasonYear),
      nbaApi.getGames({ season: seasonYear, team: slug }).catch(() => []),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : 'Team not found';
  }

  if (error || !teamDetail?.team) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link
          href="/nba/rankings"
          className="inline-flex items-center gap-2 text-text-muted hover:text-brand text-sm mb-8 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          NBA Rankings
        </Link>
        <div className="text-center py-24">
          <p className="text-text-muted">
            {error ?? 'Team not found. NBA data ingestion is coming in Phase 2.'}
          </p>
        </div>
      </div>
    );
  }

  const { team, season, ratings } = teamDetail;
  const fmtNet = (v: number | null) => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(1);

  return (
    <div>
      {/* Ink header */}
      <header className="bg-ink text-white relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(700px 300px at 92% -20%, rgba(64,144,128,0.18), transparent 60%)' }}
        />
        <div className="max-w-[1240px] mx-auto px-8 pt-[30px] relative">
          <Link
            href="/nba/rankings"
            className="inline-flex items-center gap-[7px] text-ink-fg2 hover:text-brand2 font-semibold text-[13px] pb-[22px] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
            Back to rankings
          </Link>

          <div className="flex items-center gap-6 pb-[26px]">
            {/* logo — white tile */}
            {team.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={team.logo_url}
                alt={team.name}
                className="w-[84px] h-[84px] object-contain bg-white rounded-[16px] p-[11px] shadow-[0_6px_18px_rgba(0,0,0,0.3)] shrink-0"
              />
            ) : (
              <div className="w-[84px] h-[84px] bg-white rounded-[16px] flex items-center justify-center text-2xl font-bold text-ink shrink-0">
                {team.name.charAt(0)}
              </div>
            )}

            <div className="flex-1 min-w-0">
              <div className="font-mono font-bold text-[12px] text-brand2 tracking-[0.1em] uppercase mb-[9px] inline-flex items-center gap-2">
                {ratings?.rank_adj_net != null && <>No. {ratings.rank_adj_net}</>}
                <span className="text-ink-fg2 font-normal">· {team.conference}ern · {team.division}</span>
              </div>
              <h1 className="font-display font-bold text-[clamp(38px,5vw,60px)] leading-[0.95] uppercase tracking-[0.005em] m-0 text-white">
                {team.name}
              </h1>
              <div className="font-sans text-[14px] text-ink-fg mt-[10px] flex gap-[18px] flex-wrap">
                {season && <span>Season <b className="text-white font-mono font-semibold">{season.display_name}</b></span>}
                {ratings?.adj_off != null && <span>Off <b className="text-white font-mono font-semibold">{ratings.adj_off.toFixed(1)}</b></span>}
                {ratings?.adj_def != null && <span>Def <b className="text-white font-mono font-semibold">{ratings.adj_def.toFixed(1)}</b></span>}
              </div>
            </div>

            <div className="shrink-0 text-right">
              <span className="block font-sans font-semibold text-[11px] tracking-[0.08em] uppercase text-ink-fg2 mb-2">Adj. Net Rating</span>
              <span className="font-mono font-bold text-[46px] leading-none text-brand2">
                {fmtNet(ratings?.adj_net ?? null)}
              </span>
            </div>
          </div>
        </div>
      </header>

      <NBATeamPageTabs slug={slug} seasonYear={seasonYear} ratings={ratings} games={games} />
    </div>
  );
}

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

  return (
    <div className="container mx-auto px-4 py-8">
      <Link
        href="/nba/rankings"
        className="inline-flex items-center gap-2 text-text-muted hover:text-brand text-sm mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        NBA Rankings
      </Link>

      {/* Team header */}
      <div className="flex flex-wrap items-center gap-6 mb-8 p-6 bg-ui-card border border-ui-border rounded-lg">
        {team.logo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={team.logo_url}
            alt={team.name}
            className="w-20 h-20 object-contain flex-shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm text-text-muted mb-0.5">
            {team.conference}ern Conference · {team.division}
          </div>
          <h1 className="text-3xl font-bold">{team.name}</h1>
          {season && (
            <div className="text-text-muted text-sm mt-0.5">{season.display_name} season</div>
          )}
          {ratings && ratings.rank_adj_net != null && (
            <div className="inline-block mt-2 bg-brand/10 text-brand text-sm font-bold px-3 py-0.5 rounded-full border border-brand/20">
              Rank #{ratings.rank_adj_net}
            </div>
          )}
        </div>

        {/* Key ratings snapshot */}
        {ratings && (
          <div className="flex flex-wrap gap-4 sm:gap-6">
            {[
              { label: 'Adj Net', value: ratings.adj_net, color: 'text-brand' },
              { label: 'Adj Off', value: ratings.adj_off, color: 'text-emerald-700' },
              { label: 'Adj Def', value: ratings.adj_def, color: 'text-rose-700', note: '↓ better' },
              { label: 'FFI', value: ratings.ffi, color: 'text-brand' },
            ].map(({ label, value, color, note }) => (
              <div key={label} className="text-center">
                <div className={`text-2xl font-bold font-mono ${color}`}>
                  {value != null ? value.toFixed(1) : '—'}
                </div>
                <div className="text-xs text-text-muted mt-0.5">{label}</div>
                {note && <div className="text-[10px] text-text-muted/60">{note}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tab content */}
      <NBATeamPageTabs slug={slug} seasonYear={seasonYear} ratings={ratings} games={games} />
    </div>
  );
}

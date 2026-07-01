'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowUpDown, Search } from 'lucide-react';
import TeamLogo from '@/components/TeamLogo';
import type { TeamSeasonOutlookSummary } from '@/types/nba';
import { nbaApi } from '@/lib/nba-api';
import {
  formatProjectedRecord,
  formatRating,
  formatSignedNumber,
  getAgeLabel,
  getContinuityLabel,
  getDisplayAdjNet,
  getOutlookTierLabel,
  getStarConcentrationLabel,
  getTeamRiskSignal,
  getTierClass,
  getTierDotClass,
} from '@/lib/nba-outlook-helpers';

type ConferenceFilter = 'All' | 'East' | 'West';
type SortOption = 'rank' | 'wins' | 'adjnet' | 'youngest' | 'continuity';

const CONFERENCE_FILTERS: ConferenceFilter[] = ['All', 'East', 'West'];

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: 'rank', label: 'MacFax Rank' },
  { value: 'wins', label: 'Projected Wins' },
  { value: 'adjnet', label: 'AdjNet' },
  { value: 'youngest', label: 'Youngest' },
  { value: 'continuity', label: 'Continuity' },
];

function valueOrLow(value: number | null | undefined): number {
  return value ?? Number.NEGATIVE_INFINITY;
}

function valueOrHigh(value: number | null | undefined): number {
  return value ?? Number.POSITIVE_INFINITY;
}

function buildRankMap(teams: TeamSeasonOutlookSummary[]): Record<string, number> {
  return [...teams]
    .sort((a, b) => {
      const rankDiff = (a.league_rank ?? 999) - (b.league_rank ?? 999);
      if (rankDiff !== 0) return rankDiff;
      const netDiff = valueOrLow(getDisplayAdjNet(b)) - valueOrLow(getDisplayAdjNet(a));
      if (netDiff !== 0) return netDiff;
      return a.team_name.localeCompare(b.team_name);
    })
    .reduce<Record<string, number>>((acc, team, index) => {
      acc[team.team_slug] = index + 1;
      return acc;
    }, {});
}

function sortTeams(teams: TeamSeasonOutlookSummary[], sort: SortOption): TeamSeasonOutlookSummary[] {
  return [...teams].sort((a, b) => {
    if (sort === 'wins') {
      return valueOrLow(b.projected_wins ?? b.wins) - valueOrLow(a.projected_wins ?? a.wins);
    }
    if (sort === 'adjnet') {
      return valueOrLow(getDisplayAdjNet(b)) - valueOrLow(getDisplayAdjNet(a));
    }
    if (sort === 'youngest') {
      return valueOrHigh(a.weighted_effective_age) - valueOrHigh(b.weighted_effective_age);
    }
    if (sort === 'continuity') {
      return valueOrLow(b.continuity_score) - valueOrLow(a.continuity_score);
    }
    const rankDiff = (a.league_rank ?? 999) - (b.league_rank ?? 999);
    if (rankDiff !== 0) return rankDiff;
    const netDiff = valueOrLow(getDisplayAdjNet(b)) - valueOrLow(getDisplayAdjNet(a));
    if (netDiff !== 0) return netDiff;
    return a.team_name.localeCompare(b.team_name);
  });
}

function TeamSignalRow({ team }: { team: TeamSeasonOutlookSummary }) {
  const continuity = getContinuityLabel(team.continuity_score);
  const age = getAgeLabel(team.weighted_effective_age);
  const concentration = getStarConcentrationLabel(team.top2_bpr_concentration);
  const signals = [
    team.continuity_score !== null ? continuity.label : null,
    team.weighted_effective_age !== null ? age.label : null,
    team.top2_bpr_concentration !== null ? concentration.label : null,
  ].filter(Boolean).slice(0, 2);

  if (signals.length === 0) {
    signals.push(getTeamRiskSignal(team));
  }

  return (
    <p className="text-[12px] leading-snug text-text-muted m-0">
      {signals.join(' · ')}
    </p>
  );
}

function TeamOutlookCard({
  team,
  displayRank,
}: {
  team: TeamSeasonOutlookSummary;
  displayRank: number;
}) {
  const adjNet = getDisplayAdjNet(team);
  const tier = getOutlookTierLabel(team.outlook_tier, adjNet, team.projected_wins ?? team.wins);
  const wins = team.projected_wins ?? team.wins;

  return (
    <Link
      href={`/nba/teams/${team.team_slug}`}
      className="group relative flex min-h-[250px] flex-col justify-between overflow-hidden rounded-lg border border-ui-border bg-ui-card p-5 no-underline shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand/60 hover:shadow-[0_18px_40px_-28px_rgba(11,18,32,0.55)]"
    >
      <div
        className="absolute inset-x-0 top-0 h-1"
        style={{ background: team.primary_color || 'var(--brand)' }}
      />
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-white p-2 shadow-sm ring-1 ring-ui-border">
            <TeamLogo
              src={team.logo_url}
              alt={team.team_abbr}
              width={42}
              height={42}
              className="max-h-[42px] max-w-[42px] object-contain"
              fallbackColor={team.primary_color}
            />
          </div>
          <div className="min-w-0">
            <p className="font-display text-[21px] font-bold uppercase leading-[1.02] tracking-[0.005em] text-text-primary m-0 group-hover:text-brand">
              {team.team_name}
            </p>
            <p className="mt-1 text-[12px] font-medium text-text-muted m-0">
              {team.conference} · #{displayRank}
            </p>
          </div>
        </div>
        <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${getTierDotClass(tier)}`} />
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3">
        <div>
          <p className="table-header m-0 mb-1">Projected</p>
          <p className="font-mono text-[24px] font-bold leading-none text-text-primary m-0">
            {formatProjectedRecord(team)}
          </p>
          <p className="mt-1 text-[12px] text-text-muted m-0">
            {wins !== null && wins !== undefined ? `${wins} projected wins` : 'projection pending'}
          </p>
        </div>
        <div className="text-right">
          <p className="table-header m-0 mb-1">AdjNet</p>
          <p className={`font-mono text-[24px] font-bold leading-none m-0 ${adjNet !== null && adjNet > 0 ? 'text-positive' : adjNet !== null && adjNet < 0 ? 'text-negative' : 'text-text-muted'}`}>
            {formatSignedNumber(adjNet)}
          </p>
          <p className="mt-1 text-[12px] text-text-muted m-0">
            per 100 poss.
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 border-t border-ui-border pt-4">
        <div className="flex items-center justify-between gap-3">
          <span className={`inline-flex items-center rounded px-2.5 py-1 text-[11px] font-semibold ${getTierClass(tier)}`}>
            {tier}
          </span>
          {team.projected_adj_o !== null && team.projected_adj_d !== null && (
            <span className="font-mono text-[11px] text-text-muted">
              {formatRating(team.projected_adj_o)} O · {formatRating(team.projected_adj_d)} D
            </span>
          )}
        </div>
        <TeamSignalRow team={team} />
      </div>
    </Link>
  );
}

function HowToReadItem({
  label,
  text,
}: {
  label: string;
  text: string;
}) {
  return (
    <div className="border-l border-ui-border pl-4">
      <p className="font-display text-[14px] font-bold uppercase tracking-wide text-text-primary m-0">
        {label}
      </p>
      <p className="mt-1 text-[13px] leading-snug text-text-muted m-0">{text}</p>
    </div>
  );
}

export default function NBATeamsPage() {
  const [teams, setTeams] = useState<TeamSeasonOutlookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conference, setConference] = useState<ConferenceFilter>('All');
  const [sort, setSort] = useState<SortOption>('rank');
  const [query, setQuery] = useState('');

  useEffect(() => {
    nbaApi
      .getTeamOutlooks()
      .then(setTeams)
      .catch((e) => setError(e.message ?? 'Failed to load NBA team outlooks'))
      .finally(() => setLoading(false));
  }, []);

  const rankMap = useMemo(() => buildRankMap(teams), [teams]);

  const visibleTeams = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = teams.filter((team) => {
      const conferenceMatch = conference === 'All' || team.conference === conference;
      const searchMatch =
        !normalizedQuery ||
        team.team_name.toLowerCase().includes(normalizedQuery) ||
        team.team_abbr.toLowerCase().includes(normalizedQuery);
      return conferenceMatch && searchMatch;
    });
    return sortTeams(filtered, sort);
  }, [conference, query, sort, teams]);

  const leader = rankMap && teams.length > 0
    ? teams.find((team) => rankMap[team.team_slug] === 1)
    : null;

  return (
    <div>
      <header className="bg-ink text-white border-b-4 border-brand">
        <div className="max-w-[1240px] mx-auto px-5 sm:px-8 py-10 sm:py-12">
          <div className="flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-[760px]">
              <p className="kicker-sport text-brand2 mb-3">NBA · 2026-27 Model Preview</p>
              <h1 className="font-display text-[clamp(38px,5vw,68px)] font-bold uppercase leading-[0.98] tracking-[0.005em] text-white m-0">
                NBA Team Outlooks
              </h1>
              <p className="mt-4 max-w-[680px] text-[16px] leading-relaxed text-ink-fg m-0">
                Model-based 2026-27 projections for all 30 teams, built from adjusted efficiency,
                roster value, development curves, and offseason movement.
              </p>
            </div>
            {leader && (
              <Link
                href={`/nba/teams/${leader.team_slug}`}
                className="flex w-full max-w-[360px] items-center gap-4 rounded-lg border border-ink-line bg-ink-2 p-4 no-underline transition-colors hover:border-brand"
              >
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-white p-2">
                  <TeamLogo
                    src={leader.logo_url}
                    alt={leader.team_abbr}
                    width={48}
                    height={48}
                    className="max-h-12 max-w-12 object-contain"
                    fallbackColor={leader.primary_color}
                  />
                </div>
                <div className="min-w-0">
                  <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-brand2 m-0">
                    #1 in the outlook model
                  </p>
                  <p className="mt-1 font-display text-[24px] font-bold uppercase leading-none text-white m-0">
                    {leader.team_name}
                  </p>
                  <p className="mt-2 text-[13px] text-ink-fg2 m-0">
                    {formatProjectedRecord(leader)} · {formatSignedNumber(getDisplayAdjNet(leader))} AdjNet
                  </p>
                </div>
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1240px] mx-auto px-5 sm:px-8 py-8 pb-16">
        <section className="grid gap-4 border-b border-ui-border pb-7 md:grid-cols-3">
          <HowToReadItem label="AdjNet" text="Team strength per 100 possessions, adjusted for context." />
          <HowToReadItem label="Projected Wins" text="Model baseline, not a betting line or ceiling case." />
          <HowToReadItem label="Range" text="Uncertainty from injuries, development, and roster volatility." />
        </section>

        <section className="mt-7 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {CONFERENCE_FILTERS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setConference(tab)}
                className={`rounded-lg border px-4 py-2 text-[13px] font-semibold transition-colors ${
                  conference === tab
                    ? 'border-brand bg-brand text-white'
                    : 'border-ui-border bg-ui-card text-text-muted hover:border-brand/60 hover:text-text-primary'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative block sm:w-[260px]">
              <span className="sr-only">Search team name</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" strokeWidth={1.75} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search team"
                className="h-10 w-full rounded-lg border border-ui-border bg-ui-card pl-9 pr-3 text-[14px] text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-brand"
              />
            </label>
            <label className="relative block sm:w-[210px]">
              <span className="sr-only">Sort team outlooks</span>
              <ArrowUpDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" strokeWidth={1.75} />
              <select
                value={sort}
                onChange={(event) => setSort(event.target.value as SortOption)}
                className="h-10 w-full appearance-none rounded-lg border border-ui-border bg-ui-card pl-9 pr-8 text-[14px] text-text-primary outline-none transition-colors focus:border-brand"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        {loading && (
          <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="h-[250px] rounded-lg border border-ui-border bg-ui-card p-5">
                <div className="skeleton h-14 w-14" />
                <div className="skeleton mt-6 h-6 w-3/4" />
                <div className="skeleton mt-4 h-16 w-full" />
                <div className="skeleton mt-5 h-10 w-full" />
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="mt-8 rounded-lg border border-negative/25 bg-negative/5 p-6 text-[14px] text-negative">
            {error}
          </div>
        )}

        {!loading && !error && visibleTeams.length === 0 && (
          <div className="mt-8 rounded-lg border border-ui-border bg-ui-card p-8 text-center">
            <p className="font-display text-[22px] font-bold uppercase text-text-primary m-0">
              No teams found
            </p>
            <p className="mt-2 text-[14px] text-text-muted m-0">
              Try a different conference or search term.
            </p>
          </div>
        )}

        {!loading && !error && visibleTeams.length > 0 && (
          <section className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visibleTeams.map((team) => (
              <TeamOutlookCard
                key={team.team_slug}
                team={team}
                displayRank={rankMap[team.team_slug] ?? team.league_rank}
              />
            ))}
          </section>
        )}

        {!loading && !error && visibleTeams.length > 0 && (
          <p className="mt-6 text-[12px] text-text-muted m-0">
            {visibleTeams.length} teams shown.
          </p>
        )}
      </main>
    </div>
  );
}

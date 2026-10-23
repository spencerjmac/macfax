import { METRIC_DEFINITIONS, type MetricMeta } from '@macfax/core/lib/metricMetadata';
import { computeRanks, heatStyleFromPercentile, type RankData } from '@macfax/core/lib/rankingUtils';
import { type ColumnDef } from '@tanstack/react-table';
import { router } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Text, View } from 'react-native';

import { DataTable } from '@/src/components/DataTable';
import { FavoriteStar } from '@/src/components/FavoriteButton';
import { SeasonSelect } from '@/src/components/SeasonSelect';
import { Container } from '@/src/components/ui/Screen';
import { AsyncView } from '@/src/components/ui/StateViews';
import { TeamLogo } from '@/src/components/ui/TeamLogo';
import { fetchRankings, fetchSeasons, type RankingRow } from '@/src/lib/api';
import { useAsync } from '@/src/lib/useAsync';

/** The metric columns of web's "Efficiency" view, in order. Keys index core's METRIC_DEFINITIONS. */
const METRIC_KEYS = ['adjEM', 'adjO', 'adjD', 'adjTempo', 'four_factor_index_100'] as const;
type MetricKey = (typeof METRIC_KEYS)[number];
type MetricRanks = Map<MetricKey, Map<string, RankData>>;

function formatValue(value: number, format: MetricMeta['format']): string {
  switch (format) {
    case 'number1':
      return value.toFixed(1);
    case 'number2':
      return value.toFixed(2);
    case 'percent1':
      return `${(value * 100).toFixed(1)}%`;
    case 'number1pct':
      return `${value.toFixed(1)}%`;
    case 'int':
      return Math.round(value).toString();
    default:
      return value.toString();
  }
}

/** A metric cell: value, small national rank, and the teal/slate heat background from core. */
function metricColumn(key: MetricKey, ranks: MetricRanks): ColumnDef<RankingRow, any> {
  const meta = METRIC_DEFINITIONS[key];
  return {
    accessorKey: key,
    header: meta.label,
    sortDescFirst: meta.better === 'higher',
    enableGlobalFilter: false,
    meta: { width: 92, custom: true },
    cell: (info) => {
      const value = info.getValue() as number | null;
      if (value == null) return <Text className="px-2 font-mono text-sm text-ink-fg2">-</Text>;
      const rankData = ranks.get(key)?.get(info.row.original.teamId);
      const heat = meta.heatmap ? heatStyleFromPercentile(rankData?.percentile ?? null).background : undefined;
      return (
        <View style={heat ? { backgroundColor: heat } : undefined} className="flex-row items-start rounded px-2 py-1">
          <Text className="font-mono text-sm text-text-onDark">{formatValue(value, meta.format)}</Text>
          {meta.showRank && rankData?.rank ? (
            <Text className="ml-0.5 font-sans-medium text-[9px] text-ink-fg2">{rankData.rank}</Text>
          ) : null}
        </View>
      );
    },
  };
}

function buildColumns(ranks: MetricRanks): ColumnDef<RankingRow, any>[] {
  return [
    { accessorKey: 'rank', header: 'Rk', enableGlobalFilter: false, meta: { width: 48, align: 'right' } },
    {
      accessorKey: 'teamName',
      header: 'Team',
      meta: { width: 200, grow: true, custom: true },
      cell: (info) => {
        const team = info.row.original;
        return (
          <View className="flex-row items-center gap-2">
            <TeamLogo uri={team.logoUrl} name={team.teamName} size={26} />
            {team.tournament_seed != null ? (
              <Text className="w-4 text-right font-sans-bold text-[11px] text-brand2">{team.tournament_seed}</Text>
            ) : null}
            <Text numberOfLines={1} className="flex-1 font-sans-medium text-sm text-text-onDark">
              {team.teamName}
            </Text>
            <FavoriteStar teamId={team.teamId} />
          </View>
        );
      },
    },
    {
      accessorKey: 'conference',
      header: 'Conf',
      meta: { width: 64, custom: true },
      cell: (info) => <Text className="font-sans text-xs uppercase text-ink-fg2">{info.getValue() as string}</Text>,
    },
    { accessorKey: 'record', header: 'Record', enableSorting: false, enableGlobalFilter: false, meta: { width: 72, align: 'right' } },
    ...METRIC_KEYS.map((key) => metricColumn(key, ranks)),
  ];
}

const getRowId = (row: RankingRow) => row.teamId;
const INITIAL_SORTING = [{ id: 'rank', desc: false }];

function formatUpdated(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Rankings tab: NCAA team rankings (the "Efficiency" view of web's /ncaa/rankings). */
export default function RankingsScreen() {
  // undefined = the API's current season, same as web without ?season=.
  const [season, setSeason] = useState<number | undefined>(undefined);

  const seasons = useAsync(() => fetchSeasons(), []);
  const rankings = useAsync(({ force }) => fetchRankings(season, { force }), [season]);

  const teams = rankings.status === 'ready' ? rankings.data.teams : null;

  // Ranks come from the full Division I list, so heat colors mean the same thing whatever the search shows.
  const columns = useMemo(() => {
    const ranks: MetricRanks = new Map();
    for (const key of METRIC_KEYS) {
      const entries = (teams ?? []).map((t) => ({ id: t.teamId, value: t[key] }));
      ranks.set(key, computeRanks(entries, METRIC_DEFINITIONS[key].better));
    }
    return buildColumns(ranks);
  }, [teams]);

  // Pass the selected season along so the team screen shows the same one. No param means the current season.
  const openTeam = useCallback(
    (team: RankingRow) =>
      router.push({ pathname: '/team/[slug]', params: season ? { slug: team.teamId, season: String(season) } : { slug: team.teamId } }),
    [season],
  );

  const seasonLabel = rankings.status === 'ready' ? rankings.data.season : '';
  const updated = rankings.status === 'ready' ? formatUpdated(rankings.data.lastUpdated) : null;

  return (
    <View className="flex-1 bg-bg">
      <View className="border-b border-ink-line bg-ink">
        <Container className="gap-2 py-5 md:py-8">
          <Text className="font-display-semibold text-[13px] uppercase tracking-[2px] text-brand">
            College Basketball{seasonLabel ? ` · ${seasonLabel}` : ''}
          </Text>
          <Text className="font-display text-3xl uppercase text-text-onDark md:text-5xl">NCAA Rankings</Text>
          <View className="flex-row flex-wrap items-center gap-3">
            <Text className="hidden font-sans text-[15px] text-ink-fg2 md:flex">
              Team rankings powered by opponent-adjusted ratings, with season, search and sorting.
            </Text>
            {updated ? (
              <View className="flex-row items-center gap-2 rounded-md border border-ink-line bg-ink-2 px-2.5 py-1">
                <View className="h-1.5 w-1.5 rounded-full bg-brand2" />
                <Text className="font-mono text-xs text-ink-fg2">Updated {updated}</Text>
              </View>
            ) : null}
          </View>
        </Container>
      </View>

      <Container className="flex-1 pt-4">
        <AsyncView
          state={rankings}
          loadingLabel="Loading rankings…"
          errorTitle="Could not load rankings"
          isEmpty={(data) => data.teams.length === 0}
          emptyTitle="No rankings for this season"
          emptyMessage="Ratings have not been computed for the selected season."
        >
          {(data) => (
            <DataTable
              data={data.teams}
              columns={columns}
              getRowId={getRowId}
              onRowPress={openTeam}
              initialSorting={INITIAL_SORTING}
              searchPlaceholder="Search teams..."
              emptyTitle="No teams found matching your search."
              toolbar={
                seasons.status === 'ready' ? <SeasonSelect seasons={seasons.data} value={season} onChange={setSeason} /> : null
              }
            />
          )}
        </AsyncView>
      </Container>
    </View>
  );
}

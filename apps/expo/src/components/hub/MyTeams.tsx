import { Pressable, Text, View } from 'react-native';

import { Star } from '@/src/components/ui/icons';
import { TeamLogo } from '@/src/components/ui/TeamLogo';
import type { RankingRow } from '@/src/lib/api';
import { openLink } from '@/src/lib/links';
import type { AsyncResult } from '@/src/lib/useAsync';
import { clearFavorites, selectFavoriteIds } from '@/src/store/favoritesSlice';
import { useAppDispatch, useAppSelector } from '@/src/store/hooks';
import { palette } from '@/src/theme/tokens';

/** One starred team: tap to open its team page. */
function MyTeamRow({ team, first }: { team: RankingRow; first: boolean }) {
  return (
    <Pressable
      onPress={() => openLink({ kind: 'app', href: `/team/${team.teamId}` })}
      accessibilityRole="link"
      className={`flex-row items-center gap-3 px-4 py-3 active:bg-ink-3 md:px-6 ${first ? '' : 'border-t border-ink-line'}`}
    >
      <TeamLogo uri={team.logoUrl} name={team.teamName} size={36} />
      <View className="flex-1">
        <Text numberOfLines={1} className="font-sans-bold text-base text-text-onDark">
          {team.teamName}
        </Text>
        <Text className="mt-0.5 font-sans text-[13px] text-ink-fg2">
          #{team.rank} · {team.conference} · {team.record}
        </Text>
      </View>
      <View className="items-end">
        <Text className="mb-1 font-sans-semibold text-[10px] uppercase tracking-wider text-ink-fg2">AdjEM</Text>
        <Text className="font-mono-semibold text-base text-brand2">
          {`${team.adjEM > 0 ? '+' : ''}${team.adjEM.toFixed(1)}`}
        </Text>
      </View>
    </Pressable>
  );
}

/**
 * The Home tab's "My Teams" section. The starred team ids come from the Redux
 * store (set by FavoriteButton on the team screen); the stats come from the
 * current-season rankings the hub already loaded.
 */
export function MyTeams({ rankings }: { rankings: AsyncResult<RankingRow[]> }) {
  const dispatch = useAppDispatch();
  const favoriteIds = useAppSelector(selectFavoriteIds);

  const byId = new Map(rankings.status === 'ready' ? rankings.data.map((t) => [t.teamId, t]) : []);
  const teams = favoriteIds.map((id) => byId.get(id)).filter((t): t is RankingRow => t !== undefined);

  return (
    <View>
      <View className="mb-4 flex-row items-end justify-between">
        <View className="gap-2">
          <Text className="font-display-semibold text-[13px] uppercase tracking-[2px] text-brand">Watchlist</Text>
          <Text className="font-display text-3xl uppercase text-text-onDark">
            My Teams{favoriteIds.length ? ` (${favoriteIds.length})` : ''}
          </Text>
        </View>
        {favoriteIds.length ? (
          <Pressable onPress={() => dispatch(clearFavorites())} accessibilityRole="button" hitSlop={8}>
            <Text className="font-display-semibold text-sm uppercase tracking-wider text-ink-fg2">Clear</Text>
          </Pressable>
        ) : null}
      </View>

      {favoriteIds.length > 0 && rankings.status !== 'ready' ? null : favoriteIds.length === 0 ? (
        <View className="flex-row items-center gap-3 rounded-[14px] border border-dashed border-ink-line p-5">
          <Star color={palette.muted} size={18} strokeWidth={1.5} />
          <Text className="flex-1 font-sans text-sm text-ink-fg2">
            No teams yet. Open a team and tap Add to pin it here.
          </Text>
        </View>
      ) : (
        <View className="overflow-hidden rounded-[14px] border border-ink-line bg-ink-2">
          {teams.map((team, i) => (
            <MyTeamRow key={team.teamId} team={team} first={i === 0} />
          ))}
        </View>
      )}
    </View>
  );
}

import { Pressable, Text } from 'react-native';

import { Star } from '@/src/components/ui/icons';
import { selectIsFavorite, toggleFavorite } from '@/src/store/favoritesSlice';
import { useAppDispatch, useAppSelector } from '@/src/store/hooks';
import { ink, palette } from '@/src/theme/tokens';

/**
 * Star / unstar a team. Reads whether the team is starred from the Redux store
 * and dispatches toggleFavorite on press, so every screen showing the team
 * updates together.
 */
export function FavoriteButton({ teamId, teamName }: { teamId: string; teamName: string }) {
  const dispatch = useAppDispatch();
  const isFavorite = useAppSelector((state) => selectIsFavorite(state, teamId));

  return (
    <Pressable
      onPress={() => dispatch(toggleFavorite(teamId))}
      accessibilityRole="button"
      accessibilityState={{ selected: isFavorite }}
      accessibilityLabel={isFavorite ? `Remove ${teamName} from My Teams` : `Add ${teamName} to My Teams`}
      hitSlop={8}
      className={`flex-row items-center gap-1.5 rounded-lg border px-3 py-2 ${
        isFavorite ? 'border-brand2 bg-brand2/15' : 'border-ink-line bg-ink-2 active:border-brand2'
      }`}
    >
      <Star
        color={isFavorite ? palette.brand2 : ink.fg2}
        fill={isFavorite ? palette.brand2 : 'transparent'}
        size={16}
        strokeWidth={1.5}
      />
      <Text className={`font-sans-semibold text-xs uppercase tracking-wider ${isFavorite ? 'text-brand2' : 'text-ink-fg2'}`}>
        {isFavorite ? 'My team' : 'Add'}
      </Text>
    </Pressable>
  );
}

/** A small read-only star shown next to starred teams (e.g. in the rankings table). Renders nothing otherwise. */
export function FavoriteStar({ teamId, size = 12 }: { teamId: string; size?: number }) {
  const isFavorite = useAppSelector((state) => selectIsFavorite(state, teamId));
  if (!isFavorite) return null;
  return <Star color={palette.brand2} fill={palette.brand2} size={size} strokeWidth={1.5} accessibilityLabel="In My Teams" />;
}

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

import type { RootState } from './index';

/**
 * "My Teams": the teams the user has starred. Only team ids are stored; screens
 * look the rest (name, logo, ratings) up in the rankings data they already load,
 * so the store never holds stale stats. An array, not a Set, because Redux state
 * must be serializable. Newest first.
 */
export interface FavoritesState {
  teamIds: string[];
}

const initialState: FavoritesState = {
  teamIds: [],
};

const favoritesSlice = createSlice({
  name: 'favorites',
  initialState,
  reducers: {
    /** Star the team if it is not starred, unstar it if it is. */
    toggleFavorite(state, action: PayloadAction<string>) {
      const teamId = action.payload;
      const index = state.teamIds.indexOf(teamId);
      if (index === -1) {
        state.teamIds.unshift(teamId);
      } else {
        state.teamIds.splice(index, 1);
      }
    },
    removeFavorite(state, action: PayloadAction<string>) {
      state.teamIds = state.teamIds.filter((id) => id !== action.payload);
    },
    clearFavorites(state) {
      state.teamIds = [];
    },
  },
});

export const { toggleFavorite, removeFavorite, clearFavorites } = favoritesSlice.actions;
export default favoritesSlice.reducer;

export const selectFavoriteIds = (state: RootState) => state.favorites.teamIds;
export const selectIsFavorite = (state: RootState, teamId: string) => state.favorites.teamIds.includes(teamId);

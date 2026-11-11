import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit';

import { fetchFavoriteTeamIds, saveFavoriteTeamIds } from '@/src/lib/api';
import { getDeviceId } from '@/src/lib/deviceId';

import type { RootState } from './index';

export type FavoritesSyncStatus = 'idle' | 'loading' | 'saving' | 'saved' | 'error';

/**
 * "My Teams": the teams the user has starred. Only team ids are stored; screens
 * look the rest (name, logo, ratings) up in the rankings data they already load,
 * so the store never holds stale stats. An array, not a Set, because Redux state
 * must be serializable. Newest first.
 *
 * The list is kept on the backend (/api/favorites/), keyed by an anonymous
 * per-install id: loadFavorites runs once at launch, and the listener in
 * store/index.ts runs saveFavorites shortly after each change.
 */
export interface FavoritesState {
  teamIds: string[];
  syncStatus: FavoritesSyncStatus;
  /** Which request failed when syncStatus is 'error', so Retry can repeat it. */
  failedRequest: 'load' | 'save' | null;
  /**
   * True when the user changed the list while a load was in flight. The load
   * then keeps the local list instead of replacing it, and the listener saves it.
   */
  changedBeforeLoad: boolean;
}

const initialState: FavoritesState = {
  teamIds: [],
  syncStatus: 'idle',
  failedRequest: null,
  changedBeforeLoad: false,
};

/** Fetch this install's saved list from the backend. */
export const loadFavorites = createAsyncThunk<string[], void, { state: RootState }>(
  'favorites/load',
  async () => fetchFavoriteTeamIds(await getDeviceId()),
);

/**
 * Send the whole current list to the backend, which replaces what it had.
 * Nothing is rolled back on failure: the next save sends the whole list again.
 */
export const saveFavorites = createAsyncThunk<string[], void, { state: RootState }>(
  'favorites/save',
  async (_, { getState }) => saveFavoriteTeamIds(await getDeviceId(), getState().favorites.teamIds),
);

/** Called by every user change, so a pending load knows not to overwrite it. */
function noteLocalChange(state: FavoritesState) {
  if (state.syncStatus === 'loading') state.changedBeforeLoad = true;
}

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
      noteLocalChange(state);
    },
    removeFavorite(state, action: PayloadAction<string>) {
      state.teamIds = state.teamIds.filter((id) => id !== action.payload);
      noteLocalChange(state);
    },
    clearFavorites(state) {
      state.teamIds = [];
      noteLocalChange(state);
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadFavorites.pending, (state) => {
        state.syncStatus = 'loading';
        state.failedRequest = null;
        state.changedBeforeLoad = false;
      })
      .addCase(loadFavorites.fulfilled, (state, action) => {
        if (!state.changedBeforeLoad) state.teamIds = action.payload;
        state.syncStatus = 'idle';
      })
      .addCase(loadFavorites.rejected, (state) => {
        state.syncStatus = 'error';
        state.failedRequest = 'load';
      })
      .addCase(saveFavorites.pending, (state) => {
        state.syncStatus = 'saving';
        state.failedRequest = null;
      })
      // The server's reply is the list that was sent. It is not copied back,
      // since the user may have changed the list while the request was out.
      .addCase(saveFavorites.fulfilled, (state) => {
        state.syncStatus = 'saved';
      })
      .addCase(saveFavorites.rejected, (state) => {
        state.syncStatus = 'error';
        state.failedRequest = 'save';
      });
  },
});

export const { toggleFavorite, removeFavorite, clearFavorites } = favoritesSlice.actions;
export default favoritesSlice.reducer;

export const selectFavoriteIds = (state: RootState) => state.favorites.teamIds;
export const selectIsFavorite = (state: RootState, teamId: string) => state.favorites.teamIds.includes(teamId);
export const selectFavoritesSyncStatus = (state: RootState) => state.favorites.syncStatus;
export const selectFavoritesFailedRequest = (state: RootState) => state.favorites.failedRequest;

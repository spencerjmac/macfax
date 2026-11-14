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
 *
 * Until the first load succeeds (still running, or failed offline) the local
 * list is not the whole story, so it is never saved. Instead each tap is also
 * recorded in pendingChanges and replayed on top of the server's list when the
 * load succeeds; that merged list is then saved.
 */
export interface FavoritesState {
  teamIds: string[];
  syncStatus: FavoritesSyncStatus;
  /** Which request failed when syncStatus is 'error', so Retry can repeat it. */
  failedRequest: 'load' | 'save' | null;
  /** True after the first successful loadFavorites. No save is sent before then. */
  hasLoaded: boolean;
  /**
   * The user's latest intent per team from taps made before hasLoaded, in tap
   * order (oldest first). Replayed on top of the server's list by the first
   * successful load, then emptied.
   */
  pendingChanges: Record<string, 'add' | 'remove'>;
}

const initialState: FavoritesState = {
  teamIds: [],
  syncStatus: 'idle',
  failedRequest: null,
  hasLoaded: false,
  pendingChanges: {},
};

/** Fetch this install's saved list from the backend. */
export const loadFavorites = createAsyncThunk<string[], void, { state: RootState }>(
  'favorites/load',
  async () => fetchFavoriteTeamIds(await getDeviceId()),
);

/**
 * Send the whole current list to the backend, which replaces what it had.
 * Nothing is rolled back on failure: the next save sends the whole list again.
 * Skipped (no request, no status change) until a load has succeeded, since the
 * local list could be missing teams saved earlier.
 */
export const saveFavorites = createAsyncThunk<string[], void, { state: RootState }>(
  'favorites/save',
  async (_, { getState }) => saveFavoriteTeamIds(await getDeviceId(), getState().favorites.teamIds),
  { condition: (_, { getState }) => getState().favorites.hasLoaded },
);

/** Before the first load, remember the user's latest intent for a team. */
function recordIntent(state: FavoritesState, teamId: string, intent: 'add' | 'remove') {
  if (state.hasLoaded) return;
  // Delete first so a re-tapped team moves to the end (most recent tap).
  delete state.pendingChanges[teamId];
  state.pendingChanges[teamId] = intent;
}

/**
 * The server's list with the pre-load taps replayed in tap order: 'add' puts a
 * missing team at the front (newest first), 'remove' drops it.
 */
function applyPendingChanges(serverIds: string[], changes: FavoritesState['pendingChanges']): string[] {
  let ids = [...serverIds];
  for (const [teamId, intent] of Object.entries(changes)) {
    if (intent === 'add') {
      if (!ids.includes(teamId)) ids.unshift(teamId);
    } else {
      ids = ids.filter((id) => id !== teamId);
    }
  }
  return ids;
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
        recordIntent(state, teamId, 'add');
      } else {
        state.teamIds.splice(index, 1);
        recordIntent(state, teamId, 'remove');
      }
    },
    removeFavorite(state, action: PayloadAction<string>) {
      state.teamIds = state.teamIds.filter((id) => id !== action.payload);
      recordIntent(state, action.payload, 'remove');
    },
    /** Before the first load this only removes the teams shown at that moment. */
    clearFavorites(state) {
      for (const teamId of state.teamIds) recordIntent(state, teamId, 'remove');
      state.teamIds = [];
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadFavorites.pending, (state) => {
        state.syncStatus = 'loading';
        state.failedRequest = null;
      })
      // The listener in store/index.ts saves the result if pendingChanges was not empty.
      .addCase(loadFavorites.fulfilled, (state, action) => {
        state.teamIds = applyPendingChanges(action.payload, state.pendingChanges);
        state.pendingChanges = {};
        state.hasLoaded = true;
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

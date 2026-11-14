import { configureStore, createListenerMiddleware, isAnyOf } from '@reduxjs/toolkit';

import favoritesReducer, {
  clearFavorites,
  loadFavorites,
  removeFavorite,
  saveFavorites,
  toggleFavorite,
} from './favoritesSlice';

/** Wait this long after the last change before saving, so quick taps send one request. */
const SAVE_DEBOUNCE_MS = 400;

const listenerMiddleware = createListenerMiddleware();

/** The app's Redux store. Provided to every screen in app/_layout.tsx. */
export const store = configureStore({
  reducer: {
    favorites: favoritesReducer,
  },
  middleware: (getDefaultMiddleware) => getDefaultMiddleware().prepend(listenerMiddleware.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

const startAppListening = listenerMiddleware.startListening.withTypes<RootState, AppDispatch>();

const isSyncBusy = (state: RootState) =>
  state.favorites.syncStatus === 'loading' || state.favorites.syncStatus === 'saving';

// Save My Teams to the backend after the user changes it. A newer change
// cancels the wait, so a burst of taps sends one request with the final list.
// A save waits for any load or save in flight, so requests never overlap and
// the last one sent always carries the latest list.
// Before the first successful load nothing is saved here: the taps are kept in
// pendingChanges, and the load-success listener below saves the merged list.
startAppListening({
  matcher: isAnyOf(toggleFavorite, removeFavorite, clearFavorites),
  effect: async (_action, listenerApi) => {
    listenerApi.cancelActiveListeners();
    if (!listenerApi.getState().favorites.hasLoaded) return;
    await listenerApi.delay(SAVE_DEBOUNCE_MS);
    // condition() only checks on later actions, so look at the current state first.
    if (isSyncBusy(listenerApi.getState())) {
      await listenerApi.condition((_a, state) => !isSyncBusy(state));
    }
    listenerApi.dispatch(saveFavorites());
  },
});

// After a load, save the merged list if taps made before it were replayed.
// Nothing else is in flight at that point (no save runs before the first load).
startAppListening({
  actionCreator: loadFavorites.fulfilled,
  effect: (_action, listenerApi) => {
    const replayed = Object.keys(listenerApi.getOriginalState().favorites.pendingChanges).length > 0;
    if (replayed) listenerApi.dispatch(saveFavorites());
  },
});

// Load this install's saved list once at launch.
store.dispatch(loadFavorites());

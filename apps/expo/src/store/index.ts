import { configureStore } from '@reduxjs/toolkit';

import favoritesReducer from './favoritesSlice';

/** The app's Redux store. Provided to every screen in app/_layout.tsx. */
export const store = configureStore({
  reducer: {
    favorites: favoritesReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

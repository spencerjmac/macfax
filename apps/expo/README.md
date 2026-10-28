# Macfax (Expo)

The Macfax mobile and web client, built with Expo SDK 58 and Expo Router. It is a
separate app from `web/` (the Next.js site) and shares pure TypeScript code with
it through `packages/core`, imported as `@macfax/core/*`.

There are no npm workspaces: this folder has its own `package.json` and lockfile.
Run every command below from `apps/expo`.

## Running

```bash
npm install

# Web, against local Django on port 8000
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000 npx expo start --web

# Phones on the same LAN (scan the QR code with Expo Go)
npx expo start

# Phones on another network
npx expo start --tunnel
```

`--tunnel` needs `@expo/ngrok`, which is not a dependency of this app. Expo's
docs install it with `npm i -g @expo/ngrok`.

## Expo Go and SDK 58

This app is on SDK 58. Expo Go only opens projects whose SDK matches the Expo Go
build on the phone, so check that the installed Expo Go supports SDK 58 before a
phone test. SDK 54 was dropped because the Expo Go build in use no longer
supported it.

## API base URL

- `EXPO_PUBLIC_API_BASE_URL` sets the API host. When it is unset, the app falls
  back to `https://macfax.usu.edu`.
- Do not create a `.env.local` pointing at `localhost`. It would apply to every
  platform, and on a phone `localhost` is the phone itself. Pass the variable
  inline for web development, as shown above.
- `EXPO_PUBLIC_` values are embedded in the JavaScript bundle. Never put secrets
  in them.
- `.env.example` documents the variable. Expo does not load it.
- After changing an `EXPO_PUBLIC_` value, add `--clear` to the next
  `expo export` (and to `expo start` if the old value seems to stick). Metro's
  cache otherwise keeps the value from the previous build.
- The production website sends no CORS headers for other origins, so the web
  build can only load data from a host that allows its origin (local Django
  with `http://localhost:8081` allowed). Phones are not affected.

## Checks

```bash
npx expo customize tsconfig.json    # regenerates route types in .expo/types after adding a screen
npx tsc --noEmit
npx expo lint
npx expo-doctor
npx expo install --check
npx expo export --clear --platform web      # also ios, android
```

`expo export` writes to `dist/`, which is gitignored.

## Screens

| Route | File | What it is |
| --- | --- | --- |
| `/` | `app/(tabs)/index.tsx` | Home: the NCAA hub |
| `/rankings` | `app/(tabs)/rankings.tsx` | Team rankings table |
| `/methodology` | `app/(tabs)/methodology.tsx` | Methodology index |
| `/team/[slug]?season=2025` | `app/team/[slug].tsx` | Team: Overview and Game log tabs |
| `/methodology/[slug]` | `app/methodology/[slug].tsx` | Methodology article |
| `/gate` | `app/gate.tsx` | Developer test bench |

`/gate` exists only in development, or in a build made with
`EXPO_PUBLIC_ENABLE_GATE=1`. Otherwise it redirects to Home.

## Known issues

- **Win-probability data for game 123501.** The curve from
  `/api/games/123501/detail/` (Michigan 69–63 Connecticut) keeps going after
  the final score and ends at 90–87. The website shows the same curve, so it
  is backend data, not the chart. Do not draw a curve whose last point
  disagrees with the game's final score; hide the chart or flag the game.
- **Native behaviour is unverified.** The app has been tested in a web browser
  and bundle-compiled for iOS and Android, but not run on a phone. Unknowns:
  tab bar and safe areas, the season picker modal, keyboard handling, scroll
  smoothness, logo loading, external links, and the chart's WebView.
  `src/charts/experimental/` has never run on a device.
- **Stale `EXPO_PUBLIC_` values.** Metro's cache can keep the value from the
  previous build. Add `--clear` to `expo export` (and to `expo start` if a
  value sticks) after changing one.
- **Not ported yet.** Team page tabs other than Overview and Game log (four
  factors, offense/defense, résumé, charts, players); game pages; the
  rankings four-factor views, conference/tournament filter, pre-tournament
  toggle and player rankings; matchup, outlook, visualizations, glossary and
  model health (these open the website); typeset formulas (shown as LaTeX
  source); everything NBA.

## Layout

- `app/` holds the Expo Router screens. `app/(tabs)/` are the bottom tabs;
  everything else pushes on top of them with a back button.
- `src/lib/api.ts` is the only place that talks to the network.
- `src/components/` holds shared components; `src/components/ui/` has the
  header, logo, and loading / error / empty states.
- `src/store/` holds the Redux store (Redux Toolkit). `favoritesSlice.ts` is
  "My Teams": `toggleFavorite`, `removeFavorite` and `clearFavorites` actions
  over a list of starred team ids. `FavoriteButton` on the team screen
  dispatches; Home's My Teams section and the rankings star read it. Use the
  typed `useAppDispatch` / `useAppSelector` from `src/store/hooks.ts`. The
  store is in memory only, so starred teams reset when the app restarts.
- `src/charts/` holds chart components, which take data as props.
  `src/charts/experimental/` is unverified on devices.
- `src/theme/tokens.ts` holds the design tokens, copied by hand from
  `web/src/app/globals.css` and `web/tailwind.config.js`.
- `tailwind.config.js`, `global.css`, `babel.config.js` and `metro.config.js`
  hold the NativeWind setup. `metro.config.js` also makes `packages/core`
  resolvable.

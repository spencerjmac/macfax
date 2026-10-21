# Macfax (Expo)

The Macfax mobile and web client, built with Expo SDK 54 and Expo Router. It is a
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

## Expo Go and SDK 54

This app stays on SDK 54 on purpose. The App Store build of Expo Go supports
SDK 54; newer SDKs on a physical iPhone need `eas go`, which requires a paid
Apple Developer Program membership.

If the App Store build of Expo Go moves to a newer SDK, this project will stop
opening on an iPhone. Check which SDK the store build supports before each phone
test.

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
| `/team/[slug]` | `app/team/[slug].tsx` | Team screen (placeholder) |
| `/methodology/[slug]` | `app/methodology/[slug].tsx` | Methodology article |
| `/gate` | `app/gate.tsx` | Developer test bench |

`/gate` exists only in development, or in a build made with
`EXPO_PUBLIC_ENABLE_GATE=1`. Otherwise it redirects to Home.

## Layout

- `app/` holds the Expo Router screens. `app/(tabs)/` are the bottom tabs;
  everything else pushes on top of them with a back button.
- `src/lib/api.ts` is the only place that talks to the network.
- `src/components/` holds shared components; `src/components/ui/` has the
  header, logo, and loading / error / empty states.
- `src/charts/` holds chart components, which take data as props.
  `src/charts/experimental/` is unverified on devices.
- `src/theme/tokens.ts` holds the design tokens, copied by hand from
  `web/src/app/globals.css` and `web/tailwind.config.js`.
- `tailwind.config.js`, `global.css`, `babel.config.js` and `metro.config.js`
  hold the NativeWind setup. `metro.config.js` also makes `packages/core`
  resolvable.

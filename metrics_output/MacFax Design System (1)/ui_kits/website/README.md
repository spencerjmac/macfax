# MacFax Website — UI Kit

Hi-fi recreation of the MacFax marketing + product surfaces (`macfax.usu.edu`). Single HTML file, plain JSX components, click-thru between Home → NCAA Rankings → Team Profile → Matchup → About.

## Files
- `index.html` — interactive shell (loads React + Babel from CDN, mounts the app)
- `components/App.jsx` — page router + top-level layout
- `components/Navigation.jsx` — sticky dark navbar with sport switcher
- `components/Footer.jsx` — minimal hairline footer
- `components/Home.jsx` — landing
- `components/Rankings.jsx` — sortable rankings table with heat-mapped AdjEM
- `components/TeamProfile.jsx` — team header + stat cards
- `components/Matchup.jsx` — two-team selector + projected outcome + four-factor edges
- `components/About.jsx` — editorial "What is MacFax?" page
- `components/Primitives.jsx` — Button, Card, Pill, Eyebrow, StatCard, FactorEdge, Lucide-style icons

Drawn from `web/src/` in `spencerjmac/macfax`. Component structure mirrors the codebase but cuts the data layer — everything renders against a small in-file `MOCK_TEAMS` array.

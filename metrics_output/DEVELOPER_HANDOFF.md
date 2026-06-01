# MacFax 2026 Redesign — Developer Handoff

This is the build checklist for porting the **2026 broadcast redesign** from the design system
into `spencerjmac/macfax` (`/web`, Next.js 14 + TS + Tailwind). Work top-to-bottom: tokens first
(low-risk, mostly find/replace), then the two structural logic changes, then the screen rebuilds.

> **Reference, not drop-in.** The prototype CSS (`redesign.css`) uses plain `.mfx-*` classes and the
> HTML files run React via CDN+Babel. Do **not** paste them in. Translate the *values* into your
> Tailwind/`globals.css` conventions and rebuild the screens as real components.

---

## Files to pull from the design system

Copy these out of the design-system project for reference while you build (drop them in a scratch
folder like `web/.design-ref/` — they are NOT shipped):

| File | Why you need it |
|---|---|
| `colors_and_type.css` | The token source of truth — copy the new vars verbatim |
| `ui_kits/website/redesign.css` | Every layout's exact values, keyed by `.mfx-*` class |
| `ui_kits/website/data.js` | Mock data shape + `TEAM_COLORS` map + `NCAA_BASE` baselines + `readable()` logic |
| `ui_kits/website/Homepage Redesign.html` | Homepage layout reference |
| `ui_kits/website/Sport Hub.html` | NEW sport-hub route reference |
| `ui_kits/website/NCAA Rankings.html` | Rankings table (heat-map + views) reference |
| `ui_kits/website/Team Profile.html` + `teamprofile.jsx` | Team profile tabs + mini-chart reference |
| `ui_kits/website/Visualizations.html` | Visualizations editorial layout reference |
| `ui_kits/website/Matchup.html` | Matchup tool (team colors + sections) reference |
| `README.md` (§ 2026 Broadcast Redesign) | The written spec / rationale |

The simplest way to grab all of them: **download the whole `ui_kits/website/` folder + the root
`colors_and_type.css` + `README.md`** (see "What to download" at the bottom).

---

## Phase 1 — Design tokens  → `web/src/app/globals.css` + `tailwind.config.js`

Low-risk. These mostly map onto your existing `:root` block.

### 1.1 Add the display font (Oswald)
- **Google Fonts import** (wherever you currently load Inter + IBM Plex Mono): add
  `Oswald:wght@400;500;600;700`.
- **`globals.css` `:root`:** add
  ```css
  --font-display: 'Oswald', 'Inter', system-ui, sans-serif;
  ```
- **`tailwind.config.js` → `theme.extend.fontFamily`:**
  ```js
  display: ['Oswald', 'Inter', 'system-ui', 'sans-serif'],
  ```
  → enables `font-display` utility.

### 1.2 Add broadcast-ink tokens
```css
--ink:      #0b1220;
--ink-2:    #131c2e;
--ink-3:    #1b2740;
--ink-line: #243149;
--ink-fg:   #c2cde0;
--ink-fg2:  #8d9bb5;
```
Mirror in Tailwind `theme.extend.colors` if you prefer utilities (`bg-ink`, `text-ink-fg`, …).

### 1.3 Replace the heat-map scale (teal-only)
Swap the old emerald/amber/rose values for:
```css
--heat-3:    rgba(64,144,128,0.52);  /* elite */
--heat-2:    rgba(64,144,128,0.34);
--heat-1:    rgba(64,144,128,0.16);
--heat-0:    rgba(100,116,139,0.05); /* ~average */
--heat-lo-1: rgba(100,116,139,0.10);
--heat-lo-2: rgba(100,116,139,0.14); /* well below avg */
```
Keep your existing `--heat-good/mid/bad-*` names as **aliases** pointing at these (so old markup
keeps working): `--heat-good-3: var(--heat-3)`, etc. (See `colors_and_type.css` for the full alias block.)

### 1.4 Heading utilities
Add these helpers (or Tailwind `@layer components`):
```css
.display-sport { font: 700 clamp(46px,5.4vw,76px)/1.0 var(--font-display); text-transform: uppercase; letter-spacing: .005em; }
.head-sport    { font: 700 clamp(30px,3.4vw,42px)/1.0 var(--font-display); text-transform: uppercase; }
.kicker-sport  { font: 600 13px/1 var(--font-display); text-transform: uppercase; letter-spacing: .14em; color: var(--brand); }
```

**Type rule going forward:** Oswald = wordmark, hero/section headlines, table headers, tab labels,
buttons (uppercase, slight positive tracking). Inter = body/lede/nav/forms. IBM Plex Mono = every number.

---

## Phase 2 — Two structural logic changes (the important ones)

### 2.1 Heat-map anchoring  → `RankingsTable`
**Bug today:** cells are colored relative to the rows currently on screen, so the lowest visible
team paints red even if it's #15 of 365.

**Fix:** color each numeric cell against a **fixed national baseline** (min/max across all D-I teams,
not the visible slice). Reference impl in `data.js` (`NCAA_BASE`) + `NCAA Rankings.html` (`heatStyle`):
```js
// lo/hi are NATIONAL bounds per metric; invert for defense (lower = better)
function heatStyle(v, [lo, hi], invert=false){
  let t = (v - lo) / (hi - lo); if (invert) t = 1 - t; t = Math.max(0, Math.min(1, t));
  if (t >= 0.5){ const a=(t-0.5)/0.5; return { background:`rgba(64,144,128,${0.10+a*0.42})` }; }
  const a=(0.5-t)/0.5; return { background:`rgba(100,116,139,${a*0.14})` };
}
```
Baselines used in the prototype: `adjEM [-12,36]`, `adjO [92,122]`, `adjD [84,112]`, `tempo [60,74]`.
Replace with real season percentiles from your API if you have them.

### 2.2 Matchup team colors  → `MatchupTool`
**Intent:** tint the forecast scores, four-factor bars, win-probability bar, and recent-form record
cards with the **two selected teams' colors** — as **accents on a white page only**, never full-bleed
backgrounds (that "color flood" is the failure mode to avoid).

- Add a `TEAM_COLORS` lookup keyed by team id (see `data.js`; populate from your real team metadata
  if you have official hexes).
- Add the `readable(hex)` luminance helper that darkens light colors (Carolina blue, Spurs silver)
  for use as text, so they stay legible on white. (Full fn in `Matchup.html`.)
- Apply color to: predicted-score numbers, win-prob bar fills, four-factor bar fills + value labels,
  recent-form record card tint (`color + '14'` bg, `color + '40'` border).

---

## Phase 3 — Screen rebuilds (match the prototypes)

For each, open the prototype HTML, lift exact spacing/type/colors from `redesign.css` (classes noted),
and rebuild as real components against your live data.

| # | Build | Prototype | Your component(s) | Notes |
|---|---|---|---|---|
| 1 | **Homepage** | `Homepage Redesign.html` | marketing landing | Ink hero (`.mfx-hero`), "Pick your league" cards (`.mfx-league`) link to the hubs. **Remove** Open-Source card + "365/30 teams" filler bar. |
| 2 | **Sport Hub** (NEW route `/ncaa`, `/nba`) | `Sport Hub.html` | new `SportHub` page | Compact ink hero + #1 leader spotlight (`.mfx-shero`/`.mfx-spot`), top-5 strip (`.mfx-strip`), tools grid (`.mfx-tools`), viz cards (`.mfx-viz`). White tile behind dark logos. |
| 3 | **NCAA Rankings** | `NCAA Rankings.html` | `RankingsTable` | Dark Oswald header bar, **Efficiency / Four-Factors** view toggle, sortable cols w/ national-rank superscripts, search + conf filter, national-baseline heat map (Phase 2.1). Sync NBA table to same format. |
| 4 | **Team Profile** | `Team Profile.html` + `teamprofile.jsx` | `TeamHeader` + `TeamPageTabs` | Ink header. Tabs: **Overview** ("story in 30s": 3 key stats + narrative + 1 signature chart + recent form/4-factor rail), **Off/Def** (two-column hierarchy), **Game Log** (add **ORtg + DRtg** alongside four factors), **Charts** (all viz as mini-charts, *this team highlighted*). |
| 5 | **Visualizations** | `Visualizations.html` | visualizations index | Editorial: dark feature hero w/ live chart (`.mfx-feature`) + article-card grid (`.mfx-article`) w/ category, standfirst, date, Live/Soon. Trapezoid sits **wide-side-up**. |
| 6 | **Matchup** | `Matchup.html` | `MatchupTool` | Team colors (Phase 2.2). Sections: Game Forecast, Four-Factor Breakdown (w/ impact pts), Game Volatility (0–100 + Pace/3P/Variance), Recent Form (last 10). **No** model-meta footer strip. |

**Global nav:** sport switcher (NCAA/NBA) + Oswald uppercase links, 4px teal hairline under the dark bar.
Icons are **Lucide** (stroke 1.5), not emoji. Trapezoid/crystal-ball/slipper are bespoke marks — see prototypes.

---

## Phase 4 — Separate bug-fix track (not redesign, but on the list)

These are pre-existing code bugs, independent of the visual port:
- [ ] **Last-updated date** always shows today — use the real data timestamp, not `new Date()`.
- [ ] **Efficiency Landscape** doesn't resize with the window — add a resize observer / responsive width.
- [ ] **Efficiency Landscape filters** do nothing — wire filter state into the chart query.
- [ ] **BPR/MPIR warning block** on NBA Player Stats — remove the JSX warning block.

## Out of scope (future passes)
- **NBA Compare** page (side-by-side players) — design not built yet; NBA needs more data first.
- **NBA four-factor data** — the Matchup four-factor + shot-profile sections need NBA four-factor
  fields wired in (NBA data currently carries only net/O/D rating).

---

## What to download from this project

Grab the whole UI-kit folder plus the two root spec files:

```
colors_and_type.css                 ← token source of truth (Phase 1)
README.md                           ← § 2026 Broadcast Redesign (the written spec)
ui_kits/website/                    ← everything below
├── redesign.css                    ← layout values, keyed by .mfx-* class
├── data.js                         ← mock data shape, TEAM_COLORS, NCAA_BASE, readable()
├── Homepage Redesign.html
├── Sport Hub.html
├── NCAA Rankings.html
├── Team Profile.html
├── teamprofile.jsx                 ← team-profile tab components + mini charts
├── Visualizations.html
├── Matchup.html
└── Redesign Index.html             ← click-through launcher for all six
```

(Skip `index.html`, `styles.css`, `components/`, `tweaks-panel.jsx` — those are the OLD pre-redesign
kit + prototype scaffolding, not part of the port.)

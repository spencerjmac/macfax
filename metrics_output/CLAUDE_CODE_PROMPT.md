# Claude Code Prompt — MacFax 2026 Redesign Implementation

Copy everything in the fenced block below into Claude Code, running inside your local clone of
`spencerjmac/macfax`. Before you start, copy the design-system reference files into
`web/.design-ref/` (see the list at the very bottom of this file, and in `DEVELOPER_HANDOFF.md`).

---

```
You are implementing the MacFax "2026 broadcast redesign" in this repo (Next.js 14 + TypeScript +
Tailwind, app lives in /web; Django API in /backend). A complete visual spec and reference build
is in web/.design-ref/ — read it before changing anything:

  - web/.design-ref/DEVELOPER_HANDOFF.md   ← the build checklist; follow it phase by phase
  - web/.design-ref/colors_and_type.css    ← token source of truth
  - web/.design-ref/redesign.css           ← exact layout values, keyed by .mfx-* classes
  - web/.design-ref/data.js                ← mock-data SHAPE + TEAM_COLORS + NCAA_BASE + readable()
  - web/.design-ref/*.html, teamprofile.jsx ← per-screen layout references

GROUND RULES
- The reference CSS uses plain .mfx-* classes and the HTML runs React via CDN+Babel. Do NOT copy
  them in. Translate the VALUES into our Tailwind + globals.css conventions and build real,
  typed components wired to our existing data layer / API hooks.
- Reuse existing components, hooks, and API calls. Do not introduce new data-fetching patterns or
  new dependencies without asking. No new UI libraries.
- Match our existing file/component conventions (naming, folder layout, server vs client components).
- Keep every number in IBM Plex Mono. Keep the wordmark lowercase. Icons are Lucide (we can use
  lucide-react), never emoji. No gradients as decoration (one faint teal hero glow is allowed).
- Work in small, reviewable commits — one phase (or one screen) per commit. After each, run the
  build/typecheck/lint and report what you changed. Pause for my review between screens.

DO THIS IN ORDER

Phase 1 — Tokens (one commit):
  1. Add Oswald (weights 400–700) to our font loading; add --font-display to globals.css :root and
     a `display` family to tailwind.config.js.
  2. Add the broadcast-ink tokens (--ink, --ink-2, --ink-3, --ink-line, --ink-fg, --ink-fg2).
  3. Replace the heat-map CSS vars with the teal/slate scale (--heat-3..--heat-lo-2) and keep the
     old --heat-good/mid/bad-* names as aliases pointing at the new ones.
  4. Add the .display-sport / .head-sport / .kicker-sport helpers.
  Verify nothing visually regressed, then commit.

Phase 2 — Structural logic (one commit each):
  2a. RankingsTable heat map: color cells against a FIXED NATIONAL baseline (min/max across all
      teams), not the visible rows. Invert for defense (lower = better). Port heatStyle() +
      NCAA_BASE from the reference; use real season bounds from our data if available.
  2b. MatchupTool team colors: add a TEAM_COLORS lookup (prefer real team hexes from our team
      metadata; fall back to the reference map) and the readable() luminance helper. Tint ONLY
      the scores, four-factor bars, win-prob bar, and recent-form record cards — accents on a
      white page, never full-bleed backgrounds.

Phase 3 — Rebuild screens to match the prototypes (one commit per screen, pause for review):
  1. Homepage — ink hero + "Pick your league" cards into the hubs; remove the Open-Source card and
     the "365/30 teams" filler bar.
  2. Sport Hub — NEW route for /ncaa and /nba: ink hero + #1 leader spotlight, top-5 strip, tools
     grid, editorial viz cards. White tile behind dark team logos.
  3. NCAA Rankings — dark Oswald header, Efficiency/Four-Factors view toggle, sortable columns with
     national-rank superscripts, search + conference filter, national-baseline heat map. Sync the
     NBA rankings table to the same format.
  4. Team Profile — ink header; tabs: Overview (3 key stats + auto narrative + one signature chart +
     recent-form/four-factor rail), Off/Def (two-column hierarchy), Game Log (ADD ORtg + DRtg next
     to the four factors), Charts (all our visualizations as mini-charts with THIS team highlighted).
  5. Visualizations — editorial: dark feature hero with a live chart + article-card grid (category,
     standfirst, date, Live/Soon). The Trapezoid of Excellence renders wide-side-up.
  6. Matchup — apply Phase 2b colors; sections: Game Forecast, Four-Factor Breakdown (with impact
     points), Game Volatility (0–100 + Pace/3P/Variance), Recent Form (last 10). Remove the old
     model-meta footer strip.

Phase 4 — Pre-existing bug fixes (separate commits, optional if time):
  - Last-updated date shows today: use the real data timestamp, not new Date().
  - Efficiency Landscape doesn't resize: add a resize observer / responsive width.
  - Efficiency Landscape filters are inert: wire filter state into the chart.
  - Remove the BPR/MPIR warning block on NBA Player Stats.

OUT OF SCOPE — do not build unless I ask: NBA Compare page; NBA four-factor data wiring.

Start by reading web/.design-ref/DEVELOPER_HANDOFF.md and the relevant reference file(s), then give
me a short plan for Phase 1 and wait for my go-ahead before editing.
```

---

## Files to copy into `web/.design-ref/` first

From the MacFax design-system project, copy these so Claude Code can read them locally:

- `colors_and_type.css`
- `DEVELOPER_HANDOFF.md`
- `README.md`
- the entire `ui_kits/website/` folder (the `.html` files, `redesign.css`, `data.js`, `teamprofile.jsx`)

> `web/.design-ref/` is reference-only — add it to `.gitignore` or delete it once the port is done;
> none of it ships to production.

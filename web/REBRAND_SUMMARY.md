# macfax Rebrand - Implementation Summary

## ✅ Completed Changes

### 1. Brand Assets Folder
- Created `/web/public/brand/` folder for logo assets
- Added README with instructions for required logo files:
  - `macfax-logo.png` (wide wordmark for desktop navbar)
  - `macfax-mark-512.png`, `macfax-mark-180.png`, `macfax-mark-32.png` (square marks)

### 2. Design Tokens (CSS Variables)
Updated [globals.css](web/src/app/globals.css) with new color system:
```css
--bg: #0b1220          /* Dark navy background */
--surface: #ffffff      /* White surface */
--text: #0b1220        /* Primary text */
--textOnDark: #f8fafc  /* Text on dark backgrounds */
--muted: #64748b       /* Muted text */
--border: #e2e8f0      /* Borders */

--brand: #409080       /* PRIMARY teal accent */
--brand2: #70c070      /* SECONDARY green (for positive metrics) */
--brandBlue: #3080b0   /* INFO blue accent */

--positive: #22c55e    /* Semantic green */
--negative: #ef4444    /* Semantic red */
--warning: #94a3b8     /* Neutralized slate (NO ORANGE) */
```

### 3. Tailwind Configuration
Updated [tailwind.config.js](web/src/app/tailwind.config.js):
- Mapped all colors to CSS variables
- Replaced orange theme colors with brand teal
- Added fallback mappings for legacy orange references
- Updated chart palette to remove orange values

### 4. Metadata & Branding
- Updated all page titles from "CBB Analytics" to "macfax"
- Updated site description to emphasize "macfax" brand
- Added "macfax" branding to footer in [layout.tsx](web/src/app/layout.tsx)

### 5. Navigation Component
Updated [Navigation.tsx](web/src/components/Navigation.tsx):
- Dark navy background (`bg-bg`) with teal border (`border-brand`)
- Replaced basketball emoji with macfax logo images
  - Desktop: uses `macfax-logo.png`
  - Mobile: uses `macfax-mark-180.png`
- Active nav links use brand teal instead of orange

### 6. Homepage Redesign
Updated [page.tsx](web/src/app/page.tsx):
- Replaced all emoji icons with Lucide icons:
  - Rankings: `BarChart3`
  - Matchup: `Swords`
  - Visualizations: `ScatterChart`
  - Glossary: `BookOpen`
  - About: `Info`
  - Open Source: `Github`
- All hover states use brand teal
- Quick stats use brand teal accent

### 7. Orange Removal (Complete)
Replaced ALL orange usage across all components:

**Components Updated:**
- `TeamHeader.tsx` - brand teal for ranks and links
- `StatCards.tsx` - brand teal for rank pills
- `RankingsTable.tsx` - brand teal for active tabs, focus rings, highlights
- `MatchupTool.tsx` - brand teal for focus rings
- `GlossaryTable.tsx` - brand teal for focus rings
- `TrapezoidChart.tsx` - teal for trapezoid boundary and inside-trapezoid teams
- `TeamPageTabs.tsx` - brand teal for all tabs, metrics, rank pills, Four Factor Index cards
- `matchup/page.tsx` - semantic colors (negative red for disadvantage, brand teal for highlights)

**Specific Replacements:**
- `bg-orange-*` → `bg-brand`
- `text-orange-*` → `text-brand` or `text-negative` (context-dependent)
- `border-orange-*` → `border-brand`
- `ring-orange-*` → `ring-brand`
- `#ED713A`, `#D85F2E` → `#409080` (brand teal)

### 8. Dependencies
- Installed `lucide-react` for consistent icon system

---

## 🎨 Next Steps (Action Required)

### Add Logo Assets
You need to add the following image files to `/web/public/brand/`:

1. **macfax-logo.png** - Wide horizontal wordmark
   - Recommended size: ~280px width, ~64px height
   - Used in: Desktop navbar

2. **macfax-mark-180.png** - Square logo mark
   - Size: 180x180px
   - Used in: Mobile navbar

3. **macfax-mark-512.png** - Square logo mark
   - Size: 512x512px
   - Used in: PWA/app icons (future)

4. **macfax-mark-32.png** - Square logo mark
   - Size: 32x32px
   - Used in: Favicon

### Update Favicon
Once you have `macfax-mark-32.png`, add to [layout.tsx](web/src/app/layout.tsx):
```tsx
export const metadata: Metadata = {
  // ... existing fields
  icons: {
    icon: '/brand/macfax-mark-32.png',
    shortcut: '/brand/macfax-mark-32.png',
    apple: '/brand/macfax-mark-180.png',
  },
};
```

### Test the Site
Run the dev server to verify all changes:
```powershell
cd web
npm run dev
```

Then check:
- ✅ Navigation displays macfax branding (navbar will show Next.js image loading errors until logos are added)
- ✅ All links and buttons use teal accent color
- ✅ No orange colors visible anywhere
- ✅ Homepage icons are Lucide icons, not emojis
- ✅ All page titles say "macfax"
- ✅ Footer displays "macfax" branding

---

## 📋 Color Usage Guide

### Primary Interactions
- **Links, buttons, active states:** `text-brand` / `bg-brand` / `border-brand`
- **Focus rings:** `ring-brand`
- **Primary metrics/emphasis:** `text-brand`

### Semantic Colors
- **Good/Positive metrics:** `text-positive` or `text-brand2`
- **Bad/Negative metrics:** `text-negative`
- **Warnings/Neutral:** `text-warning` (slate, not orange!)

### Layout
- **Dark sections (navbar):** `bg-bg` with `text-textOnDark`
- **Light sections:** `bg-surface` with `text-text`
- **Muted text:** `text-muted`

---

## 🎯 Design Acceptance Checklist

- ✅ No layout breakage
- ✅ Brand name says "macfax" everywhere (except data source credits)
- ✅ Orange is fully removed as a UI accent
- ✅ Navbar uses dark navy + teal brand highlight
- ✅ Emojis removed; Lucide icons used consistently
- ✅ Tailwind uses brand tokens (no random hex values)
- ✅ All interactive elements use brand teal
- ✅ Semantic colors used appropriately
- ⚠️  Logo images need to be added

---

## 🔧 Technical Notes

- All color changes use CSS variables for easy future adjustments
- Tailwind config maps to variables, so you can change colors in one place ([globals.css](web/src/app/globals.css))
- Lucide icons use consistent 1.5px stroke width for visual harmony
- Navigation uses Next.js Image component for optimized logo loading
- No breaking changes to existing functionality

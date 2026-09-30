/**
 * Primary/secondary kit colors for the 48 2026 World Cup teams, used to
 * color matchup/group visualizations so each team reads as itself rather
 * than a generic palette swatch.
 */

export interface WorldCupTeamColors {
  primary: string;
  secondary: string;
}

// Cycled for any team missing from the map below.
export const DEFAULT_WC_COLORS: WorldCupTeamColors[] = [
  { primary: '#3080b0', secondary: '#409080' },
  { primary: '#409080', secondary: '#70c070' },
  { primary: '#70c070', secondary: '#3080b0' },
  { primary: '#94a3b8', secondary: '#64748b' },
];

const WORLD_CUP_TEAM_COLORS: Record<string, WorldCupTeamColors> = {
  'Mexico':                 { primary: '#006847', secondary: '#CE1126' },
  'South Africa':           { primary: '#007A4D', secondary: '#FFB612' },
  'South Korea':            { primary: '#C60C30', secondary: '#002868' },
  'Czechia':                { primary: '#D7141A', secondary: '#11457E' },
  'Canada':                 { primary: '#FF0000', secondary: '#000000' },
  'Bosnia and Herzegovina': { primary: '#002395', secondary: '#FECB00' },
  'Qatar':                  { primary: '#8D1B3D', secondary: '#FFFFFF' },
  'Switzerland':            { primary: '#FF0000', secondary: '#000000' },
  'Brazil':                 { primary: '#FFDF00', secondary: '#009739' },
  'Morocco':                { primary: '#C1272D', secondary: '#006233' },
  'Haiti':                  { primary: '#00209F', secondary: '#D21034' },
  'Scotland':               { primary: '#0065BD', secondary: '#FDB913' },
  'United States':          { primary: '#002868', secondary: '#BF0A30' },
  'Paraguay':               { primary: '#D52B1E', secondary: '#0038A8' },
  'Australia':              { primary: '#FFCD00', secondary: '#00843D' },
  'Turkey':                 { primary: '#E30A17', secondary: '#FFFFFF' },
  'Germany':                { primary: '#000000', secondary: '#DD0000' },
  'Curaçao':                { primary: '#002B7F', secondary: '#FFD100' },
  'Ivory Coast':            { primary: '#FF8200', secondary: '#009A44' },
  'Ecuador':                { primary: '#FFD100', secondary: '#034EA2' },
  'Netherlands':            { primary: '#FF6600', secondary: '#21468B' },
  'Japan':                  { primary: '#00468C', secondary: '#BC002D' },
  'Sweden':                 { primary: '#FECC02', secondary: '#006AA7' },
  'Tunisia':                { primary: '#E70013', secondary: '#FFFFFF' },
  'Belgium':                { primary: '#ED2939', secondary: '#FAE042' },
  'Egypt':                  { primary: '#CE1126', secondary: '#000000' },
  'Iran':                   { primary: '#C8102E', secondary: '#239F40' },
  'New Zealand':            { primary: '#000000', secondary: '#FFFFFF' },
  'Spain':                  { primary: '#C60B1E', secondary: '#FFC400' },
  'Cape Verde':             { primary: '#003893', secondary: '#CF2027' },
  'Saudi Arabia':           { primary: '#006C35', secondary: '#FFFFFF' },
  'Uruguay':                { primary: '#5CB7E2', secondary: '#000000' },
  'France':                 { primary: '#0055A4', secondary: '#EF4135' },
  'Senegal':                { primary: '#00853F', secondary: '#FDEF42' },
  'Iraq':                   { primary: '#CE1126', secondary: '#007A3D' },
  'Norway':                 { primary: '#EF2B2D', secondary: '#002868' },
  'Argentina':              { primary: '#75AADB', secondary: '#000000' },
  'Algeria':                { primary: '#006233', secondary: '#D21034' },
  'Austria':                { primary: '#ED2939', secondary: '#FFFFFF' },
  'Jordan':                 { primary: '#CE1126', secondary: '#007A3D' },
  'Portugal':               { primary: '#FF0000', secondary: '#006600' },
  'DR Congo':               { primary: '#007FFF', secondary: '#CE1021' },
  'Uzbekistan':             { primary: '#0099B5', secondary: '#1EB53A' },
  'Colombia':               { primary: '#FCD116', secondary: '#003893' },
  'England':                { primary: '#CE1124', secondary: '#00247D' },
  'Croatia':                { primary: '#FF0000', secondary: '#171796' },
  'Ghana':                  { primary: '#006B3F', secondary: '#FCD116' },
  'Panama':                 { primary: '#DA121A', secondary: '#072357' },
};

export function getWorldCupTeamColors(name: string, fallbackIndex = 0): WorldCupTeamColors {
  return WORLD_CUP_TEAM_COLORS[name] ?? DEFAULT_WC_COLORS[fallbackIndex % DEFAULT_WC_COLORS.length];
}

/** Black or white text for legible contrast against the given hex background. */
export function contrastText(hex: string): '#000000' | '#ffffff' {
  const c = hex.replace('#', '');
  const r = parseInt(c.substring(0, 2), 16) / 255;
  const g = parseInt(c.substring(2, 4), 16) / 255;
  const b = parseInt(c.substring(4, 6), 16) / 255;
  const lin = (v: number) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  const luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return luminance > 0.45 ? '#000000' : '#ffffff';
}

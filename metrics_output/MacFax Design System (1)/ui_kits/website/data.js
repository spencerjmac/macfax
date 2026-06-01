// MacFax — shared mock data for redesign prototypes
// Exposed as globals (no modules) so multiple <script type="text/babel"> files share them.

const LOGO = (id) => `../../assets/teams/${id}.png`;
const SVG  = (id) => `../../assets/teams/${id}.svg`;

const NCAA = [
  { id:'duke',      name:'Duke',           conf:'ACC',      rec:'24-3', em:34.21, o:120.4, d:86.2 },
  { id:'kansas',    name:'Kansas',         conf:'Big 12',   rec:'22-4', em:29.84, o:118.7, d:88.9 },
  { id:'uconn',     name:'UConn',          conf:'Big East', rec:'23-4', em:27.66, o:117.2, d:89.5 },
  { id:'houston',   name:'Houston',        conf:'Big 12',   rec:'25-2', em:25.41, o:114.1, d:88.7 },
  { id:'tennessee', name:'Tennessee',      conf:'SEC',      rec:'21-5', em:23.18, o:113.6, d:90.4 },
];

const NBA = [
  { id:'okc-thunder',         name:'OKC Thunder',        conf:'West · NW', rec:'68-14', em:12.3, o:119.2, d:106.9, ext:'svg' },
  { id:'cleveland-cavaliers', name:'Cleveland Cavaliers',conf:'East · C',  rec:'64-18', em:9.8,  o:121.0, d:111.2, ext:'svg' },
  { id:'new-york-knicks',     name:'New York Knicks',    conf:'East · ATL',rec:'51-31', em:5.4,  o:117.3, d:111.9, ext:'png' },
  { id:'san-antonio-spurs',   name:'San Antonio Spurs',  conf:'West · SW', rec:'48-34', em:3.1,  o:115.8, d:112.7, ext:'svg' },
  { id:'detroit-pistons',     name:'Detroit Pistons',    conf:'East · C',  rec:'44-38', em:1.2,  o:114.0, d:112.8, ext:'svg' },
];

const teamLogo = (t) => t.ext === 'svg' ? SVG(t.id) : LOGO(t.id);

// Primary team colors (used as ACCENTS in the matchup tool — scores, bars, win-prob,
// recent-form cards). Chosen dark enough to read on white; light ones get darkened
// for text via readable() at use site.
const TEAM_COLORS = {
  duke:'#0033A0', kansas:'#0051BA', uconn:'#0C2340', houston:'#C8102E',
  tennessee:'#E77500', ucla:'#2774AE', gonzaga:'#002967', 'iowa-st':'#A6192E',
  auburn:'#0C2340', baylor:'#154734', illinois:'#13294B', arizona:'#AB0520',
  unc:'#4B9CD3', kentucky:'#0033A0', marquette:'#003594',
  'okc-thunder':'#007AC1', 'cleveland-cavaliers':'#860038',
  'new-york-knicks':'#006BB6', 'san-antonio-spurs':'#5D6770', 'detroit-pistons':'#C8102E',
};
const teamColor = (id) => TEAM_COLORS[id] || '#409080';

// Full NCAA rankings dataset (top 15 of 365) — efficiency + four factors.
// orb/ftr added for complete four-factor view; *Rank fields are national ranks.
const NCAA_FULL = [
  { id:'duke',      name:'Duke',           conf:'ACC',      rec:'24-3', adjEM:34.21, adjO:120.4, adjD:86.2,  oRk:2,  dRk:6,   tempo:68.4, eFG:0.567, eFGd:0.461, tov:0.142, tovd:0.198, orb:0.345, ftr:0.362 },
  { id:'kansas',    name:'Kansas',         conf:'Big 12',   rec:'22-4', adjEM:29.84, adjO:118.7, adjD:88.9,  oRk:5,  dRk:11,  tempo:66.7, eFG:0.554, eFGd:0.469, tov:0.151, tovd:0.183, orb:0.318, ftr:0.341 },
  { id:'uconn',     name:'UConn',          conf:'Big East', rec:'23-4', adjEM:27.66, adjO:117.2, adjD:89.5,  oRk:8,  dRk:14,  tempo:69.1, eFG:0.548, eFGd:0.474, tov:0.163, tovd:0.190, orb:0.361, ftr:0.329 },
  { id:'houston',   name:'Houston',        conf:'Big 12',   rec:'25-2', adjEM:25.41, adjO:114.1, adjD:88.7,  oRk:18, dRk:9,   tempo:63.5, eFG:0.532, eFGd:0.461, tov:0.158, tovd:0.205, orb:0.372, ftr:0.318 },
  { id:'tennessee', name:'Tennessee',      conf:'SEC',      rec:'21-5', adjEM:23.18, adjO:113.6, adjD:90.4,  oRk:22, dRk:18,  tempo:65.2, eFG:0.529, eFGd:0.477, tov:0.166, tovd:0.196, orb:0.334, ftr:0.347 },
  { id:'ucla',      name:'UCLA',           conf:'Big Ten',  rec:'20-6', adjEM:21.82, adjO:115.1, adjD:93.3,  oRk:14, dRk:31,  tempo:66.0, eFG:0.541, eFGd:0.489, tov:0.157, tovd:0.182, orb:0.302, ftr:0.311 },
  { id:'gonzaga',   name:'Gonzaga',        conf:'WCC',      rec:'22-5', adjEM:20.94, adjO:118.3, adjD:97.4,  oRk:6,  dRk:54,  tempo:70.2, eFG:0.564, eFGd:0.496, tov:0.149, tovd:0.176, orb:0.329, ftr:0.336 },
  { id:'iowa-st',   name:'Iowa State',     conf:'Big 12',   rec:'21-6', adjEM:19.67, adjO:111.4, adjD:91.7,  oRk:38, dRk:21,  tempo:64.3, eFG:0.521, eFGd:0.481, tov:0.164, tovd:0.211, orb:0.341, ftr:0.298 },
  { id:'auburn',    name:'Auburn',         conf:'SEC',      rec:'22-5', adjEM:18.42, adjO:112.0, adjD:93.6,  oRk:31, dRk:33,  tempo:68.7, eFG:0.524, eFGd:0.486, tov:0.171, tovd:0.197, orb:0.356, ftr:0.352 },
  { id:'baylor',    name:'Baylor',         conf:'Big 12',   rec:'19-7', adjEM:17.13, adjO:113.2, adjD:96.1,  oRk:24, dRk:46,  tempo:67.4, eFG:0.534, eFGd:0.493, tov:0.156, tovd:0.184, orb:0.327, ftr:0.319 },
  { id:'illinois',  name:'Illinois',       conf:'Big Ten',  rec:'20-7', adjEM:15.88, adjO:114.7, adjD:98.8,  oRk:16, dRk:62,  tempo:69.9, eFG:0.541, eFGd:0.501, tov:0.150, tovd:0.179, orb:0.338, ftr:0.305 },
  { id:'arizona',   name:'Arizona',        conf:'Big 12',   rec:'19-8', adjEM:14.62, adjO:113.8, adjD:99.2,  oRk:20, dRk:67,  tempo:70.5, eFG:0.539, eFGd:0.500, tov:0.155, tovd:0.181, orb:0.314, ftr:0.327 },
  { id:'unc',       name:'North Carolina', conf:'ACC',      rec:'19-7', adjEM:13.41, adjO:115.6, adjD:102.2, oRk:11, dRk:96,  tempo:69.0, eFG:0.546, eFGd:0.514, tov:0.142, tovd:0.171, orb:0.331, ftr:0.343 },
  { id:'kentucky',  name:'Kentucky',       conf:'SEC',      rec:'20-7', adjEM:12.18, adjO:117.4, adjD:105.2, oRk:9,  dRk:131, tempo:71.8, eFG:0.557, eFGd:0.519, tov:0.139, tovd:0.165, orb:0.309, ftr:0.358 },
  { id:'marquette', name:'Marquette',      conf:'Big East', rec:'20-7', adjEM:11.04, adjO:111.1, adjD:100.1, oRk:42, dRk:78,  tempo:65.8, eFG:0.518, eFGd:0.498, tov:0.169, tovd:0.183, orb:0.322, ftr:0.301 },
];

// National baselines for heat-mapping (approx full-D1 spread, not just the visible 15).
// This keeps every top-15 team reading positive instead of painting #15 red.
const NCAA_BASE = { adjEM: [-12, 36], adjO: [92, 122], adjD: [84, 112], tempo: [60, 74] };

// Per-team game log (design mock; opponents drawn from the ranked set).
// oRtg/dRtg = single-game offensive/defensive rating (pts per 100 poss).
const GAMELOG = [
  { date:'Mar 6',  opp:'North Carolina', oppId:'unc',       oppRk:13, loc:'H', wl:'W', ts:84, os:71, oRtg:121.7, dRtg:102.9, eFG:0.581, tov:0.118, orb:0.372, ftr:0.341 },
  { date:'Mar 2',  opp:'Louisville',     oppId:null,        oppRk:28, loc:'A', wl:'W', ts:78, os:69, oRtg:114.2, dRtg:101.0, eFG:0.542, tov:0.144, orb:0.331, ftr:0.298 },
  { date:'Feb 26', opp:'Virginia',       oppId:null,        oppRk:41, loc:'H', wl:'W', ts:71, os:55, oRtg:118.0, dRtg:91.4,  eFG:0.566, tov:0.131, orb:0.356, ftr:0.402 },
  { date:'Feb 22', opp:'Clemson',        oppId:null,        oppRk:35, loc:'A', wl:'L', ts:68, os:72, oRtg:104.1, dRtg:110.3, eFG:0.489, tov:0.176, orb:0.288, ftr:0.265 },
  { date:'Feb 18', opp:'NC State',       oppId:null,        oppRk:62, loc:'H', wl:'W', ts:88, os:74, oRtg:126.4, dRtg:106.2, eFG:0.604, tov:0.122, orb:0.401, ftr:0.355 },
  { date:'Feb 14', opp:'Wake Forest',    oppId:null,        oppRk:78, loc:'A', wl:'W', ts:81, os:70, oRtg:117.8, dRtg:101.8, eFG:0.557, tov:0.139, orb:0.344, ftr:0.312 },
  { date:'Feb 10', opp:'Miami',          oppId:null,        oppRk:95, loc:'H', wl:'W', ts:90, os:62, oRtg:129.1, dRtg:88.9,  eFG:0.612, tov:0.108, orb:0.388, ftr:0.371 },
  { date:'Feb 6',  opp:'Pittsburgh',     oppId:null,        oppRk:84, loc:'A', wl:'W', ts:76, os:68, oRtg:112.4, dRtg:100.6, eFG:0.531, tov:0.151, orb:0.329, ftr:0.288 },
];

// Five most recent results, newest first (for the Overview form strip).
const RECENT_FORM = GAMELOG.slice(0, 5).map(g => g.wl);

const HUB = {
  ncaa: {
    label: 'NCAA', eyebrow: 'College Basketball · Updated daily',
    title: 'College Basketball', teamCount: 365,
    lede: 'Adjusted efficiency, four factors, and matchup forecasts for all 365 Division I teams — ranked by what they actually do on the floor, not their record.',
    secondaryCta: 'Matchup tool',
    facts: [{ k:'Teams', v:'365' }, { k:'Conferences', v:'32' }, { k:'Games modeled', v:'5.4', sub:'k' }],
    teams: NCAA,
    tools: [
      { i:'trophy',  t:'Rankings',       b:'Full AdjEM table with four factors, sortable by any metric and filterable by conference.' },
      { i:'swords',  t:'Matchup',        b:'Head-to-head projections for any two teams — margin, win probability, and the four-factor edges.' },
      { i:'crystal', t:'Outlook',        b:'Season projections and tournament resume — where each team is trending into March.' },
      { i:'scatter', t:'Visualizations', b:'The Trapezoid of Excellence, Efficiency Landscape, and more — read the season at a glance.' },
      { i:'book-open', t:'Glossary',     b:'Plain-English definitions for every metric. What the numbers mean and why they matter.' },
      { i:'gauge',   t:'Model Health',   b:'How the model is performing this season — calibration, accuracy, and recent hits.' },
    ],
    viz: [
      { art:'trapezoid', kick:'Efficiency', t:'Trapezoid of Excellence', b:'The four factors plotted as a single shape — see exactly where a team wins and loses games.' },
      { art:'landscape', kick:'Big picture', t:'Efficiency Landscape',  b:'Every D-I team on one offense-vs-defense plane. Elite lives in the top-right.' },
      { art:'crystal',   kick:'Forecast',    t:'Crystal Ball',          b:'Win-probability curves for the games that matter most this week.' },
    ],
  },
  nba: {
    label: 'NBA', eyebrow: 'NBA · Updated daily',
    title: 'NBA', teamCount: 30,
    lede: 'The same adjusted-efficiency engine applied to all 30 NBA teams — offense, defense, and net rating that account for who you actually played.',
    secondaryCta: 'Visualizations',
    facts: [{ k:'Teams', v:'30' }, { k:'Conferences', v:'2' }, { k:'Games modeled', v:'1.2', sub:'k' }],
    teams: NBA,
    tools: [
      { i:'trophy',  t:'Rankings',       b:'Net-rating table for all 30 teams with offense and defense splits, sortable by any column.' },
      { i:'scatter', t:'Visualizations', b:'Efficiency Landscape and team-trend charts built on the NBA model.' },
      { i:'gauge',   t:'Model Health',   b:'Calibration and accuracy for the NBA model this season.' },
      { i:'swords',  t:'Player Compare', b:'Side-by-side player comparison across impact metrics.', soon: true },
      { i:'book-open', t:'Glossary',     b:'Definitions for every NBA metric — impact, efficiency, and pace.' },
    ],
    viz: [
      { art:'landscape', kick:'Big picture', t:'Efficiency Landscape', b:'All 30 teams on one offense-vs-defense plane — contenders separate from the pack.' },
      { art:'crystal',   kick:'Forecast',    t:'Crystal Ball',         b:'Win-probability curves for tonight\u2019s slate.' },
      { art:'trapezoid', kick:'Efficiency', t:'Team Trends',           b:'Rolling net-rating over the season — who\u2019s heating up and who\u2019s sliding.' },
    ],
  },
};

Object.assign(window, { LOGO, SVG, NCAA, NBA, NCAA_FULL, NCAA_BASE, GAMELOG, RECENT_FORM, TEAM_COLORS, teamColor, teamLogo, HUB });

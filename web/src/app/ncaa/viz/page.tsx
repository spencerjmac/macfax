import { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Visualizations | macfax',
  description: 'Charts that tell a story beyond the box score — read the NCAA season at a glance.',
};

// ── Thumbnail SVGs (dark ink bg art areas) ───────────────────────────────────

function ThumbTrapezoid() {
  const dot = (cx: number, cy: number, r: number, hl: boolean, k: string) => (
    <circle key={k} cx={cx} cy={cy} r={r} fill={hl ? 'var(--brand)' : '#5b6a86'} opacity={hl ? 1 : 0.5} stroke={hl ? '#fff' : 'none'} strokeWidth={hl ? 1.5 : 0} />
  );
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      {/* wide-side-up: wide top, narrow bottom */}
      <polygon points="40,44 160,44 130,100 70,100" fill="rgba(64,144,128,0.12)" stroke="var(--brand)" strokeWidth="1.3" strokeDasharray="4 4" />
      {[[92,62],[112,58],[100,82],[84,84],[122,74]].map((p, i) => dot(p[0], p[1], 4, false, 't'+i))}
      {dot(100, 52, 6, true, 'th')}
    </svg>
  );
}

function ThumbLandscape() {
  const dot = (cx: number, cy: number, r: number, hl: boolean, k: string) => (
    <circle key={k} cx={cx} cy={cy} r={r} fill={hl ? 'var(--brand)' : '#5b6a86'} opacity={hl ? 1 : 0.5} stroke={hl ? '#fff' : 'none'} strokeWidth={hl ? 1.5 : 0} />
  );
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="24" y1="108" x2="184" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      <line x1="24" y1="20" x2="24" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      {[[60,80],[90,64],[120,50],[150,40],[78,90],[108,72],[138,58],[168,46],[95,86]].map((p, i) => dot(p[0], p[1], 4, false, 'l'+i))}
      {dot(160, 34, 6, true, 'lh')}
    </svg>
  );
}

function ThumbCrystal() {
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <circle cx="100" cy="50" r="31" fill="rgba(64,144,128,0.10)" stroke="var(--brand)" strokeWidth="2" />
      <path d="M86 40a15 15 0 0 1 12 -6" fill="none" stroke="var(--brand)" strokeWidth="1.6" opacity="0.7" />
      <path d="M85 78 C81 86 79 94 79 102 M115 78 C119 86 121 94 121 102" fill="none" stroke="var(--brand)" strokeWidth="2" />
      <path d="M73 102 h54" stroke="var(--brand)" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M150 24 l2.2 6 6 2.2 -6 2.2 -2.2 6 -2.2 -6 -6 -2.2 6 -2.2 z" fill="var(--brand)" opacity="0.8" />
    </svg>
  );
}

function ThumbCinderella() {
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <path d="M34 92 C39 83 52 79 66 77 C77 76 87 79 95 79 C112 73 134 65 153 55 C159 61 158 75 151 84 C148 87 144 89 140 90 C118 95 92 93 72 91 C58 90 45 91 34 92 Z"
        fill="rgba(64,144,128,0.12)" stroke="var(--brand)" strokeWidth="2" strokeLinejoin="round" />
      <path d="M140 90 L150 114 L157 114 L150 88" fill="none" stroke="var(--brand)" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M70 81 C82 79 90 81 96 81" fill="none" stroke="var(--brand)" strokeWidth="1.3" opacity="0.55" />
      <path d="M120 44 l1.8 5 5 1.8 -5 1.8 -1.8 5 -1.8 -5 -5 -1.8 5 -1.8 z" fill="var(--brand)" opacity="0.85" />
    </svg>
  );
}

function ThumbBracket() {
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      {/* simple bracket lines */}
      {[[20,30],[20,50],[20,70],[20,90]].map(([x,y], i) => (
        <rect key={i} x={x} y={y} width={32} height={10} rx="3" fill="none" stroke="#3a4760" strokeWidth="1.2" />
      ))}
      {[[72,40],[72,60],[72,80]].map(([x,y], i) => (
        <rect key={i} x={x} y={y} width={32} height={10} rx="3" fill="none" stroke="#3a4760" strokeWidth="1.2" />
      ))}
      <rect x={122} y={55} width={32} height={10} rx="3" fill="rgba(64,144,128,0.18)" stroke="var(--brand)" strokeWidth="1.3" />
      <line x1="52" y1="35" x2="72" y2="45" stroke="#3a4760" strokeWidth="1" />
      <line x1="52" y1="55" x2="72" y2="45" stroke="#3a4760" strokeWidth="1" />
      <line x1="52" y1="75" x2="72" y2="65" stroke="#3a4760" strokeWidth="1" />
      <line x1="52" y1="95" x2="72" y2="65" stroke="#3a4760" strokeWidth="1" />
      <line x1="104" y1="45" x2="122" y2="60" stroke="#3a4760" strokeWidth="1" />
      <line x1="104" y1="65" x2="122" y2="60" stroke="#3a4760" strokeWidth="1" />
      <path d="M166 46 l2 5.5 5.5 2 -5.5 2 -2 5.5 -2 -5.5 -5.5 -2 5.5 -2 z" fill="var(--brand)" opacity="0.8" />
    </svg>
  );
}

function ThumbKillshot() {
  const dot = (cx: number, cy: number, r: number, hl: boolean, k: string) => (
    <circle key={k} cx={cx} cy={cy} r={r} fill={hl ? 'var(--brand)' : '#5b6a86'} opacity={hl ? 1 : 0.5} stroke={hl ? '#fff' : 'none'} strokeWidth={hl ? 1.5 : 0} />
  );
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="100" y1="18" x2="100" y2="110" stroke="#3a4760" strokeWidth="1" />
      <line x1="30" y1="64" x2="170" y2="64" stroke="#3a4760" strokeWidth="1" />
      {[[70,44],[126,50],[84,86],[140,80],[60,72]].map((p, i) => dot(p[0], p[1], 4, false, 'k'+i))}
      {dot(132, 40, 6, true, 'kh')}
    </svg>
  );
}

function ThumbBuilder() {
  const dot = (cx: number, cy: number, r: number, k: string) => (
    <circle key={k} cx={cx} cy={cy} r={r} fill="#5b6a86" opacity="0.5" />
  );
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="24" y1="108" x2="184" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      <line x1="24" y1="20" x2="24" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      {[[40,96],[60,80],[80,68],[100,58],[120,50],[140,44],[160,38]].map((p, i) => dot(p[0], p[1], 4, 'b'+i))}
      <path d="M40 96 Q100 60 160 38" fill="none" stroke="var(--brand)" strokeWidth="1.5" opacity="0.6" strokeDasharray="4 3" />
    </svg>
  );
}

const THUMB_MAP: Record<string, () => React.ReactElement> = {
  trapezoid: ThumbTrapezoid,
  landscape: ThumbLandscape,
  crystal: ThumbCrystal,
  cinderella: ThumbCinderella,
  bracket: ThumbBracket,
  killshot: ThumbKillshot,
  builder: ThumbBuilder,
};

// ── Feature hero art (larger, with dark scatter) ──────────────────────────────

function FeatureArt() {
  // Pre-computed [cx, cy] for scatter dots.
  // Formula: x = 46 + ((tempo-58)/18)*374, y = 20 + ((36-em)/48)*260
  // Tempo range 60-74, AdjEM range -10 to 34 — spread across full chart.
  const dots: [number, number][] = [
    [108, 53],  // t61 em30
    [149, 64],  // t63 em27
    [191, 80],  // t65 em23
    [233, 53],  // t67 em30
    [253, 96],  // t68 em20
    [274, 117], // t69 em17
    [295, 64],  // t70 em27
    [295, 139], // t70 em13
    [316, 107], // t71 em19
    [316, 171], // t71 em8
    [337, 117], // t72 em17
    [337, 193], // t72 em3
    [358, 150], // t73 em11
    [358, 215], // t73 em-1
    [378, 182], // t74 em5
    [378, 236], // t74 em-4
    [129, 107], // t62 em19
    [129, 193], // t62 em3
    [171, 150], // t64 em11
    [212, 193], // t66 em3
    [212, 236], // t66 em-4
    [274, 215], // t69 em-1
    [87,  193], // t60 em3
    [87,  236], // t60 em-4
  ];

  const trap = '150,31 337,31 306,172 181,172';
  const [hx, hy] = [233, 53]; // highlighted team — inside trap, top area

  // True if a dot falls inside the trapezoid polygon
  const inTrap = (cx: number, cy: number) => {
    if (cy < 31 || cy > 172) return false;
    const t = (cy - 31) / (172 - 31);
    return cx >= 150 + t * 31 && cx <= 337 - t * 31;
  };

  return (
    <svg viewBox="0 0 440 300" className="w-full h-auto" aria-hidden="true">
      {[0.25, 0.5, 0.75].map(f => (
        <line key={'h'+f} x1={46} x2={420} y1={20 + f * 260} y2={20 + f * 260} stroke="#1f2b43" strokeWidth="1" />
      ))}
      {[0.25, 0.5, 0.75].map(f => (
        <line key={'v'+f} y1={20} y2={280} x1={46 + f * 374} x2={46 + f * 374} stroke="#1f2b43" strokeWidth="1" />
      ))}
      <line x1={46} x2={420} y1={280} y2={280} stroke="#3a4760" strokeWidth="1.25" />
      <line x1={46} x2={46}  y1={20}  y2={280} stroke="#3a4760" strokeWidth="1.25" />
      <polygon points={trap} fill="rgba(64,144,128,0.10)" stroke="var(--brand)" strokeWidth="1.3" strokeDasharray="5 5" />
      {/* dots — teal if inside trapezoid, grey otherwise */}
      {dots.map(([cx, cy], i) => (
        inTrap(cx, cy)
          ? <circle key={i} cx={cx} cy={cy} r="5" fill="var(--brand)" opacity="0.85" />
          : <circle key={i} cx={cx} cy={cy} r="4.5" fill="#5b6a86" opacity="0.5" />
      ))}
      {/* single highlighted team — larger glow ring, no label */}
      <circle cx={hx} cy={hy} r="13" fill="var(--brand)" opacity="0.22" />
      <circle cx={hx} cy={hy} r="7" fill="var(--brand)" stroke="#fff" strokeWidth="2" />
      <text x={233} y={296} textAnchor="middle" style={{ font: '500 10px var(--font-sans)', fill: '#8d9bb5', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Adjusted Tempo</text>
      <text x={-150} y={15} textAnchor="middle" transform="rotate(-90)" style={{ font: '500 10px var(--font-sans)', fill: '#8d9bb5', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Adj. Efficiency Margin</text>
    </svg>
  );
}

// ── Article data ──────────────────────────────────────────────────────────────

const ARTICLES = [
  {
    thumb: 'landscape',
    cat: 'Efficiency',
    status: 'live' as const,
    title: 'Efficiency Landscape',
    stand: 'Every D-I team on one offense-vs-defense plane. The closer to the top-right, the more complete the team.',
    date: 'Updated daily',
    href: '/ncaa/viz/landscape',
  },
  {
    thumb: 'crystal',
    cat: 'Forecast',
    status: 'live' as const,
    title: 'Crystal Ball',
    stand: 'Every team scored against 15 historical championship benchmarks. Ranks contenders from pretenders to title favorites.',
    date: 'Updated daily',
    href: '/ncaa/viz/crystal-ball',
  },
  {
    thumb: 'cinderella',
    cat: 'Bracket',
    status: 'live' as const,
    title: 'Cinderella Index',
    stand: 'Which double-digit seeds are built to cause chaos? Five pillars combine into a single upset-potential score.',
    date: 'Updated daily',
    href: '/ncaa/viz/cinderella',
  },
  {
    thumb: 'bracket',
    cat: 'Bracket',
    status: 'live' as const,
    title: 'Bracket Simulator',
    stand: 'Monte Carlo win probabilities for all 68 tournament teams — Sweet 16 through champion.',
    date: 'Updated daily',
    href: '/ncaa/viz/bracket',
  },
  {
    thumb: 'builder',
    cat: 'Custom',
    status: 'live' as const,
    title: 'Viz Builder',
    stand: 'Build custom scatterplots using any two stats. Explore correlations with regression and conference coloring.',
    date: 'Updated daily',
    href: '/ncaa/viz/builder',
  },
  {
    thumb: 'killshot',
    cat: 'Matchup',
    status: 'soon' as const,
    title: 'Kill Shot Analysis',
    stand: 'The single factor most likely to decide a matchup — where one team can land the knockout blow.',
    date: 'Coming soon',
    href: '/ncaa/viz/kill-shot',
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NCAAVizPage() {
  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">College Basketball</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Visualizations
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">Charts that tell a story beyond the box score</p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              7 visualizations · refreshed daily
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 pb-16">
        {/* Feature hero */}
        <Link href="/ncaa/viz/trapezoid" className="block mb-8">
          <article
            className="rounded-[18px] overflow-hidden border border-ink-line text-white grid hover:border-brand transition-colors"
            style={{ gridTemplateColumns: '1fr 1fr', background: 'linear-gradient(180deg, var(--ink-2), var(--ink))' }}
          >
            {/* copy */}
            <div className="p-10 flex flex-col items-start gap-[18px]">
              <span className="font-mono font-semibold text-[11px] tracking-[0.12em] uppercase text-brand2 inline-flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
                Featured · Efficiency
              </span>
              <h2 className="font-display font-bold text-[clamp(30px,3.6vw,46px)] leading-none uppercase tracking-[0.005em] text-white m-0">
                Trapezoid of Excellence
              </h2>
              <p className="text-[16.5px] leading-[1.6] text-ink-fg m-0 max-w-[46ch]">
                Twenty years of champions cluster inside one shape: elite efficiency at a balanced
                tempo. Plot all 365 teams and see — instantly — who has a real title profile.
              </p>
              <div className="flex items-center gap-[10px] font-sans text-[12.5px] text-ink-fg2">
                <span>MacFax Model</span>
                <span className="w-[3px] h-[3px] rounded-full bg-ink-fg2" />
                <span>Updated daily</span>
                <span className="w-[3px] h-[3px] rounded-full bg-ink-fg2" />
                <span>NCAA</span>
              </div>
              <div className="inline-flex items-center gap-2 bg-brand hover:bg-brand-hover border border-brand text-white font-display font-semibold text-sm tracking-[0.04em] uppercase rounded-lg px-5 py-2.5 transition-colors">
                Open chart <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
              </div>
            </div>
            {/* chart art */}
            <div className="border-l border-ink-line flex items-center justify-center p-7 min-h-[320px]">
              <FeatureArt />
            </div>
          </article>
        </Link>

        {/* Article grid */}
        <div className="grid grid-cols-3 gap-[22px]">
          {ARTICLES.map((a) => {
            const Thumb = THUMB_MAP[a.thumb];
            return (
              <Link key={a.title} href={a.href} className="block">
                <article className="border border-ui-border rounded-[16px] overflow-hidden bg-surface flex flex-col hover:border-brand hover:shadow-lg hover:-translate-y-0.5 transition-all duration-150 h-full">
                  {/* art */}
                  <div className="h-[168px] bg-ink border-b border-ink-line flex items-center justify-center p-5 overflow-hidden">
                    <Thumb />
                  </div>
                  {/* body */}
                  <div className="p-[22px] flex flex-col gap-[10px] flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-semibold text-[10.5px] tracking-[0.1em] uppercase text-brand">
                        {a.cat}
                      </span>
                      <span className={`font-mono font-semibold text-[9.5px] tracking-[0.08em] uppercase px-[7px] py-1 rounded ${
                        a.status === 'live'
                          ? 'bg-brand2/16 text-[#2f7a52]'
                          : 'bg-ui-surface text-muted border border-ui-border'
                      }`}>
                        {a.status === 'live' ? 'Live' : 'Soon'}
                      </span>
                    </div>
                    <h3 className="font-display font-bold text-[20px] leading-[1.05] uppercase tracking-[0.01em] m-0">
                      {a.title}
                    </h3>
                    <p className="text-[13.5px] leading-[1.55] text-muted m-0 flex-1">{a.stand}</p>
                    <div className="flex items-center justify-between border-t border-ui-border pt-[14px] mt-[4px]">
                      <span className="font-mono text-[11.5px] text-muted-2">{a.date}</span>
                      <span className="font-display font-semibold text-[12px] tracking-[0.06em] uppercase text-brand inline-flex items-center gap-[6px]">
                        Open <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
                      </span>
                    </div>
                  </div>
                </article>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

import { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Visualizations | NBA | macfax',
  description: 'Charts that tell a story beyond the box score — read the NBA season at a glance.',
};

// ── Thumbnail SVGs (dark ink bg art areas) ───────────────────────────────────

function dot(cx: number, cy: number, r: number, hl: boolean, key: string) {
  return (
    <circle key={key} cx={cx} cy={cy} r={r} fill={hl ? 'var(--brand)' : '#5b6a86'} opacity={hl ? 1 : 0.5} stroke={hl ? '#fff' : 'none'} strokeWidth={hl ? 1.5 : 0} />
  );
}

function ThumbCrystalBall() {
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

function ThumbLuck() {
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="24" y1="108" x2="184" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      <line x1="24" y1="20" x2="24" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      {/* expected-wins diagonal */}
      <line x1="30" y1="100" x2="178" y2="28" stroke="var(--brand)" strokeWidth="1.3" strokeDasharray="5 5" opacity="0.7" />
      {/* lucky teams above the line, unlucky below */}
      {dot(70, 56, 4, true, 'lu0')}
      {dot(100, 50, 4, true, 'lu1')}
      {dot(140, 40, 4, true, 'lu2')}
      {dot(60, 88, 4, false, 'lu3')}
      {dot(95, 92, 4, false, 'lu4')}
      {dot(130, 86, 4, false, 'lu5')}
      {dot(160, 70, 4, false, 'lu6')}
    </svg>
  );
}

function ThumbBPR() {
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="24" y1="108" x2="184" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      <line x1="24" y1="20" x2="24" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      {/* depth cluster */}
      {[[64,86],[80,90],[96,82],[112,94],[128,84],[78,98],[110,80]].map((p, i) => dot(p[0], p[1], 3.5, false, 'bp'+i))}
      {/* star player — large highlighted dot, far upper-right */}
      <circle cx={156} cy={36} r="11" fill="var(--brand)" opacity="0.2" />
      {dot(156, 36, 7, true, 'bpstar')}
    </svg>
  );
}

function ThumbFourFactors() {
  const bars: [number, number, boolean][] = [
    [40, 70, true],
    [76, 50, true],
    [112, 84, false],
    [148, 38, true],
  ];
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="24" y1="108" x2="184" y2="108" stroke="#3a4760" strokeWidth="1.2" />
      {bars.map(([x, h, hl], i) => (
        <rect key={'ff'+i} x={x} y={108 - h} width={24} height={h} rx="3"
          fill={hl ? 'var(--brand)' : '#5b6a86'} opacity={hl ? 0.85 : 0.45} />
      ))}
    </svg>
  );
}

function ThumbMomentum() {
  return (
    <svg viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="24" y1="64" x2="184" y2="64" stroke="#3a4760" strokeWidth="1.2" strokeDasharray="3 3" />
      <path d="M30 80 L60 70 L90 85 L120 50 L150 58 L178 28" fill="none" stroke="var(--brand)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {[[30,80],[60,70],[90,85],[120,50],[150,58],[178,28]].map((p, i) => dot(p[0], p[1], 3.5, i === 5, 'mo'+i))}
    </svg>
  );
}

const THUMB_MAP: Record<string, () => React.ReactElement> = {
  crystal: ThumbCrystalBall,
  luck: ThumbLuck,
  bpr: ThumbBPR,
  fourfactors: ThumbFourFactors,
  momentum: ThumbMomentum,
};

// ── Feature hero art — Efficiency Landscape scatter w/ tier lines ─────────────

function FeatureArt() {
  const dots: [number, number, boolean][] = [
    [108, 53, false], [149, 64, false], [191, 80, false], [233, 53, true],
    [253, 96, false], [274, 117, false], [295, 64, true], [295, 139, false],
    [316, 107, false], [316, 171, false], [337, 117, false], [337, 193, false],
    [358, 150, false], [358, 215, false], [378, 182, false], [378, 236, false],
    [129, 107, false], [129, 193, false], [171, 150, false], [212, 193, false],
    [212, 236, false], [274, 215, false], [87, 193, false], [87, 236, false],
  ];

  return (
    <svg viewBox="0 0 440 300" className="w-full h-auto" aria-hidden="true">
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={'h' + f} x1={46} x2={420} y1={20 + f * 260} y2={20 + f * 260} stroke="#1f2b43" strokeWidth="1" />
      ))}
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={'v' + f} y1={20} y2={280} x1={46 + f * 374} x2={46 + f * 374} stroke="#1f2b43" strokeWidth="1" />
      ))}
      <line x1={46} x2={420} y1={280} y2={280} stroke="#3a4760" strokeWidth="1.25" />
      <line x1={46} x2={46} y1={20} y2={280} stroke="#3a4760" strokeWidth="1.25" />
      {/* tier diagonals — champion (solid), contender (dashed), playoff (grey dashed) */}
      <line x1={120} y1={280} x2={420} y2={40} stroke="var(--brand)" strokeWidth="2" />
      <line x1={60} y1={280} x2={420} y2={100} stroke="#30A2DA" strokeWidth="1.5" strokeDasharray="6 6" opacity="0.8" />
      <line x1={46} y1={230} x2={340} y2={20} stroke="#999" strokeWidth="1.5" strokeDasharray="6 6" opacity="0.7" />
      {dots.map(([cx, cy, hl], i) => (
        hl
          ? <circle key={i} cx={cx} cy={cy} r="5" fill="var(--brand)" opacity="0.9" />
          : <circle key={i} cx={cx} cy={cy} r="4.5" fill="#5b6a86" opacity="0.5" />
      ))}
      <text x={233} y={296} textAnchor="middle" style={{ font: '500 10px var(--font-sans)', fill: '#8d9bb5', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Adj Off</text>
      <text x={-150} y={15} textAnchor="middle" transform="rotate(-90)" style={{ font: '500 10px var(--font-sans)', fill: '#8d9bb5', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Adj Def</text>
    </svg>
  );
}

// ── Article data ──────────────────────────────────────────────────────────────

const ARTICLES = [
  {
    thumb: 'crystal',
    cat: 'Forecast',
    status: 'live' as const,
    href: '/nba/viz/crystal-ball',
    title: 'Crystal Ball',
    stand: 'Every team scored against backtested championship benchmarks drawn from 10 seasons of NBA history.',
    date: 'Updated daily',
  },
  {
    thumb: 'luck',
    cat: 'Efficiency',
    status: 'live' as const,
    href: '/nba/viz/luck-chart',
    title: 'Luck Chart',
    stand: 'Net rating vs. wins above expected — which teams are over- or under-performing their point differential.',
    date: 'Updated daily',
  },
  {
    thumb: 'bpr',
    cat: 'Players',
    status: 'soon' as const,
    title: 'BPR Landscape',
    stand: 'Star power vs. depth — plot every roster by its best player and the strength of the next seven.',
    date: 'Coming soon',
  },
  {
    thumb: 'fourfactors',
    cat: 'Efficiency',
    status: 'soon' as const,
    title: 'Four Factors Profile',
    stand: 'Shooting, turnovers, rebounding, and free throws — see which factors are driving each team’s rating.',
    date: 'Coming soon',
  },
  {
    thumb: 'momentum',
    cat: 'Form',
    status: 'soon' as const,
    title: 'Form & Momentum',
    stand: 'Rolling 10-game net rating trends — who’s heating up and who’s cooling off.',
    date: 'Coming soon',
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NBAVizPage() {
  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">NBA</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Visualizations
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">Charts that tell a story beyond the box score</p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              3 live · 3 coming soon
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 pb-16">
        {/* Feature hero */}
        <Link href="/nba/viz/landscape" className="block mb-8">
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
                Efficiency Landscape
              </h2>
              <p className="text-[16.5px] leading-[1.6] text-ink-fg m-0 max-w-[46ch]">
                All 30 teams plotted by Adj Off vs Adj Def, with three tier lines —
                Champion, Contender, and Playoff — derived from a backtest of 10 seasons
                of NBA history.
              </p>
              <div className="flex items-center gap-[10px] font-sans text-[12.5px] text-ink-fg2">
                <span>MacFax Model</span>
                <span className="w-[3px] h-[3px] rounded-full bg-ink-fg2" />
                <span>Updated daily</span>
                <span className="w-[3px] h-[3px] rounded-full bg-ink-fg2" />
                <span>NBA</span>
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
            const isLive = a.status === 'live';
            const card = (
              <article className={`border border-ui-border rounded-[16px] overflow-hidden bg-surface flex flex-col h-full transition-colors ${isLive ? 'hover:border-brand' : 'opacity-90'}`}>
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
                    {isLive ? (
                      <span className="font-mono font-semibold text-[9.5px] tracking-[0.08em] uppercase px-[7px] py-1 rounded bg-brand2/10 text-brand2 border border-brand2/30 inline-flex items-center gap-[5px]">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
                        Live
                      </span>
                    ) : (
                      <span className="font-mono font-semibold text-[9.5px] tracking-[0.08em] uppercase px-[7px] py-1 rounded bg-ui-surface text-muted border border-ui-border">
                        Soon
                      </span>
                    )}
                  </div>
                  <h3 className="font-display font-bold text-[20px] leading-[1.05] uppercase tracking-[0.01em] m-0">
                    {a.title}
                  </h3>
                  <p className="text-[13.5px] leading-[1.55] text-muted m-0 flex-1">{a.stand}</p>
                  <div className="flex items-center justify-between border-t border-ui-border pt-[14px] mt-[4px]">
                    <span className="font-mono text-[11.5px] text-muted-2">{a.date}</span>
                  </div>
                </div>
              </article>
            );
            return isLive ? (
              <Link key={a.title} href={a.href} className="block">
                {card}
              </Link>
            ) : (
              <div key={a.title}>{card}</div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

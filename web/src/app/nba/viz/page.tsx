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

const THUMB_MAP: Record<string, () => React.ReactElement> = {
  crystal: ThumbCrystalBall,
  luck: ThumbLuck,
};

// ── Feature hero art — Efficiency Landscape scatter w/ tier lines ─────────────

function FeatureArt() {
  // Mirrors the real chart: x = Adj Off (right is better), y = Adj Def with the
  // axis reversed (top is better), so Net = Off - Def grows toward the top-right
  // and each tier line (constant Net) runs parallel, upper-left to lower-right.
  // In these coords a line is x - y = k; plot area is x 46..420, y 20..280.
  // Champion k=230, Contender k=170, Playoff k=90. Highlighted dots are the
  // teams above the Champion line (x - y > 230).
  const dots: [number, number, boolean][] = [
    // champion zone
    [300, 52, true], [330, 60, true], [372, 95, true],
    // contender band
    [250, 62, false], [280, 80, false], [340, 140, false], [380, 170, false],
    // playoff band
    [150, 40, false], [180, 60, false], [220, 95, false], [260, 150, false],
    [300, 170, false], [320, 190, false], [350, 210, false],
    // below the playoff line
    [100, 90, false], [110, 60, false], [120, 110, false], [160, 140, false],
    [200, 170, false], [240, 200, false], [280, 230, false], [90, 150, false],
    [140, 200, false], [190, 230, false],
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
      {/* tier lines — parallel, champion (solid) nearest the top-right corner */}
      <line x1={250} y1={20} x2={420} y2={190} stroke="var(--brand)" strokeWidth="2" />
      <line x1={190} y1={20} x2={420} y2={250} stroke="#30A2DA" strokeWidth="1.5" strokeDasharray="6 6" opacity="0.8" />
      <line x1={110} y1={20} x2={370} y2={280} stroke="#999" strokeWidth="1.5" strokeDasharray="6 6" opacity="0.7" />
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
              3 live
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
        <div className="grid grid-cols-2 gap-[22px]">
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

import Link from 'next/link';
import { ArrowRight, type LucideIcon } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface HubTeam {
  id: string;
  name: string;
  logoUrl: string;
  conf: string;
  meta: string;
  em: number;
  off: number;
  def: number;
  href: string;
}

interface HubFact {
  k: string;
  v: string;
  sub?: string;
}

interface HubTool {
  icon: LucideIcon;
  title: string;
  body: string;
  href: string;
  soon?: boolean;
}

interface HubViz {
  art: 'trapezoid' | 'landscape' | 'crystal';
  kick: string;
  title: string;
  body: string;
  href: string;
}

export interface HubConfig {
  label: string;
  eyebrow: string;
  title: string;
  teamCount: number;
  lede: string;
  rankingsHref: string;
  secondaryCta: string;
  secondaryCtaHref: string;
  facts: HubFact[];
  tools: HubTool[];
  viz: HubViz[];
}

// ── Viz art SVGs (ported from reference) ─────────────────────────────────────

function VizArt({ kind }: { kind: HubViz['art'] }) {
  const common = { width: 150, height: 90, viewBox: '0 0 150 90', fill: 'none', stroke: 'currentColor', strokeWidth: 1.4 };
  if (kind === 'trapezoid') return (
    <svg {...common}>
      <path d="M30 70 L52 22 L98 22 L120 70 Z" opacity="0.5" />
      <circle cx="66" cy="40" r="3.5" fill="currentColor" stroke="none" />
      <circle cx="84" cy="34" r="3.5" fill="currentColor" stroke="none" />
      <circle cx="75" cy="52" r="3.5" fill="currentColor" stroke="none" />
      <circle cx="52" cy="58" r="3" fill="currentColor" stroke="none" opacity="0.6" />
      <circle cx="98" cy="60" r="3" fill="currentColor" stroke="none" opacity="0.6" />
    </svg>
  );
  if (kind === 'landscape') return (
    <svg {...common}>
      <line x1="20" y1="78" x2="130" y2="78" opacity="0.4" />
      <line x1="20" y1="78" x2="20" y2="12" opacity="0.4" />
      <circle cx="50" cy="55" r="4" fill="currentColor" stroke="none" />
      <circle cx="80" cy="38" r="4" fill="currentColor" stroke="none" />
      <circle cx="100" cy="28" r="4" fill="currentColor" stroke="none" />
      <circle cx="65" cy="62" r="3" fill="currentColor" stroke="none" opacity="0.6" />
      <circle cx="110" cy="48" r="3" fill="currentColor" stroke="none" opacity="0.6" />
    </svg>
  );
  return (
    <svg {...common}>
      <circle cx="75" cy="36" r="23" />
      <path d="M64 26a12 12 0 0 1 9-5" opacity="0.75" strokeWidth="1.6" />
      <path d="M60 56c-4 4-6 9-6 15M90 56c4 4 6 9 6 15" />
      <path d="M48 73h54" strokeWidth="1.6" />
      <path d="M118 22l1.6 4 4 1.6-4 1.6-1.6 4-1.6-4-4-1.6 4-1.6z" fill="currentColor" stroke="none" opacity="0.7" />
    </svg>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SportHubPage({
  config,
  teams,
}: {
  config: HubConfig;
  teams: HubTeam[];
}) {
  const leader = teams[0];
  const top5 = teams.slice(0, 5);

  return (
    <div>
      {/* ── Sport hero ─────────────────────────────────────────────────── */}
      <header className="bg-ink text-white border-b-4 border-brand relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(800px 340px at 90% -10%, rgba(64,144,128,0.18), transparent 60%)' }}
        />
        <div className="max-w-[1240px] mx-auto px-8 relative">
          <div
            className="grid items-center gap-12 py-[54px] pb-[58px]"
            style={{ gridTemplateColumns: '1fr 360px' }}
          >
            {/* Copy */}
            <div className="flex flex-col items-start gap-[18px]">
              <p className="kicker-sport text-brand2 flex items-center gap-3">
                <span className="w-1.5 h-1.5 rounded-full bg-brand2 shadow-[0_0_0_4px_rgba(112,192,112,0.18)]" />
                {config.eyebrow}
              </p>
              <h1 className="font-display font-bold text-[clamp(42px,5vw,66px)] leading-[0.98] uppercase tracking-[0.005em] text-white m-0">
                {config.title}
              </h1>
              <p className="text-ink-fg text-[17px] leading-[1.55] max-w-[520px] m-0">
                {config.lede}
              </p>
              <div className="flex gap-3 flex-wrap">
                <Link
                  href={config.rankingsHref}
                  className="inline-flex items-center gap-2 bg-brand hover:bg-brand-hover border border-brand text-white font-display font-semibold text-sm tracking-[0.04em] uppercase rounded-lg px-5 py-2.5 transition-colors"
                >
                  Full rankings <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
                </Link>
                <Link
                  href={config.secondaryCtaHref}
                  className="inline-flex items-center gap-2 bg-transparent hover:border-brand2 border border-[#2f3d59] text-white font-display font-semibold text-sm tracking-[0.04em] uppercase rounded-lg px-5 py-2.5 transition-colors"
                >
                  {config.secondaryCta}
                </Link>
              </div>

              {/* facts */}
              <div className="flex gap-[30px] flex-wrap pt-1">
                {config.facts.map(f => (
                  <div key={f.k}>
                    <span className="block font-sans font-semibold text-[11px] tracking-[0.08em] uppercase text-ink-fg2 mb-[7px]">{f.k}</span>
                    <span className="font-mono font-bold text-[22px] text-white">
                      {f.v}{f.sub && <small className="text-[13px] text-ink-fg2 ml-1">{f.sub}</small>}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Leader spotlight */}
            {leader && (
              <aside className="bg-gradient-to-b from-ink-2 to-ink border border-ink-line rounded-[16px] p-[22px] shadow-[0_30px_60px_-20px_rgba(0,0,0,0.6)]">
                <div className="font-mono font-semibold text-[11px] tracking-[0.1em] uppercase text-brand2 flex items-center gap-[7px] mb-4">
                  <span className="w-[7px] h-[7px] rounded-full bg-brand2" />
                  #1 in the model
                </div>
                <div className="flex items-center gap-[15px] mb-[18px]">
                  {/* white tile behind logo */}
                  {leader.logoUrl ? (
                    <img
                      src={leader.logoUrl}
                      alt={leader.name}
                      className="w-[60px] h-[60px] object-contain bg-white rounded-[12px] p-[7px] shadow-[0_2px_8px_rgba(0,0,0,0.25)] shrink-0"
                    />
                  ) : (
                    <div className="w-[60px] h-[60px] bg-white rounded-[12px] flex items-center justify-center text-xl font-bold text-ink shrink-0">
                      {leader.name.charAt(0)}
                    </div>
                  )}
                  <div>
                    <div className="font-mono font-bold text-[12px] text-brand2 uppercase tracking-[0.08em]">
                      {config.label} · No. 1
                    </div>
                    <div className="font-display font-bold text-[26px] uppercase leading-[1.05] mt-1">
                      {leader.name}
                    </div>
                    <div className="font-sans text-[13px] text-ink-fg2 mt-1">
                      {leader.conf} · {leader.meta}
                    </div>
                  </div>
                </div>
                {/* stats row */}
                <div
                  className="grid rounded-[10px] overflow-hidden border border-ink-line"
                  style={{ gridTemplateColumns: '1fr 1fr 1fr', gap: '1px', background: 'var(--ink-line)' }}
                >
                  {[
                    { k: 'AdjEM', v: (leader.em > 0 ? '+' : '') + leader.em.toFixed(1) },
                    { k: 'AdjO',  v: leader.off.toFixed(1) },
                    { k: 'AdjD',  v: leader.def.toFixed(1) },
                  ].map(s => (
                    <div key={s.k} className="bg-ink px-3 py-[13px] text-center">
                      <span className="block font-sans font-semibold text-[10px] tracking-[0.07em] uppercase text-ink-fg2 mb-[7px]">{s.k}</span>
                      <span className="font-mono font-bold text-[20px] text-white">{s.v}</span>
                    </div>
                  ))}
                </div>
              </aside>
            )}
          </div>
        </div>
      </header>

      {/* ── Top 5 strip ────────────────────────────────────────────────── */}
      <section className="py-[56px]">
        <div className="max-w-[1240px] mx-auto px-8">
          <div className="flex items-end justify-between gap-6 mb-[30px]">
            <div>
              <p className="kicker-sport text-brand mb-2">This week</p>
              <h2 className="head-sport text-text-primary m-0">Top of the {config.label} rankings</h2>
            </div>
            <Link
              href={config.rankingsHref}
              className="text-brand hover:gap-[11px] font-display font-semibold text-[14px] tracking-[0.06em] uppercase inline-flex items-center gap-[7px] whitespace-nowrap transition-all"
            >
              All {config.teamCount} teams <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
            </Link>
          </div>

          <div className="border border-ui-border rounded-[14px] overflow-hidden bg-surface">
            {top5.map((tm, i) => (
              <Link
                key={tm.id}
                href={tm.href}
                className="grid items-center gap-4 w-full px-[22px] py-4 border-t border-ui-border first:border-t-0 hover:bg-ui-surface transition-colors text-left"
                style={{ gridTemplateColumns: '56px 40px 1fr 130px 110px' }}
              >
                <span className="font-display font-bold text-[26px] text-text-primary">{i + 1}</span>
                {tm.logoUrl ? (
                  <img src={tm.logoUrl} alt="" className="w-10 h-10 object-contain" />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-ui-surface flex items-center justify-center text-sm font-bold text-text-muted">
                    {tm.name.charAt(0)}
                  </div>
                )}
                <span>
                  <span className="block font-bold text-[16px]">{tm.name}</span>
                  <span className="block text-[13px] text-muted mt-1">{tm.conf} · {tm.meta}</span>
                </span>
                <span>
                  <span className="block font-sans font-semibold text-[10px] tracking-[0.08em] uppercase text-muted-2 mb-[5px]">AdjO</span>
                  <span className="font-mono font-bold text-[18px]">{tm.off.toFixed(1)}</span>
                </span>
                <span className="text-right">
                  <span className="block font-sans font-semibold text-[10px] tracking-[0.08em] uppercase text-muted-2 mb-[5px]">AdjEM</span>
                  <span className="font-mono font-bold text-[18px] text-brand">
                    {tm.em > 0 ? '+' : ''}{tm.em.toFixed(2)}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tools grid ─────────────────────────────────────────────────── */}
      <section className="py-[56px] border-t border-ui-border bg-[#F7F7F8]">
        <div className="max-w-[1240px] mx-auto px-8">
          <div className="mb-[30px]">
            <p className="kicker-sport text-brand mb-2">Explore</p>
            <h2 className="head-sport text-text-primary m-0">{config.label} tools</h2>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {config.tools.map(t => {
              const Icon = t.icon;
              const inner = (
                <div className="flex gap-4 items-start border border-ui-border rounded-[14px] p-[22px] bg-surface hover:border-brand hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 h-full">
                  <div className="w-11 h-11 rounded-[11px] bg-brand/10 text-brand flex items-center justify-center shrink-0">
                    <Icon className="w-[22px] h-[22px]" strokeWidth={1.5} />
                  </div>
                  <div>
                    <h4 className="font-display font-bold text-[17px] uppercase tracking-[0.01em] m-0 mb-[6px] flex items-center gap-2">
                      {t.title}
                      {t.soon && (
                        <span className="font-mono font-semibold text-[10px] tracking-[0.08em] uppercase px-[9px] py-[5px] rounded-[5px] bg-ui-surface border border-ui-border text-muted">
                          Soon
                        </span>
                      )}
                    </h4>
                    <p className="text-[13px] leading-[1.5] text-muted m-0">{t.body}</p>
                  </div>
                </div>
              );
              return t.soon ? (
                <div key={t.title}>{inner}</div>
              ) : (
                <Link key={t.title} href={t.href} className="block">
                  {inner}
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Viz cards ──────────────────────────────────────────────────── */}
      <section className="py-[56px]">
        <div className="max-w-[1240px] mx-auto px-8">
          <div className="flex items-end justify-between gap-6 mb-[30px]">
            <div>
              <p className="kicker-sport text-brand mb-2">Latest</p>
              <h2 className="head-sport text-text-primary m-0">{config.label} visualizations</h2>
            </div>
            <Link
              href={config.secondaryCtaHref.includes('viz') ? config.secondaryCtaHref : `/${config.label.toLowerCase()}/viz`}
              className="text-brand font-display font-semibold text-[14px] tracking-[0.06em] uppercase inline-flex items-center gap-[7px] whitespace-nowrap"
            >
              All visualizations <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
            </Link>
          </div>
          <div className="grid grid-cols-3 gap-[18px]">
            {config.viz.map(v => (
              <Link
                key={v.title}
                href={v.href}
                className="border border-ui-border rounded-[16px] overflow-hidden bg-surface flex flex-col hover:border-brand hover:shadow-lg hover:-translate-y-0.5 transition-all duration-150"
              >
                {/* art area */}
                <div className="h-[150px] bg-ink border-b border-ink-line flex items-center justify-center text-brand2 overflow-hidden">
                  <VizArt kind={v.art} />
                </div>
                {/* body */}
                <div className="p-5 flex flex-col gap-2 flex-1">
                  <span className="font-sans font-semibold text-[11px] tracking-[0.08em] uppercase text-muted-2">
                    {v.kick}
                  </span>
                  <h4 className="font-display font-bold text-[19px] uppercase tracking-[0.01em] m-0">
                    {v.title}
                  </h4>
                  <p className="text-[13.5px] leading-[1.5] text-muted m-0 flex-1">{v.body}</p>
                  <div className="pt-1 mt-auto">
                    <span className="text-brand font-display font-semibold text-[13px] tracking-[0.06em] uppercase inline-flex items-center gap-[6px]">
                      Open <ArrowRight className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

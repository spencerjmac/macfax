// MacFax — Team Profile tab components + mini charts
// Loaded after React + data.js. Exposes components on window.

const { useState } = React;

/* ---------------- Icons ---------------- */
const TP_PATHS = {
  'arrow-left':  <><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></>,
  'arrow-right': <><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></>,
  'trophy':      <><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></>,
};
const TPIcon = ({ name, size = 16, stroke = 1.6 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">{TP_PATHS[name] || null}</svg>
);

const fmtEM = v => (v > 0 ? '+' : '') + v.toFixed(2);
const pct = v => (v * 100).toFixed(1);
const ord = n => { const s=['th','st','nd','rd'], v=n%100; return n + (s[(v-20)%10]||s[v]||s[0]); };

/* ============================================================
   MINI CHARTS — shared scatter with the focus team highlighted
   ============================================================ */
function Scatter({ team, xKey, yKey, xLabel, yLabel, invertX, invertY, overlay }) {
  const W = 460, H = 280, P = { l: 44, r: 18, t: 16, b: 34 };
  const data = NCAA_FULL;
  const xs = data.map(d => d[xKey]), ys = data.map(d => d[yKey]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const padX = (xMax - xMin) * 0.12, padY = (yMax - yMin) * 0.12;
  const x0 = xMin - padX, x1 = xMax + padX, y0 = yMin - padY, y1 = yMax + padY;
  const sx = v => { const t = (v - x0) / (x1 - x0); return P.l + (invertX ? 1 - t : t) * (W - P.l - P.r); };
  const sy = v => { const t = (v - y0) / (y1 - y0); return P.t + (invertY ? t : 1 - t) * (H - P.t - P.b); };

  return (
    <svg className="mfx-chart__plot" viewBox={`0 0 ${W} ${H}`} role="img">
      {/* grid */}
      {[0.25, 0.5, 0.75].map(f => (
        <line key={'h'+f} x1={P.l} x2={W-P.r} y1={P.t+f*(H-P.t-P.b)} y2={P.t+f*(H-P.t-P.b)} stroke="var(--border)" strokeWidth="1" />
      ))}
      {[0.25, 0.5, 0.75].map(f => (
        <line key={'v'+f} y1={P.t} y2={H-P.b} x1={P.l+f*(W-P.l-P.r)} x2={P.l+f*(W-P.l-P.r)} stroke="var(--border)" strokeWidth="1" />
      ))}
      {/* axes */}
      <line x1={P.l} x2={W-P.r} y1={H-P.b} y2={H-P.b} stroke="var(--muted-2)" strokeWidth="1.25" />
      <line x1={P.l} x2={P.l} y1={P.t} y2={H-P.b} stroke="var(--muted-2)" strokeWidth="1.25" />
      {overlay && overlay(sx, sy)}
      {/* other teams */}
      {data.filter(d => d.id !== team.id).map(d => (
        <circle key={d.id} cx={sx(d[xKey])} cy={sy(d[yKey])} r="4" fill="var(--muted-2)" opacity="0.42" />
      ))}
      {/* focus team */}
      <circle cx={sx(team[xKey])} cy={sy(team[yKey])} r="11" fill="var(--brand)" opacity="0.18" />
      <circle cx={sx(team[xKey])} cy={sy(team[yKey])} r="6" fill="var(--brand)" stroke="#fff" strokeWidth="2" />
      <text x={sx(team[xKey])} y={sy(team[yKey]) - 13} textAnchor="middle"
            style={{ font: '700 12px var(--font-display)', fill: 'var(--brand)' }}>{team.name}</text>
      {/* axis labels */}
      <text className="mfx-chart__axis" x={(P.l + W - P.r) / 2} y={H - 6} textAnchor="middle">{xLabel}</text>
      <text className="mfx-chart__axis" x={-(P.t + H - P.b) / 2} y={13} textAnchor="middle" transform="rotate(-90)">{yLabel}</text>
    </svg>
  );
}

function ChartCard({ title, sub, children }) {
  return (
    <div className="mfx-chart">
      <div className="mfx-chart__h">
        <h4>{title}</h4>
        <span className="open">Open full <TPIcon name="arrow-right" size={12} /></span>
      </div>
      <p className="mfx-chart__sub">{sub}</p>
      {children}
      <p className="mfx-chart__note"><span className="swatch" /> This team highlighted · all 365 D-I teams shown</p>
    </div>
  );
}

/* ============================================================
   TABS
   ============================================================ */
function OverviewTab({ team }) {
  const form = RECENT_FORM;
  const wins = form.filter(w => w === 'W').length;
  return (
    <div className="mfx-ov">
      <div className="mfx-ov__main">
        {/* the story: 3 headline stats */}
        <div className="mfx-keystats">
          <div className="mfx-keystat mfx-keystat--em">
            <span className="k">Adj. Efficiency Margin</span>
            <span className="v">{fmtEM(team.adjEM)} <span className="rk">{ord(team.natRank)}</span></span>
          </div>
          <div className="mfx-keystat mfx-keystat--o">
            <span className="k">Adj. Offense</span>
            <span className="v">{team.adjO.toFixed(1)} <span className="rk">{ord(team.oRk)}</span></span>
          </div>
          <div className="mfx-keystat mfx-keystat--d">
            <span className="k">Adj. Defense</span>
            <span className="v">{team.adjD.toFixed(1)} <span className="rk">{ord(team.dRk)}</span></span>
          </div>
        </div>

        {/* narrative takeaway */}
        <div className="mfx-card">
          <h3 className="mfx-card__h">The story</h3>
          <p className="mfx-takeaway">
            {team.name} ranks <b>{ord(team.natRank)} nationally</b> in adjusted efficiency, powered by
            a <b>top-{Math.max(team.oRk, 5)} offense</b> ({team.adjO.toFixed(1)} pts / 100). The defense sits
            at <b>{ord(team.dRk)}</b>, allowing {team.adjD.toFixed(1)} per 100 — the
            {team.dRk <= team.oRk ? ' steadier' : ' softer'} side of the ledger. At {team.tempo.toFixed(1)} possessions a
            game they play {team.tempo > 68 ? 'up-tempo' : 'a controlled pace'}, and they've won {wins} of their last 5.
          </p>
        </div>

        {/* signature chart */}
        <div className="mfx-chart">
          <div className="mfx-chart__h">
            <h4>Efficiency Landscape</h4>
            <span className="open">All charts <TPIcon name="arrow-right" size={12} /></span>
          </div>
          <p className="mfx-chart__sub">Offense vs. defense — elite teams climb to the top-right.</p>
          <Scatter team={team} xKey="adjD" yKey="adjO" xLabel="Adj. Defense (← better)" yLabel="Adj. Offense" invertX />
          <p className="mfx-chart__note"><span className="swatch" /> This team highlighted</p>
        </div>
      </div>

      {/* side rail */}
      <div className="mfx-ov__side">
        <div className="mfx-card">
          <h3 className="mfx-card__h">Recent form <span className="more">Game log →</span></h3>
          <div className="mfx-form" style={{ marginBottom: 16 }}>
            {form.map((w, i) => <span key={i} className={'mfx-wl ' + (w === 'W' ? 'mfx-wl--w' : 'mfx-wl--l')}>{w}</span>)}
          </div>
          {GAMELOG.slice(0, 5).map((g, i) => (
            <div key={i} className="mfx-formrow">
              <span className="mfx-formrow__opp"><span className="loc">{g.loc}</span> {g.opp}</span>
              <span className="mfx-formrow__sc"><span className={g.wl === 'W' ? 'w' : 'l'}>{g.wl} {g.ts}–{g.os}</span></span>
            </div>
          ))}
        </div>

        <div className="mfx-card">
          <h3 className="mfx-card__h">Four factors edge</h3>
          {[
            { n:'Shooting (eFG%)', o: pct(team.eFG), d: pct(team.eFGd), good: team.eFG > team.eFGd },
            { n:'Turnovers (TOV%)', o: pct(team.tov), d: pct(team.tovd), good: team.tov < team.tovd, low:true },
            { n:'Off. rebound (ORB%)', o: pct(team.orb), d: '—', good: true },
            { n:'Free-throw rate', o: team.ftr.toFixed(3).slice(1), d: '—', good: true },
          ].map(f => (
            <div key={f.n} className="mfx-formrow">
              <span className="mfx-formrow__opp" style={{ color:'var(--muted)', fontWeight:500 }}>{f.n}</span>
              <span className="mfx-formrow__sc" style={{ color:'var(--text)' }}>{f.o}<span style={{color:'var(--muted-2)'}}> / {f.d}</span></span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function OffDefTab({ team }) {
  const Side = ({ title, tag, tagcls, rows }) => (
    <div className="mfx-card">
      <div className="mfx-side-h">{title} <span className={'tag ' + tagcls}>{tag}</span></div>
      <p className="mfx-chart__sub" style={{ marginBottom: 6 }}>Per 100 possessions, adjusted for opponent.</p>
      {rows.map(r => (
        <div key={r.n} className="mfx-metric">
          <div className="mfx-metric__top">
            <span className="mfx-metric__name">{r.n} {r.sub && <small>· {r.sub}</small>}</span>
            <span className="mfx-metric__val">{r.v}{r.rk && <span className="rk">{ord(r.rk)}</span>}</span>
          </div>
          <div className="mfx-bar"><span style={{ width: r.pctw, background: r.color }} /></div>
        </div>
      ))}
    </div>
  );
  return (
    <div className="mfx-offdef">
      <Side title="Offense" tag="ATTACK" tagcls="o" rows={[
        { n:'Offensive Rating', sub:'AdjO', v: team.adjO.toFixed(1), rk: team.oRk, pctw:'82%', color:'#2f7a52' },
        { n:'Effective FG%', v: pct(team.eFG), pctw:'74%', color:'#2f7a52' },
        { n:'Turnover %', sub:'lower is better', v: pct(team.tov), pctw:'68%', color:'#2f7a52' },
        { n:'Offensive rebound %', v: pct(team.orb), pctw:'71%', color:'#2f7a52' },
        { n:'Free-throw rate', v: team.ftr.toFixed(3).slice(1), pctw:'66%', color:'#2f7a52' },
        { n:'Tempo', sub:'poss / 40 min', v: team.tempo.toFixed(1), pctw:'60%', color:'var(--muted)' },
      ]} />
      <Side title="Defense" tag="STOPS" tagcls="d" rows={[
        { n:'Defensive Rating', sub:'AdjD', v: team.adjD.toFixed(1), rk: team.dRk, pctw:'78%', color:'var(--brand-blue)' },
        { n:'Opp. effective FG%', v: pct(team.eFGd), pctw:'70%', color:'var(--brand-blue)' },
        { n:'Forced turnover %', v: pct(team.tovd), pctw:'73%', color:'var(--brand-blue)' },
        { n:'Def. rebound %', v: (100 - team.orb * 100).toFixed(1), pctw:'69%', color:'var(--brand-blue)' },
        { n:'Opp. free-throw rate', v: '.281', pctw:'64%', color:'var(--brand-blue)' },
        { n:'Opp. shot quality', sub:'allowed', v: 'B+', pctw:'67%', color:'var(--muted)' },
      ]} />
    </div>
  );
}

function GameLogTab() {
  return (
    <div className="mfx-tablewrap">
      <table className="mfx-glog">
        <thead>
          <tr>
            <th className="lft">Date</th>
            <th className="lft">Opponent</th>
            <th>Result</th>
            <th className="grp">ORtg</th>
            <th>DRtg</th>
            <th className="grp">eFG%</th>
            <th>TOV%</th>
            <th>ORB%</th>
            <th>FTR</th>
          </tr>
        </thead>
        <tbody>
          {GAMELOG.map((g, i) => (
            <tr key={i}>
              <td className="lft" style={{ color:'var(--muted)' }}>{g.date}</td>
              <td className="lft">
                <span className="mfx-glog__opp">
                  <span className="loc">{g.loc}</span>{g.opp}<span className="rk">{g.oppRk}</span>
                </span>
              </td>
              <td><span className={'mfx-wlpill ' + (g.wl === 'W' ? 'w' : 'l')}>{g.wl} {g.ts}–{g.os}</span></td>
              <td className="grp" style={{ color:'#2f7a52', fontWeight:600 }}>{g.oRtg.toFixed(1)}</td>
              <td style={{ color:'var(--brand-blue)', fontWeight:600 }}>{g.dRtg.toFixed(1)}</td>
              <td className="grp">{pct(g.eFG)}</td>
              <td>{pct(g.tov)}</td>
              <td>{pct(g.orb)}</td>
              <td>{g.ftr.toFixed(3).slice(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartsTab({ team }) {
  // trapezoid overlay (tempo x adjEM y) — wide base at bottom
  const trapOverlay = (sx, sy) => {
    const [tlo, thi] = NCAA_BASE.tempo;
    return (
      <polygon
        points={`${sx(63)},${sy(34)} ${sx(72)},${sy(34)} ${sx(70)},${sy(8)} ${sx(65)},${sy(8)}`}
        fill="rgba(64,144,128,0.10)" stroke="var(--brand)" strokeWidth="1.25" strokeDasharray="4 4" />
    );
  };
  return (
    <div className="mfx-chartgrid">
      <ChartCard title="Efficiency Landscape" sub="Offense vs. defense — top-right is elite.">
        <Scatter team={team} xKey="adjD" yKey="adjO" xLabel="Adj. Defense (← better)" yLabel="Adj. Offense" invertX />
      </ChartCard>
      <ChartCard title="Trapezoid of Excellence" sub="Tempo vs. efficiency — champions live inside the trapezoid.">
        <Scatter team={team} xKey="tempo" yKey="adjEM" xLabel="Adj. Tempo" yLabel="Adj. Efficiency Margin" overlay={trapOverlay} />
      </ChartCard>
      <ChartCard title="Shooting Split" sub="Your eFG% vs. the eFG% you allow.">
        <Scatter team={team} xKey="eFGd" yKey="eFG" xLabel="Opp. eFG% (← better)" yLabel="Team eFG%" invertX />
      </ChartCard>
      <ChartCard title="Pace & Protection" sub="Tempo vs. turnover rate — fast but safe is rare.">
        <Scatter team={team} xKey="tempo" yKey="tov" xLabel="Adj. Tempo" yLabel="Turnover % (↓ better)" invertY />
      </ChartCard>
    </div>
  );
}

Object.assign(window, { OverviewTab, OffDefTab, GameLogTab, ChartsTab, TPIcon, fmtEM, ord });

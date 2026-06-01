// MacFax — NCAA Rankings (sortable + heat-mapped AdjEM)
// Mirrors web/src/components/RankingsTable.tsx

const heatColor = (v, min, max) => {
  if (v == null) return null;
  const t = (v - min) / (max - min); // 0..1
  if (t > 0.85) return { bg: 'rgba(16,185,129,.30)', fg: '#064e3b' };
  if (t > 0.65) return { bg: 'rgba(16,185,129,.20)', fg: '#065f46' };
  if (t > 0.50) return { bg: 'rgba(16,185,129,.10)', fg: '#047857' };
  if (t > 0.35) return { bg: 'rgba(245,158,11,.10)', fg: '#92400e' };
  if (t > 0.20) return { bg: 'rgba(244,63,94,.10)',  fg: '#9f1239' };
  if (t > 0.05) return { bg: 'rgba(244,63,94,.20)',  fg: '#881337' };
  return            { bg: 'rgba(244,63,94,.30)',     fg: '#4c0519' };
};

const Rankings = ({ navigate }) => {
  const [sort, setSort] = React.useState('adjEM');
  const [dir, setDir]   = React.useState('desc');
  const [tab, setTab]   = React.useState('teams');

  const sorted = React.useMemo(() => {
    return [...window.MOCK_TEAMS].sort((a, b) => {
      const av = a[sort], bv = b[sort];
      return (dir === 'desc' ? bv - av : av - bv);
    });
  }, [sort, dir]);

  const adjEMs = sorted.map(t => t.adjEM);
  const minEM = Math.min(...adjEMs), maxEM = Math.max(...adjEMs);

  const handleSort = key => {
    if (sort === key) setDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSort(key); setDir('desc'); }
  };

  const arrow = key => sort === key ? (dir === 'desc' ? ' ↓' : ' ↑') : '';

  return (
    <div className="mf-page">
      <div className="mf-pageheader">
        <h1>NCAA Rankings</h1>
        <p className="mf-lede mf-lede--sm">
          Complete rankings for {window.MOCK_TEAMS.length} NCAA Division I teams &mdash; 2025–26
          <span className="mf-meta">Last updated: November 12, 2025</span>
        </p>
      </div>

      <div className="mf-tabs">
        {[{ id:'teams', label:'Team Rankings', icon:'bar-chart-3' },
          { id:'players', label:'Player Stats', icon:'users' }].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
                  className={MF.cx('mf-tab', tab === t.id && 'is-on')}>
            <MF.Icon name={t.icon} size={16} />{t.label}
          </button>
        ))}
      </div>

      {tab === 'teams' && (
        <div className="mf-table-wrap">
          <table className="mf-table">
            <thead>
              <tr>
                <th style={{width:48}}>Rk</th>
                <th>Team</th>
                <th>Conf</th>
                <th className="num" onClick={() => handleSort('adjEM')}>AdjEM{arrow('adjEM')}</th>
                <th className="num" onClick={() => handleSort('adjO')}>AdjO{arrow('adjO')}</th>
                <th className="num" onClick={() => handleSort('adjD')}>AdjD{arrow('adjD')}</th>
                <th className="num" onClick={() => handleSort('tempo')}>Tempo{arrow('tempo')}</th>
                <th className="num" onClick={() => handleSort('eFG')}>eFG%{arrow('eFG')}</th>
                <th className="num">Record</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((t, i) => {
                const heat = heatColor(t.adjEM, minEM, maxEM);
                return (
                  <tr key={t.id} onClick={() => navigate('team', { teamId: t.id })}>
                    <td className="num mf-rank">{i + 1}</td>
                    <td>
                      <span className="mf-team">
                        <img className="mf-team__logo" src={t.logo} alt="" />
                        <span>{t.name}</span>
                      </span>
                    </td>
                    <td className="muted">{t.conference}</td>
                    <td className="num" style={heat ? { background: heat.bg, color: heat.fg } : null}>
                      {t.adjEM > 0 ? '+' : ''}{t.adjEM.toFixed(2)}
                    </td>
                    <td className="num">{t.adjO.toFixed(1)}</td>
                    <td className="num">{t.adjD.toFixed(1)}</td>
                    <td className="num">{t.tempo.toFixed(1)}</td>
                    <td className="num">{(t.eFG * 100).toFixed(1)}</td>
                    <td className="num">{t.record}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <MF.Card surface="alt" className="mf-legend">
        <h3>Metric Definitions</h3>
        <div className="mf-grid-2">
          <div><strong className="brand">AdjEM:</strong> Adjusted Efficiency Margin (AdjO − AdjD), the predicted point margin vs an average team on a neutral court.</div>
          <div><strong className="positive">AdjO:</strong> Adjusted Offensive Efficiency, points scored per 100 possessions vs an average D1 defense.</div>
          <div><strong style={{color:'var(--brand-blue)'}}>AdjD:</strong> Adjusted Defensive Efficiency, points allowed per 100 possessions vs an average D1 offense.</div>
          <div><strong>Tempo:</strong> Adjusted possessions per 40 minutes.</div>
        </div>
      </MF.Card>
    </div>
  );
};
window.MF.Rankings = Rankings;

// MacFax — Matchup
// Mirrors web/src/components/MatchupTool.tsx

const TeamPicker = ({ label, team, setTeam, accent }) => {
  const [q, setQ] = React.useState('');
  const opts = q ? window.MOCK_TEAMS.filter(t => t.name.toLowerCase().includes(q.toLowerCase())).slice(0,6) : [];
  return (
    <div>
      <label className="mf-label">{label}</label>
      <div className="mf-search">
        <input value={team ? team.name : q}
               onChange={e => { setTeam(null); setQ(e.target.value); }}
               placeholder="Search for a team..." />
        {q && !team && opts.length > 0 && (
          <div className="mf-search__menu">
            {opts.map(t => (
              <button key={t.id} onClick={() => { setTeam(t); setQ(''); }}>
                <img className="mf-team__logo" src={t.logo} alt="" />
                <span>{t.name}</span>
                <span className="num muted" style={{marginLeft:'auto'}}>#{t.rank}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {team && (
        <div className="mf-pickcard" style={{ borderColor: accent, background: accent + '14' }}>
          <div className="mf-pickcard__head">
            <span className="mf-team__logo mf-team__logo--lg">
              <img src={team.logo} alt="" />
            </span>
            <div>
              <div className="h3" style={{margin:0}}>{team.name}</div>
              <div className="muted small">#{team.rank} · {team.conference}</div>
            </div>
          </div>
          <div className="mf-pickcard__stats">
            <div><span className="caption">AdjEM</span><span className="num bold">{team.adjEM.toFixed(1)}</span></div>
            <div><span className="caption">AdjO</span><span className="num bold">{team.adjO.toFixed(1)}</span></div>
            <div><span className="caption">AdjD</span><span className="num bold">{team.adjD.toFixed(1)}</span></div>
          </div>
        </div>
      )}
    </div>
  );
};

const Matchup = () => {
  const [a, setA] = React.useState(window.MOCK_TEAMS[0]);
  const [b, setB] = React.useState(window.MOCK_TEAMS[2]);
  const [loc, setLoc] = React.useState('neutral');

  const ready = a && b;
  const homeAdj = loc === 'a' ? 3 : loc === 'b' ? -3 : 0;
  const projA   = ready ? a.adjO + b.adjD - 100 + (homeAdj/2) : 0;
  const projB   = ready ? b.adjO + a.adjD - 100 - (homeAdj/2) : 0;
  const tempo   = ready ? (a.tempo + b.tempo) / 2 : 0;
  const margin  = ready ? a.adjEM - b.adjEM + homeAdj : 0;
  const eFGedge = ready ? ((a.eFG - a.eFGd) - (b.eFG - b.eFGd)) * 100 : 0;
  const tovEdge = ready ? ((a.tovd - a.tov) - (b.tovd - b.tov)) * 100 : 0;

  return (
    <div className="mf-page">
      <div className="mf-pageheader">
        <h1>Matchup Tool</h1>
        <p className="mf-lede mf-lede--sm">Head-to-head with projected efficiency and four-factor edges.</p>
      </div>

      <div className="mf-grid-2">
        <TeamPicker label="Team A" team={a} setTeam={setA} accent="var(--brand)" />
        <TeamPicker label="Team B" team={b} setTeam={setB} accent="var(--brand-blue)" />
      </div>

      {ready && (
        <>
          <div className="mf-loc">
            <button onClick={() => setLoc('a')}       className={MF.cx('mf-loc__btn', loc==='a' && 'is-on is-a')}>@ {a.name}</button>
            <button onClick={() => setLoc('neutral')} className={MF.cx('mf-loc__btn', loc==='neutral' && 'is-on is-n')}>Neutral</button>
            <button onClick={() => setLoc('b')}       className={MF.cx('mf-loc__btn', loc==='b' && 'is-on is-b')}>@ {b.name}</button>
          </div>

          <MF.Card className="mf-projected">
            <h2>Projected Outcome</h2>
            <div className="mf-projected__row">
              <div>
                <div className="caption">{a.name}</div>
                <div className="stat-lg" style={{color: 'var(--brand)'}}>{projA.toFixed(0)}</div>
              </div>
              <span className="h2 muted">vs</span>
              <div>
                <div className="caption">{b.name}</div>
                <div className="stat-lg" style={{color: 'var(--brand-blue)'}}>{projB.toFixed(0)}</div>
              </div>
            </div>
            <p className="muted small" style={{textAlign:'center', marginTop:16}}>
              Projected at {tempo.toFixed(1)} tempo{loc !== 'neutral' && ' · includes home court advantage'}
            </p>
          </MF.Card>

          <h2 style={{marginTop:32}}>Four-Factor Edges</h2>
          <div className="mf-grid-2">
            <MF.FactorEdge label="eFG% Margin Edge" value={(eFGedge>0?'+':'') + eFGedge.toFixed(1) + '%'} favorsA={eFGedge > 0} teamA={a.name} teamB={b.name} />
            <MF.FactorEdge label="Turnover Edge"     value={(tovEdge>0?'+':'') + tovEdge.toFixed(1) + '%'} favorsA={tovEdge > 0} teamA={a.name} teamB={b.name} />
            <MF.FactorEdge label="Efficiency Margin Diff" value={(margin>0?'+':'') + margin.toFixed(2)} favorsA={margin > 0} teamA={a.name} teamB={b.name} />
            <MF.FactorEdge label="Tempo Δ"           value={(a.tempo - b.tempo).toFixed(1)} favorsA={a.tempo > b.tempo} teamA={a.name + ' faster'} teamB={b.name + ' faster'} />
          </div>
        </>
      )}
    </div>
  );
};
window.MF.Matchup = Matchup;

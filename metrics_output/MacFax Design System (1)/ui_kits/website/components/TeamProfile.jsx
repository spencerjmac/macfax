// MacFax — Team profile
// Mirrors web/src/components/TeamHeader.tsx + TeamPageTabs.tsx (Overview only)

const TeamProfile = ({ teamId, navigate }) => {
  const team = window.MOCK_TEAMS.find(t => t.id === teamId) || window.MOCK_TEAMS[0];
  const [tab, setTab] = React.useState('overview');

  return (
    <div className="mf-page">
      <button className="mf-back" onClick={() => navigate('rankings')}>
        <MF.Icon name="arrow-left" size={16} /> Back to Rankings
      </button>

      <MF.Card className="mf-team-header">
        <div className="mf-team-header__logo">
          <img src={team.logo} alt="" />
        </div>
        <div className="mf-team-header__info">
          <div className="mf-team-header__title">
            <h1>{team.name}</h1>
            <span className="muted h3">{team.conference}</span>
          </div>
          <div className="mf-team-header__meta">
            <span><span className="muted">Record:</span> <span className="num">{team.record}</span></span>
            <span><span className="muted">Rank:</span> <span className="num brand">#{team.rank}</span></span>
            <span><span className="muted">AdjEM:</span> <span className="num brand">{team.adjEM > 0 ? '+' : ''}{team.adjEM.toFixed(2)}</span> <MF.Pill rank={team.rank} /></span>
          </div>
        </div>
      </MF.Card>

      <div className="mf-tabs">
        {['overview', 'four factors', 'off / def', 'resume', 'charts'].map(t => (
          <button key={t} onClick={() => setTab(t)}
                  className={MF.cx('mf-tab', tab === t && 'is-on')}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <>
          <div className="mf-grid-3 mf-grid--gap-lg">
            <MF.StatCard label="Adjusted Efficiency Margin" value={(team.adjEM > 0 ? '+' : '') + team.adjEM.toFixed(2)} rank={team.rank} color="var(--brand)" />
            <MF.StatCard label="Adjusted Offense" value={team.adjO.toFixed(1)} rank={team.adjORank} color="var(--positive)" />
            <MF.StatCard label="Adjusted Defense" value={team.adjD.toFixed(1)} rank={team.adjDRank} color="var(--brand-blue)" />
          </div>

          <h2 style={{marginTop: 32}}>Four Factors</h2>
          <div className="mf-grid-2">
            <MF.Card className="mf-factor">
              <h3>Shooting (eFG%)</h3>
              <p className="muted small">Effective field-goal percentage.</p>
              <div className="mf-factor__row">
                <div><span className="caption">Offense</span><span className="stat positive">{(team.eFG * 100).toFixed(1)}</span></div>
                <div><span className="caption">Defense</span><span className="stat" style={{color:'var(--brand-blue)'}}>{(team.eFGd * 100).toFixed(1)}</span></div>
                <div><span className="caption">Margin</span><span className="stat positive">+{((team.eFG - team.eFGd) * 100).toFixed(1)}</span></div>
              </div>
            </MF.Card>
            <MF.Card className="mf-factor">
              <h3>Turnovers (TOV%)</h3>
              <p className="muted small">Turnovers per 100 plays.</p>
              <div className="mf-factor__row">
                <div><span className="caption">Offense</span><span className="stat positive">{(team.tov * 100).toFixed(1)}</span></div>
                <div><span className="caption">Defense</span><span className="stat" style={{color:'var(--brand-blue)'}}>{(team.tovd * 100).toFixed(1)}</span></div>
                <div><span className="caption">Edge</span><span className="stat positive">+{((team.tovd - team.tov) * 100).toFixed(1)}</span></div>
              </div>
            </MF.Card>
          </div>
        </>
      )}

      {tab !== 'overview' && (
        <MF.Card surface="alt" className="mf-empty">
          <p>This tab&apos;s mock view is not part of the kit. See <strong>web/src/components/TeamPageTabs.tsx</strong> in the codebase for the full implementation.</p>
        </MF.Card>
      )}
    </div>
  );
};
window.MF.TeamProfile = TeamProfile;

// MacFax — Home (landing)
const Home = ({ navigate }) => (
  <div className="mf-page mf-home">
    <section className="mf-hero">
      <h1 className="mf-display-1">College basketball, with the math behind it.</h1>
      <p className="mf-lede">
        Adjusted efficiency, four factors, matchup forecasts, and original visualizations &mdash;
        all in one place, updated daily.
      </p>
      <div className="mf-cta-row">
        <MF.Button onClick={() => navigate('rankings')}>View NCAA Rankings</MF.Button>
        <MF.Button variant="secondary" onClick={() => navigate('matchup')}>Matchup Tool</MF.Button>
      </div>
    </section>

    <section className="mf-section">
      <h2>What MacFax gives you</h2>
      <div className="mf-grid-2">
        {[
          { i: 'bar-chart-3', t: 'Team Rankings', b: "Adjusted efficiency and four factors across all 365 D1 teams. Find who's actually good, not just who has the easy schedule.", r: 'rankings' },
          { i: 'swords',      t: 'Matchup Tool',  b: 'Compare any two teams head-to-head. See projected efficiency margins and where each team wins or loses the four-factor battle.', r: 'matchup' },
          { i: 'scatter',     t: 'Visualizations', b: 'Trapezoid of Excellence, Efficiency Landscape, Crystal Ball, Cinderella Index — original charts that tell a story beyond the box score.' },
          { i: 'book-open',   t: 'Glossary',      b: 'Plain-English definitions for every metric. No jargon walls, just clear explanations of what the numbers mean and why they matter.' },
        ].map(c => (
          <MF.Card key={c.t} hover onClick={c.r ? () => navigate(c.r) : undefined} className="mf-feature">
            <span className="mf-feature__icon"><MF.Icon name={c.i} size={32} /></span>
            <div>
              <h3>{c.t}</h3>
              <p>{c.b}</p>
            </div>
          </MF.Card>
        ))}
      </div>
    </section>

    <section className="mf-section">
      <h2>This week&apos;s top 5</h2>
      <MF.Card className="mf-mini-table">
        {window.MOCK_TEAMS.slice(0, 5).map(t => (
          <button key={t.id} className="mf-mini-row" onClick={() => navigate('team', { teamId: t.id })}>
            <span className="mf-mini-rank">{t.rank}</span>
            <img className="mf-mini-logo" src={t.logo} alt="" />
            <span className="mf-mini-name">{t.name}</span>
            <span className="mf-mini-conf">{t.conference}</span>
            <span className="mf-mini-em">+{t.adjEM.toFixed(2)}</span>
          </button>
        ))}
      </MF.Card>
    </section>
  </div>
);
window.MF.Home = Home;

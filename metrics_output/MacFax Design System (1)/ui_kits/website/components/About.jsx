// MacFax — About
const About = ({ navigate }) => (
  <div className="mf-page mf-about">
    <section className="mf-section">
      <h1 className="mf-display-1">What is MacFax?</h1>
      <p className="mf-lede" style={{maxWidth:640}}>
        MacFax is an independent college basketball analytics platform built to give fans, analysts,
        and bracket sickos a serious edge. We combine adjusted efficiency ratings, four factors
        breakdowns, matchup forecasting, and original visualizations &mdash; all in one place,
        updated daily.
      </p>
    </section>

    <section className="mf-section">
      <h2>What MacFax gives you</h2>
      <div className="mf-grid-2">
        {[
          { i: 'bar-chart-3', t: 'Team Rankings', b: "Adjusted efficiency ratings, four factors, and sorting across all 365 D1 teams. Find who's actually good, not just who has the easy schedule." },
          { i: 'swords',      t: 'Matchup Tool',  b: 'Compare any two teams head-to-head. See projected efficiency margins and where each team wins or loses the four-factor battle.' },
          { i: 'scatter',     t: 'Visualizations', b: 'The Trapezoid of Excellence, Efficiency Landscape, Kill Shot, and Crystal Ball — original charts that tell a story beyond the box score.' },
          { i: 'book-open',   t: 'Glossary',      b: 'Plain-English definitions for every metric. No jargon walls, just clear explanations of what the numbers mean and why they matter.' },
        ].map(c => (
          <MF.Card key={c.t} className="mf-feature">
            <span className="mf-feature__icon"><MF.Icon name={c.i} size={32} /></span>
            <div><h3>{c.t}</h3><p>{c.b}</p></div>
          </MF.Card>
        ))}
      </div>
    </section>

    <section className="mf-section">
      <h2>What makes it different</h2>
      <div className="mf-stack">
        {[
          { i:'flask',      t:'Everything in one place', b:'Adjusted efficiency, four factors, shooting splits, WAB, Barthag, and schedule strength — unified under one roof instead of scattered across five tabs on three different sites.' },
          { i:'trending-up', t:'Original analysis, not just republished numbers', b:"MacFax builds on established efficiency frameworks to produce its own derived metrics, composite ratings, and matchup projections. The goal isn't to mirror other platforms — it's to say something new." },
          { i:'users',      t:'Built for actual fans', b:"Whether you're researching a bracket, scouting a game, or just trying to understand why your team keeps losing winnable games — MacFax is designed to be useful, not academic." },
        ].map(x => (
          <MF.Card key={x.t} surface="alt" className="mf-row-card">
            <span className="mf-feature__icon mf-feature__icon--sm"><MF.Icon name={x.i} size={20} /></span>
            <div><h4>{x.t}</h4><p className="muted small">{x.b}</p></div>
          </MF.Card>
        ))}
      </div>
    </section>

    <section className="mf-section">
      <h2>Built by</h2>
      <div className="mf-builtby">
        <img src="../../assets/founder-portrait.jpg" alt="" />
        <p>
          MacFax is an independent project — not affiliated with any university, media company,
          or analytics service. It was built by someone who got frustrated trying to cross-reference
          five different sites every morning and decided to just build the thing they actually wanted.
        </p>
      </div>
    </section>

    <section className="mf-section">
      <MF.Card className="mf-callout">
        <p><strong>Independent platform.</strong> MacFax is not affiliated with or endorsed by KenPom.com, barttorvik.com, or any other analytics site. Adjusted efficiency metrics draw on methodologies pioneered by Ken Pomeroy and Dean Oliver — we acknowledge their foundational work.</p>
      </MF.Card>
    </section>

    <div className="mf-cta-row">
      <MF.Button onClick={() => navigate('rankings')}>View Rankings</MF.Button>
      <MF.Button variant="secondary" onClick={() => navigate('matchup')}>Matchup Tool</MF.Button>
    </div>
  </div>
);
window.MF.About = About;

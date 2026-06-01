// MacFax — Navigation
// Mirrors web/src/components/Navigation.tsx + SportSwitcher.tsx

const Navigation = ({ route, sport, navigate }) => {
  const NCAA_NAV = [
    { id: 'rankings', label: 'Rankings' },
    { id: 'matchup',  label: 'Matchup' },
    { id: 'outlook',  label: 'Outlook' },
    { id: 'viz',      label: 'Visualizations' },
    { id: 'glossary', label: 'Glossary' },
    { id: 'accuracy', label: 'Accuracy' },
  ];
  const NBA_NAV = [
    { id: 'nba-rankings', label: 'Rankings' },
    { id: 'nba-viz',      label: 'Visualizations' },
    { id: 'nba-health',   label: 'Model Health' },
  ];
  const items = sport === 'nba' ? NBA_NAV : NCAA_NAV;

  return (
    <nav className="mf-nav">
      <div className="mf-nav__inner">
        <button className="mf-nav__brand" onClick={() => navigate('home')}>
          <img src="../../assets/macfax-logo.png" alt="" />
          <span>macfax</span>
        </button>

        <div className="mf-nav__right">
          <div className="mf-sport">
            <button onClick={() => navigate('rankings', { sport: 'ncaa' })}
                    className={MF.cx('mf-sport__btn', sport === 'ncaa' && 'is-on')}>NCAA</button>
            <button onClick={() => navigate('nba-rankings', { sport: 'nba' })}
                    className={MF.cx('mf-sport__btn', sport === 'nba' && 'is-on')}>NBA</button>
          </div>

          <span className="mf-nav__divider" />

          {items.map(item => (
            <button key={item.id}
                    onClick={() => navigate(item.id)}
                    className={MF.cx('mf-nav__link', route === item.id && 'is-on')}>
              {item.label}
            </button>
          ))}

          <span className="mf-nav__divider" />
          <button onClick={() => navigate('methodology')}
                  className={MF.cx('mf-nav__link', route === 'methodology' && 'is-on')}>Methodology</button>
          <button onClick={() => navigate('about')}
                  className={MF.cx('mf-nav__link', route === 'about' && 'is-on')}>About</button>
        </div>
      </div>
    </nav>
  );
};

const Footer = () => (
  <footer className="mf-footer">
    <div className="mf-footer__inner">
      <span className="mf-footer__brand">macfax</span>
      <div className="mf-footer__links">
        <a>Model Accuracy</a><a>Methodology</a><a>Glossary</a><a>About</a>
      </div>
    </div>
  </footer>
);

window.MF.Navigation = Navigation;
window.MF.Footer = Footer;

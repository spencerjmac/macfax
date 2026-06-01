// MacFax — Primitives
// Button, Card, Pill, Eyebrow, StatCard, FactorEdge, Icon
// Mirrors: web/src/components/StatCards.tsx + button/card patterns

const cx = (...xs) => xs.filter(Boolean).join(' ');

// --- Lucide-style stroke icons (1.5 stroke-width to match codebase) ---
const Icon = ({ name, size = 20, className = '', stroke = 1.5 }) => {
  const paths = {
    'bar-chart-3': <><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-5"/></>,
    'swords':      <><path d="M14.5 17.5L3 6V3h3l11.5 11.5"/><path d="M13 19l6-6"/><path d="M16 16l4 4"/><path d="M19 21l2-2"/><path d="M14.5 6.5L18 3h3v3l-3.5 3.5"/><path d="M5 14l9 9"/></>,
    'scatter':     <><circle cx="7" cy="17" r="1.5"/><circle cx="11" cy="11" r="1.5"/><circle cx="17" cy="7" r="1.5"/><circle cx="15" cy="14" r="1.5"/><path d="M3 3v18h18"/></>,
    'book-open':   <><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></>,
    'flask':       <><path d="M9 3h6"/><path d="M10 3v8L4 21h16L14 11V3"/></>,
    'trending-up': <><path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/></>,
    'users':       <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></>,
    'arrow-left':  <><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></>,
    'arrow-right': <><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></>,
    'search':      <><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></>,
    'sliders':     <><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="2" y1="14" x2="6" y2="14"/><line x1="10" y1="8" x2="14" y2="8"/><line x1="18" y1="16" x2="22" y2="16"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" className={className}>
      {paths[name] || null}
    </svg>
  );
};

const Button = ({ variant = 'primary', size = 'md', className = '', children, ...rest }) => {
  const variants = {
    primary:   'bg-brand text-white hover:bg-brand-hover border-brand',
    secondary: 'bg-surface-2 text-text border-border hover:border-brand',
    ghost:     'bg-transparent text-text border-transparent hover:bg-surface-2',
  };
  const sizes = { sm: 'px-3.5 py-2 text-sm', md: 'px-5 py-3 text-sm', lg: 'px-6 py-3.5 text-base' };
  return (
    <button className={cx('mf-btn', variants[variant], sizes[size], className)} {...rest}>
      {children}
    </button>
  );
};

const Card = ({ children, className = '', surface = 'card', hover = false, onClick }) => {
  const bg = surface === 'alt' ? 'bg-surface-2' : 'bg-surface';
  return (
    <div onClick={onClick}
         className={cx('mf-card', bg, hover && 'mf-card--hover', onClick && 'cursor-pointer', className)}>
      {children}
    </div>
  );
};

const Eyebrow = ({ children, className = '' }) => (
  <div className={cx('mf-eyebrow', className)}>{children}</div>
);

const Pill = ({ rank, className = '' }) => {
  if (rank == null) return <span className={cx('mf-pill mf-pill--na', className)}>N/A</span>;
  let tone = 'mf-pill--default';
  if (rank <= 10) tone = 'mf-pill--elite';
  else if (rank <= 25) tone = 'mf-pill--good';
  else if (rank <= 50) tone = 'mf-pill--ok';
  return <span className={cx('mf-pill', tone, className)}>#{rank}</span>;
};

const StatusTag = ({ tone = 'live', children }) => (
  <span className={cx('mf-tag', `mf-tag--${tone}`)}>{children}</span>
);

const StatCard = ({ label, value, rank, color, description }) => (
  <Card className="mf-statcard">
    <div className="mf-statcard__row">
      <span className="mf-statcard__label">{label}</span>
      {rank !== undefined && <Pill rank={rank} />}
    </div>
    <div className="mf-statcard__value" style={color ? { color } : null}>{value}</div>
    {description && <p className="mf-statcard__desc">{description}</p>}
  </Card>
);

const FactorEdge = ({ label, value, favorsA, teamA, teamB }) => (
  <Card className="mf-edge">
    <div className="mf-edge__label">{label}</div>
    <div className="mf-edge__value" style={{ color: favorsA ? 'var(--brand)' : 'var(--brand-blue)' }}>{value}</div>
    <div className="mf-edge__hint">Edge: {favorsA ? teamA : teamB}</div>
  </Card>
);

window.MF = window.MF || {};
Object.assign(window.MF, { cx, Icon, Button, Card, Eyebrow, Pill, StatusTag, StatCard, FactorEdge });

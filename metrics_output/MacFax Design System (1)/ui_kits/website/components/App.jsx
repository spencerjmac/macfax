// MacFax — App router
// Local team logos in /assets/teams (filename = team id)
const LOGO = (id) => `../../assets/teams/${id}.png`;

window.MOCK_TEAMS = [
  { id:'duke',      name:'Duke',           conference:'ACC',       color:'#003594', logo:LOGO('duke'),  rank:1, record:'24-3', adjEM:34.21, adjO:120.4, adjD:86.2, adjORank:2,  adjDRank:6,  tempo:68.4, eFG:0.567, eFGd:0.461, tov:0.142, tovd:0.198 },
  { id:'kansas',    name:'Kansas',         conference:'Big 12',    color:'#0051ba', logo:LOGO('kansas'), rank:2, record:'22-4', adjEM:29.84, adjO:118.7, adjD:88.9, adjORank:5,  adjDRank:11, tempo:66.7, eFG:0.554, eFGd:0.469, tov:0.151, tovd:0.183 },
  { id:'uconn',     name:'UConn',          conference:'Big East',  color:'#0e1c36', logo:LOGO('uconn'),   rank:3, record:'23-4', adjEM:27.66, adjO:117.2, adjD:89.5, adjORank:8,  adjDRank:14, tempo:69.1, eFG:0.548, eFGd:0.474, tov:0.163, tovd:0.190 },
  { id:'houston',   name:'Houston',        conference:'Big 12',    color:'#c8102e', logo:LOGO('houston'),  rank:4, record:'25-2', adjEM:25.41, adjO:114.1, adjD:88.7, adjORank:18, adjDRank:9,  tempo:63.5, eFG:0.532, eFGd:0.461, tov:0.158, tovd:0.205 },
  { id:'tennessee', name:'Tennessee',      conference:'SEC',       color:'#ff8200', logo:LOGO('tennessee'), rank:5, record:'21-5', adjEM:23.18, adjO:113.6, adjD:90.4, adjORank:22, adjDRank:18, tempo:65.2, eFG:0.529, eFGd:0.477, tov:0.166, tovd:0.196 },
  { id:'ucla',      name:'UCLA',           conference:'Big Ten',   color:'#2d68c4', logo:LOGO('ucla'),   rank:6, record:'20-6', adjEM:21.82, adjO:115.1, adjD:93.3, adjORank:14, adjDRank:31, tempo:66.0, eFG:0.541, eFGd:0.489, tov:0.157, tovd:0.182 },
  { id:'gonzaga',   name:'Gonzaga',        conference:'WCC',       color:'#041e42', logo:LOGO('gonzaga'), rank:7, record:'22-5', adjEM:20.94, adjO:118.3, adjD:97.4, adjORank:6,  adjDRank:54, tempo:70.2, eFG:0.564, eFGd:0.496, tov:0.149, tovd:0.176 },
  { id:'iowa-st',   name:'Iowa State',     conference:'Big 12',    color:'#c8102e', logo:LOGO('iowa-st'),   rank:8, record:'21-6', adjEM:19.67, adjO:111.4, adjD:91.7, adjORank:38, adjDRank:21, tempo:64.3, eFG:0.521, eFGd:0.481, tov:0.164, tovd:0.211 },
  { id:'auburn',    name:'Auburn',         conference:'SEC',       color:'#0c2340', logo:LOGO('auburn'),    rank:9, record:'22-5', adjEM:18.42, adjO:112.0, adjD:93.6, adjORank:31, adjDRank:33, tempo:68.7, eFG:0.524, eFGd:0.486, tov:0.171, tovd:0.197 },
  { id:'baylor',    name:'Baylor',         conference:'Big 12',    color:'#003015', logo:LOGO('baylor'),  rank:10,record:'19-7', adjEM:17.13, adjO:113.2, adjD:96.1, adjORank:24, adjDRank:46, tempo:67.4, eFG:0.534, eFGd:0.493, tov:0.156, tovd:0.184 },
  { id:'illinois',  name:'Illinois',       conference:'Big Ten',   color:'#13294b', logo:LOGO('illinois'),  rank:11,record:'20-7', adjEM:15.88, adjO:114.7, adjD:98.8, adjORank:16, adjDRank:62, tempo:69.9, eFG:0.541, eFGd:0.501, tov:0.150, tovd:0.179 },
  { id:'arizona',   name:'Arizona',        conference:'Big 12',    color:'#003366', logo:LOGO('arizona'),   rank:12,record:'19-8', adjEM:14.62, adjO:113.8, adjD:99.2, adjORank:20, adjDRank:67, tempo:70.5, eFG:0.539, eFGd:0.500, tov:0.155, tovd:0.181 },
  { id:'unc',       name:'North Carolina', conference:'ACC',       color:'#7bafd4', logo:LOGO('unc'),  rank:13,record:'19-7', adjEM:13.41, adjO:115.6, adjD:102.2,adjORank:11, adjDRank:96, tempo:69.0, eFG:0.546, eFGd:0.514, tov:0.142, tovd:0.171 },
  { id:'kentucky',  name:'Kentucky',       conference:'SEC',       color:'#0033a0', logo:LOGO('kentucky'),   rank:14,record:'20-7', adjEM:12.18, adjO:117.4, adjD:105.2,adjORank:9,  adjDRank:131,tempo:71.8, eFG:0.557, eFGd:0.519, tov:0.139, tovd:0.165 },
  { id:'marquette', name:'Marquette',      conference:'Big East',  color:'#003366', logo:LOGO('marquette'),  rank:15,record:'20-7', adjEM:11.04, adjO:111.1, adjD:100.1,adjORank:42, adjDRank:78, tempo:65.8, eFG:0.518, eFGd:0.498, tov:0.169, tovd:0.183 },
];

const App = () => {
  const [route, setRoute] = React.useState('home');
  const [params, setParams] = React.useState({});
  const [sport, setSport] = React.useState('ncaa');

  const navigate = (r, p = {}) => {
    if (p.sport) setSport(p.sport);
    setRoute(r);
    setParams(p);
    window.scrollTo(0, 0);
  };

  return (
    <div className="mf-app">
      <MF.Navigation route={route} sport={sport} navigate={navigate} />
      <main>
        {route === 'home'        && <MF.Home navigate={navigate} />}
        {route === 'rankings'    && <MF.Rankings navigate={navigate} />}
        {route === 'team'        && <MF.TeamProfile teamId={params.teamId} navigate={navigate} />}
        {route === 'matchup'     && <MF.Matchup />}
        {route === 'about'       && <MF.About navigate={navigate} />}
        {!['home','rankings','team','matchup','about'].includes(route) && (
          <div className="mf-page">
            <MF.Card surface="alt" className="mf-empty">
              <h2>{route}</h2>
              <p className="muted">This route is not part of the kit. The full implementation lives in <code>web/src/app/</code> in the <code>spencerjmac/macfax</code> codebase.</p>
              <MF.Button variant="secondary" onClick={() => navigate('home')}>Back home</MF.Button>
            </MF.Card>
          </div>
        )}
      </main>
      <MF.Footer />
    </div>
  );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

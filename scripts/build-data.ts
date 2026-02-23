/**
 * Data Pipeline: Transform raw CSV data into unified TeamSeason JSON
 * 
 * This script:
 * 1. Reads KenPom, Torvik, and CBB Analytics CSV files
 * 2. Normalizes team names using team-name-map.json
 * 3. Merges data sources by team
 * 4. Resolves logo paths
 * 5. Calculates derived metrics (margins, edges)
 * 6. Outputs unified teams.json for the web app
 */

import * as fs from 'fs';
import * as path from 'path';
import { parse } from 'csv-parse/sync';

// Types
interface TeamSeason {
  // Identity
  teamId: string;
  teamName: string;
  teamNameAlt: string[];
  conference: string;
  logoUrl: string;
  
  // Season Context
  season: string;
  lastUpdated: string;
  games: number;
  record: string;
  
  // Core Ratings
  rank: number;
  adjEM: number;
  adjO: number;
  adjD: number;
  adjTempo: number;
  
  // Four Factors - Offense
  eFG: number;
  tov: number;
  orb: number;
  ftr: number;
  
  // Four Factors - Defense
  eFG_d: number;
  tov_d: number;
  drb: number;
  ftr_d: number;
  
  // Four Factors - Margins (derived)
  eFG_margin: number;
  tov_edge: number;
  reb_edge: number;
  ftr_margin: number;
  
  // Four Factor Index
  four_factor_index_100: number | null;
  
  // Raw Four Factors (unadjusted) - from CBB Analytics
  raw_eFG: number | null;
  raw_tov: number | null;
  raw_orb: number | null;
  raw_ftr: number | null;
  raw_eFG_d: number | null;
  raw_tov_d: number | null;
  raw_drb: number | null;
  raw_ftr_d: number | null;
  raw_eFG_margin: number | null;
  raw_tov_edge: number | null;
  raw_reb_edge: number | null;
  raw_ftr_margin: number | null;
  
  // Shooting Splits
  fg2_pct: number | null;
  fg2_pct_d: number | null;
  fg3_pct: number | null;
  fg3_pct_d: number | null;
  fg3_rate: number | null;
  fg3_rate_d: number | null;
  
  // Resume Metrics
  wab: number | null;
  sor: number | null;
  luck: number | null;
  sos_adjEM: number | null;
  ncsos_adjEM: number | null;
  barthag: number | null;
  
  // Source metadata
  sources: {
    kenpom: boolean;
    torvik: boolean;
    cbbAnalytics: boolean;
  };
}

interface TeamNameMapping {
  slug: string;
  display: string;
  aliases: string[];
}

// Helper: Load CSV
function loadCSV(filePath: string): any[] {
  const content = fs.readFileSync(filePath, 'utf-8');
  return parse(content, { columns: true, skip_empty_lines: true });
}

// Helper: Normalize team name to slug
function normalizeTeamName(name: string, mapping: Record<string, TeamNameMapping>): string {
  // Direct match
  if (mapping[name]) return mapping[name].slug;
  
  // Try aliases
  for (const [key, value] of Object.entries(mapping)) {
    if (value.aliases.some(alias => alias.toLowerCase() === name.toLowerCase())) {
      return value.slug;
    }
  }
  
  // Fallback: slugify
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

// Helper: Get logo path
function getLogoPath(teamSlug: string): string {
  const logoDir = path.join(__dirname, '..', 'web', 'public', 'logos');
  
  // Manual overrides for teams where slug doesn't match logo filename
  const manualMappings: Record<string, string> = {
    // UConn specifically
    'connecticut': 'uconn_huskies.png',
    
    // UNC and other Carolina schools - MOST IMPORTANT: main schools come first
    'north-carolina': 'north_carolina_tar_heels.png',
    'unc': 'north_carolina_tar_heels.png',
    'north-carolina-at': 'north_carolina_at_aggies.png',
    'nc-at': 'north_carolina_at_aggies.png',
    'south-carolina': 'south_carolina_gamecocks.png',
    'east-carolina': 'east_carolina_pirates.png',
    'western-carolina': 'western_carolina_catamounts.png',
    'coastal-carolina': 'coastal_carolina_chanticleers.png',
    
    // Albany variants
    'albany': 'ualbany_great_danes.png',
    'ualbany': 'ualbany_great_danes.png',
    
    // State schools with abbreviated slugs
    'michigan-st': 'michigan_state_spartans.png',
    'michigan-state': 'michigan_state_spartans.png',
    'illinois-st': 'illinois_state_redbirds.png',
    'illinois-state': 'illinois_state_redbirds.png',
    'iowa-st': 'iowa_state_cyclones.png',
    'iowa-state': 'iowa_state_cyclones.png',
    'kansas-st': 'kansas_state_wildcats.png',
    'kansas-state': 'kansas_state_wildcats.png',
    'ohio-st': 'ohio_state_buckeyes.png',
    'ohio-state': 'ohio_state_buckeyes.png',
    'oklahoma-st': 'oklahoma_state_cowboys.png',
    'oklahoma-state': 'oklahoma_state_cowboys.png',
    'oregon-st': 'oregon_state_beavers.png',
    'oregon-state': 'oregon_state_beavers.png',
    'penn-st': 'penn_state_nittany_lions.png',
    'penn-state': 'penn_state_nittany_lions.png',
    'mississippi-st': 'mississippi_state_bulldogs.png',
    'mississippi-state': 'mississippi_state_bulldogs.png',
    'utah-st': 'utah_state_aggies.png',
    'utah-state': 'utah_state_aggies.png',
    'washington-st': 'washington_state_cougars.png',
    'washington-state': 'washington_state_cougars.png',
    'arizona-st': 'arizona_state_sun_devils.png',
    'arizona-state': 'arizona_state_sun_devils.png',
    'colorado-st': 'colorado_state_rams.png',
    'colorado-state': 'colorado_state_rams.png',
    'fresno-st': 'fresno_state_bulldogs.png',
    'fresno-state': 'fresno_state_bulldogs.png',
    'san-diego-st': 'san_diego_state_aztecs.png',
    'san-diego-state': 'san_diego_state_aztecs.png',
    'san-jose-st': 'san_josé_state_spartans.png',
    'san-jose-state': 'san_josé_state_spartans.png',
    'boise-st': 'boise_state_broncos.png',
    'boise-state': 'boise_state_broncos.png',
    'ball-st': 'ball_state_cardinals.png',
    'ball-state': 'ball_state_cardinals.png',
    'florida-st': 'florida_state_seminoles.png',
    'florida-state': 'florida_state_seminoles.png',
    'wichita-st': 'wichita_state_shockers.png',
    'wichita-state': 'wichita_state_shockers.png',
    'mcneese-st': 'mcneese_cowboys.png',
    'mcneese-state': 'mcneese_cowboys.png',
    'montana-st': 'montana_state_bobcats.png',
    'montana-state': 'montana_state_bobcats.png',
    'south-dakota-st': 'south_dakota_state_jackrabbits.png',
    'south-dakota-state': 'south_dakota_state_jackrabbits.png',
    'north-dakota-st': 'north_dakota_state_bison.png',
    'north-dakota-state': 'north_dakota_state_bison.png',
    'jackson-st': 'jackson_state_tigers.png',
    'jackson-state': 'jackson_state_tigers.png',
    'jacksonville-st': 'jacksonville_state_gamecocks.png',
    'jacksonville-state': 'jacksonville_state_gamecocks.png',
    'sam-houston-st': 'sam_houston_bearkats.png',
    'sam-houston-state': 'sam_houston_bearkats.png',
    'stephen-f-austin': 'stephen_f_austin_lumberjacks.png',
    'tennessee-st': 'tennessee_state_tigers.png',
    'tennessee-state': 'tennessee_state_tigers.png',
    'murray-st': 'murray_state_racers.png',
    'murray-state': 'murray_state_racers.png',
    'east-tennessee-st': 'east_tennessee_state_buccaneers.png',
    'east-tennessee-state': 'east_tennessee_state_buccaneers.png',
    'appalachian-st': 'app_state_mountaineers.png',
    'appalachian-state': 'app_state_mountaineers.png',
    'morehead-st': 'morehead_state_eagles.png',
    'morehead-state': 'morehead_state_eagles.png',
    'arkansas-st': 'arkansas_state_red_wolves.png',
    'arkansas-state': 'arkansas_state_red_wolves.png',
    'georgia-st': 'georgia_state_panthers.png',
    'georgia-state': 'georgia_state_panthers.png',
    'kent-st': 'kent_state_golden_flashes.png',
    'kent-state': 'kent_state_golden_flashes.png',
    'norfolk-st': 'norfolk_state_spartans.png',
    'norfolk-state': 'norfolk_state_spartans.png',
    'portland-st': 'portland_state_vikings.png',
    'portland-state': 'portland_state_vikings.png',
    'sacramento-st': 'sacramento_state_hornets.png',
    'sacramento-state': 'sacramento_state_hornets.png',
    'weber-st': 'weber_state_wildcats.png',
    'weber-state': 'weber_state_wildcats.png',
    'northern-colorado': 'northern_colorado_bears.png',
    'northern-arizona': 'northern_arizona_lumberjacks.png',
    'indiana-st': 'indiana_state_sycamores.png',
    'indiana-state': 'indiana_state_sycamores.png',
    'texas-st': 'texas_state_bobcats.png',
    'texas-state': 'texas_state_bobcats.png',
    
    // Special abbreviations
    'fiu': 'florida_international_panthers.png',
    'florida-international': 'florida_international_panthers.png',
    'uic': 'uic_flames.png',
    'illinois-chicago': 'uic_flames.png',
    'umass': 'massachusetts_minutemen.png',
    'umbc': 'umbc_retrievers.png',
    'unc-greensboro': 'unc_greensboro_spartans.png',
    'unc-wilmington': 'unc_wilmington_seahawks.png',
    'unc-asheville': 'unc_asheville_bulldogs.png',
    'lsu': 'lsu_tigers.png',
    'smu': 'smu_mustangs.png',
    'tcu': 'tcu_horned_frogs.png',
    'uab': 'uab_blazers.png',
    'ucf': 'ucf_knights.png',
    'ucla': 'ucla_bruins.png',
    'unlv': 'unlv_rebels.png',
    'usc': 'usc_trojans.png',
    'utep': 'utep_miners.png',
    'utsa': 'utsa_roadrunners.png',
    'vcu': 'vcu_rams.png',
    'vmi': 'vmi_keydets.png',
    
    // NC State specifically
    'n-c-state': 'nc_state_wolfpack.png',
    'nc-state': 'nc_state_wolfpack.png',
    
    // St. schools (both st- and saint- variants)
    'st-johns': 'st_johns_red_storm.png',
    'st-john-s': 'st_johns_red_storm.png',
    'saint-johns': 'st_johns_red_storm.png',
    'saint-john-s': 'st_johns_red_storm.png',
    'st-josephs': 'saint_josephs_hawks.png',
    'st-joseph-s': 'saint_josephs_hawks.png',
    'saint-josephs': 'saint_josephs_hawks.png',
    'saint-joseph-s': 'saint_josephs_hawks.png',
    'st-louis': 'saint_louis_billikens.png',
    'saint-louis': 'saint_louis_billikens.png',
    'st-marys': 'saint_marys_gaels.png',
    'st-mary-s': 'saint_marys_gaels.png',
    'saint-marys': 'saint_marys_gaels.png',
    'saint-mary-s': 'saint_marys_gaels.png',
    'st-peters': 'saint_peters_peacocks.png',
    'st-peter-s': 'saint_peters_peacocks.png',
    'saint-peters': 'saint_peters_peacocks.png',
    'saint-peter-s': 'saint_peters_peacocks.png',
    'st-bonaventure': 'st_bonaventure_bonnies.png',
    'saint-bonaventure': 'st_bonaventure_bonnies.png',
    'st-francis': 'saint_francis_red_flash.png',
    'saint-francis': 'saint_francis_red_flash.png',
    'st-thomas-minnesota': 'st_thomas-minnesota_tommies.png',
    
    // Other common mismatches
    'illinois': 'illinois_fighting_illini.png',
    'iowa': 'iowa_hawkeyes.png',
    'miami-fl': 'miami_hurricanes.png',
    'miami-oh': 'miami_oh_redhawks.png',
    'long-island': 'long_island_university_sharks.png',
    'liu': 'long_island_university_sharks.png',

    // Small/Mid-Major State Schools
    'st-thomas': 'st_thomas-minnesota_tommies.png',
    'cal-baptist': 'california_baptist_lancers.png',
    'cal-st-northridge': 'cal_state_northridge_matadors.png',
    'csun': 'cal_state_northridge_matadors.png',
    'wright-st': 'wright_state_raiders.png',
    'new-mexico-st': 'new_mexico_state_aggies.png',
    'cal-st-fullerton': 'cal_state_fullerton_titans.png',
    'kennesaw-st': 'kennesaw_state_owls.png',
    'cal-st-bakersfield': 'cal_state_bakersfield_roadrunners.png',
    'youngstown-st': 'youngstown_state_penguins.png',
    'tarleton-st': 'tarleton_state_texans.png',
    'missouri-st': 'missouri_state_bears.png',
    'nicholls-st': 'nicholls_colonels.png',
    'long-beach-st': 'long_beach_state_beach.png',
    'idaho-st': 'idaho_state_bengals.png',
    'southeast-missouri-st': 'southeast_missouri_state_redhawks.png',
    'grambling-st': 'grambling_tigers.png',
    'northwestern-st': 'northwestern_state_demons.png',
    'alabama-st': 'alabama_state_hornets.png',
    'cleveland-st': 'cleveland_state_vikings.png',
    'alcorn-st': 'alcorn_state_braves.png',
    'chicago-st': 'chicago_state_cougars.png',
    'morgan-st': 'morgan_state_bears.png',
    'south-carolina-st': 'south_carolina_state_bulldogs.png',
    'delaware-st': 'delaware_state_hornets.png',
    'coppin-st': 'coppin_state_eagles.png',

    // A&M and Special Schools
    'texas-a-m-corpus-chris': 'texas_am-corpus_christi_islanders.png',
    'bethune-cookman': 'bethune-cookman_wildcats.png',
    'north-carolina-a-t': 'north_carolina_at_aggies.png',
    'east-texas-a-m': 'east_texas_am_lions.png',
    'arkansas-pine-bluff': 'arkansas-pine_bluff_golden_lions.png',
    'alabama-a-m': 'alabama_am_bulldogs.png',
    'prairie-view-a-m': 'prairie_view_am_panthers.png',
    'florida-a-m': 'florida_am_rattlers.png',

    // Other Schools with Abbreviations/Special Names
    'tennessee-martin': 'ut_martin_skyhawks.png',
    'siue': 'siu_edwardsville_cougars.png',
    'nebraska-omaha': 'omaha_mavericks.png',
    'southeastern-louisiana': 'se_louisiana_lions.png',
    'mount-st-mary-s': 'mount_st_marys_mountaineers.png',
    'usc-upstate': 'south_carolina_upstate_spartans.png',
    'iu-indy': 'iu_indianapolis_jaguars.png',
    'loyola-md': 'loyola_maryland_greyhounds.png',
    'the-citadel': 'citadel_bulldogs.png',
    'louisiana-monroe': 'ul_monroe_warhawks.png',
    'umkc': 'kansas_city_roos.png',
    'gardner-webb': 'gardner-webb_runnin_bulldogs.png',
    'mississippi-valley-st': 'mississippi_valley_state_delta_devils.png',
  };
  
  if (manualMappings[teamSlug]) {
    return `/logos/${manualMappings[teamSlug]}`;
  }
  
  // Try exact match
  const exactPath = `${teamSlug}.png`;
  if (fs.existsSync(path.join(logoDir, exactPath))) {
    return `/logos/${exactPath}`;
  }
  
  // Try matching files that start with the team slug followed by underscore
  const files = fs.readdirSync(logoDir);
  const slugPattern = teamSlug.replace(/-/g, '_'); // Convert dashes to underscores
  
  // Find matches that start with slug + underscore (e.g., "michigan_" for slug "michigan")
  let matches = files.filter(f => 
    f.toLowerCase().startsWith(slugPattern.toLowerCase() + '_') && f.endsWith('.png')
  );
  
  // If we have matches, prefer ones that don't contain extra school names
  // (e.g., prefer "north_carolina_tar_heels" over "north_carolina_at_aggies")
  if (matches.length > 1) {
    // Filter out matches that have compound suffixes indicating a different school
    const compoundSuffixes = [
      'state', 'tech', 'am', 'at',  // State/Tech/A&M/A&T schools
      'southern', 'northern', 'eastern', 'western',  // Directional schools
      'central', 'upstate',  // More directional variants
    ];
    
    const cleanMatches = matches.filter(f => {
      const afterSlug = f.slice(slugPattern.length + 1).toLowerCase();
      return !compoundSuffixes.some(suffix => afterSlug.startsWith(suffix + '_'));
    });
    
    if (cleanMatches.length > 0) {
      matches = cleanMatches;
    }
  }
  
  // If we have matches, prefer the shortest one (most specific)
  if (matches.length > 0) {
    matches.sort((a, b) => a.length - b.length);
    return `/logos/${matches[0]}`;
  }
  
  return '/logos/default.svg';
}

// Helper: Parse percentage string to decimal
function parsePercentage(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return value;
  const str = String(value).replace('%', '');
  const num = parseFloat(str);
  return isNaN(num) ? null : (str.includes('%') ? num / 100 : num);
}

// Helper: Parse number
function parseNum(value: any): number | null {
  if (value === null || value === undefined || value === '') return null;
  const num = typeof value === 'number' ? value : parseFloat(String(value));
  return isNaN(num) ? null : num;
}

// Main pipeline
function buildData() {
  console.log('🏀 CBB Analytics Data Pipeline');
  console.log('================================\n');
  
  // Load team name mapping
  const teamNameMap: Record<string, TeamNameMapping> = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'team-name-map.json'), 'utf-8')
  );
  
  // Load CSVs
  console.log('📂 Loading source data...');
  const kenpomPath = path.join(__dirname, '..', 'KenPom Data', 'kenpom_tableau.csv');
  const torvikPath = path.join(__dirname, '..', 'Bart Torvik', 'torvik_tableau.csv');
  const cbbAnalyticsPath = path.join(__dirname, '..', 'CBB Analytics', 'cbb_analytics_tableau_cleaned.csv');
  
  const kenpomData = loadCSV(kenpomPath);
  const torvikData = loadCSV(torvikPath);
  const cbbAnalyticsData = loadCSV(cbbAnalyticsPath);
  
  console.log(`  ✓ KenPom: ${kenpomData.length} teams`);
  console.log(`  ✓ Torvik: ${torvikData.length} teams`);
  console.log(`  ✓ CBB Analytics: ${cbbAnalyticsData.length} teams\n`);
  
  // Build unified dataset
  console.log('🔗 Merging data sources...');
  const teamsMap = new Map<string, TeamSeason>();
  
  // Process Torvik first (has most complete Four Factors data)
  for (const row of torvikData) {
    const teamName = row.team_name;
    const teamSlug = normalizeTeamName(teamName, teamNameMap);
    
    const team: TeamSeason = {
      // Identity
      teamId: teamSlug,
      teamName: teamNameMap[teamName]?.display || teamName,
      teamNameAlt: teamNameMap[teamName]?.aliases || [teamName],
      conference: row.conference || '',
      logoUrl: getLogoPath(teamSlug),
      
      // Season Context
      season: '2025-26',
      lastUpdated: row.date || new Date().toISOString().split('T')[0],
      games: parseNum(row.games) || 0,
      record: row.record || '',
      
      // Core Ratings (Torvik names: adj_oe, adj_de, barthag, adj_tempo)
      rank: parseNum(row.rank) || 999,
      adjEM: parseNum(row.adj_oe) && parseNum(row.adj_de) 
        ? parseNum(row.adj_oe)! - parseNum(row.adj_de)! 
        : 0,
      adjO: parseNum(row.adj_oe) || 0,
      adjD: parseNum(row.adj_de) || 0,
      adjTempo: parseNum(row.adj_tempo) || 0,
      
      // Four Factors - Offense
      eFG: parsePercentage(row.efg_pct) || 0,
      tov: parsePercentage(row.tor) || 0,
      orb: parsePercentage(row.orb) || 0,
      ftr: parsePercentage(row.ftr) || 0,
      
      // Four Factors - Defense
      eFG_d: parsePercentage(row.efg_pct_d) || 0,
      tov_d: parsePercentage(row.tord) || 0,
      drb: parsePercentage(row.drb) || 0,
      ftr_d: parsePercentage(row.ftrd) || 0,
      
      // Margins (calculate)
      eFG_margin: 0, // calculated below
      tov_edge: 0,
      reb_edge: 0,
      ftr_margin: 0,
      
      // Four Factor Index
      four_factor_index_100: null, // calculated after all teams loaded
      
      // Raw Four Factors (from CBB Analytics)
      raw_eFG: null,
      raw_tov: null,
      raw_orb: null,
      raw_ftr: null,
      raw_eFG_d: null,
      raw_tov_d: null,
      raw_drb: null,
      raw_ftr_d: null,
      raw_eFG_margin: null,
      raw_tov_edge: null,
      raw_reb_edge: null,
      raw_ftr_margin: null,
      
      // Shooting Splits
      fg2_pct: parsePercentage(row.two_p_pct),
      fg2_pct_d: parsePercentage(row.two_p_pct_d),
      fg3_pct: parsePercentage(row.three_p_pct),
      fg3_pct_d: parsePercentage(row.three_p_pct_d),
      fg3_rate: parsePercentage(row.three_pr),
      fg3_rate_d: parsePercentage(row.three_prd),
      
      // Resume Metrics
      wab: parseNum(row.wab),
      sor: null,
      luck: null,
      sos_adjEM: null,
      ncsos_adjEM: null,
      barthag: parseNum(row.barthag),
      
      // Sources
      sources: {
        kenpom: false,
        torvik: true,
        cbbAnalytics: false,
      },
    };
    
    // Calculate margins
    team.eFG_margin = team.eFG - team.eFG_d;
    team.tov_edge = team.tov_d - team.tov;
    team.reb_edge = team.orb - team.drb;
    team.ftr_margin = team.ftr - team.ftr_d;
    
    teamsMap.set(teamSlug, team);
  }
  
  // Merge KenPom data
  for (const row of kenpomData) {
    const teamName = row.team_name;
    const teamSlug = normalizeTeamName(teamName, teamNameMap);
    
    const existing = teamsMap.get(teamSlug);
    if (existing) {
      // Update with KenPom data
      existing.rank = parseNum(row.rank) || existing.rank;
      existing.adjEM = parseNum(row.adj_em) || existing.adjEM;
      existing.adjO = parseNum(row.adj_o) || existing.adjO;
      existing.adjD = parseNum(row.adj_d) || existing.adjD;
      existing.adjTempo = parseNum(row.adj_tempo) || existing.adjTempo;
      existing.luck = parseNum(row.luck);
      existing.sos_adjEM = parseNum(row.sos_adj_em);
      existing.ncsos_adjEM = parseNum(row.ncsos_adj_em);
      existing.sources.kenpom = true;
    } else {
      // Create new entry from KenPom
      const team: TeamSeason = {
        teamId: teamSlug,
        teamName: teamNameMap[teamName]?.display || teamName,
        teamNameAlt: teamNameMap[teamName]?.aliases || [teamName],
        conference: row.conference || '',
        logoUrl: getLogoPath(teamSlug),
        season: '2025-26',
        lastUpdated: row.date || new Date().toISOString().split('T')[0],
        games: 0,
        record: '',
        rank: parseNum(row.rank) || 999,
        adjEM: parseNum(row.adj_em) || 0,
        adjO: parseNum(row.adj_o) || 0,
        adjD: parseNum(row.adj_d) || 0,
        adjTempo: parseNum(row.adj_tempo) || 0,
        eFG: 0, tov: 0, orb: 0, ftr: 0,
        eFG_d: 0, tov_d: 0, drb: 0, ftr_d: 0,
        eFG_margin: 0, tov_edge: 0, reb_edge: 0, ftr_margin: 0,
        four_factor_index_100: null,
        raw_eFG: null, raw_tov: null, raw_orb: null, raw_ftr: null,
        raw_eFG_d: null, raw_tov_d: null, raw_drb: null, raw_ftr_d: null,
        raw_eFG_margin: null, raw_tov_edge: null, raw_reb_edge: null, raw_ftr_margin: null,
        fg2_pct: null, fg2_pct_d: null,
        fg3_pct: null, fg3_pct_d: null,
        fg3_rate: null, fg3_rate_d: null,
        wab: null, sor: null,
        luck: parseNum(row.luck),
        sos_adjEM: parseNum(row.sos_adj_em),
        ncsos_adjEM: parseNum(row.ncsos_adj_em),
        barthag: null,
        sources: { kenpom: true, torvik: false, cbbAnalytics: false },
      };
      teamsMap.set(teamSlug, team);
    }
  }
  
  // Merge CBB Analytics data (supplemental)
  for (const row of cbbAnalyticsData) {
    const teamName = row['Team Name'];
    if (!teamName) continue;
    
    const teamSlug = normalizeTeamName(teamName, teamNameMap);
    const existing = teamsMap.get(teamSlug);
    
    if (existing) {
      existing.sources.cbbAnalytics = true;
      // CBB Analytics has adjusted metrics but we prefer Torvik/KenPom
      // Only use if missing
      if (!existing.adjO && row.OrtgAdj) {
        existing.adjO = parseNum(row.OrtgAdj) || existing.adjO;
      }
      if (!existing.adjD && row.DRtgAdj) {
        existing.adjD = parseNum(row.DRtgAdj) || existing.adjD;
      }
      
      // Extract raw (unadjusted) four factors
      // CBB Analytics has: eFG%, ORB%, TOV%, FTA Rate (offensive)
      // And defensive stats: DRB%, STL%, BLK% (we can derive defensive four factors)
      existing.raw_eFG = parsePercentage(row['eFG%']);
      existing.raw_tov = parsePercentage(row['TOV%']);
      existing.raw_orb = parsePercentage(row['ORB%']);
      existing.raw_ftr = parsePercentage(row['FTA Rate']);
      
      // For defense, we need opponent stats - CBB Analytics has DRB%
      existing.raw_drb = parsePercentage(row['DRB%']);
      // Opponent eFG%, TOV%, FTR need to be derived from game-level stats
      // For now, leave as null - we can add these if needed
      existing.raw_eFG_d = null;
      existing.raw_tov_d = null;
      existing.raw_ftr_d = null;
      
      // Calculate raw margins where possible
      if (existing.raw_eFG != null && existing.raw_eFG_d != null) {
        existing.raw_eFG_margin = existing.raw_eFG - existing.raw_eFG_d;
      }
      if (existing.raw_tov != null && existing.raw_tov_d != null) {
        existing.raw_tov_edge = existing.raw_tov_d - existing.raw_tov;
      }
      if (existing.raw_orb != null && existing.raw_drb != null) {
        existing.raw_reb_edge = existing.raw_orb - existing.raw_drb;
      }
      if (existing.raw_ftr != null && existing.raw_ftr_d != null) {
        existing.raw_ftr_margin = existing.raw_ftr - existing.raw_ftr_d;
      }
    }
  }
  
  console.log(`  ✓ Merged ${teamsMap.size} unique teams\n`);
  
  // Convert to array and sort by rank
  const teams = Array.from(teamsMap.values()).sort((a, b) => a.rank - b.rank);
  
  // Calculate Four Factor Index using z-scores
  console.log('🧮 Calculating Four Factor Index (z-score weighted)...');
  
  // Collect all margins/edges
  const efgMargins = teams.map(t => t.eFG_margin);
  const tovEdges = teams.map(t => t.tov_edge);
  const rebEdges = teams.map(t => t.reb_edge);
  const ftrMargins = teams.map(t => t.ftr_margin);
  
  // Calculate means and standard deviations
  const computeStats = (values: number[]) => {
    const n = values.length;
    const mean = values.reduce((sum, v) => sum + v, 0) / n;
    const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / n;
    const stdDev = Math.sqrt(variance);
    return { mean, stdDev };
  };
  
  const efgStats = computeStats(efgMargins);
  const tovStats = computeStats(tovEdges);
  const rebStats = computeStats(rebEdges);
  const ftrStats = computeStats(ftrMargins);
  
  // Calculate z-score
  const zScore = (value: number, mean: number, stdDev: number) => {
    return stdDev === 0 ? 0 : (value - mean) / stdDev;
  };
  
  // Calculate FFI for each team
  for (const team of teams) {
    const z_efg = zScore(team.eFG_margin, efgStats.mean, efgStats.stdDev);
    const z_tov = zScore(team.tov_edge, tovStats.mean, tovStats.stdDev);
    const z_reb = zScore(team.reb_edge, rebStats.mean, rebStats.stdDev);
    const z_ftr = zScore(team.ftr_margin, ftrStats.mean, ftrStats.stdDev);
    
    // Weighted z-score: eFG 40.69%, TOV 40.69%, REB 14.32%, FTR 4.28%
    const ffi_z = (
      0.4069 * z_efg +
      0.4069 * z_tov +
      0.1432 * z_reb +
      0.0428 * z_ftr
    );
    
    // Scale to 0-100: FFI_100 = clamp(50 + 20 * ffi_z, 0, 100)
    team.four_factor_index_100 = Math.max(0, Math.min(100, 50 + 20 * ffi_z));
  }
  
  console.log(`  ✓ Four Factor Index calculated for ${teams.length} teams\n`);
  
  // Generate metadata
  const metadata = {
    lastUpdated: new Date().toISOString(),
    season: '2025-26',
    teamCount: teams.length,
    sources: {
      kenpom: teams.filter(t => t.sources.kenpom).length,
      torvik: teams.filter(t => t.sources.torvik).length,
      cbbAnalytics: teams.filter(t => t.sources.cbbAnalytics).length,
    },
  };
  
  // Write output
  const outputDir = path.join(__dirname, '..', 'web', 'public', 'data');
  fs.mkdirSync(outputDir, { recursive: true });
  
  const outputPath = path.join(outputDir, 'teams.json');
  fs.writeFileSync(
    outputPath,
    JSON.stringify({ metadata, teams }, null, 2)
  );
  
  console.log('✅ Data pipeline complete!');
  console.log(`   Output: ${outputPath}`);
  console.log(`   Teams: ${teams.length}`);
  console.log(`   Size: ${(fs.statSync(outputPath).size / 1024).toFixed(1)} KB\n`);
  
  // Print sample
  console.log('📊 Sample (Top 5):');
  teams.slice(0, 5).forEach((t, i) => {
    console.log(`   ${i + 1}. ${t.teamName} (${t.conference}) - AdjEM: ${t.adjEM.toFixed(2)}`);
  });
}

// Run pipeline
try {
  buildData();
} catch (error) {
  console.error('❌ Pipeline failed:', error);
  process.exit(1);
}

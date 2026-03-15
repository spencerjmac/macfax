import { NextRequest, NextResponse } from 'next/server';

interface EspnTeam {
  displayName: string;
  shortDisplayName: string;
  location: string;
  color: string;         // 6-digit hex, no '#'
  alternateColor: string;
}

let cache: EspnTeam[] | null = null;
let cacheExpiry = 0;
const TTL_MS = 24 * 60 * 60 * 1000;

async function getTeams(): Promise<EspnTeam[]> {
  if (cache && Date.now() < cacheExpiry) return cache;

  const res = await fetch(
    'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams?limit=700',
    { next: { revalidate: 86400 } }
  );
  if (!res.ok) throw new Error(`ESPN API ${res.status}`);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await res.json() as any;
  const items: unknown[] = data?.sports?.[0]?.leagues?.[0]?.teams ?? [];

  const teams: EspnTeam[] = [];
  for (const item of items) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const t = (item as any)?.team;
    if (t?.color) {
      teams.push({
        displayName: t.displayName ?? '',
        shortDisplayName: t.shortDisplayName ?? '',
        location: t.location ?? '',
        color: t.color,
        alternateColor: t.alternateColor ?? t.color,
      });
    }
  }

  cache = teams;
  cacheExpiry = Date.now() + TTL_MS;
  return teams;
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
}

function findTeam(teams: EspnTeam[], name: string, slug: string): EspnTeam | null {
  const nName = normalize(name);
  const nSlug = normalize(slug.replace(/-/g, ' '));

  // 1. Exact location match  (e.g. name="Duke" matches location="Duke")
  let m = teams.find(t => normalize(t.location) === nName);
  if (m) return m;

  // 2. Exact shortDisplayName match
  m = teams.find(t => normalize(t.shortDisplayName) === nName);
  if (m) return m;

  // 3. Exact displayName match
  m = teams.find(t => normalize(t.displayName) === nName);
  if (m) return m;

  // 4. Match by slug (e.g. "duke" in "duke blue devils")
  m = teams.find(t => normalize(t.displayName).startsWith(nSlug));
  if (m) return m;

  // 5. Our name is contained in ESPN's displayName
  m = teams.find(t => normalize(t.displayName).includes(nName));
  if (m) return m;

  // 6. ESPN's location is contained in our name (handles e.g. long official names)
  m = teams.find(t => nName.includes(normalize(t.location)) && normalize(t.location).length > 3);
  if (m) return m;

  return null;
}

export async function GET(request: NextRequest) {
  const name = request.nextUrl.searchParams.get('name') ?? '';
  const slug = request.nextUrl.searchParams.get('slug') ?? '';

  if (!name && !slug) {
    return NextResponse.json({ error: 'name or slug required' }, { status: 400 });
  }

  try {
    const teams = await getTeams();
    const team = findTeam(teams, name || slug.replace(/-/g, ' '), slug);

    if (!team) {
      return NextResponse.json({ error: 'not found' }, { status: 404 });
    }

    return NextResponse.json({
      name: team.displayName,
      primary: `#${team.color}`,
      secondary: `#${team.alternateColor}`,
    });
  } catch (err) {
    console.error('[team-colors]', err);
    return NextResponse.json({ error: 'internal error' }, { status: 500 });
  }
}

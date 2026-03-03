import type {
  Team,
  MatchupResult,
  Conference,
  TrapezoidData,
  EfficiencyLandscapeData,
  VizStats,
  VizScatterData,
} from '@/types';

type QueryParams = Record<string, string | number | boolean | undefined | null>;

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const API_ROOT = `${API_BASE_URL}/api`;

function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(`${API_ROOT}${path.startsWith('/') ? '' : '/'}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      url.searchParams.set(key, String(value));
    });
  }
  return url.toString();
}

/**
 * Turn API error response body into a short, readable message.
 * Avoids dumping Django debug HTML or long stack traces into the UI.
 */
function parseErrorMessage(status: number, body: string): string {
  const statusLabel = status >= 500 ? 'Server error' : 'Request failed';
  // Prefer JSON error payload
  const trimmed = body.trim();
  if (trimmed.startsWith('{')) {
    try {
      const json = JSON.parse(body) as { error?: string; detail?: string; message?: string };
      const msg = json.error ?? json.detail ?? json.message;
      if (typeof msg === 'string' && msg.length > 0 && msg.length < 500) return msg;
    } catch {
      // not JSON, fall through
    }
  }
  // If response looks like HTML (e.g. Django debug page), show generic message
  if (
    trimmed.startsWith('<!') ||
    trimmed.toLowerCase().includes('</html>') ||
    trimmed.toLowerCase().includes('<html')
  ) {
    return status >= 500
      ? `${statusLabel} (${status}). Check the server logs or try again later.`
      : `${statusLabel} (${status}).`;
  }
  // Short plain text is fine to show
  if (body.length <= 200) return body;
  return `${statusLabel} (${status}).`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-store' });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseErrorMessage(res.status, text) || `Request failed (${res.status})`);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error('Invalid JSON in response');
  }
}

function unwrapResults<T>(data: any): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && Array.isArray(data.results)) return data.results as T[];
  return [] as T[];
}

export const api = {
  async getTeams(): Promise<Team[]> {
    const data = await fetchJson<any>(buildUrl('/teams/'));
    return unwrapResults<Team>(data);
  },

  async getMatchup(teamA: string, teamB: string, site: 'neutral' | 'home' | 'away'): Promise<MatchupResult> {
    return fetchJson<MatchupResult>(
      buildUrl('/matchup/', { teamA, teamB, site })
    );
  },

  async getConferences(): Promise<Conference[]> {
    const data = await fetchJson<any>(buildUrl('/conferences/'));
    return unwrapResults<Conference>(data);
  },

  async getTrapezoid(params: { conference?: string; top?: number }): Promise<TrapezoidData> {
    return fetchJson<TrapezoidData>(
      buildUrl('/viz/trapezoid', { conference: params.conference, top: params.top })
    );
  },

  async getLandscape(params: { conference?: string; top?: number }): Promise<EfficiencyLandscapeData> {
    return fetchJson<EfficiencyLandscapeData>(
      buildUrl('/viz/landscape', { conference: params.conference, top: params.top })
    );
  },

  async getVizStats(): Promise<VizStats> {
    return fetchJson<VizStats>(buildUrl('/viz/stats'));
  },

  async getVizScatter(params: { x: string; y: string; colorBy?: string }): Promise<VizScatterData> {
    return fetchJson<VizScatterData>(
      buildUrl('/viz/scatter', { x: params.x, y: params.y, colorBy: params.colorBy })
    );
  },
};

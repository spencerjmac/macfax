import type { WorldCupTeam } from '@/types/worldcup';

const API_BASE_URL = (
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'http://127.0.0.1:8000'
).replace(/\/$/, '');

const WORLDCUP_API_ROOT = `${API_BASE_URL}/api/world-cup`;

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`World Cup API request failed (${res.status}): ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const worldCupApi = {
  async getRankings(): Promise<WorldCupTeam[]> {
    const data = await fetchJson<{ teams: WorldCupTeam[] }>(`${WORLDCUP_API_ROOT}/rankings/`);
    return data.teams;
  },
};

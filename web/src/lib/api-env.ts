/**
 * Next.js web configuration for the createApi factory (lib/api-client.ts).
 *
 * Server-side: prefer the internal Docker URL (never exposed to browsers).
 * Client-side: only NEXT_PUBLIC_* is inlined into the bundle, so this
 * resolves to the public URL baked in at build time.
 */

/** Local-dev fallbacks. The two spellings predate this module; kept so URLs don't change. */
export const LOCAL_API_ORIGIN = 'http://127.0.0.1:8000';
export const LOCALHOST_API_ORIGIN = 'http://localhost:8000';

export const WEB_FETCH_OPTIONS: RequestInit = { cache: 'no-store' };

export function webApiOrigin(fallback: string): string {
  return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || fallback;
}

export function stripTrailingSlash(url: string): string {
  return url.replace(/\/$/, '');
}

/** During Next.js production build (e.g. Docker) no backend is running; avoid fetch. */
export function isBuildPhase(): boolean {
  return process.env.NEXT_PHASE === 'phase-production-build';
}

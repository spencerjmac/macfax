/**
 * Routes hidden from the public site. The list lives in
 * config/hidden-routes.json so next.config.js (redirects), the web UI and the
 * Expo app all read the same file. Pure: no React, env, or DOM.
 */

import config from '../config/hidden-routes.json';

export interface HiddenRoute {
  path: string;
  redirectTo: string;
  label: string;
  reason: string;
}

export const HIDDEN_ROUTES: readonly HiddenRoute[] = config.routes;

/** Strip query string, hash and trailing slash: "/nba/teams/?x=1" -> "/nba/teams" */
function pathOnly(href: string): string {
  const path = href.split(/[?#]/)[0];
  return path.length > 1 ? path.replace(/\/+$/, '') : path;
}

/** True for a hidden path and anything beneath it ("/nba/teams" hides "/nba/teams/celtics" but not "/nba/team/celtics"). */
export function isHiddenRoute(href: string): boolean {
  const path = pathOnly(href);
  return HIDDEN_ROUTES.some((r) => path === r.path || path.startsWith(`${r.path}/`));
}

/** Drop items whose `href` is a hidden route. */
export function withoutHidden<T extends { href: string }>(items: readonly T[]): T[] {
  return items.filter((item) => !isHiddenRoute(item.href));
}

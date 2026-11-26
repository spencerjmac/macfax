'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '@/lib/api';
import { pickCurrentSeason } from '@macfax/core/lib/season';

/** `/ncaa/team/<slug>`, plus `?season=` only when `season` is known and is not the current one. */
export function ncaaTeamHref(slug: string, season?: number | null, currentSeason?: number | null): string {
  const past = season != null && currentSeason != null && season !== currentSeason;
  return `/ncaa/team/${slug}${past ? `?season=${season}` : ''}`;
}

// One seasons request per page load, shared by every caller.
let currentSeasonPromise: Promise<number | null> | null = null;

function loadCurrentSeasonYear(): Promise<number | null> {
  if (!currentSeasonPromise) {
    currentSeasonPromise = api
      .getSeasons()
      .then((seasons) => pickCurrentSeason(seasons)?.year ?? null)
      .catch(() => {
        currentSeasonPromise = null;
        return null;
      });
  }
  return currentSeasonPromise;
}

/** The API's current season year; null until loaded (links then omit ?season=). */
export function useCurrentSeasonYear(): number | null {
  const [year, setYear] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    loadCurrentSeasonYear().then((y) => {
      if (live) setYear(y);
    });
    return () => {
      live = false;
    };
  }, []);
  return year;
}

const LinkSeasonContext = createContext<number | null>(null);

/** Season the team links inside belong to (e.g. the Crystal Ball season being viewed). */
export function TeamLinkSeason({ season, children }: { season?: number | null; children: ReactNode }) {
  return <LinkSeasonContext.Provider value={season ?? null}>{children}</LinkSeasonContext.Provider>;
}

/** Builds team-page links that keep a past season (`?season=`) from the nearest TeamLinkSeason. */
export function useNcaaTeamHref(): (slug: string) => string {
  const season = useContext(LinkSeasonContext);
  const current = useCurrentSeasonYear();
  return (slug: string) => ncaaTeamHref(slug, season, current);
}

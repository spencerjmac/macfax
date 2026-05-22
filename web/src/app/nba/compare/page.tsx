"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { nbaApi } from "@/lib/nba-api";
import { PlayerCompareView } from "@/components/PlayerCompareView";
import { PlayerScoutingCard } from "@/components/PlayerScoutingCard";
import type { NBAPlayerSeasonStats } from "@/types/nba";

function ComparePageInner() {
  const searchParams = useSearchParams();
  const idsParam = searchParams.get("ids") ?? "";
  const seasonParam = searchParams.get("season");

  const [players, setPlayers] = useState<NBAPlayerSeasonStats[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ids = idsParam
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n));

  const season = seasonParam ? parseInt(seasonParam, 10) : undefined;

  useEffect(() => {
    if (!ids.length) { setPlayers([]); return; }
    setLoading(true);
    setError(null);
    nbaApi.comparePlayers(ids, season)
      .then(setPlayers)
      .catch((e) => setError(e.message ?? "Failed to load players"))
      .finally(() => setLoading(false));
  }, [idsParam, seasonParam]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-6">
        <a href="/nba/rankings?tab=players" className="text-xs text-slate-500 hover:text-teal-400 transition-colors">
          ← Back to rankings
        </a>
        <h1 className="text-2xl font-semibold text-slate-100 mt-2 font-mono">Player Compare</h1>
        <p className="text-xs text-slate-500 mt-1">
          Add player IDs to URL: <code className="bg-slate-800 px-1 rounded">/nba/compare?ids=1641705,1628983</code>
        </p>
      </div>

      {loading && (
        <div className="text-slate-500 font-mono text-sm">Loading...</div>
      )}
      {error && (
        <div className="text-rose-400 font-mono text-sm">{error}</div>
      )}

      {!loading && !error && players.length > 0 && (
        <div className="space-y-8">
          {/* Side-by-side compare table */}
          <PlayerCompareView players={players} />

          {/* Individual scouting cards */}
          <div
            className="grid gap-4"
            style={{ gridTemplateColumns: `repeat(${Math.min(players.length, 2)}, 1fr)` }}
          >
            {players.map((p) => (
              <PlayerScoutingCard key={p.id} player={p} className="w-full" />
            ))}
          </div>
        </div>
      )}

      {!loading && !error && !ids.length && (
        <div className="text-slate-600 font-mono text-sm">
          No player IDs provided. Add <code className="bg-slate-800 px-1 rounded">?ids=</code> to the URL.
        </div>
      )}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="text-slate-500 font-mono text-sm p-8">Loading...</div>}>
      <ComparePageInner />
    </Suspense>
  );
}

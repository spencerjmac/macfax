import { notFound } from "next/navigation";
import { nbaApi } from "@/lib/nba-api";
import { PlayerScoutingCard } from "@/components/PlayerScoutingCard";

interface Props {
  params: { id: string };
  searchParams: { season?: string };
}

export default async function PlayerScoutingPage({ params, searchParams }: Props) {
  const playerId = parseInt(params.id, 10);
  if (isNaN(playerId)) notFound();

  const season = searchParams.season ? parseInt(searchParams.season, 10) : undefined;

  // Fetch all current-season players and find by player_id
  const players = await nbaApi.getLeaguePlayers({ season, ordering: "-bpr" });
  const player = players.find((p) => p.player_id === playerId);
  if (!player) notFound();

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="mb-6">
        <a href="/nba/rankings?tab=players" className="text-xs text-slate-500 hover:text-teal-400 transition-colors">
          ← Back to rankings
        </a>
      </div>
      <PlayerScoutingCard player={player} className="w-full" />
      <p className="mt-4 text-xs text-slate-600 text-center">
        BPR = Bayesian Performance Rating (pts/100 above avg, prior-informed RAPM) ·{" "}
        Wins added = (BPR + 2.0) × MPG/48 × GP/56
      </p>
    </main>
  );
}

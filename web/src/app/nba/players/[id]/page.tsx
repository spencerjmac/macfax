import Link from "next/link";
import { notFound } from "next/navigation";
import { nbaApi } from "@/lib/nba-api";
import { PlayerScoutingCard } from "@/components/PlayerScoutingCard";

interface Props {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ season?: string }>;
}

export default async function PlayerScoutingPage({ params, searchParams }: Props) {
  const { id } = await params;
  const sp = await searchParams;
  const playerId = parseInt(id, 10);
  if (isNaN(playerId)) notFound();

  const season = sp.season ? parseInt(sp.season, 10) : undefined;

  // Fetch all current-season players and find by player_id (min_gp 1: the API's default
  // of 5 games would 404 a player with fewer)
  const players = await nbaApi.getLeaguePlayers({ season, ordering: "-bpr", min_gp: 1 });
  const player = players.find((p) => p.player_id === playerId);
  if (!player) notFound();

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Link href="/nba/players" className="text-xs text-slate-500 hover:text-teal-400 transition-colors">
          ← Back to player ratings
        </Link>
      </div>
      <PlayerScoutingCard player={player} className="w-full" />
      <p className="mt-4 text-xs text-slate-600 text-center">
        MPR = Macfax Player Rating (pts/100 above avg, prior-informed RAPM) ·{" "}
        Wins added = (MPR + 2.0) × MPG/48 × GP/56
      </p>
    </main>
  );
}

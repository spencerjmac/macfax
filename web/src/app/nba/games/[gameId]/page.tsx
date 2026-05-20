import GameDetailPage from '@/components/games/GameDetailPage';

export const dynamic = 'force-dynamic';

interface Props {
  params: Promise<{ gameId: string }>;
}

export default async function Page({ params }: Props) {
  const { gameId } = await params;
  return <GameDetailPage gameId={gameId} league="nba" />;
}

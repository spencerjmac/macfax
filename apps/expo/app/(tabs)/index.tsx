import { Link } from 'expo-router';

import { SportHub } from '@/src/components/hub/SportHub';
import { Container, ScrollScreen } from '@/src/components/ui/Screen';
import { NCAA_HUB } from '@/src/config/ncaaHub';
import { fetchRankings } from '@/src/lib/api';
import { GATE_ENABLED } from '@/src/lib/devFlags';
import { useAsync } from '@/src/lib/useAsync';

/** Home tab: the NCAA hub (web's /ncaa page). */
export default function HomeScreen() {
  // Same data as web's /ncaa page: current-season rankings, sorted by rank.
  const rankings = useAsync(
    async ({ force }) => {
      const { teams } = await fetchRankings(undefined, { force });
      return [...teams].sort((a, b) => a.rank - b.rank);
    },
    [],
  );

  return (
    <ScrollScreen>
      <SportHub config={NCAA_HUB} rankings={rankings} />
      {GATE_ENABLED ? (
        <Container>
          <Link href="/gate" className="font-mono text-xs text-ink-fg2 underline">
            Dev: open gate screen
          </Link>
        </Container>
      ) : null}
    </ScrollScreen>
  );
}

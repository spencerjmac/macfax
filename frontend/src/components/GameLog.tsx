/**
 * Game Log Component
 * Displays a team's game-by-game statistics with Four Factors and Kill Shots
 */

'use client';

import { useState, useEffect } from 'react';
import type { GameLogEntry, TeamSeasonStats } from '@/types';

interface GameLogProps {
  teamSlug: string;
  seasonYear: number;
}

export default function GameLog({ teamSlug, seasonYear }: GameLogProps) {
  const [gameLog, setGameLog] = useState<GameLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    location: 'all', // all, home, away, neutral
    opponentSearch: '',
    sortBy: 'date', // date, ortg, drtg, margin
    sortDir: 'desc' as 'asc' | 'desc',
  });

  useEffect(() => {
    fetchGameLog();
  }, [teamSlug, seasonYear]);

  const fetchGameLog = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `/api/teams/${teamSlug}/gamelog?season=${seasonYear}`
      );
      const data = await response.json();
      setGameLog(data.game_log || []);
    } catch (error) {
      console.error('Failed to fetch game log:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredAndSortedGames = gameLog
    .filter((game) => {
      // Location filter
      if (filters.location !== 'all') {
        const locationMap = { home: 'H', away: 'A', neutral: 'N' };
        if (game.home_away !== locationMap[filters.location as keyof typeof locationMap]) {
          return false;
        }
      }

      // Opponent search
      if (filters.opponentSearch) {
        const search = filters.opponentSearch.toLowerCase();
        if (!game.opponent_name.toLowerCase().includes(search)) {
          return false;
        }
      }

      return true;
    })
    .sort((a, b) => {
      let aVal: any, bVal: any;

      switch (filters.sortBy) {
        case 'date':
          aVal = new Date(a.game_date).getTime();
          bVal = new Date(b.game_date).getTime();
          break;
        case 'ortg':
          aVal = a.ortg;
          bVal = b.ortg;
          break;
        case 'drtg':
          aVal = a.drtg;
          bVal = b.drtg;
          break;
        case 'margin':
          aVal = a.margin;
          bVal = b.margin;
          break;
        default:
          return 0;
      }

      return filters.sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-400">Loading game log...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-gray-800 rounded-lg p-4 space-y-4">
        <h3 className="text-lg font-semibold text-white">Filters</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Location Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Location
            </label>
            <select
              value={filters.location}
              onChange={(e) =>
                setFilters({ ...filters, location: e.target.value })
              }
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
            >
              <option value="all">All Games</option>
              <option value="home">Home</option>
              <option value="away">Away</option>
              <option value="neutral">Neutral</option>
            </select>
          </div>

          {/* Opponent Search */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Opponent
            </label>
            <input
              type="text"
              placeholder="Search opponent..."
              value={filters.opponentSearch}
              onChange={(e) =>
                setFilters({ ...filters, opponentSearch: e.target.value })
              }
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white placeholder-gray-400"
            />
          </div>

          {/* Sort By */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Sort By
            </label>
            <select
              value={filters.sortBy}
              onChange={(e) =>
                setFilters({ ...filters, sortBy: e.target.value })
              }
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
            >
              <option value="date">Date</option>
              <option value="ortg">ORtg</option>
              <option value="drtg">DRtg</option>
              <option value="margin">Margin</option>
            </select>
          </div>

          {/* Sort Direction */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Direction
            </label>
            <select
              value={filters.sortDir}
              onChange={(e) =>
                setFilters({ ...filters, sortDir: e.target.value as 'asc' | 'desc' })
              }
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </div>
        </div>
      </div>

      {/* Game Log Table */}
      <div className="bg-gray-800 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                  Opponent
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  Loc
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  Result
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  Score
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  Poss
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  ORtg
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  DRtg
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  eFG%
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  TOV%
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  ORB%
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider">
                  FTR
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {filteredAndSortedGames.map((game, idx) => (
                <tr
                  key={game.id}
                  className={`hover:bg-gray-700 ${
                    idx % 2 === 0 ? 'bg-gray-800' : 'bg-gray-850'
                  }`}
                >
                  <td className="px-4 py-3 text-sm text-gray-300">
                    {new Date(game.game_date).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <a
                      href={`/teams/${game.opponent_slug}`}
                      className="text-blue-400 hover:text-blue-300"
                    >
                      {game.opponent_name}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.home_away === 'H' && '🏠'}
                    {game.home_away === 'A' && '✈️'}
                    {game.home_away === 'N' && '⚖️'}
                  </td>
                  <td className="px-4 py-3 text-center text-sm">
                    <span
                      className={
                        game.result === 'W'
                          ? 'text-green-400 font-semibold'
                          : 'text-red-400 font-semibold'
                      }
                    >
                      {game.result}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.pts}
                    <span className="text-gray-500 text-xs ml-1">
                      ({game.margin > 0 ? '+' : ''}
                      {game.margin})
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.possessions}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.ortg.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.drtg.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.efg_pct.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.tov_pct.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.orb_pct.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-300">
                    {game.ftr.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredAndSortedGames.length === 0 && (
          <div className="text-center py-8 text-gray-400">
            No games found matching the filters.
          </div>
        )}
      </div>

      {/* Summary Stats */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-3">
          Summary ({filteredAndSortedGames.length} games)
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-sm text-gray-400">Avg ORtg</div>
            <div className="text-xl font-semibold text-white">
              {(
                filteredAndSortedGames.reduce((sum, g) => sum + g.ortg, 0) /
                (filteredAndSortedGames.length || 1)
              ).toFixed(1)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Avg DRtg</div>
            <div className="text-xl font-semibold text-white">
              {(
                filteredAndSortedGames.reduce((sum, g) => sum + g.drtg, 0) /
                (filteredAndSortedGames.length || 1)
              ).toFixed(1)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Avg eFG%</div>
            <div className="text-xl font-semibold text-white">
              {(
                filteredAndSortedGames.reduce((sum, g) => sum + g.efg_pct, 0) /
                (filteredAndSortedGames.length || 1)
              ).toFixed(1)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Record</div>
            <div className="text-xl font-semibold text-white">
              {filteredAndSortedGames.filter((g) => g.result === 'W').length}-
              {filteredAndSortedGames.filter((g) => g.result === 'L').length}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

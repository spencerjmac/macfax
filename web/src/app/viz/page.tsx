import { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Visualizations | CBB Analytics',
  description: 'Advanced basketball analytics visualizations and tools',
};

export default function VisualizationsPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">Visualizations</h1>
        <p className="text-gray-600">
          Advanced analytics tools to evaluate team performance and championship potential
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Trapezoid of Excellence */}
        <Link 
          href="/viz/trapezoid"
          className="block bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow overflow-hidden border-2 border-transparent hover:border-blue-500"
        >
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold mb-2">Trapezoid of Excellence</h2>
                <span className="inline-block px-2 py-1 text-xs font-semibold text-green-800 bg-green-100 rounded">
                  LIVE
                </span>
              </div>
              <div className="text-4xl">📐</div>
            </div>
            <p className="text-gray-600 mb-4">
              Identify elite teams by evaluating tempo and efficiency margin. Uses Ryan Hammer's national 
              baseline algorithm to maintain consistent championship standards across all filters.
            </p>
            <div className="text-blue-600 font-medium flex items-center">
              View Visualization
              <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </Link>

        {/* Efficiency Landscape */}
        <Link 
          href="/viz/landscape"
          className="block bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow overflow-hidden border-2 border-transparent hover:border-blue-500"
        >
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold mb-2">Efficiency Landscape</h2>
                <span className="inline-block px-2 py-1 text-xs font-semibold text-green-800 bg-green-100 rounded">
                  LIVE
                </span>
              </div>
              <div className="text-4xl">🗺️</div>
            </div>
            <p className="text-gray-600 mb-4">
              Maps teams by Adjusted Offensive and Defensive ratings with championship tier boundaries. 
              Diagonal lines separate title contenders from pretenders using national baselines.
            </p>
            <div className="text-blue-600 font-medium flex items-center">
              View Visualization
              <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </Link>

        {/* Viz Builder */}
        <Link 
          href="/viz/builder"
          className="block bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow overflow-hidden border-2 border-transparent hover:border-blue-500"
        >
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold mb-2">Viz Builder</h2>
                <span className="inline-block px-2 py-1 text-xs font-semibold text-green-800 bg-green-100 rounded">
                  LIVE
                </span>
              </div>
              <div className="text-4xl">🛠️</div>
            </div>
            <p className="text-gray-600 mb-4">
              Build custom scatterplots using any two stats computed from our game log data. 
              Explore correlations with regression analysis and conference-based coloring.
            </p>
            <div className="text-blue-600 font-medium flex items-center">
              View Visualization
              <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </Link>

        {/* Crystal Ball */}
        <Link 
          href="/viz/crystal-ball"
          className="block bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden border-2 border-transparent hover:border-gray-300 opacity-75"
        >
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold mb-2">The Crystal Ball</h2>
                <span className="inline-block px-2 py-1 text-xs font-semibold text-gray-600 bg-gray-200 rounded">
                  COMING SOON
                </span>
              </div>
              <div className="text-4xl">🔮</div>
            </div>
            <p className="text-gray-600 mb-4">
              Championship profile analysis using a rules engine with configurable thresholds for 
              efficiency margins, Four Factors, and historical championship benchmarks.
            </p>
            <div className="text-gray-500 font-medium flex items-center">
              Preview Coming Soon
              <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </Link>

        {/* Kill Shot Analysis */}
        <Link 
          href="/viz/kill-shot"
          className="block bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden border-2 border-transparent hover:border-gray-300 opacity-75"
        >
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold mb-2">Kill Shot Analysis</h2>
                <span className="inline-block px-2 py-1 text-xs font-semibold text-gray-600 bg-gray-200 rounded">
                  COMING SOON
                </span>
              </div>
              <div className="text-4xl">🎯</div>
            </div>
            <p className="text-gray-600 mb-4">
              Analyze game-changing possessions and momentum swings. Identifies kill shot opportunities 
              that shift win probability by 5+ points or occur in critical late-game situations.
            </p>
            <div className="text-gray-500 font-medium flex items-center">
              Preview Coming Soon
              <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </Link>
      </div>

      {/* Info Section */}
      <div className="mt-12 bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="text-xl font-bold mb-3">About These Tools</h3>
        <p className="text-gray-700 mb-4">
          All visualizations use computed ratings from our game-by-game analysis pipeline. National 
          baselines ensure that championship standards remain constant regardless of conference filters, 
          allowing fair comparisons across the entire Division I landscape.
        </p>
        <ul className="list-disc list-inside space-y-2 text-gray-700">
          <li><strong>Adjusted Efficiency Margin (Adj EM):</strong> Overall team quality (Adj O - Adj D)</li>
          <li><strong>Adjusted Tempo:</strong> Pace of play adjusted for opponent strength</li>
          <li><strong>Adjusted Offensive Rating (Adj O):</strong> Points per 100 possessions vs average defense</li>
          <li><strong>Adjusted Defensive Rating (Adj D):</strong> Points allowed per 100 possessions vs average offense</li>
        </ul>
      </div>
    </div>
  );
}

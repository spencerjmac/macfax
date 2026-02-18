'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';

export default function VisualizationsPage() {
  const router = useRouter();
  
  const visualizations = [
    {
      id: 'trapezoid',
      title: 'Trapezoid of Excellence',
      description: 'Identifies elite teams that balance efficiency with optimal tempo. Championship-caliber teams cluster within this dynamically-calculated region.',
      href: '/viz/trapezoid',
      color: 'from-red-500 to-pink-500',
      icon: '📐',
      credit: 'Concept by Ryan Hammer',
    },
    {
      id: 'landscape',
      title: 'Predicted Efficiency Landscape',
      description: 'Maps teams by offensive and defensive ratings with diagonal tier boundaries separating championship contenders from the rest.',
      href: '/viz/landscape',
      color: 'from-orange-500 to-blue-500',
      icon: '🗺️',
      credit: null,
    },
    {
      id: 'builder',
      title: 'Viz Builder',
      description: 'Build your own custom scatterplot. Choose any two stats from KenPom, Torvik, Evan Miya, or CBB Analytics to explore relationships and correlations.',
      href: '/viz/builder',
      color: 'from-purple-500 to-indigo-500',
      icon: '🛠️',
      credit: null,
    },
  ];
  
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">Visualizations</h1>
        <p className="text-gray-600 text-lg">
          Explore interactive charts and advanced analytics to identify championship-caliber teams
        </p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {visualizations.map((viz) => (
          <Link
            key={viz.id}
            href={viz.href}
            className="group block bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow overflow-hidden"
          >
            <div className={`h-32 bg-gradient-to-br ${viz.color} flex items-center justify-center`}>
              <span className="text-6xl" role="img" aria-label={viz.title}>
                {viz.icon}
              </span>
            </div>
            
            <div className="p-6">
              <h2 className="text-2xl font-bold mb-2 group-hover:text-primary transition-colors">
                {viz.title}
              </h2>
              
              <p className="text-gray-600 mb-4">
                {viz.description}
              </p>
              
              {viz.credit && (
                <p className="text-sm text-gray-500 italic">
                  {viz.credit}
                </p>
              )}
              
              <div className="mt-4 flex items-center text-primary font-medium">
                <span>Explore</span>
                <svg
                  className="ml-2 w-4 h-4 group-hover:translate-x-1 transition-transform"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </div>
            </div>
          </Link>
        ))}
      </div>
      
      <div className="mt-12 bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="text-xl font-bold mb-3 text-blue-900">About These Visualizations</h3>
        <p className="text-blue-800 mb-3">
          These advanced analytics tools help you identify championship-caliber teams before Selection Sunday. 
          Both visualizations use adjusted efficiency metrics that account for strength of schedule and opponent quality.
        </p>
        <p className="text-sm text-blue-700">
          <strong>Pro Tip:</strong> Use the conference filter to focus on specific leagues, or set "Top Teams" 
          to narrow your view to tournament-caliber programs.
        </p>
      </div>
    </div>
  );
}

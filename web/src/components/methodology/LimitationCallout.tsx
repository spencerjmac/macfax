import { AlertTriangle } from 'lucide-react';

interface LimitationCalloutProps {
  limitations: string[];
}

export function LimitationCallout({ limitations }: LimitationCalloutProps) {
  return (
    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 my-2">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-yellow-600 shrink-0" />
        <span className="text-xs font-medium uppercase tracking-wide text-yellow-700">
          Known Limitations
        </span>
      </div>
      <ul className="space-y-1.5">
        {limitations.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-yellow-800">
            <span className="shrink-0 mt-0.5 text-yellow-500">•</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

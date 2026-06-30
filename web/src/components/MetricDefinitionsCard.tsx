'use client';

export interface MetricDefinition {
  k: string;
  v: string;
}

interface MetricDefinitionsCardProps {
  definitions: MetricDefinition[];
}

export default function MetricDefinitionsCard({ definitions }: MetricDefinitionsCardProps) {
  return (
    <div className="mt-8 p-6 bg-ui-surface border border-ui-border rounded-lg">
      <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-[14px]">Metric Definitions</h2>
      <div className="grid md:grid-cols-2 gap-3 text-[13.5px]">
        {definitions.map((d) => (
          <div key={d.k} className="text-muted">
            <b className="font-mono font-semibold text-text-primary mr-1.5">{d.k}</b>{d.v}
          </div>
        ))}
      </div>
    </div>
  );
}

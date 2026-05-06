interface ValidationMetricCardProps {
  label: string;
  value: string;
  description: string;
  subtext?: string;
  highlight?: boolean;
}

export function ValidationMetricCard({ label, value, description, subtext, highlight }: ValidationMetricCardProps) {
  return (
    <div className={`bg-ui-card border rounded-xl p-5 ${highlight ? 'border-brand/40' : 'border-ui-border'}`}>
      <div className="text-xs font-medium text-text-muted uppercase tracking-wide mb-2">{label}</div>
      <div className={`text-3xl font-bold mb-1 ${highlight ? 'text-brand' : 'text-text-primary'}`}>{value}</div>
      <div className="text-sm text-text-muted">{description}</div>
      {subtext && <div className="text-xs text-text-muted mt-2 opacity-70">{subtext}</div>}
    </div>
  );
}

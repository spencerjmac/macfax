import { BookOpen } from 'lucide-react';

interface ExampleCardProps {
  example: string;
}

export function ExampleCard({ example }: ExampleCardProps) {
  return (
    <div className="bg-brand/5 border border-brand/20 rounded-xl p-5 my-2">
      <div className="flex items-center gap-2 mb-3">
        <BookOpen className="w-4 h-4 text-brand" />
        <span className="text-xs font-medium uppercase tracking-wide text-brand">Example</span>
      </div>
      <p className="text-sm text-text-primary leading-relaxed">{example}</p>
    </div>
  );
}

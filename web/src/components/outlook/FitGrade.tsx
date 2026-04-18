'use client';

import clsx from 'clsx';
import type { FitGrade as FitGradeType } from '@/types/outlook';

interface FitGradeBadgeProps {
  grade: FitGradeType | null | undefined;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

function gradeColor(letter: string): string {
  if (letter.startsWith('A')) return 'bg-emerald-100 text-emerald-800 border-emerald-300';
  if (letter.startsWith('B')) return 'bg-teal-100 text-teal-800 border-teal-300';
  if (letter.startsWith('C')) return 'bg-yellow-100 text-yellow-800 border-yellow-300';
  if (letter.startsWith('D')) return 'bg-orange-100 text-orange-800 border-orange-300';
  return 'bg-rose-100 text-rose-800 border-rose-300';
}

export function FitGradeBadge({ grade, size = 'md', showLabel = false }: FitGradeBadgeProps) {
  if (!grade || grade.score == null) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded border text-xs font-mono bg-ui-surface text-text-muted border-ui-border">
        N/A
      </span>
    );
  }

  const sizeClasses = {
    sm: 'text-xs px-1.5 py-0.5',
    md: 'text-sm px-2.5 py-0.5',
    lg: 'text-base px-3 py-1',
  }[size];

  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 rounded border font-semibold font-mono',
      gradeColor(grade.letter),
      sizeClasses,
    )}>
      <span>{grade.letter}</span>
      {showLabel && (
        <span className="font-normal text-xs opacity-75">{grade.label}</span>
      )}
      {grade.score != null && (
        <span className="font-normal text-xs opacity-60">({grade.score})</span>
      )}
    </span>
  );
}

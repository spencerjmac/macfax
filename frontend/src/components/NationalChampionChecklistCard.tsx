/**
 * National Champion Checklist Card
 * 
 * Displays the 15-item championship checklist for a team on their profile page.
 */

import React from 'react';
import type { NationalChampionChecklist } from '@/types';

interface Props {
  checklist: NationalChampionChecklist;
  isLoading?: boolean;
  error?: string | null;
}

export default function NationalChampionChecklistCard({ checklist, isLoading, error }: Props) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-3/4 mb-4"></div>
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-4 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-bold mb-2">National Champion Checklist</h3>
        <p className="text-sm text-gray-500">{error}</p>
      </div>
    );
  }

  const passPercentage = Math.round((checklist.passedCount / checklist.totalCount) * 100);

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-blue-700 text-white p-6">
        <h3 className="text-xl font-bold mb-2">National Champion Checklist</h3>
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold mono">
            {checklist.passedCount} / {checklist.totalCount}
          </span>
          <span className="text-indigo-100">checks passed</span>
        </div>
        
        {/* Progress Bar */}
        <div className="mt-4 bg-indigo-800 rounded-full h-2 overflow-hidden">
          <div
            className="bg-white h-full transition-all duration-500"
            style={{ width: `${passPercentage}%` }}
          ></div>
        </div>
      </div>

      {/* Checklist Items */}
      <div className="p-6">
        <div className="space-y-3">
          {checklist.items.map((item, index) => (
            <ChecklistItemRow key={item.key} item={item} index={index} />
          ))}
        </div>
      </div>

      {/* Footer Note */}
      <div className="px-6 pb-6">
        <p className="text-xs text-gray-500 italic">
          Based on historical championship team thresholds. Teams passing 12+ checks are considered strong contenders.
        </p>
      </div>
    </div>
  );
}

interface ChecklistItemRowProps {
  item: {
    key: string;
    label: string;
    pass: boolean;
    value: string | number;
    threshold: string;
    details: string;
  };
  index: number;
}

function ChecklistItemRow({ item, index }: ChecklistItemRowProps) {
  const isNA = item.value === 'N/A';
  
  return (
    <div
      className={`
        flex items-start gap-3 p-3 rounded-lg border transition-all
        ${item.pass && !isNA 
          ? 'bg-green-50 border-green-200' 
          : 'bg-gray-50 border-gray-200'
        }
        hover:shadow-sm
      `}
      title={item.details}
    >
      {/* Pass/Fail Icon */}
      <div className="flex-shrink-0 mt-0.5">
        {item.pass && !isNA ? (
          <svg
            className="w-5 h-5 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2.5}
              d="M5 13l4 4L19 7"
            />
          </svg>
        ) : (
          <svg
            className="w-5 h-5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2.5}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4">
          {/* Label */}
          <div className="flex-1">
            <span className="text-sm font-medium text-gray-900">
              {index + 1}. {item.label}
            </span>
          </div>

          {/* Value and Threshold */}
          <div className="text-right">
            <div className={`
              text-sm font-bold mono
              ${item.pass && !isNA ? 'text-green-700' : 'text-gray-600'}
            `}>
              {item.value}
            </div>
            <div className="text-xs text-gray-500 mono">
              {item.threshold}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export type MethodologySection =
  | 'core-ratings'
  | 'player-evaluation'
  | 'roster-projections'
  | 'prediction-tools'
  | 'visual-frameworks'
  | 'resume-data';

export interface InterpretationBandEntry {
  label: string;
  range: string;
  color: string;
  description: string;
}

export interface RelatedMetric {
  label: string;
  slug: string;
}

export interface WeightEntry {
  label: string;
  value: string;
  pct: string;
}

export interface FormulaContent {
  latex?: string;
  prose?: string;
}

export interface MethodologyContent {
  slug: string;
  title: string;
  subtitle: string;
  summary: string;
  whatItMeasures: string;
  whyItMatters: string;
  howToInterpret: string;
  basicFormula?: FormulaContent;
  weights?: WeightEntry[];
  interpretationBands?: InterpretationBandEntry[];
  technicalNotes: string[];
  knownLimitations: string[];
  example?: string;
  relatedMetrics?: RelatedMetric[];
  lastUpdated: string;
  methodologyVersion: string;
  section: MethodologySection;
  description: string;
  bestUsedFor: string;
}

export interface MethodologySectionConfig {
  id: MethodologySection;
  title: string;
  slugs: string[];
}

export type GlossaryCategory =
  | 'efficiency'
  | 'four-factors'
  | 'player-ratings'
  | 'resume'
  | 'prediction'
  | 'validation'
  | 'visual-frameworks';

export const CATEGORY_LABELS: Record<GlossaryCategory, string> = {
  'efficiency': 'Efficiency Ratings',
  'four-factors': 'Four Factors',
  'player-ratings': 'Player Ratings',
  'resume': 'Resume Metrics',
  'prediction': 'Prediction',
  'validation': 'Validation',
  'visual-frameworks': 'Visual Frameworks',
};

export interface GlossaryTerm {
  id: string;
  term: string;
  aliases?: string[];
  category: GlossaryCategory;
  shortDefinition: string;
  detailedDefinition: string;
  formula?: {
    display: string;
    prose?: string;
  };
  howToInterpret?: string;
  methodologySlug?: string;
  relatedTerms?: string[];
  isHigherBetter?: boolean | null;
}

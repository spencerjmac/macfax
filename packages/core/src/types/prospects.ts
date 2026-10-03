export interface Prospect {
  rank: number;
  name: string;
  position: string;
  positionGroup: string;
  college: string;
  age: number;
  bpm: number | null;
  dbpm: number | null;
  obpm: number | null;
  per: number | null;
  ts: number | null;
  fgPct: number | null;
  ws40: number | null;
  ppg: number | null;
  rpg: number | null;
  apg: number | null;
  stlPg: number | null;
  blkPg: number | null;
  orbPct: number | null;
  astPct: number | null;
  strengths: string[];
  weaknesses: string[];
  comp1: string | null;
  comp1Year: number | null;
  comp1Pick: number | null;
  comp1Sim: number | null;
  comp2: string | null;
  comp2Year: number | null;
  comp2Pick: number | null;
  comp2Sim: number | null;
  mpsComposite: number;
  srsAdj: number;
  ageAdj: number;
  scoutAdj: number;
  availAdj: number;
  mps: number;
  grade: 'S' | 'A' | 'D';
  tankRank: number | null;
  tier: 'full' | 'high' | 'medium';
  note: string;
  heightFloor: number;
  combinePen: number;
  headshot: string | null;
}

export interface ProspectsData {
  updatedAt: string;
  totalProspects: number;
  prospects: Prospect[];
}

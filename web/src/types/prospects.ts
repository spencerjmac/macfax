export interface Prospect {
  rank: number;
  name: string;
  position: string;
  positionGroup: string;
  college: string;
  age: number;
  bpm: number | null;
  dbpm: number | null;
  per: number | null;
  ts: number | null;
  mpsComposite: number;
  srsAdj: number;
  ageAdj: number;
  scoutAdj: number;
  availAdj: number;
  mps: number;
  grade: 'S' | 'A' | 'B' | 'C' | 'D';
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

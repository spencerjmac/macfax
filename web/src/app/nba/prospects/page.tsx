import { Metadata } from 'next';
import prospectsData from '@/data/prospects_2026.json';
import { ProspectsBigBoard } from '@/components/prospects/ProspectsBigBoard';
import { ProspectsData } from '@/types/prospects';

export const metadata: Metadata = {
  title: '2026 NBA Draft Big Board | MacFacts',
  description:
    'MacFax Prospect Score — empirically-derived NBA draft rankings validated on 500+ historical prospects with 11-fold cross-validation.',
};

export default function ProspectsPage() {
  return (
    <div className="min-h-screen">
      <ProspectsBigBoard data={prospectsData as ProspectsData} />
    </div>
  );
}

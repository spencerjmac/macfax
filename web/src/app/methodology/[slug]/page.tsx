import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import {
  getMethodologyBySlug,
  getAllMethodologySlugs,
} from '@/lib/methodologyContent';
import { MethodologyArticle } from '@/components/methodology/MethodologyArticle';

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  return getAllMethodologySlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const content = getMethodologyBySlug(slug);

  if (!content) {
    return { title: 'Not Found | macfax' };
  }

  return {
    title: `${content.title} | Methodology | macfax`,
    description: content.summary,
  };
}

export default async function MethodologyArticlePage({ params }: Props) {
  const { slug } = await params;
  const content = getMethodologyBySlug(slug);

  if (!content) {
    notFound();
  }

  return <MethodologyArticle content={content} />;
}

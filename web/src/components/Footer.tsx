import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="border-t border-ui-border py-5 mt-auto">
      <div className="container mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-text-muted">
        <span className="font-semibold text-text-primary">macfax</span>
        <div className="flex items-center gap-6">
          <Link href="/validation" className="hover:text-text-primary transition-colors">
            Model Accuracy
          </Link>
          <Link href="/methodology" className="hover:text-text-primary transition-colors">
            Methodology
          </Link>
          <Link href="/ncaa/glossary" className="hover:text-text-primary transition-colors">
            Glossary
          </Link>
          <Link href="/about" className="hover:text-text-primary transition-colors">
            About
          </Link>
        </div>
      </div>
    </footer>
  );
}

import Link from 'next/link';

export default function OutlookNotFound() {
  return (
    <div className="container mx-auto px-4 py-24 text-center">
      <h1 className="text-4xl font-bold text-text-primary mb-4">Team not found</h1>
      <p className="text-text-muted mb-8">
        No roster outlook data found for this team. The team slug may be incorrect, or
        projection data may not yet be available for this season.
      </p>
      <Link
        href="/"
        className="inline-block px-6 py-2 rounded bg-brand text-white font-medium hover:opacity-90 transition"
      >
        Go home
      </Link>
    </div>
  );
}

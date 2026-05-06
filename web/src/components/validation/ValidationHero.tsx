export function ValidationHero() {
  return (
    <div className="mb-10">
      <h1 className="text-4xl font-bold text-text-primary mb-3">How Accurate Is Macfax?</h1>
      <p className="text-lg text-text-muted leading-relaxed max-w-2xl">
        Macfax is an independent college basketball model. This page tracks how the model performs
        against actual results, what it gets right, and where it is still improving.
      </p>
      <div className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm text-text-muted">
        <svg className="w-4 h-4 text-brand flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        Validation is based on locked pregame predictions saved before final scores are known.
      </div>
    </div>
  );
}

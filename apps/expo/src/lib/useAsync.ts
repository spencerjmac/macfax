import { useCallback, useEffect, useState, type DependencyList } from 'react';

export type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: T };

export type AsyncResult<T> = AsyncState<T> & {
  /** Run the loader again. The loader receives `force: true` so it can skip caches. */
  retry: () => void;
};

/**
 * Runs an async loader and tracks loading / error / ready. Reruns when `deps`
 * change. Results from an outdated run are ignored, so a slow earlier request
 * cannot overwrite a newer one. Pair with <AsyncView> to render the states.
 */
export function useAsync<T>(load: (options: { force: boolean }) => Promise<T>, deps: DependencyList): AsyncResult<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  // Back to loading as soon as the inputs change (React's "adjust state while rendering"),
  // so the effect below only sets state from the async callbacks.
  const inputs = [...deps, attempt];
  const [seenInputs, setSeenInputs] = useState(inputs);
  if (inputs.length !== seenInputs.length || inputs.some((value, i) => !Object.is(value, seenInputs[i]))) {
    setSeenInputs(inputs);
    setState({ status: 'loading' });
  }

  useEffect(() => {
    let cancelled = false;
    load({ force: attempt > 0 })
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
    // `load` is expected to be an inline closure; `deps` lists what it reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}

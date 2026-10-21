import { AlertTriangle, Inbox } from '@/src/components/ui/icons';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';

import type { AsyncResult } from '@/src/lib/useAsync';
import { ink, palette } from '@/src/theme/tokens';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <View className="items-center justify-center gap-3 p-8">
      <ActivityIndicator color={palette.brand} />
      <Text className="font-sans text-sm text-ink-fg2">{label}</Text>
    </View>
  );
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  return (
    <View className="items-center justify-center gap-3 p-8">
      <AlertTriangle color={palette.negative} size={28} strokeWidth={1.5} />
      <Text className="text-center font-sans-semibold text-base text-text-onDark">{title}</Text>
      <Text className="max-w-[420px] text-center font-sans text-sm text-ink-fg">{message}</Text>
      {onRetry ? (
        <Pressable onPress={onRetry} accessibilityRole="button" className="mt-1 rounded-lg bg-brand px-5 py-2.5 active:bg-brand-hover">
          <Text className="font-display-semibold text-sm uppercase tracking-wider text-text-onDark">Retry</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function EmptyState({ title, message }: { title: string; message?: string }) {
  return (
    <View className="items-center justify-center gap-2 p-8">
      <Inbox color={ink.fg2} size={28} strokeWidth={1.5} />
      <Text className="text-center font-sans-semibold text-base text-text-onDark">{title}</Text>
      {message ? <Text className="max-w-[420px] text-center font-sans text-sm text-ink-fg2">{message}</Text> : null}
    </View>
  );
}

interface AsyncViewProps<T> {
  state: AsyncResult<T>;
  children: (data: T) => React.ReactNode;
  loadingLabel?: string;
  errorTitle?: string;
  /** Treat this data as "nothing to show" and render the empty state instead. */
  isEmpty?: (data: T) => boolean;
  emptyTitle?: string;
  emptyMessage?: string;
}

/**
 * The app's standard way to render a useAsync result: a spinner while loading,
 * the error with a Retry button on failure, an empty state when there is no
 * data, and otherwise the children.
 */
export function AsyncView<T>({ state, children, loadingLabel, errorTitle, isEmpty, emptyTitle = 'Nothing to show', emptyMessage }: AsyncViewProps<T>) {
  if (state.status === 'loading') return <LoadingState label={loadingLabel} />;
  if (state.status === 'error') return <ErrorState title={errorTitle} message={state.message} onRetry={state.retry} />;
  if (isEmpty?.(state.data)) return <EmptyState title={emptyTitle} message={emptyMessage} />;
  return <>{children(state.data)}</>;
}

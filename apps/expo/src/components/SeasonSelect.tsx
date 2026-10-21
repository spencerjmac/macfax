import type { SeasonInfo } from '@macfax/core/types';
import { Check, ChevronDown } from '@/src/components/ui/icons';
import { useState } from 'react';
import { FlatList, Modal, Pressable, Text } from 'react-native';

import { ink, palette } from '@/src/theme/tokens';

interface SeasonSelectProps {
  seasons: SeasonInfo[];
  /** Selected season year; undefined means the current season. */
  value: number | undefined;
  onChange: (year: number) => void;
}

/**
 * Season picker: a button that opens a list in a modal. React Native has no
 * <select>, so this stands in for the dropdown in web's RankingsTable.
 * Like web, it renders nothing when there is only one season.
 */
export function SeasonSelect({ seasons, value, onChange }: SeasonSelectProps) {
  const [open, setOpen] = useState(false);
  if (seasons.length <= 1) return null;

  const selected = seasons.find((s) => s.year === value) ?? seasons.find((s) => s.is_current) ?? seasons[0];

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={`Season ${selected.display_name}. Change season`}
        className="h-10 flex-row items-center gap-2 rounded-lg border border-ink-line bg-ink-2 px-3 active:border-brand"
      >
        <Text className="font-sans-medium text-sm text-text-onDark">{selected.display_name}</Text>
        <ChevronDown color={ink.fg2} size={16} strokeWidth={1.5} />
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable onPress={() => setOpen(false)} className="flex-1 items-center justify-center bg-black/60 p-6">
          {/* Inner Pressable swallows taps so only the backdrop closes the modal. */}
          <Pressable className="max-h-[70%] w-full max-w-[340px] overflow-hidden rounded-xl border border-ink-line bg-ink-2">
            <Text className="border-b border-ink-line px-4 py-3 font-display-semibold text-sm uppercase tracking-wider text-ink-fg">
              Season
            </Text>
            <FlatList
              data={seasons}
              keyExtractor={(s) => String(s.year)}
              renderItem={({ item }) => {
                const active = item.year === selected.year;
                return (
                  <Pressable
                    onPress={() => {
                      setOpen(false);
                      if (!active) onChange(item.year);
                    }}
                    accessibilityRole="button"
                    className="flex-row items-center justify-between border-b border-ink-line px-4 py-3 active:bg-ink-3"
                  >
                    <Text className={`text-base ${active ? 'font-sans-semibold text-brand2' : 'font-sans text-text-onDark'}`}>
                      {item.display_name}
                      {item.is_current ? ' (Current)' : ''}
                    </Text>
                    {active ? <Check color={palette.brand2} size={18} strokeWidth={2} /> : null}
                  </Pressable>
                );
              }}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

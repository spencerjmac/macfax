import { ScrollView, View } from 'react-native';

/** Centers content and caps its width at the website's 1240px, so wide screens do not stretch. */
export function Container({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <View className={`w-full max-w-[1240px] self-center px-4 md:px-8 ${className}`}>{children}</View>;
}

/** A vertically scrolling screen on the navy background. */
export function ScrollScreen({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView className="flex-1 bg-bg" contentContainerClassName="pb-10">
      {children}
    </ScrollView>
  );
}

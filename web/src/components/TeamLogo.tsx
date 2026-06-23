'use client';

interface TeamLogoProps {
  src: string | null;
  alt: string;
  width?: number;
  height?: number;
  className?: string;
  fallbackColor?: string;
}

export default function TeamLogo({
  src,
  alt,
  width = 28,
  height = 28,
  className = '',
  fallbackColor = '#64748b',
}: TeamLogoProps) {
  if (!src) {
    return (
      <div
        className={`rounded-full flex-shrink-0 ${className}`}
        style={{ width, height, backgroundColor: fallbackColor }}
      />
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      className={className}
      onError={(e) => {
        (e.target as HTMLImageElement).style.display = 'none';
      }}
    />
  );
}

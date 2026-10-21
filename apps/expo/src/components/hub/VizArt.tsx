import Svg, { Circle, Line, Path } from 'react-native-svg';

import type { HubViz } from '@/src/config/ncaaHub';
import { palette } from '@/src/theme/tokens';

const COLOR = palette.brand2;

/** The three line-art thumbnails from web's SportHubPage, redrawn with react-native-svg. */
export function VizArt({ kind }: { kind: HubViz['art'] }) {
  const common = { width: 150, height: 90, viewBox: '0 0 150 90', fill: 'none', stroke: COLOR, strokeWidth: 1.4 } as const;

  if (kind === 'trapezoid') {
    return (
      <Svg {...common}>
        <Path d="M30 70 L52 22 L98 22 L120 70 Z" opacity={0.5} />
        <Circle cx={66} cy={40} r={3.5} fill={COLOR} stroke="none" />
        <Circle cx={84} cy={34} r={3.5} fill={COLOR} stroke="none" />
        <Circle cx={75} cy={52} r={3.5} fill={COLOR} stroke="none" />
        <Circle cx={52} cy={58} r={3} fill={COLOR} stroke="none" opacity={0.6} />
        <Circle cx={98} cy={60} r={3} fill={COLOR} stroke="none" opacity={0.6} />
      </Svg>
    );
  }

  if (kind === 'landscape') {
    return (
      <Svg {...common}>
        <Line x1={20} y1={78} x2={130} y2={78} opacity={0.4} />
        <Line x1={20} y1={78} x2={20} y2={12} opacity={0.4} />
        <Circle cx={50} cy={55} r={4} fill={COLOR} stroke="none" />
        <Circle cx={80} cy={38} r={4} fill={COLOR} stroke="none" />
        <Circle cx={100} cy={28} r={4} fill={COLOR} stroke="none" />
        <Circle cx={65} cy={62} r={3} fill={COLOR} stroke="none" opacity={0.6} />
        <Circle cx={110} cy={48} r={3} fill={COLOR} stroke="none" opacity={0.6} />
      </Svg>
    );
  }

  return (
    <Svg {...common}>
      <Circle cx={75} cy={36} r={23} />
      <Path d="M64 26a12 12 0 0 1 9-5" opacity={0.75} strokeWidth={1.6} />
      <Path d="M60 56c-4 4-6 9-6 15M90 56c4 4 6 9 6 15" />
      <Path d="M48 73h54" strokeWidth={1.6} />
      <Path d="M118 22l1.6 4 4 1.6-4 1.6-1.6 4-1.6-4-4-1.6 4-1.6z" fill={COLOR} stroke="none" opacity={0.7} />
    </Svg>
  );
}

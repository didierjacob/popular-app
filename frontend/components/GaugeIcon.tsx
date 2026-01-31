import React from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Path, Circle, Line } from 'react-native-svg';

interface GaugeIconProps {
  score: number; // 0-100
  size?: number;
}

export function GaugeIcon({ score, size = 40 }: GaugeIconProps) {
  // Ensure size is valid
  const safeSize = Math.max(size, 20);
  
  // Convert score (0-100) to angle (-135 to 135 degrees)
  const scoreToAngle = (s: number) => {
    const clampedScore = Math.max(0, Math.min(100, s));
    return (clampedScore - 50) * 2.7;
  };

  const currentAngle = scoreToAngle(score);

  const center = safeSize / 2;
  const radius = safeSize * 0.38;
  const strokeWidth = Math.max(safeSize * 0.1, 3);

  // Helper function to convert polar to cartesian coordinates
  const polarToCartesian = (cx: number, cy: number, r: number, angle: number) => {
    const rad = ((angle - 90) * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    };
  };

  // Create arc path
  const createArc = (startAngle: number, endAngle: number) => {
    const start = polarToCartesian(center, center, radius, startAngle);
    const end = polarToCartesian(center, center, radius, endAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? 0 : 1;
    return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius.toFixed(2)} ${radius.toFixed(2)} 0 ${largeArcFlag} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
  };

  // Calculate needle endpoint
  const needleLength = radius - strokeWidth / 2;
  const needleEnd = polarToCartesian(center, center, needleLength, currentAngle - 90);

  return (
    <View style={[styles.container, { width: safeSize, height: safeSize }]}>
      <Svg width={safeSize} height={safeSize} viewBox={`0 0 ${safeSize} ${safeSize}`}>
        {/* Red segment (left) */}
        <Path
          d={createArc(-135, -45)}
          stroke="#E53935"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
        />
        {/* Gray segment (center) */}
        <Path
          d={createArc(-45, 45)}
          stroke="#607D8B"
          strokeWidth={strokeWidth}
          strokeLinecap="butt"
          fill="none"
        />
        {/* Green segment (right) */}
        <Path
          d={createArc(45, 135)}
          stroke="#00E676"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
        />
        {/* Needle */}
        <Line
          x1={center}
          y1={center}
          x2={needleEnd.x}
          y2={needleEnd.y}
          stroke="#FFFFFF"
          strokeWidth={Math.max(2, safeSize * 0.05)}
          strokeLinecap="round"
        />
        {/* Center circle */}
        <Circle
          cx={center}
          cy={center}
          r={Math.max(safeSize * 0.08, 2)}
          fill="#FFFFFF"
        />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'relative',
  },
});

export default GaugeIcon;

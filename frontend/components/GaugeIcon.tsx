import React, { useEffect, useRef, useState } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Path, Circle, Defs, LinearGradient, Stop, RadialGradient, G, Ellipse } from 'react-native-svg';

interface GaugeIconProps {
  score: number; // 0-100
  size?: number;
}

export function GaugeIcon({ score, size = 40 }: GaugeIconProps) {
  const [oscillationOffset, setOscillationOffset] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  // Ensure size is valid
  const safeSize = Math.max(size, 20);
  
  // Convert score (0-100) to angle (-135 to 135 degrees)
  const scoreToAngle = (s: number) => {
    const clampedScore = Math.max(0, Math.min(100, s));
    return (clampedScore - 50) * 2.7;
  };

  const baseAngle = scoreToAngle(score);
  const currentAngle = baseAngle + oscillationOffset;

  // Oscillation effect for "live" feeling
  useEffect(() => {
    let direction = 1;
    let offset = 0;
    
    intervalRef.current = setInterval(() => {
      offset += direction * 0.25;
      if (offset > 1.5) direction = -1;
      if (offset < -1.5) direction = 1;
      setOscillationOffset(offset);
    }, 80);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  const center = safeSize / 2;
  const outerRadius = safeSize * 0.42;
  const innerRadius = safeSize * 0.28;
  const strokeWidth = outerRadius - innerRadius;

  // Helper function to convert polar to cartesian coordinates
  const polarToCartesian = (cx: number, cy: number, r: number, angle: number) => {
    const rad = ((angle - 90) * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    };
  };

  // Create arc path for thick segments
  const createArcPath = (startAngle: number, endAngle: number, outerR: number, innerR: number) => {
    const outerStart = polarToCartesian(center, center, outerR, startAngle);
    const outerEnd = polarToCartesian(center, center, outerR, endAngle);
    const innerStart = polarToCartesian(center, center, innerR, startAngle);
    const innerEnd = polarToCartesian(center, center, innerR, endAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? 0 : 1;
    
    return `M ${outerStart.x.toFixed(2)} ${outerStart.y.toFixed(2)} 
            A ${outerR.toFixed(2)} ${outerR.toFixed(2)} 0 ${largeArcFlag} 1 ${outerEnd.x.toFixed(2)} ${outerEnd.y.toFixed(2)}
            L ${innerEnd.x.toFixed(2)} ${innerEnd.y.toFixed(2)}
            A ${innerR.toFixed(2)} ${innerR.toFixed(2)} 0 ${largeArcFlag} 0 ${innerStart.x.toFixed(2)} ${innerStart.y.toFixed(2)}
            Z`;
  };

  // Calculate needle
  const needleLength = outerRadius + safeSize * 0.02;
  const needleBase = safeSize * 0.06;
  const angleRad = ((currentAngle - 90) * Math.PI) / 180;
  
  // Needle tip
  const tipX = center + needleLength * Math.cos(angleRad);
  const tipY = center + needleLength * Math.sin(angleRad);
  
  // Needle base points (perpendicular to needle direction)
  const perpAngle = angleRad + Math.PI / 2;
  const baseX1 = center + needleBase * Math.cos(perpAngle);
  const baseY1 = center + needleBase * Math.sin(perpAngle);
  const baseX2 = center - needleBase * Math.cos(perpAngle);
  const baseY2 = center - needleBase * Math.sin(perpAngle);

  // Tick marks positions
  const tickAngles = [-135, -90, -45, 0, 45, 90, 135];

  return (
    <View style={[styles.container, { width: safeSize, height: safeSize }]}>
      <Svg width={safeSize} height={safeSize} viewBox={`0 0 ${safeSize} ${safeSize}`}>
        <Defs>
          {/* Red gradient */}
          <LinearGradient id="redGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#FF5252" />
            <Stop offset="50%" stopColor="#E53935" />
            <Stop offset="100%" stopColor="#B71C1C" />
          </LinearGradient>
          
          {/* Gray gradient */}
          <LinearGradient id="grayGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#90A4AE" />
            <Stop offset="50%" stopColor="#607D8B" />
            <Stop offset="100%" stopColor="#455A64" />
          </LinearGradient>
          
          {/* Green gradient */}
          <LinearGradient id="greenGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#69F0AE" />
            <Stop offset="50%" stopColor="#00E676" />
            <Stop offset="100%" stopColor="#00C853" />
          </LinearGradient>
          
          {/* Center knob gradient */}
          <RadialGradient id="knobGrad" cx="40%" cy="40%" r="60%">
            <Stop offset="0%" stopColor="#FFFFFF" />
            <Stop offset="70%" stopColor="#E0E0E0" />
            <Stop offset="100%" stopColor="#9E9E9E" />
          </RadialGradient>
          
          {/* Needle gradient */}
          <LinearGradient id="needleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#FFFFFF" />
            <Stop offset="100%" stopColor="#BDBDBD" />
          </LinearGradient>
          
          {/* Inner shadow */}
          <RadialGradient id="innerShadow" cx="50%" cy="50%" r="50%">
            <Stop offset="60%" stopColor="transparent" />
            <Stop offset="100%" stopColor="rgba(0,0,0,0.3)" />
          </RadialGradient>
        </Defs>
        
        {/* Background ring for depth */}
        <Circle
          cx={center}
          cy={center}
          r={(outerRadius + innerRadius) / 2}
          stroke="rgba(0,0,0,0.4)"
          strokeWidth={strokeWidth + 2}
          fill="none"
        />
        
        {/* Red segment (left) */}
        <Path
          d={createArcPath(-135, -45, outerRadius, innerRadius)}
          fill="url(#redGrad)"
        />
        
        {/* Gray segment (center) */}
        <Path
          d={createArcPath(-45, 45, outerRadius, innerRadius)}
          fill="url(#grayGrad)"
        />
        
        {/* Green segment (right) */}
        <Path
          d={createArcPath(45, 135, outerRadius, innerRadius)}
          fill="url(#greenGrad)"
        />
        
        {/* Inner arc highlight for 3D effect */}
        <Path
          d={createArcPath(-135, 135, innerRadius + strokeWidth * 0.15, innerRadius)}
          fill="rgba(255,255,255,0.15)"
        />
        
        {/* Tick marks */}
        {tickAngles.map((angle, index) => {
          const innerTick = polarToCartesian(center, center, innerRadius - 1, angle);
          const outerTick = polarToCartesian(center, center, innerRadius - safeSize * 0.06, angle);
          return (
            <Path
              key={index}
              d={`M ${innerTick.x} ${innerTick.y} L ${outerTick.x} ${outerTick.y}`}
              stroke="rgba(255,255,255,0.6)"
              strokeWidth={Math.max(1, safeSize * 0.02)}
              strokeLinecap="round"
            />
          );
        })}
        
        {/* Needle shadow */}
        <Path
          d={`M ${baseX1 + 1} ${baseY1 + 1} L ${tipX + 1} ${tipY + 1} L ${baseX2 + 1} ${baseY2 + 1} Z`}
          fill="rgba(0,0,0,0.3)"
        />
        
        {/* Needle */}
        <Path
          d={`M ${baseX1} ${baseY1} L ${tipX} ${tipY} L ${baseX2} ${baseY2} Z`}
          fill="url(#needleGrad)"
        />
        
        {/* Center knob shadow */}
        <Ellipse
          cx={center + 1}
          cy={center + 1}
          rx={safeSize * 0.11}
          ry={safeSize * 0.11}
          fill="rgba(0,0,0,0.4)"
        />
        
        {/* Center knob */}
        <Circle
          cx={center}
          cy={center}
          r={safeSize * 0.11}
          fill="url(#knobGrad)"
        />
        
        {/* Center knob highlight */}
        <Circle
          cx={center - safeSize * 0.03}
          cy={center - safeSize * 0.03}
          r={safeSize * 0.04}
          fill="rgba(255,255,255,0.5)"
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

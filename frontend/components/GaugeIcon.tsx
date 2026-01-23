import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, Easing } from 'react-native';
import Svg, { Path, Circle, G } from 'react-native-svg';

interface GaugeIconProps {
  score: number; // 0-100
  size?: number;
}

const AnimatedG = Animated.createAnimatedComponent(G);

export function GaugeIcon({ score, size = 40 }: GaugeIconProps) {
  const oscillation = useRef(new Animated.Value(0)).current;
  const needleAngle = useRef(new Animated.Value(0)).current;
  
  // Convert score (0-100) to angle (-135 to 135 degrees, where 0 is center/top)
  // Score 0 = -135° (left/red), Score 50 = 0° (center/gray), Score 100 = 135° (right/green)
  const scoreToAngle = (s: number) => {
    // Clamp score between 0 and 100
    const clampedScore = Math.max(0, Math.min(100, s));
    // Map 0-100 to -135 to +135 degrees
    return (clampedScore - 50) * 2.7;
  };

  useEffect(() => {
    // Animate needle to target position
    Animated.timing(needleAngle, {
      toValue: scoreToAngle(score),
      duration: 800,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();

    // Start oscillation animation for "live" feel
    const oscillate = Animated.loop(
      Animated.sequence([
        Animated.timing(oscillation, {
          toValue: 1,
          duration: 1500 + Math.random() * 500,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(oscillation, {
          toValue: -1,
          duration: 1500 + Math.random() * 500,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ])
    );
    oscillate.start();

    return () => oscillate.stop();
  }, [score]);

  // Combine target angle with small oscillation
  const rotation = Animated.add(
    needleAngle,
    oscillation.interpolate({
      inputRange: [-1, 1],
      outputRange: [-2, 2], // Small 2-degree oscillation
    })
  );

  const rotateStyle = {
    transform: [
      {
        rotate: rotation.interpolate({
          inputRange: [-180, 180],
          outputRange: ['-180deg', '180deg'],
        }),
      },
    ],
  };

  const center = size / 2;
  const radius = size * 0.42;
  const strokeWidth = size * 0.12;

  // Create arc paths for each segment
  const createArc = (startAngle: number, endAngle: number) => {
    const start = polarToCartesian(center, center, radius, startAngle);
    const end = polarToCartesian(center, center, radius, endAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? 0 : 1;
    return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
  };

  const polarToCartesian = (cx: number, cy: number, r: number, angle: number) => {
    const rad = ((angle - 90) * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    };
  };

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Red segment (left) - from -135 to -45 degrees */}
        <Path
          d={createArc(-135, -45)}
          stroke="#E53935"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
        />
        {/* Gray segment (center) - from -45 to 45 degrees */}
        <Path
          d={createArc(-45, 45)}
          stroke="#78909C"
          strokeWidth={strokeWidth}
          strokeLinecap="butt"
          fill="none"
        />
        {/* Green segment (right) - from 45 to 135 degrees */}
        <Path
          d={createArc(45, 135)}
          stroke="#00E676"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
        />
        {/* Center circle */}
        <Circle
          cx={center}
          cy={center}
          r={size * 0.08}
          fill="#FFFFFF"
        />
      </Svg>
      
      {/* Animated needle overlay */}
      <Animated.View 
        style={[
          styles.needleContainer, 
          { width: size, height: size },
          rotateStyle
        ]}
      >
        <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <G>
            {/* Needle pointing up (will be rotated) */}
            <Path
              d={`M ${center - size * 0.025} ${center} 
                  L ${center} ${center - radius + strokeWidth / 2} 
                  L ${center + size * 0.025} ${center} Z`}
              fill="#FFFFFF"
            />
          </G>
        </Svg>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'relative',
  },
  needleContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
  },
});

export default GaugeIcon;

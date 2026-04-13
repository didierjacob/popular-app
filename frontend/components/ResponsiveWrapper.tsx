import React from 'react';
import { View, StyleSheet, useWindowDimensions } from 'react-native';

/**
 * Responsive content wrapper that limits width on iPad/tablets
 * Centers content with maxWidth on large screens, full width on phones
 */
export const ResponsiveWrapper: React.FC<{ children: React.ReactNode; style?: any }> = ({ children, style }) => {
  const { width } = useWindowDimensions();
  const isTablet = width > 768;

  return (
    <View style={[styles.wrapper, isTablet && styles.tabletWrapper, style]}>
      {children}
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: {
    flex: 1,
    width: '100%',
  },
  tabletWrapper: {
    maxWidth: 600,
    alignSelf: 'center',
    width: '100%',
  },
});

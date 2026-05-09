import React, { useState, useEffect, useCallback } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  RefreshControl,
  Linking,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CreditsService, type OutsiderData } from '../services/creditsService';
import { useTranslation } from 'react-i18next';
import AsyncStorage from '@react-native-async-storage/async-storage';

const PALETTE = {
  bg: '#0F2F22',
  card: '#162E23',
  cardBorder: '#1E4433',
  text: '#EAEAEA',
  subtext: '#8FA89B',
  accent: '#009B4D',
  accent2: '#2ECC71',
  gold: '#FFD700',
  heart: '#FF4757',
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

// ---- Outsider Feed Card with Heart + Social ----
function OutsiderFeedCard({ outsider, onLike }: { outsider: OutsiderData; onLike: (id: string) => void }) {
  const router = useRouter();
  const { t } = useTranslation();
  const isGolden = outsider.tier === 'golden_booster';

  const initials = outsider.avatar_initials ||
    outsider.name.split(' ').map((w: string) => w[0]).join('').toUpperCase().slice(0, 2);

  const hoursLeft = outsider.hours_remaining || 0;
  const d = Math.floor(hoursLeft / 24);
  const h = Math.floor(hoursLeft % 24);
  const timeStr = d > 0 ? `${d}d ${h}h` : `${h}h`;

  return (
    <View style={[styles.feedCard, isGolden && styles.feedCardGolden]}>
      {/* Header row: avatar + name + tier */}
      <TouchableOpacity
        style={styles.feedCardHeader}
        onPress={() => router.push({ pathname: '/person', params: { id: outsider.id, name: outsider.name } })}
        activeOpacity={0.7}
      >
        <View style={[
          styles.feedAvatar,
          { backgroundColor: outsider.avatar_color || '#1C3A2C' },
          isGolden && { borderColor: PALETTE.gold, borderWidth: 2 },
        ]}>
          <Text style={styles.feedAvatarText}>{initials}</Text>
        </View>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={[styles.feedName, isGolden && { color: PALETTE.gold }]} numberOfLines={1}>
            {outsider.name}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 3, flexWrap: 'wrap' }}>
            <View style={[styles.tierBadge, isGolden && { backgroundColor: PALETTE.gold + '22', borderColor: PALETTE.gold + '44' }]}>
              <Ionicons name={isGolden ? 'trophy' : 'rocket'} size={11} color={isGolden ? PALETTE.gold : PALETTE.accent2} />
              <Text style={[styles.tierText, isGolden && { color: PALETTE.gold }]}>{outsider.tier_name}</Text>
            </View>
            {hoursLeft > 0 && (
              <View style={styles.timeBadge}>
                <Ionicons name="time-outline" size={10} color={PALETTE.accent2} />
                <Text style={styles.timeText}>{timeStr}</Text>
              </View>
            )}
          </View>
        </View>
      </TouchableOpacity>

      {/* Action row: Heart + Social links */}
      <View style={styles.feedActions}>
        {/* Heart (Like) Button */}
        <TouchableOpacity
          style={styles.heartButton}
          onPress={() => onLike(outsider.id)}
          activeOpacity={0.7}
        >
          <Ionicons name="heart" size={22} color={PALETTE.heart} />
          <Text style={styles.heartText}>{outsider.likes || 0}</Text>
        </TouchableOpacity>

        {/* Social Links */}
        <View style={styles.socialRow}>
          {outsider.social_links?.instagram && (
            <TouchableOpacity
              style={[styles.socialBtn, { backgroundColor: '#E1306C' }]}
              onPress={() => {
                const u = outsider.social_links.instagram?.replace('@', '') || '';
                Linking.openURL(`https://instagram.com/${u}`).catch(() => {});
              }}
              activeOpacity={0.7}
            >
              <Ionicons name="logo-instagram" size={16} color="#fff" />
            </TouchableOpacity>
          )}
          {outsider.social_links?.tiktok && (
            <TouchableOpacity
              style={[styles.socialBtn, { backgroundColor: '#111' }]}
              onPress={() => {
                const u = outsider.social_links.tiktok?.replace('@', '') || '';
                Linking.openURL(`https://tiktok.com/@${u}`).catch(() => {});
              }}
              activeOpacity={0.7}
            >
              <Ionicons name="logo-tiktok" size={16} color="#fff" />
            </TouchableOpacity>
          )}
          {outsider.social_links?.x && (
            <TouchableOpacity
              style={[styles.socialBtn, { backgroundColor: '#000' }]}
              onPress={() => {
                const u = outsider.social_links.x?.replace('@', '') || '';
                Linking.openURL(`https://x.com/${u}`).catch(() => {});
              }}
              activeOpacity={0.7}
            >
              <Ionicons name="logo-twitter" size={16} color="#fff" />
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
}

// ---- Booster Promo Card (injected every 10 items) ----
function BoosterPromoCard({ variant }: { variant: number }) {
  const router = useRouter();
  const { t } = useTranslation();

  const promos = [
    { icon: 'rocket' as const, title: t('premium.title'), sub: t('premium.subtitle'), color: PALETTE.accent },
    { icon: 'trophy' as const, title: 'Golden Booster', sub: 'Top ranking position', color: PALETTE.gold },
    { icon: 'star' as const, title: 'Super Booster', sub: 'Accelerate your rise', color: '#9B59B6' },
  ];
  const promo = promos[variant % promos.length];

  return (
    <TouchableOpacity
      style={[styles.promoCard, { borderColor: promo.color }]}
      onPress={() => router.push('/premium')}
      activeOpacity={0.7}
    >
      <View style={[styles.promoIcon, { backgroundColor: promo.color + '22' }]}>
        <Ionicons name={promo.icon} size={28} color={promo.color} />
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={[styles.promoTitle, { color: promo.color }]}>{promo.title}</Text>
        <Text style={styles.promoSub}>{promo.sub}</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={promo.color} />
    </TouchableOpacity>
  );
}

// ---- Main Outsiders Page ----
export default function OutsidersScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const [outsiders, setOutsiders] = useState<OutsiderData[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadOutsiders = useCallback(async () => {
    try {
      const data = await CreditsService.getOutsiders();
      // Merge golden (top position) and regular into a single feed
      const all = [...(data.golden || []), ...(data.regular || [])];
      setOutsiders(all);
    } catch (err) {
      console.error('Failed to load outsiders:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadOutsiders();
  }, [loadOutsiders]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadOutsiders();
  }, [loadOutsiders]);

  // BLOC 2.4: Like an outsider directly from the card
  const handleLike = useCallback(async (personId: string) => {
    try {
      const userId = await AsyncStorage.getItem('popular_user_id') || `user_temp_${Date.now()}`;
      const res = await fetch(API(`/people/${personId}/vote`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, delta: 1 }),
      });

      if (res.ok) {
        // Optimistic update
        setOutsiders(prev =>
          prev.map(o => o.id === personId ? { ...o, likes: (o.likes || 0) + 1 } : o)
        );
      } else {
        const data = await res.json();
        if (data?.detail) {
          Alert.alert(
            t('person.alreadyVotedTitle'),
            typeof data.detail === 'string' ? data.detail : t('person.alreadyVotedMessage', { name: '' })
          );
        }
      }
    } catch (err) {
      console.error('Vote error:', err);
    }
  }, [t]);

  // Build feed: outsider cards + promo cards every 10 items
  const buildFeed = () => {
    const items: { type: 'outsider' | 'promo'; data?: OutsiderData; variant?: number }[] = [];
    let promoCount = 0;

    outsiders.forEach((o, i) => {
      items.push({ type: 'outsider', data: o });
      if ((i + 1) % 10 === 0) {
        items.push({ type: 'promo', variant: promoCount });
        promoCount++;
      }
    });

    return items;
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color={PALETTE.accent} style={{ flex: 1 }} />
      </SafeAreaView>
    );
  }

  const feed = buildFeed();

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent} />}
      >
        {/* Header */}
        <View style={styles.headerSection}>
          <Text style={styles.headerTitle}>{t('tabs.outsiders')}</Text>
          <Text style={styles.headerSub}>
            {t('home.outsiderSectionTitle') || 'Discover emerging talents'}
          </Text>
        </View>

        {/* Feed */}
        {feed.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="people-outline" size={48} color={PALETTE.subtext} />
            <Text style={styles.emptyText}>No Outsiders yet</Text>
            <TouchableOpacity
              style={styles.boostCta}
              onPress={() => router.push('/premium')}
              activeOpacity={0.7}
            >
              <Text style={styles.boostCtaText}>{t('premium.title')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          feed.map((item, index) => {
            if (item.type === 'promo') {
              return <BoosterPromoCard key={`promo-${index}`} variant={item.variant || 0} />;
            }
            return (
              <OutsiderFeedCard
                key={item.data!.id}
                outsider={item.data!}
                onLike={handleLike}
              />
            );
          })
        )}

        {/* Bottom CTA */}
        {outsiders.length > 0 && (
          <TouchableOpacity
            style={styles.bottomCta}
            onPress={() => router.push('/premium')}
            activeOpacity={0.7}
          >
            <Ionicons name="rocket" size={20} color={PALETTE.accent} />
            <Text style={styles.bottomCtaText}>{t('premium.title')}</Text>
          </TouchableOpacity>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  scrollContent: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  headerSection: {
    marginBottom: 20,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '800',
    color: PALETTE.text,
    marginBottom: 4,
  },
  headerSub: {
    fontSize: 14,
    color: PALETTE.subtext,
    lineHeight: 20,
  },
  // Feed Card
  feedCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: PALETTE.cardBorder,
    padding: 16,
    marginBottom: 12,
  },
  feedCardGolden: {
    borderColor: PALETTE.gold + '66',
    backgroundColor: '#1C3524',
  },
  feedCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  feedAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  feedAvatarText: {
    color: '#FFF',
    fontWeight: '700',
    fontSize: 16,
  },
  feedName: {
    fontSize: 17,
    fontWeight: '700',
    color: PALETTE.text,
  },
  feedMeta: {
    fontSize: 13,
    color: PALETTE.subtext,
    marginTop: 2,
  },
  tierBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(46,204,113,0.12)',
    borderRadius: 10,
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: 'rgba(46,204,113,0.25)',
    marginRight: 6,
  },
  tierText: {
    color: PALETTE.accent2,
    fontSize: 11,
    fontWeight: '600',
    marginLeft: 3,
  },
  timeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0,155,77,0.12)',
    borderRadius: 10,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  timeText: {
    color: PALETTE.accent2,
    fontSize: 10,
    fontWeight: '600',
    marginLeft: 3,
  },
  feedActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: PALETTE.cardBorder,
  },
  heartButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 71, 87, 0.12)',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 24,
    minWidth: 80,
    justifyContent: 'center',
  },
  heartText: {
    color: '#FF4757',
    fontWeight: '700',
    fontSize: 15,
    marginLeft: 6,
  },
  socialRow: {
    flexDirection: 'row',
    gap: 8,
  },
  socialBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
  },
  // Promo Card
  promoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: PALETTE.card,
    borderRadius: 16,
    borderWidth: 1.5,
    padding: 16,
    marginBottom: 12,
    marginVertical: 4,
  },
  promoIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  promoTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  promoSub: {
    fontSize: 13,
    color: PALETTE.subtext,
    marginTop: 2,
  },
  // Empty State
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyText: {
    fontSize: 16,
    color: PALETTE.subtext,
    marginTop: 12,
    marginBottom: 20,
  },
  boostCta: {
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 24,
  },
  boostCtaText: {
    color: '#FFF',
    fontWeight: '700',
    fontSize: 15,
  },
  // Bottom CTA
  bottomCta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: PALETTE.card,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: PALETTE.accent + '44',
    padding: 16,
    marginTop: 8,
    gap: 8,
  },
  bottomCtaText: {
    color: PALETTE.accent,
    fontWeight: '700',
    fontSize: 15,
  },
});

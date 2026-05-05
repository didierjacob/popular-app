import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Animated,
  Platform,
  SafeAreaView,
  StatusBar,
  Dimensions,
  RefreshControl,
  Share,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';

// ─── Design System ───
const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  green: "#009B4D",
  border: "#2E6148",
  gold: "#FFD700",
  darkBg: "#0A1F16",
  winGreen: "#00E676",
  lossRed: "#FF5252",
  timerOrange: "#FF9800",
  legendPurple: "#BB86FC",
};

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string): string => {
  const prefix = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}/api${prefix}`;
};

// ─── Types ───
interface DailyRunTarget {
  id: string;
  name: string;
  popularoo_index: number;
  category: string;
  avatar_letter: string;
  avatar_color: string;
  tier: string;
  victory_condition: string;
  reward: string;
  index_gap: number;
}

interface ActiveDailyRun {
  run_id: string;
  outsider_name: string;
  outsider_index: number;
  target_name: string;
  target_index: number;
  tier: string;
  victory_condition: string;
  reward: string;
  started_at: string;
  ends_at: string;
  current_momentum_outsider: number;
  current_momentum_target: number;
  is_winning: boolean;
}

interface DailyRunHistory {
  run_id: string;
  target_name: string;
  tier: string;
  result: string;
  outsider_momentum: number;
  target_momentum: number;
  completed_at: string;
}

interface RunStatus {
  total_slots: number;
  used_slots: number;
  available_slots: number;
  cooldown_remaining_seconds: number;
  tier_name: string;
}

// ─── Mock Data (Static mockup — will be replaced by API calls) ───
const MOCK_STATUS: RunStatus = {
  total_slots: 7,
  used_slots: 2,
  available_slots: 5,
  cooldown_remaining_seconds: 0,
  tier_name: "Golden Booster",
};

const MOCK_ACTIVE_RUN: ActiveDailyRun = {
  run_id: "dr_active_001",
  outsider_name: "Didier",
  outsider_index: 42.8,
  target_name: "Cristiano Ronaldo",
  target_index: 78.5,
  tier: "legendary",
  victory_condition: "Beat Cristiano Ronaldo's 24h momentum",
  reward: "+15 Popularoo Index bonus",
  started_at: new Date(Date.now() - 8 * 3600000).toISOString(),
  ends_at: new Date(Date.now() + 16 * 3600000).toISOString(),
  current_momentum_outsider: 156,
  current_momentum_target: 134,
  is_winning: true,
};

const MOCK_SUGGESTED_TARGETS: DailyRunTarget[] = [
  {
    id: "t1", name: "Emma Watson", popularoo_index: 56.2, category: "Cinema",
    avatar_letter: "E", avatar_color: "#9C27B0", tier: "underdog",
    victory_condition: "Beat Emma Watson's 24h momentum", reward: "+10 Index bonus",
    index_gap: 13.4,
  },
  {
    id: "t2", name: "Mbappé", popularoo_index: 71.8, category: "Sport",
    avatar_letter: "M", avatar_color: "#2196F3", tier: "legendary",
    victory_condition: "Beat Mbappé's 24h momentum", reward: "+15 Index bonus",
    index_gap: 29.0,
  },
  {
    id: "t3", name: "Zendaya", popularoo_index: 48.9, category: "Cinema",
    avatar_letter: "Z", avatar_color: "#E91E63", tier: "standard",
    victory_condition: "Beat Zendaya's 24h momentum", reward: "+5 Index bonus",
    index_gap: 6.1,
  },
  {
    id: "t4", name: "Elon Musk", popularoo_index: 85.3, category: "Business",
    avatar_letter: "E", avatar_color: "#607D8B", tier: "legendary",
    victory_condition: "Beat Elon Musk's 24h momentum", reward: "+15 Index bonus",
    index_gap: 42.5,
  },
];

const MOCK_HISTORY: DailyRunHistory[] = [
  {
    run_id: "dr_h1", target_name: "Taylor Swift", tier: "underdog", result: "win",
    outsider_momentum: 89, target_momentum: 72, completed_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    run_id: "dr_h2", target_name: "LeBron James", tier: "legendary", result: "loss",
    outsider_momentum: 45, target_momentum: 112, completed_at: new Date(Date.now() - 172800000).toISOString(),
  },
  {
    run_id: "dr_h3", target_name: "Rihanna", tier: "standard", result: "win",
    outsider_momentum: 67, target_momentum: 54, completed_at: new Date(Date.now() - 259200000).toISOString(),
  },
];

const MOCK_STRIKES = {
  active_strikes: 2,
  current_label: "On Fire",
  next_label: "Trending",
  progress_to_next: 0.65,
  strike_types: [
    { type: "Strike Flash", description: "5 Superlikes in < 30 min", active: true },
    { type: "Strike Diversité", description: "10 users in 24h", active: true },
    { type: "Strike Série", description: "3 consecutive in 1 hour", active: false },
  ],
};

// ─── Helper functions ───
const getTierColor = (tier: string) => {
  switch (tier) {
    case 'legendary': return PALETTE.gold;
    case 'underdog': return PALETTE.legendPurple;
    case 'standard': return PALETTE.green;
    default: return PALETTE.subtext;
  }
};

const getTierLabel = (tier: string) => {
  switch (tier) {
    case 'legendary': return 'Legendary Strike';
    case 'underdog': return 'Underdog Win';
    case 'standard': return 'Standard Win';
    default: return tier;
  }
};

const getStrikeLabelColor = (label: string) => {
  switch (label) {
    case 'Heating Up': return '#FF9800';
    case 'On Fire': return '#FF5722';
    case 'Trending': return '#E91E63';
    case 'Going Viral': return '#9C27B0';
    case 'Legend Mode': return PALETTE.gold;
    default: return PALETTE.subtext;
  }
};

const formatCountdown = (endsAt: string): string => {
  const diff = new Date(endsAt).getTime() - Date.now();
  if (diff <= 0) return '00:00:00';
  const hrs = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  const secs = Math.floor((diff % 60000) / 1000);
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

const formatTimeAgo = (dateStr: string): string => {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};

// ─── Components ───

const StrikeIndicator = ({ strikes }: { strikes: typeof MOCK_STRIKES }) => {
  const labelColor = getStrikeLabelColor(strikes.current_label);
  return (
    <View style={styles.strikeCard}>
      <View style={styles.strikeHeader}>
        <Ionicons name="flame" size={20} color={labelColor} />
        <Text style={[styles.strikeLabel, { color: labelColor }]}>
          {strikes.current_label}
        </Text>
        <Text style={styles.strikeCount}>
          {strikes.active_strikes} Active Strikes
        </Text>
      </View>
      {/* Progress bar to next label */}
      <View style={styles.strikeProgressContainer}>
        <View style={styles.strikeProgressBg}>
          <View
            style={[
              styles.strikeProgressFill,
              { width: `${strikes.progress_to_next * 100}%`, backgroundColor: labelColor },
            ]}
          />
        </View>
        <Text style={styles.strikeNextLabel}>
          Next: {strikes.next_label}
        </Text>
      </View>
      {/* Strike types */}
      <View style={styles.strikeTypes}>
        {strikes.strike_types.map((s, i) => (
          <View key={i} style={styles.strikeTypeRow}>
            <Ionicons
              name={s.active ? "checkmark-circle" : "lock-closed"}
              size={14}
              color={s.active ? PALETTE.winGreen : PALETTE.subtext}
              style={!s.active ? { opacity: 0.5 } : undefined}
            />
            <Text style={[styles.strikeTypeName, s.active && { color: PALETTE.text }]}>
              {s.type}
            </Text>
            <Text style={styles.strikeTypeDesc}>{s.description}</Text>
          </View>
        ))}
      </View>
    </View>
  );
};

const SlotsIndicator = ({ status }: { status: RunStatus }) => (
  <View style={styles.slotsCard}>
    <Text style={styles.slotsTitle}>Daily Run Slots</Text>
    <View style={styles.slotsRow}>
      {Array.from({ length: status.total_slots }, (_, i) => (
        <View
          key={i}
          style={[
            styles.slotDot,
            i < status.used_slots
              ? { backgroundColor: PALETTE.subtext }
              : { backgroundColor: PALETTE.winGreen },
          ]}
        />
      ))}
    </View>
    <Text style={styles.slotsText}>
      {status.available_slots} / {status.total_slots} remaining
      {status.tier_name ? ` · ${status.tier_name}` : ''}
    </Text>
  </View>
);

const MomentumBar = ({
  label, value, maxValue, color, isLeading,
}: {
  label: string; value: number; maxValue: number; color: string; isLeading: boolean;
}) => {
  const pct = maxValue > 0 ? Math.min((value / maxValue) * 100, 100) : 0;
  return (
    <View style={styles.momentumBarContainer}>
      <View style={styles.momentumLabelRow}>
        <Text style={[styles.momentumLabel, isLeading && { color }]}>{label}</Text>
        <Text style={[styles.momentumValue, isLeading && { color }]}>{value}</Text>
      </View>
      <View style={styles.momentumBarBg}>
        <View style={[styles.momentumBarFill, { width: `${pct}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
};

const ActiveRunCard = ({
  run, countdown,
}: { run: ActiveDailyRun; countdown: string }) => {
  const tierColor = getTierColor(run.tier);
  const maxMomentum = Math.max(run.current_momentum_outsider, run.current_momentum_target, 1);

  return (
    <View style={[styles.activeRunCard, { borderColor: tierColor }]}>
      {/* Header */}
      <View style={styles.activeRunHeader}>
        <View style={[styles.tierBadge, { backgroundColor: tierColor + '20', borderColor: tierColor }]}>
          <Text style={[styles.tierBadgeText, { color: tierColor }]}>
            {getTierLabel(run.tier)}
          </Text>
        </View>
        <View style={styles.timerContainer}>
          <Text style={styles.timerLabel}>Time remaining</Text>
          <View style={styles.timerRow}>
            <Ionicons name="time-outline" size={16} color={PALETTE.timerOrange} />
            <Text style={styles.timerText}>{countdown}</Text>
          </View>
        </View>
      </View>

      {/* VS comparison (Bloomberg style) */}
      <View style={styles.vsContainer}>
        {/* Your side */}
        <View style={styles.vsSide}>
          <View style={[styles.vsAvatar, { backgroundColor: PALETTE.green }]}>
            <Text style={styles.vsAvatarText}>{run.outsider_name[0]}</Text>
          </View>
          <Text style={styles.vsName} numberOfLines={1}>{run.outsider_name}</Text>
          <Text style={[styles.vsIndex, { color: run.is_winning ? PALETTE.winGreen : PALETTE.text }]}>
            {run.outsider_index.toFixed(1)}
          </Text>
          <Text style={styles.vsIndexLabel}>Popularoo Index</Text>
        </View>

        {/* VS badge */}
        <View style={styles.vsBadge}>
          <Text style={styles.vsText}>VS</Text>
          {run.is_winning && (
            <View style={styles.winningIndicator}>
              <Ionicons name="caret-up" size={18} color={PALETTE.winGreen} />
              <Text style={styles.winningText}>LEADING</Text>
            </View>
          )}
          {!run.is_winning && (
            <View style={styles.winningIndicator}>
              <Ionicons name="caret-down" size={18} color={PALETTE.lossRed} />
              <Text style={[styles.winningText, { color: PALETTE.lossRed }]}>BEHIND</Text>
            </View>
          )}
        </View>

        {/* Target side */}
        <View style={styles.vsSide}>
          <View style={[styles.vsAvatar, { backgroundColor: PALETTE.accent2 }]}>
            <Text style={styles.vsAvatarText}>{run.target_name[0]}</Text>
          </View>
          <Text style={styles.vsName} numberOfLines={1}>{run.target_name}</Text>
          <Text style={styles.vsIndex}>{run.target_index.toFixed(1)}</Text>
          <Text style={styles.vsIndexLabel}>Popularoo Index</Text>
        </View>
      </View>

      {/* Momentum comparison */}
      <View style={styles.momentumSection}>
        <Text style={styles.momentumTitle}>24h Momentum</Text>
        <MomentumBar
          label={run.outsider_name}
          value={run.current_momentum_outsider}
          maxValue={maxMomentum}
          color={run.is_winning ? PALETTE.winGreen : PALETTE.lossRed}
          isLeading={run.is_winning}
        />
        <MomentumBar
          label={run.target_name}
          value={run.current_momentum_target}
          maxValue={maxMomentum}
          color={!run.is_winning ? PALETTE.winGreen : PALETTE.subtext}
          isLeading={!run.is_winning}
        />
      </View>

      {/* Reward */}
      <View style={styles.rewardRow}>
        <Ionicons name="trophy" size={16} color={tierColor} />
        <Text style={[styles.rewardText, { color: tierColor }]}>{run.reward}</Text>
      </View>
    </View>
  );
};

const TargetCard = ({
  target, onSelect,
}: { target: DailyRunTarget; onSelect: () => void }) => {
  const tierColor = getTierColor(target.tier);
  return (
    <TouchableOpacity style={styles.targetCard} activeOpacity={0.7} onPress={onSelect}>
      <View style={[styles.targetAvatar, { backgroundColor: target.avatar_color }]}>
        <Text style={styles.targetAvatarText}>{target.avatar_letter}</Text>
      </View>
      <View style={styles.targetInfo}>
        <Text style={styles.targetName}>{target.name}</Text>
        <Text style={styles.targetCategory}>
          {target.category} · Popularoo Index {target.popularoo_index.toFixed(1)}
        </Text>
      </View>
      <View style={styles.targetRight}>
        <View style={[styles.targetTierBadge, { backgroundColor: tierColor + '20' }]}>
          <Text style={[styles.targetTierText, { color: tierColor }]}>
            {getTierLabel(target.tier)}
          </Text>
        </View>
        <Text style={[styles.targetGap, { color: tierColor }]}>
          Gap: {target.index_gap.toFixed(1)}
        </Text>
      </View>
    </TouchableOpacity>
  );
};

const HistoryCard = ({ run }: { run: DailyRunHistory }) => {
  const isWin = run.result === 'win';
  const tierColor = getTierColor(run.tier);
  return (
    <View style={styles.historyCard}>
      <View style={[styles.historyResult, { backgroundColor: isWin ? PALETTE.winGreen + '20' : PALETTE.lossRed + '20' }]}>
        <Ionicons
          name={isWin ? "trophy" : "close-circle"}
          size={20}
          color={isWin ? PALETTE.winGreen : PALETTE.lossRed}
        />
      </View>
      <View style={styles.historyInfo}>
        <Text style={styles.historyTarget}>vs {run.target_name}</Text>
        <View style={styles.historyMeta}>
          <View style={[styles.historyTierBadge, { backgroundColor: tierColor + '15' }]}>
            <Text style={[styles.historyTierText, { color: tierColor }]}>{getTierLabel(run.tier)}</Text>
          </View>
          <Text style={styles.historyTime}>{formatTimeAgo(run.completed_at)}</Text>
        </View>
      </View>
      <View style={styles.historyMomentum}>
        <Text style={[styles.historyScore, { color: isWin ? PALETTE.winGreen : PALETTE.lossRed }]}>
          {run.outsider_momentum}
        </Text>
        <Text style={styles.historyScoreSep}>—</Text>
        <Text style={styles.historyScoreTarget}>{run.target_momentum}</Text>
      </View>
    </View>
  );
};

// ─── Main Screen ───
export default function DailyRunScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ personId?: string; userId?: string }>();
  
  const [tab, setTab] = useState<'run' | 'targets' | 'history'>('run');
  const [countdown, setCountdown] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  // Mock state — will be replaced by real API data
  const [activeRun] = useState<ActiveDailyRun | null>(MOCK_ACTIVE_RUN);
  const [status] = useState<RunStatus>(MOCK_STATUS);
  const [strikes] = useState(MOCK_STRIKES);
  const [targets] = useState(MOCK_SUGGESTED_TARGETS);
  const [history] = useState(MOCK_HISTORY);

  // Countdown timer
  useEffect(() => {
    if (!activeRun) return;
    const interval = setInterval(() => {
      setCountdown(formatCountdown(activeRun.ends_at));
    }, 1000);
    setCountdown(formatCountdown(activeRun.ends_at));
    return () => clearInterval(interval);
  }, [activeRun]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 1000);
  }, []);

  const handleShare = async () => {
    try {
      await Share.share({
        message: activeRun
          ? `I'm challenging ${activeRun.target_name} in a Daily Run on Popularoo! Currently ${activeRun.is_winning ? 'LEADING' : 'behind'} — momentum ${activeRun.current_momentum_outsider} vs ${activeRun.current_momentum_target} 🔥`
          : 'Challenge celebrities on Popularoo — the stock market of fame!',
      });
    } catch (e) { /* ignore */ }
  };

  const filteredTargets = searchQuery
    ? targets.filter(t => t.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : targets;

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" />
      
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={PALETTE.text} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>Daily Run</Text>
          <Text style={styles.headerSubtitle}>24h Momentum Challenge</Text>
        </View>
      </View>

      {/* Tab bar */}
      <View style={styles.tabBar}>
        {[
          { key: 'run' as const, label: 'Active', icon: 'flash' as const },
          { key: 'targets' as const, label: 'Challenge', icon: 'search' as const },
          { key: 'history' as const, label: 'History', icon: 'time' as const },
        ].map(t => (
          <TouchableOpacity
            key={t.key}
            style={[styles.tab, tab === t.key && styles.tabActive]}
            onPress={() => setTab(t.key)}
          >
            <Ionicons
              name={t.icon}
              size={18}
              color={tab === t.key ? PALETTE.winGreen : PALETTE.subtext}
            />
            <Text style={[styles.tabLabel, tab === t.key && styles.tabLabelActive]}>
              {t.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentInner}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
        showsVerticalScrollIndicator={false}
      >
        {/* ─── TAB: Active Run ─── */}
        {tab === 'run' && (
          <>
            {/* Slots */}
            <SlotsIndicator status={status} />

            {/* Strikes */}
            <StrikeIndicator strikes={strikes} />

            {/* Active run or empty state */}
            {activeRun ? (
              <ActiveRunCard run={activeRun} countdown={countdown} />
            ) : (
              <View style={styles.emptyState}>
                <Ionicons name="rocket-outline" size={48} color={PALETTE.subtext} />
                <Text style={styles.emptyTitle}>No Active Daily Run</Text>
                <Text style={styles.emptySubtitle}>
                  Choose a target to start your 24h momentum challenge
                </Text>
                <TouchableOpacity
                  style={styles.startButton}
                  onPress={() => setTab('targets')}
                >
                  <Text style={styles.startButtonText}>Start a Daily Run</Text>
                </TouchableOpacity>
              </View>
            )}
          </>
        )}

        {/* ─── TAB: Target Selection ─── */}
        {tab === 'targets' && (
          <>
            {/* Search (Choose Anyone) */}
            <View style={styles.searchContainer}>
              <Ionicons name="search" size={18} color={PALETTE.subtext} />
              <TextInput
                style={styles.searchInput}
                placeholder="Choose Anyone..."
                placeholderTextColor={PALETTE.subtext}
                value={searchQuery}
                onChangeText={setSearchQuery}
              />
              {searchQuery.length > 0 && (
                <TouchableOpacity onPress={() => setSearchQuery('')}>
                  <Ionicons name="close-circle" size={18} color={PALETTE.subtext} />
                </TouchableOpacity>
              )}
            </View>

            <Text style={styles.sectionTitle}>
              {searchQuery ? 'Search Results' : 'Suggested Targets'}
            </Text>
            <Text style={styles.sectionSubtitle}>
              Personalities with similar Popularoo Index to yours
            </Text>

            {filteredTargets.map(target => (
              <TargetCard
                key={target.id}
                target={target}
                onSelect={() => {
                  // Will activate Daily Run via API
                }}
              />
            ))}

            {/* Tier legend */}
            <View style={styles.tierLegend}>
              <Text style={styles.tierLegendTitle}>Victory Tiers</Text>
              {[
                { tier: 'standard', gap: '< 20 pts', bonus: '+5 Index' },
                { tier: 'underdog', gap: '20–50 pts', bonus: '+10 Index' },
                { tier: 'legendary', gap: '> 50 pts', bonus: '+15 Index' },
              ].map(item => (
                <View key={item.tier} style={styles.tierLegendRow}>
                  <View style={[styles.tierLegendDot, { backgroundColor: getTierColor(item.tier) }]} />
                  <Text style={[styles.tierLegendLabel, { color: getTierColor(item.tier) }]}>
                    {getTierLabel(item.tier)}
                  </Text>
                  <Text style={styles.tierLegendGap}>{item.gap}</Text>
                  <Text style={styles.tierLegendBonus}>{item.bonus}</Text>
                </View>
              ))}
            </View>
          </>
        )}

        {/* ─── TAB: History ─── */}
        {tab === 'history' && (
          <>
            <Text style={styles.sectionTitle}>Recent Daily Runs</Text>
            {history.length > 0 ? (
              history.map(run => (
                <HistoryCard key={run.run_id} run={run} />
              ))
            ) : (
              <View style={styles.emptyState}>
                <Ionicons name="time-outline" size={48} color={PALETTE.subtext} />
                <Text style={styles.emptyTitle}>No History Yet</Text>
                <Text style={styles.emptySubtitle}>
                  Complete your first Daily Run to see results here
                </Text>
              </View>
            )}

            {/* Stats summary */}
            {history.length > 0 && (
              <View style={styles.statsSummary}>
                <Text style={styles.statsSummaryTitle}>Summary</Text>
                <View style={styles.statsRow}>
                  <View style={styles.statBox}>
                    <Text style={[styles.statValue, { color: PALETTE.winGreen }]}>
                      {history.filter(h => h.result === 'win').length}
                    </Text>
                    <Text style={styles.statLabel}>Wins</Text>
                  </View>
                  <View style={styles.statBox}>
                    <Text style={[styles.statValue, { color: PALETTE.lossRed }]}>
                      {history.filter(h => h.result === 'loss').length}
                    </Text>
                    <Text style={styles.statLabel}>Losses</Text>
                  </View>
                  <View style={styles.statBox}>
                    <Text style={[styles.statValue, { color: PALETTE.gold }]}>
                      {history.filter(h => h.tier === 'legendary' && h.result === 'win').length}
                    </Text>
                    <Text style={styles.statLabel}>Legendaries Won</Text>
                  </View>
                  <View style={styles.statBox}>
                    <Text style={styles.statValue}>
                      {history.length > 0
                        ? Math.round((history.filter(h => h.result === 'win').length / history.length) * 100)
                        : 0}%
                    </Text>
                    <Text style={styles.statLabel}>Win Rate</Text>
                    <Text style={styles.statSubLabel}>
                      {history.filter(h => h.result === 'win').length} out of {history.length}
                    </Text>
                  </View>
                </View>
              </View>
            )}

            {/* Index Evolution (Critical 5 — extra content) */}
            {history.length > 0 && (
              <View style={styles.indexEvolutionCard}>
                <Text style={styles.indexEvolutionTitle}>Popularoo Index Evolution</Text>
                <View style={styles.indexChart}>
                  {/* Mock sparkline chart */}
                  <View style={styles.chartRow}>
                    {[42, 44, 43, 47, 49, 48, 52].map((val, idx) => (
                      <View key={idx} style={styles.chartBarWrapper}>
                        <View
                          style={[
                            styles.chartBar,
                            {
                              height: `${(val / 60) * 100}%`,
                              backgroundColor: idx === 6 ? PALETTE.winGreen : PALETTE.border,
                            },
                          ]}
                        />
                        <Text style={styles.chartLabel}>
                          {idx === 0 ? '7d' : idx === 6 ? 'Now' : ''}
                        </Text>
                      </View>
                    ))}
                  </View>
                  <View style={styles.chartLegend}>
                    <Text style={styles.chartLegendText}>+10 pts this week</Text>
                    <Ionicons name="trending-up" size={14} color={PALETTE.winGreen} />
                  </View>
                </View>
              </View>
            )}

            {/* Suggest next target CTA (Critical 5) */}
            <TouchableOpacity
              style={styles.suggestCta}
              onPress={() => setTab('targets')}
              activeOpacity={0.7}
            >
              <Ionicons name="rocket" size={20} color={PALETTE.text} />
              <View style={styles.suggestCtaContent}>
                <Text style={styles.suggestCtaTitle}>Ready for the next challenge?</Text>
                <Text style={styles.suggestCtaSubtitle}>Find your next target to beat</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </>
        )}

        {/* Bottom padding */}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ─── Styles ───
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: PALETTE.bg },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { color: PALETTE.text, fontSize: 20, fontWeight: '700' },
  headerSubtitle: { color: PALETTE.subtext, fontSize: 12, marginTop: 2 },

  // Share CTA (sticky bottom - Critical 1)
  shareCta: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#2ECC71',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    gap: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 10,
  },
  shareCtaText: { color: '#000', fontSize: 16, fontWeight: '800', letterSpacing: 0.5 },

  // Tab bar
  tabBar: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    gap: 6,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: PALETTE.winGreen },
  tabLabel: { color: PALETTE.subtext, fontSize: 13, fontWeight: '500' },
  tabLabelActive: { color: PALETTE.winGreen },

  // Content
  content: { flex: 1 },
  contentInner: { padding: 16, gap: 16 },

  // Slots
  slotsCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  slotsTitle: { color: PALETTE.text, fontSize: 14, fontWeight: '600', marginBottom: 10 },
  slotsRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  slotDot: { width: 12, height: 12, borderRadius: 6 },
  slotsText: { color: PALETTE.subtext, fontSize: 12 },

  // Strikes
  strikeCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
  },
  strikeHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  strikeLabel: { fontSize: 16, fontWeight: '700' },
  strikeCount: { color: PALETTE.subtext, fontSize: 12, marginLeft: 'auto' },
  strikeProgressContainer: { marginTop: 12 },
  strikeProgressBg: {
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.border,
    overflow: 'hidden',
  },
  strikeProgressFill: { height: '100%', borderRadius: 2 },
  strikeNextLabel: { color: PALETTE.subtext, fontSize: 11, marginTop: 4, textAlign: 'right' },
  strikeTypes: { marginTop: 12, gap: 6 },
  strikeTypeRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  strikeTypeName: { color: PALETTE.subtext, fontSize: 12, fontWeight: '600', width: 110 },
  strikeTypeDesc: { color: PALETTE.subtext, fontSize: 11 },

  // Active run
  activeRunCard: {
    backgroundColor: PALETTE.darkBg,
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
  },
  activeRunHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  tierBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
  },
  tierBadgeText: { fontSize: 12, fontWeight: '700' },
  timerContainer: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  timerText: { color: PALETTE.timerOrange, fontSize: 18, fontWeight: '700', fontVariant: ['tabular-nums'] },

  // VS
  vsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  vsSide: { alignItems: 'center', flex: 1 },
  vsAvatar: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  vsAvatarText: { color: '#fff', fontSize: 22, fontWeight: '700' },
  vsName: { color: PALETTE.text, fontSize: 13, fontWeight: '600', marginTop: 8, textAlign: 'center' },
  vsIndex: { color: PALETTE.text, fontSize: 24, fontWeight: '800', marginTop: 4 },
  vsIndexLabel: { color: PALETTE.subtext, fontSize: 10, marginTop: 2 },
  vsBadge: { alignItems: 'center', paddingHorizontal: 8 },
  vsText: { color: PALETTE.subtext, fontSize: 14, fontWeight: '800', letterSpacing: 2 },
  winningIndicator: { flexDirection: 'row', alignItems: 'center', gap: 2, marginTop: 4 },
  winningText: { color: PALETTE.winGreen, fontSize: 10, fontWeight: '700' },

  // Momentum
  momentumSection: { marginBottom: 16 },
  momentumTitle: { color: PALETTE.subtext, fontSize: 12, fontWeight: '600', marginBottom: 10 },
  momentumBarContainer: { marginBottom: 8 },
  momentumLabelRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  momentumLabel: { color: PALETTE.subtext, fontSize: 12 },
  momentumValue: { color: PALETTE.subtext, fontSize: 12, fontWeight: '700' },
  momentumBarBg: { height: 8, borderRadius: 4, backgroundColor: PALETTE.border, overflow: 'hidden' },
  momentumBarFill: { height: '100%', borderRadius: 4 },

  // Reward
  rewardRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 12, borderTopWidth: 1, borderTopColor: PALETTE.border },
  rewardText: { fontSize: 13, fontWeight: '600' },

  // Target cards
  targetCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  targetAvatar: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  targetAvatarText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  targetInfo: { flex: 1 },
  targetName: { color: PALETTE.text, fontSize: 15, fontWeight: '600' },
  targetMeta: { flexDirection: 'row', gap: 8, marginTop: 4 },
  targetCategory: { color: PALETTE.subtext, fontSize: 11 },
  targetIndex: { color: PALETTE.subtext, fontSize: 11 },
  targetRight: { alignItems: 'flex-end', gap: 4 },
  targetTierBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  targetTierText: { fontSize: 10, fontWeight: '700' },
  targetGap: { fontSize: 11 },

  // Search
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    gap: 10,
  },
  searchInput: { flex: 1, color: PALETTE.text, fontSize: 15 },

  // Sections
  sectionTitle: { color: PALETTE.text, fontSize: 17, fontWeight: '700' },
  sectionSubtitle: { color: PALETTE.subtext, fontSize: 12, marginTop: -8 },

  // Tier legend
  tierLegend: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    gap: 8,
  },
  tierLegendTitle: { color: PALETTE.text, fontSize: 14, fontWeight: '600', marginBottom: 4 },
  tierLegendRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  tierLegendDot: { width: 8, height: 8, borderRadius: 4 },
  tierLegendLabel: { fontSize: 12, fontWeight: '600', width: 110 },
  tierLegendGap: { color: PALETTE.subtext, fontSize: 11, flex: 1 },
  tierLegendBonus: { color: PALETTE.text, fontSize: 11, fontWeight: '600' },

  // History
  historyCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  historyResult: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  historyInfo: { flex: 1 },
  historyTarget: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
  historyMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  historyTierBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 },
  historyTierText: { fontSize: 10, fontWeight: '600' },
  historyTime: { color: PALETTE.subtext, fontSize: 11 },
  historyMomentum: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  historyScore: { fontSize: 16, fontWeight: '800' },
  historyScoreSep: { color: PALETTE.subtext, fontSize: 12 },
  historyScoreTarget: { color: PALETTE.subtext, fontSize: 16, fontWeight: '600' },

  // Stats summary
  statsSummary: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
  },
  statsSummaryTitle: { color: PALETTE.text, fontSize: 14, fontWeight: '600', marginBottom: 12 },
  statsRow: { flexDirection: 'row', justifyContent: 'space-around' },
  statBox: { alignItems: 'center' },
  statValue: { color: PALETTE.text, fontSize: 22, fontWeight: '800' },
  statLabel: { color: PALETTE.subtext, fontSize: 11, marginTop: 2 },

  // Empty state
  emptyState: { alignItems: 'center', paddingVertical: 40, gap: 8 },
  emptyTitle: { color: PALETTE.text, fontSize: 18, fontWeight: '700' },
  emptySubtitle: { color: PALETTE.subtext, fontSize: 13, textAlign: 'center', paddingHorizontal: 40 },
  startButton: {
    marginTop: 16,
    backgroundColor: PALETTE.winGreen,
    paddingHorizontal: 28,
    paddingVertical: 14,
    borderRadius: 24,
  },
  startButtonText: { color: '#000', fontSize: 15, fontWeight: '700' },
});

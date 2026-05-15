import React, { useState, useRef, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Animated,
  Easing,
  Modal,
  TextInput,
  Platform,
  KeyboardAvoidingView,
  Share,
  Alert,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import Constants from "expo-constants";

const API_BASE = Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL
  || process.env.EXPO_PUBLIC_BACKEND_URL
  || "https://popular-app.onrender.com";

// ===================== PALETTE — identique au reste de l'app =====================
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
  orange: "#FFA500",
};

const RANK_CONFIG = {
  legend: { emoji: "🌟", name: "Legend", color: PALETTE.gold },
  icon: { emoji: "👑", name: "Icon", color: PALETTE.orange },
  a_list: { emoji: "🥇", name: "A-List", color: PALETTE.gold },
  big_name: { emoji: "🥈", name: "Big Name", color: "#C0C0C0" },
  rising_star: { emoji: "🥉", name: "Rising Star", color: "#CD7F32" },
  none: { emoji: "🎯", name: "Challenger", color: PALETTE.subtext },
};

// ===================== MOCK DATA =====================
const MOCK_BULL_RUN = {
  active: true,
  bull_run_id: "mock_br_001",
  person_id: "mock_person_001",
  started_at: "2026-04-25T10:00:00Z",
  expires_at: "2026-05-02T10:00:00Z",
  time_remaining: { days: 4, hours: 18, total_seconds: 410400 },
  current_rank: "big_name",
  wins_count: 23,
  cumulative_wins: 23,
  pending_wins: 1,
  next_rank: { rank: "a_list", display: "🥇 A-List", wins_needed: 77, threshold: 100 },
};

const MOCK_LADDER = {
  above: [
    { id: "celeb_001", name: "Beyoncé", category: "entertainment", raw_score: 72.41, score: 75, total_votes: 510, gap: 5.07, status: "target" },
    { id: "celeb_002", name: "Tim Cook", category: "tech", raw_score: 83.33, score: 75, total_votes: 480, gap: 16.0, status: "target" },
    { id: "celeb_003", name: "Volodymyr Zelenskyy", category: "politics", raw_score: 88.24, score: 100, total_votes: 690, gap: 20.9, status: "target" },
  ],
  below: [
    { id: "celeb_004", name: "Joe Biden", category: "politics", raw_score: 55.01, score: 50, total_votes: 430, gap: 12.33, status: "out-rallied", won_at: "2026-04-27T14:22:00Z" },
    { id: "celeb_005", name: "Serena Williams", category: "sport", raw_score: 48.76, score: 50, total_votes: 320, gap: 18.58, status: "out-rallied", won_at: "2026-04-26T09:15:00Z" },
    { id: "celeb_006", name: "Jamie Dimon", category: "business", raw_score: 42.11, score: 50, total_votes: 190, gap: 25.23, status: "out-rallied", won_at: "2026-04-25T18:33:00Z" },
  ],
  user: { id: "mock_person_001", name: "Alexandre Martin", raw_score: 67.34, score: 75, total_votes: 150 },
};

// ===================== SUB-COMPONENTS =====================

function PulsingDot({ color }) {
  const pulse = useRef(new Animated.Value(0.4)).current;
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1000, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.4, duration: 1000, useNativeDriver: true }),
      ])
    ).start();
  }, []);
  return <Animated.View style={[styles.pulsingDot, { backgroundColor: color, opacity: pulse }]} />;
}

function TimerBadge({ days, hours }) {
  return (
    <View style={styles.timerBadge}>
      <Ionicons name="time-outline" size={14} color={PALETTE.green} />
      <Text style={styles.timerText}>{days}d {hours}h left</Text>
    </View>
  );
}

function RankBadge({ rank }) {
  const config = RANK_CONFIG[rank] || RANK_CONFIG.none;
  return (
    <View style={styles.rankBadge}>
      <Text style={styles.rankEmoji}>{config.emoji}</Text>
      <Text style={[styles.rankName, { color: PALETTE.gold }]}>{config.name}</Text>
    </View>
  );
}

function ProgressBar({ current, needed, nextRank }) {
  const total = current + needed;
  const pct = total > 0 ? (current / total) * 100 : 0;
  return (
    <View style={styles.progressContainer}>
      <View style={styles.progressRow}>
        <Text style={styles.progressLabel}>Next: {nextRank}</Text>
        <Text style={styles.progressCount}>{current}/{total} wins</Text>
      </View>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${Math.min(pct, 100)}%` }]} />
      </View>
    </View>
  );
}

function LadderItem({ person, index, isTarget, isClosest }) {
  const slideAnim = useRef(new Animated.Value(isTarget ? -20 : 20)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(slideAnim, { toValue: 0, duration: 350, delay: index * 80, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      Animated.timing(fadeAnim, { toValue: 1, duration: 250, delay: index * 80, useNativeDriver: true }),
    ]).start();
    if (isClosest) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(glowAnim, { toValue: 1, duration: 1200, useNativeDriver: true }),
          Animated.timing(glowAnim, { toValue: 0, duration: 1200, useNativeDriver: true }),
        ])
      ).start();
    }
  }, []);

  const statusLabel = isTarget ? "target" : "out-rallied";

  return (
    <Animated.View style={[
      styles.ladderRow,
      isTarget ? styles.ladderRowTarget : styles.ladderRowBeaten,
      isClosest && styles.ladderRowClosest,
      { transform: [{ translateY: slideAnim }], opacity: fadeAnim },
    ]}>
      {/* Closest target badge */}
      {isClosest && (
        <View style={styles.closestBadge}>
          <Ionicons name="flash" size={10} color={PALETTE.gold} />
          <Text style={styles.closestBadgeText}>Closest target</Text>
        </View>
      )}
      {/* Rank icon */}
      <View style={[styles.ladderIcon, isTarget ? styles.ladderIconTarget : styles.ladderIconBeaten, isClosest && styles.ladderIconClosest]}>
        <Ionicons name={isTarget ? "arrow-up" : "checkmark"} size={16} color={isClosest ? PALETTE.gold : isTarget ? PALETTE.accent2 : PALETTE.green} />
      </View>
      {/* Info */}
      <View style={styles.ladderInfo}>
        <Text style={[styles.ladderName, isClosest && { color: PALETTE.gold }]} numberOfLines={1} ellipsizeMode="tail">{person.name}</Text>
        <Text style={[styles.ladderGap, { color: isClosest ? PALETTE.gold : isTarget ? PALETTE.accent2 : PALETTE.green }]}>
          {isTarget ? `${Math.round(person.gap)} momentum behind` : `Out-rallied by ${Math.round(person.gap)} pts`}
        </Text>
      </View>
      {/* Score */}
      <View style={styles.ladderScoreBox}>
        <Text style={[styles.ladderScore, isClosest && { color: PALETTE.gold }]}>{Math.round(person.raw_score)}</Text>
        <Text style={styles.ladderScoreUnit}>pts</Text>
      </View>
    </Animated.View>
  );
}

function UserCard({ user, rank }) {
  const config = RANK_CONFIG[rank] || RANK_CONFIG.none;
  return (
    <View style={styles.userCard}>
      <View style={styles.userCardTop}>
        <Text style={{ fontSize: 18 }}>{config.emoji}</Text>
        <Text style={[styles.userCardRank, { color: PALETTE.gold }]}>{config.name}</Text>
      </View>
      <Text style={styles.userCardName} numberOfLines={1} ellipsizeMode="tail">{user.name}</Text>
      <View style={styles.userCardStats}>
        <View style={styles.userCardStat}>
          <Text style={styles.userCardStatNum}>{Math.round(user.raw_score)}</Text>
          <Text style={styles.userCardStatLabel}>Points</Text>
        </View>
        <View style={styles.userCardDivider} />
        <View style={styles.userCardStat}>
          <Text style={styles.userCardStatNum}>{user.total_votes.toLocaleString()}</Text>
          <Text style={styles.userCardStatLabel}>Votes</Text>
        </View>
      </View>
    </View>
  );
}

// ===================== RALLY CRY MODAL =====================

function RallyCryModal({ visible, onClose, targets }) {
  const [step, setStep] = useState(1);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [tone, setTone] = useState("fierce");
  const [message, setMessage] = useState("");

  const tones = [
    { id: "fierce", emoji: "🔥", label: "Fierce" },
    { id: "playful", emoji: "😎", label: "Playful" },
    { id: "sincere", emoji: "💚", label: "Sincere" },
    { id: "custom", emoji: "✍️", label: "Custom" },
  ];

  const resetAndClose = () => {
    setStep(1);
    setSelectedTarget(null);
    setTone("fierce");
    setMessage("");
    onClose();
  };

  const selectedTargetData = targets.find((t) => t.id === selectedTarget);

  return (
    <Modal visible={visible} animationType="slide" transparent={true}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          {/* Header */}
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={resetAndClose} style={styles.modalClose}>
              <Ionicons name="close" size={22} color={PALETTE.subtext} />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>
              {step === 1 && "Choose Target"}
              {step === 2 && "Set Tone"}
              {step === 3 && "Your Message"}
              {step === 4 && "Confirm"}
            </Text>
            <Text style={styles.modalStep}>{step}/4</Text>
          </View>

          {/* Progress dots */}
          <View style={styles.dotsRow}>
            {[1, 2, 3, 4].map((s) => (
              <View key={s} style={[styles.dot, s <= step && styles.dotActive]} />
            ))}
          </View>

          {/* Step 1: Choose Target */}
          {step === 1 && (
            <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
              <Text style={styles.modalDesc}>Who do you want to out-rally?</Text>
              {targets.map((target) => (
                <TouchableOpacity
                  key={target.id}
                  style={[styles.targetRow, selectedTarget === target.id && styles.targetRowSelected]}
                  onPress={() => { setSelectedTarget(target.id); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
                >
                  <View style={styles.targetInfo}>
                    <Text style={styles.targetName} numberOfLines={1}>{target.name}</Text>
                    <Text style={styles.targetGap}>{Math.round(target.gap)} momentum away</Text>
                  </View>
                  <Text style={styles.targetScore}>{Math.round(target.raw_score)} pts</Text>
                  {selectedTarget === target.id && <Ionicons name="checkmark-circle" size={20} color={PALETTE.green} />}
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          {/* Step 2: Choose Tone */}
          {step === 2 && (
            <View style={styles.modalBody}>
              <Text style={styles.modalDesc}>Set the mood for your Rally Cry</Text>
              <View style={styles.tonesGrid}>
                {tones.map((t) => (
                  <TouchableOpacity
                    key={t.id}
                    style={[styles.toneCard, tone === t.id && styles.toneCardSelected]}
                    onPress={() => { setTone(t.id); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
                  >
                    <Text style={styles.toneEmoji}>{t.emoji}</Text>
                    <Text style={[styles.toneLabel, tone === t.id && { color: PALETTE.accent2 }]}>{t.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {/* Step 3: Write Message */}
          {step === 3 && (
            <View style={styles.modalBody}>
              <Text style={styles.modalDesc}>Write a short rallying message (max 100 chars)</Text>
              <TextInput
                style={styles.msgInput}
                placeholder="Help me out-rally them! 🚀"
                placeholderTextColor={PALETTE.subtext}
                value={message}
                onChangeText={(t) => setMessage(t.slice(0, 100))}
                multiline
                maxLength={100}
              />
              <Text style={styles.charCount}>{message.length}/100</Text>
            </View>
          )}

          {/* Step 4: Confirmation + Share */}
          {step === 4 && (
            <View style={styles.modalBody}>
              <View style={styles.confirmCard}>
                <Text style={styles.confirmTitle}>Ready to launch!</Text>
                <View style={styles.confirmLine}>
                  <Text style={styles.confirmLabel}>Target</Text>
                  <Text style={styles.confirmValue}>{selectedTargetData?.name}</Text>
                </View>
                <View style={styles.confirmLine}>
                  <Text style={styles.confirmLabel}>Gap</Text>
                  <Text style={[styles.confirmValue, { color: PALETTE.accent2 }]}>{Math.round(selectedTargetData?.gap || 0)} momentum</Text>
                </View>
                <View style={styles.confirmLine}>
                  <Text style={styles.confirmLabel}>Tone</Text>
                  <Text style={styles.confirmValue}>{tones.find((t) => t.id === tone)?.emoji} {tones.find((t) => t.id === tone)?.label}</Text>
                </View>
                <View style={styles.confirmLine}>
                  <Text style={styles.confirmLabel}>Duration</Text>
                  <Text style={styles.confirmValue}>2 hours</Text>
                </View>
                {message ? <Text style={styles.confirmMsg}>{message}</Text> : null}
              </View>

              {/* Share CTA */}
              <TouchableOpacity
                style={styles.shareCta}
                activeOpacity={0.8}
                onPress={async () => {
                  try {
                    const shareMsg = `🚀 I'm competing against ${selectedTargetData?.name} on Popularoo!\n\n` +
                      `Only ${Math.round(selectedTargetData?.gap || 0)} momentum away.\n` +
                      `Help me win — vote on Popularoo!\n\n` +
                      `https://popularoo.com`;
                    await Share.share({
                      message: shareMsg,
                      title: `Rally Cry — Vote for me on Popularoo!`,
                    });
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  } catch (e) {
                    // Share cancelled or failed — no action needed
                  }
                }}
              >
                <Ionicons name="share-social" size={18} color={PALETTE.gold} />
                <Text style={styles.shareCtaText}>Share Rally Cry</Text>
                <Text style={styles.shareCtaSub}>WhatsApp, SMS, TikTok...</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Footer */}
          <View style={styles.modalFooter}>
            {step > 1 && (
              <TouchableOpacity style={styles.btnBack} onPress={() => setStep(step - 1)}>
                <Text style={styles.btnBackText}>Back</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={[
                styles.btnNext,
                step === 1 && !selectedTarget && { opacity: 0.4, backgroundColor: PALETTE.subtext },
                step === 1 && selectedTarget && { backgroundColor: PALETTE.green },
              ]}
              disabled={step === 1 && !selectedTarget}
              onPress={() => {
                if (step < 4) { setStep(step + 1); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); }
                else { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); resetAndClose(); }
              }}
            >
              <Text style={styles.btnNextText}>{step === 4 ? "🚀 Launch Rally Cry" : "Next"}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// ===================== MAIN SCREEN =====================

export default function BullRunScreen() {
  const router = useRouter();
  const [showRallyCry, setShowRallyCry] = useState(false);

  const bullRun = MOCK_BULL_RUN;
  const ladder = MOCK_LADDER;
  const rank = bullRun.current_rank;

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={PALETTE.text} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>Bull Run</Text>
          <View style={styles.liveBadge}>
            <PulsingDot color={PALETTE.green} />
            <Text style={styles.liveText}>LIVE</Text>
          </View>
        </View>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollInner} showsVerticalScrollIndicator={false}>
        {/* Rank + Timer */}
        <View style={styles.topRow}>
          <RankBadge rank={rank} />
          <TimerBadge days={bullRun.time_remaining.days} hours={bullRun.time_remaining.hours} />
        </View>

        {/* Progress bar */}
        <ProgressBar current={bullRun.cumulative_wins} needed={bullRun.next_rank.wins_needed} nextRank={bullRun.next_rank.display} />

        {/* Stats */}
        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Text style={styles.statNum}>{bullRun.wins_count}</Text>
            <Text style={styles.statLabel}>This week</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statNum}>{bullRun.cumulative_wins}</Text>
            <Text style={styles.statLabel}>Total wins</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={[styles.statNum, { color: PALETTE.orange }]}>{bullRun.pending_wins}</Text>
            <Text style={styles.statLabel}>Pending</Text>
          </View>
        </View>

        {/* Ladder */}
        <Text style={styles.sectionTitle}>The Ladder</Text>

        {/* Targets above (reversed so closest is nearest to user) */}
        {[...ladder.above].reverse().map((person, idx) => (
          <LadderItem key={person.id} person={person} index={idx} isTarget={true} isClosest={idx === 0} />
        ))}

        {/* User in the middle */}
        <UserCard user={ladder.user} rank={rank} />

        {/* Out-rallied below */}
        {ladder.below.map((person, idx) => (
          <LadderItem key={person.id} person={person} index={idx + ladder.above.length} isTarget={false} isClosest={false} />
        ))}

        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Sticky Rally Cry CTA at bottom */}
      <View style={styles.stickyFooter}>
        <TouchableOpacity
          style={styles.rallyCryBtn}
          activeOpacity={0.8}
          onPress={() => { setShowRallyCry(true); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy); }}
        >
          <Ionicons name="megaphone" size={20} color="#FFF" />
          <Text style={styles.rallyCryBtnText}>Launch Rally Cry</Text>
        </TouchableOpacity>
        <Text style={styles.rallyCrySub}>Rally Popularoo voters to back you up</Text>
      </View>

      {/* Rally Cry Modal */}
      <RallyCryModal visible={showRallyCry} onClose={() => setShowRallyCry(false)} targets={ladder.above} />
    </SafeAreaView>
  );
}

// ===================== STYLES =====================
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },

  // Header — same pattern as other pages
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  backBtn: { width: 44, height: 44, justifyContent: "center", alignItems: "center" },
  headerCenter: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  headerTitle: { color: PALETTE.text, fontSize: 24, fontWeight: "700" },
  liveBadge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: PALETTE.green + "15",
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10,
  },
  liveText: { fontSize: 10, fontWeight: "700", color: PALETTE.green },
  pulsingDot: { width: 6, height: 6, borderRadius: 3 },

  // Scroll
  scroll: { flex: 1 },
  scrollInner: { paddingHorizontal: 16, paddingTop: 16 },

  // Top row
  topRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },

  // Rank badge
  rankBadge: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 1, borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 6,
    backgroundColor: PALETTE.card, borderColor: PALETTE.gold,
  },
  rankEmoji: { fontSize: 16 },
  rankName: { fontSize: 13, fontWeight: "700" },

  // Timer badge
  timerBadge: {
    flexDirection: "row", alignItems: "center", gap: 5,
    backgroundColor: PALETTE.card,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 10, borderWidth: 1, borderColor: PALETTE.gold,
  },
  timerText: { fontSize: 12, fontWeight: "600", color: PALETTE.green },

  // Progress
  progressContainer: { marginBottom: 16 },
  progressRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: 5 },
  progressLabel: { fontSize: 12, color: PALETTE.subtext, fontWeight: "500" },
  progressCount: { fontSize: 12, color: PALETTE.subtext, fontWeight: "500" },
  progressTrack: { height: 5, backgroundColor: PALETTE.card, borderRadius: 3, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: PALETTE.gold, borderRadius: 3 },

  // Stats row — same pattern as outsiders page
  statsRow: { flexDirection: "row", gap: 8, marginBottom: 20 },
  statCard: {
    flex: 1, alignItems: "center",
    backgroundColor: PALETTE.card, borderRadius: 12,
    paddingVertical: 12, borderWidth: 1, borderColor: PALETTE.gold,
  },
  statNum: { fontSize: 22, fontWeight: "700", color: PALETTE.green },
  statLabel: { fontSize: 12, color: PALETTE.subtext, marginTop: 3, fontWeight: "500" },

  // Section title
  sectionTitle: { color: PALETTE.text, fontSize: 20, fontWeight: "700", marginBottom: 12 },

  // Ladder rows — inspired by outsiders list rows
  ladderRow: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 12, paddingHorizontal: 12,
    borderRadius: 12, marginBottom: 8,
    borderWidth: 1, gap: 10,
  },
  ladderRowTarget: { backgroundColor: PALETTE.accent + "10", borderColor: PALETTE.accent2 + "30" },
  ladderRowBeaten: { backgroundColor: PALETTE.green + "10", borderColor: PALETTE.green + "30" },
  ladderRowClosest: {
    backgroundColor: PALETTE.gold + "12",
    borderColor: PALETTE.gold,
    borderWidth: 2,
  },
  closestBadge: {
    position: "absolute",
    top: -10,
    right: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: PALETTE.gold,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  closestBadgeText: {
    color: "#0F2F22",
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.3,
  },
  ladderIcon: {
    width: 32, height: 32, borderRadius: 16,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1,
  },
  ladderIconTarget: { backgroundColor: PALETTE.accent + "20", borderColor: PALETTE.accent2 + "40" },
  ladderIconBeaten: { backgroundColor: PALETTE.green + "20", borderColor: PALETTE.green + "40" },
  ladderIconClosest: { backgroundColor: PALETTE.gold + "25", borderColor: PALETTE.gold },
  ladderInfo: { flex: 1 },
  ladderName: { color: PALETTE.text, fontSize: 16, fontWeight: "600" },
  ladderGap: { fontSize: 12, fontWeight: "500", marginTop: 2 },
  ladderScoreBox: { alignItems: "center" },
  ladderScore: { color: PALETTE.text, fontSize: 18, fontWeight: "700" },
  ladderScoreUnit: { color: PALETTE.subtext, fontSize: 10, fontWeight: "500" },

  // User card — center of ladder
  userCard: {
    backgroundColor: PALETTE.card, borderRadius: 14,
    padding: 16, marginVertical: 10,
    borderWidth: 2, alignItems: "center",
    borderColor: PALETTE.gold,
  },
  userCardTop: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 },
  userCardRank: { fontSize: 13, fontWeight: "700" },
  userCardName: { color: PALETTE.text, fontSize: 20, fontWeight: "700", marginBottom: 10, textAlign: "center" },
  userCardStats: { flexDirection: "row", alignItems: "center", gap: 20 },
  userCardStat: { alignItems: "center" },
  userCardStatNum: { color: PALETTE.text, fontSize: 24, fontWeight: "700" },
  userCardStatLabel: { color: PALETTE.subtext, fontSize: 12, fontWeight: "500", marginTop: 2 },
  userCardDivider: { width: 1, height: 28, backgroundColor: PALETTE.border },

  // Rally Cry CTA — sticky at bottom with bold gradient style
  stickyFooter: {
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: Platform.OS === "ios" ? 24 : 16,
    borderTopWidth: 1,
    borderTopColor: PALETTE.gold + "30",
    backgroundColor: PALETTE.bg,
  },
  rallyCryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10,
    backgroundColor: PALETTE.gold, borderRadius: 25,
    paddingVertical: 16,
  },
  rallyCryBtnText: { color: "#0F2F22", fontSize: 17, fontWeight: "800" },
  rallyCrySub: { color: PALETTE.subtext, fontSize: 12, textAlign: "center", marginTop: 6 },
  // Share CTA in Step 4
  shareCta: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10,
    marginTop: 16, paddingVertical: 14, paddingHorizontal: 20,
    borderRadius: 14, borderWidth: 1.5, borderColor: PALETTE.gold + "50",
    backgroundColor: PALETTE.gold + "10",
  },
  shareCtaText: { color: PALETTE.gold, fontSize: 15, fontWeight: "700" },
  shareCtaSub: { color: PALETTE.subtext, fontSize: 11 },

  // ===== MODAL =====
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modalContent: {
    backgroundColor: PALETTE.bg,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingTop: 16, paddingHorizontal: 20,
    paddingBottom: Platform.OS === "ios" ? 36 : 24,
    maxHeight: "82%",
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 10 },
  modalClose: { width: 44, height: 44, justifyContent: "center", alignItems: "center" },
  modalTitle: { color: PALETTE.text, fontSize: 16, fontWeight: "700" },
  modalStep: { color: PALETTE.subtext, fontSize: 12, fontWeight: "600" },

  dotsRow: { flexDirection: "row", justifyContent: "center", gap: 6, marginBottom: 16 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: PALETTE.border },
  dotActive: { backgroundColor: PALETTE.accent2, width: 20 },

  modalBody: { flex: 1, marginBottom: 14 },
  modalDesc: { color: PALETTE.subtext, fontSize: 14, lineHeight: 20, marginBottom: 14 },

  // Target rows
  targetRow: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 12, paddingHorizontal: 14,
    borderRadius: 12, marginBottom: 8,
    borderWidth: 1, borderColor: PALETTE.border,
    backgroundColor: PALETTE.card,
  },
  targetRowSelected: { borderColor: PALETTE.green, backgroundColor: PALETTE.green + "10" },
  targetInfo: { flex: 1 },
  targetName: { color: PALETTE.text, fontSize: 15, fontWeight: "600" },
  targetGap: { color: PALETTE.accent2, fontSize: 12, marginTop: 2 },
  targetScore: { color: PALETTE.subtext, fontSize: 14, fontWeight: "700", marginRight: 10 },

  // Tones
  tonesGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  toneCard: {
    width: "47%", alignItems: "center",
    paddingVertical: 18, borderRadius: 12,
    borderWidth: 1, borderColor: PALETTE.border,
    backgroundColor: PALETTE.card,
  },
  toneCardSelected: { borderColor: PALETTE.accent2, backgroundColor: PALETTE.accent2 + "10" },
  toneEmoji: { fontSize: 26, marginBottom: 6 },
  toneLabel: { color: PALETTE.subtext, fontSize: 13, fontWeight: "600" },

  // Message input
  msgInput: {
    backgroundColor: PALETTE.card, borderRadius: 12,
    borderWidth: 1, borderColor: PALETTE.border,
    padding: 14, fontSize: 15, color: PALETTE.text,
    minHeight: 80, textAlignVertical: "top",
  },
  charCount: { fontSize: 11, color: PALETTE.subtext, textAlign: "right", marginTop: 4 },

  // Confirm
  confirmCard: {
    backgroundColor: PALETTE.card, borderRadius: 14,
    padding: 18, borderWidth: 1, borderColor: PALETTE.border,
  },
  confirmTitle: { color: PALETTE.text, fontSize: 17, fontWeight: "700", textAlign: "center", marginBottom: 14 },
  confirmLine: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: PALETTE.border,
  },
  confirmLabel: { color: PALETTE.subtext, fontSize: 13 },
  confirmValue: { color: PALETTE.text, fontSize: 14, fontWeight: "600" },
  confirmMsg: { color: PALETTE.accent2, fontSize: 14, fontStyle: "italic", textAlign: "center", marginTop: 12 },

  // Footer
  modalFooter: { flexDirection: "row", gap: 10 },
  btnBack: {
    flex: 1, paddingVertical: 13, borderRadius: 25,
    borderWidth: 1, borderColor: PALETTE.border, alignItems: "center",
  },
  btnBackText: { color: PALETTE.subtext, fontSize: 15, fontWeight: "600" },
  btnNext: {
    flex: 2, paddingVertical: 13, borderRadius: 25,
    backgroundColor: PALETTE.accent2, alignItems: "center",
  },
  btnNextText: { color: "#FFF", fontSize: 15, fontWeight: "700" },
});

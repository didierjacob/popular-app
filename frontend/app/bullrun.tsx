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
  useWindowDimensions,
  KeyboardAvoidingView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

// ===================== DESIGN SYSTEM =====================
const COLORS = {
  bg: "#0A0E1A",         // Deep dark blue-black (premium feel)
  card: "#141B2D",       // Slightly lighter card
  cardHigh: "#1C2640",   // Highlighted card
  gold: "#FFD700",       // Gold for ranks
  silver: "#C0C0C0",
  bronze: "#CD7F32",
  accent: "#00E676",     // Neon green (stock market rise)
  accentRed: "#FF5252",  // Red (for targets/gaps)
  text: "#FFFFFF",
  subtext: "#8892B0",
  border: "#233554",
  gradientStart: "#1A237E",
  gradientEnd: "#0D1B2A",
  rallyCry: "#FF6D00",   // Orange for Rally Cry
};

const RANK_CONFIG = {
  legend: { emoji: "🌟", name: "Legend", color: "#FFD700" },
  icon: { emoji: "👑", name: "Icon", color: "#FF8C00" },
  a_list: { emoji: "🥇", name: "A-List", color: "#FFD700" },
  big_name: { emoji: "🥈", name: "Big Name", color: "#C0C0C0" },
  rising_star: { emoji: "🥉", name: "Rising Star", color: "#CD7F32" },
  none: { emoji: "🎯", name: "Challenger", color: "#8892B0" },
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
  rank_display: RANK_CONFIG.big_name,
  wins_count: 23,
  cumulative_wins: 23,
  pending_wins: 1,
  next_rank: { rank: "a_list", display: "🥇 A-List", wins_needed: 77, threshold: 100 },
};

const MOCK_LADDER = {
  above: [
    {
      id: "celeb_001",
      name: "Beyoncé",
      category: "entertainment",
      raw_score: 72.41,
      score: 75,
      total_votes: 510,
      gap: 5.07,
      status: "target",
    },
    {
      id: "celeb_002",
      name: "Tim Cook",
      category: "tech",
      raw_score: 83.33,
      score: 75,
      total_votes: 480,
      gap: 16.0,
      status: "target",
    },
    {
      id: "celeb_003",
      name: "Volodymyr Zelenskyy",
      category: "politics",
      raw_score: 88.24,
      score: 100,
      total_votes: 690,
      gap: 20.9,
      status: "target",
    },
  ],
  below: [
    {
      id: "celeb_004",
      name: "Joe Biden",
      category: "politics",
      raw_score: 55.01,
      score: 50,
      total_votes: 430,
      gap: 12.33,
      status: "beaten",
      won_at: "2026-04-27T14:22:00Z",
    },
    {
      id: "celeb_005",
      name: "Serena Williams",
      category: "sport",
      raw_score: 48.76,
      score: 50,
      total_votes: 320,
      gap: 18.58,
      status: "beaten",
      won_at: "2026-04-26T09:15:00Z",
    },
    {
      id: "celeb_006",
      name: "Jamie Dimon",
      category: "business",
      raw_score: 42.11,
      score: 50,
      total_votes: 190,
      gap: 25.23,
      status: "beaten",
      won_at: "2026-04-25T18:33:00Z",
    },
  ],
  user: {
    id: "mock_person_001",
    name: "Alexandre Martin",
    raw_score: 67.34,
    score: 75,
    total_votes: 150,
  },
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
  return (
    <Animated.View style={[styles.pulsingDot, { backgroundColor: color, opacity: pulse }]} />
  );
}

function CountdownTimer({ days, hours }) {
  return (
    <View style={styles.timerContainer}>
      <View style={styles.timerBlock}>
        <Text style={styles.timerNumber}>{days}</Text>
        <Text style={styles.timerLabel}>DAYS</Text>
      </View>
      <Text style={styles.timerColon}>:</Text>
      <View style={styles.timerBlock}>
        <Text style={styles.timerNumber}>{hours}</Text>
        <Text style={styles.timerLabel}>HRS</Text>
      </View>
      <PulsingDot color={COLORS.accent} />
    </View>
  );
}

function RankBadge({ rank }) {
  const config = RANK_CONFIG[rank] || RANK_CONFIG.none;
  return (
    <View style={[styles.rankBadge, { borderColor: config.color }]}>
      <Text style={styles.rankEmoji}>{config.emoji}</Text>
      <Text style={[styles.rankName, { color: config.color }]}>{config.name}</Text>
    </View>
  );
}

function ProgressToNextRank({ current, needed, nextRank }) {
  const total = current + needed;
  const progress = total > 0 ? current / total : 0;
  return (
    <View style={styles.progressContainer}>
      <View style={styles.progressHeader}>
        <Text style={styles.progressLabel}>Next: {nextRank}</Text>
        <Text style={styles.progressCount}>{current}/{total} wins</Text>
      </View>
      <View style={styles.progressBar}>
        <View style={[styles.progressFill, { width: `${Math.min(progress * 100, 100)}%` }]} />
      </View>
    </View>
  );
}

function LadderItem({ person, index, isTarget }) {
  const slideAnim = useRef(new Animated.Value(isTarget ? -30 : 30)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 400,
        delay: index * 100,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }),
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 300,
        delay: index * 100,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  const gapText = isTarget
    ? `${Math.round(person.gap)} points behind`
    : `${Math.round(person.gap)} points ahead`;

  const categoryColors = {
    entertainment: "#E040FB",
    tech: "#448AFF",
    politics: "#FF6E40",
    sport: "#69F0AE",
    business: "#FFD740",
    other: "#B0BEC5",
  };

  const categoryColor = categoryColors[person.category] || categoryColors.other;

  return (
    <Animated.View
      style={[
        styles.ladderItem,
        isTarget ? styles.ladderItemTarget : styles.ladderItemBeaten,
        { transform: [{ translateX: slideAnim }], opacity: fadeAnim },
      ]}
    >
      <View style={styles.ladderItemLeft}>
        <View style={[styles.categoryDot, { backgroundColor: categoryColor }]} />
        <View style={styles.ladderItemInfo}>
          <Text style={styles.ladderItemName} numberOfLines={1} ellipsizeMode="tail">
            {person.name}
          </Text>
          <Text style={[styles.ladderItemGap, { color: isTarget ? COLORS.accentRed : COLORS.accent }]}>
            {isTarget ? "▲" : "▼"} {gapText}
          </Text>
        </View>
      </View>
      <View style={styles.ladderItemRight}>
        <Text style={styles.ladderItemScore}>{Math.round(person.raw_score)}</Text>
        <Text style={styles.ladderItemScoreLabel}>pts</Text>
      </View>
      {isTarget && (
        <View style={styles.targetBadge}>
          <Ionicons name="flag" size={10} color={COLORS.accentRed} />
        </View>
      )}
      {!isTarget && (
        <View style={styles.beatenBadge}>
          <Ionicons name="checkmark-circle" size={14} color={COLORS.accent} />
        </View>
      )}
    </Animated.View>
  );
}

function UserCard({ user, rank }) {
  const config = RANK_CONFIG[rank] || RANK_CONFIG.none;
  const glowAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 1, duration: 2000, useNativeDriver: false }),
        Animated.timing(glowAnim, { toValue: 0, duration: 2000, useNativeDriver: false }),
      ])
    ).start();
  }, []);

  return (
    <View style={[styles.userCard, { borderColor: config.color }]}>
      <View style={styles.userCardHeader}>
        <Text style={styles.userCardRankEmoji}>{config.emoji}</Text>
        <Text style={[styles.userCardRankName, { color: config.color }]}>{config.name}</Text>
      </View>
      <Text style={styles.userCardName} numberOfLines={1} ellipsizeMode="tail">
        {user.name}
      </Text>
      <View style={styles.userCardStats}>
        <View style={styles.userCardStat}>
          <Text style={styles.userCardStatValue}>{Math.round(user.raw_score)}</Text>
          <Text style={styles.userCardStatLabel}>Points</Text>
        </View>
        <View style={styles.userCardDivider} />
        <View style={styles.userCardStat}>
          <Text style={styles.userCardStatValue}>{user.total_votes.toLocaleString()}</Text>
          <Text style={styles.userCardStatLabel}>Votes</Text>
        </View>
      </View>
    </View>
  );
}

// ===================== RALLY CRY MODAL =====================

function RallyCryModal({
  visible,
  onClose,
  targets,
}) {
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
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.modalOverlay}
      >
        <View style={styles.modalContent}>
          {/* Header */}
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={resetAndClose} style={styles.modalCloseBtn}>
              <Ionicons name="close" size={24} color={COLORS.subtext} />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>
              {step === 1 && "🎯 Choose Target"}
              {step === 2 && "🎤 Set Tone"}
              {step === 3 && "✍️ Your Message"}
              {step === 4 && "🚀 Launch!"}
            </Text>
            <Text style={styles.modalStepIndicator}>Step {step}/4</Text>
          </View>

          {/* Step Progress */}
          <View style={styles.stepProgress}>
            {[1, 2, 3, 4].map((s) => (
              <View
                key={s}
                style={[styles.stepDot, s <= step && styles.stepDotActive]}
              />
            ))}
          </View>

          {/* Step 1: Choose Target */}
          {step === 1 && (
            <ScrollView style={styles.modalBody}>
              <Text style={styles.modalDescription}>
                Who do you want to overtake? Your community will rally votes to help you beat them!
              </Text>
              {targets.map((target) => (
                <TouchableOpacity
                  key={target.id}
                  style={[
                    styles.targetOption,
                    selectedTarget === target.id && styles.targetOptionSelected,
                  ]}
                  onPress={() => {
                    setSelectedTarget(target.id);
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  }}
                >
                  <View style={styles.targetOptionInfo}>
                    <Text style={styles.targetOptionName} numberOfLines={1}>
                      {target.name}
                    </Text>
                    <Text style={styles.targetOptionGap}>
                      {Math.round(target.gap)} points away
                    </Text>
                  </View>
                  <View style={styles.targetOptionScore}>
                    <Text style={styles.targetOptionScoreValue}>{Math.round(target.raw_score)}</Text>
                    <Text style={styles.targetOptionScoreLabel}>pts</Text>
                  </View>
                  {selectedTarget === target.id && (
                    <Ionicons name="checkmark-circle" size={22} color={COLORS.accent} />
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          {/* Step 2: Choose Tone */}
          {step === 2 && (
            <View style={styles.modalBody}>
              <Text style={styles.modalDescription}>
                Set the mood for your Rally Cry. This defines how your message appears to the community.
              </Text>
              <View style={styles.tonesGrid}>
                {tones.map((t) => (
                  <TouchableOpacity
                    key={t.id}
                    style={[styles.toneOption, tone === t.id && styles.toneOptionSelected]}
                    onPress={() => {
                      setTone(t.id);
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    }}
                  >
                    <Text style={styles.toneEmoji}>{t.emoji}</Text>
                    <Text style={[styles.toneLabel, tone === t.id && styles.toneLabelSelected]}>
                      {t.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {/* Step 3: Write Message */}
          {step === 3 && (
            <View style={styles.modalBody}>
              <Text style={styles.modalDescription}>
                Write a short rallying message (max 100 characters). Make it count!
              </Text>
              <TextInput
                style={styles.messageInput}
                placeholder="Help me beat them! 🚀"
                placeholderTextColor={COLORS.subtext}
                value={message}
                onChangeText={(t) => setMessage(t.slice(0, 100))}
                multiline
                maxLength={100}
              />
              <Text style={styles.charCount}>{message.length}/100</Text>
            </View>
          )}

          {/* Step 4: Confirmation */}
          {step === 4 && (
            <View style={styles.modalBody}>
              <View style={styles.confirmCard}>
                <Text style={styles.confirmTitle}>Ready to launch! 🚀</Text>
                <View style={styles.confirmRow}>
                  <Text style={styles.confirmLabel}>Target:</Text>
                  <Text style={styles.confirmValue}>{selectedTargetData?.name}</Text>
                </View>
                <View style={styles.confirmRow}>
                  <Text style={styles.confirmLabel}>Gap:</Text>
                  <Text style={[styles.confirmValue, { color: COLORS.accentRed }]}>
                    {Math.round(selectedTargetData?.gap || 0)} points
                  </Text>
                </View>
                <View style={styles.confirmRow}>
                  <Text style={styles.confirmLabel}>Tone:</Text>
                  <Text style={styles.confirmValue}>
                    {tones.find((t) => t.id === tone)?.emoji} {tones.find((t) => t.id === tone)?.label}
                  </Text>
                </View>
                <View style={styles.confirmRow}>
                  <Text style={styles.confirmLabel}>Duration:</Text>
                  <Text style={styles.confirmValue}>2 hours</Text>
                </View>
                {message ? (
                  <View style={styles.confirmMessageBox}>
                    <Text style={styles.confirmMessage}>&ldquo;{message}&rdquo;</Text>
                  </View>
                ) : null}
              </View>
            </View>
          )}

          {/* Footer Buttons */}
          <View style={styles.modalFooter}>
            {step > 1 && (
              <TouchableOpacity
                style={styles.backBtn}
                onPress={() => setStep(step - 1)}
              >
                <Text style={styles.backBtnText}>Back</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={[
                styles.nextBtn,
                step === 1 && !selectedTarget && styles.nextBtnDisabled,
              ]}
              disabled={step === 1 && !selectedTarget}
              onPress={() => {
                if (step < 4) {
                  setStep(step + 1);
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                } else {
                  // Launch Rally Cry (mock)
                  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                  resetAndClose();
                }
              }}
            >
              <Text style={styles.nextBtnText}>
                {step === 4 ? "🚀 Launch Rally Cry" : "Next"}
              </Text>
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
  const { width } = useWindowDimensions();
  const [showRallyCry, setShowRallyCry] = useState(false);

  // Use mock data
  const bullRun = MOCK_BULL_RUN;
  const ladder = MOCK_LADDER;

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>BULL RUN</Text>
          <View style={styles.liveIndicator}>
            <PulsingDot color={COLORS.accent} />
            <Text style={styles.liveText}>LIVE</Text>
          </View>
        </View>
        <View style={styles.headerRight} />
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Rank & Timer Section */}
        <View style={styles.rankSection}>
          <RankBadge rank={bullRun.current_rank} />
          <CountdownTimer
            days={bullRun.time_remaining.days}
            hours={bullRun.time_remaining.hours}
          />
        </View>

        {/* Progress to next rank */}
        <ProgressToNextRank
          current={bullRun.cumulative_wins}
          needed={bullRun.next_rank.wins_needed}
          nextRank={bullRun.next_rank.display}
        />

        {/* Stats Row */}
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{bullRun.wins_count}</Text>
            <Text style={styles.statLabel}>Wins this week</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{bullRun.cumulative_wins}</Text>
            <Text style={styles.statLabel}>Total wins</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={[styles.statValue, { color: COLORS.rallyCry }]}>
              {bullRun.pending_wins}
            </Text>
            <Text style={styles.statLabel}>Pending</Text>
          </View>
        </View>

        {/* === THE LADDER === */}
        <View style={styles.ladderSection}>
          <Text style={styles.sectionTitle}>📊 The Ladder</Text>

          {/* Targets (above) - displayed in reverse so closest is nearest to user */}
          {[...ladder.above].reverse().map((person, idx) => (
            <LadderItem
              key={person.id}
              person={person}
              index={idx}
              isTarget={true}
            />
          ))}

          {/* User position (middle) */}
          <UserCard user={ladder.user} rank={bullRun.current_rank} />

          {/* Beaten (below) */}
          {ladder.below.map((person, idx) => (
            <LadderItem
              key={person.id}
              person={person}
              index={idx + ladder.above.length}
              isTarget={false}
            />
          ))}
        </View>

        {/* Rally Cry CTA */}
        <TouchableOpacity
          style={styles.rallyCryButton}
          onPress={() => {
            setShowRallyCry(true);
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
          }}
          activeOpacity={0.8}
        >
          <View style={styles.rallyCryButtonInner}>
            <Ionicons name="megaphone" size={22} color="#FFF" />
            <Text style={styles.rallyCryButtonText}>Launch Rally Cry</Text>
          </View>
          <Text style={styles.rallyCrySubtext}>
            Ask your community to vote for you!
          </Text>
        </TouchableOpacity>

        {/* Bottom spacing */}
        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Rally Cry Modal */}
      <RallyCryModal
        visible={showRallyCry}
        onClose={() => setShowRallyCry(false)}
        targets={ladder.above}
      />
    </SafeAreaView>
  );
}

// ===================== STYLES =====================
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  backButton: {
    width: 44,
    height: 44,
    justifyContent: "center",
    alignItems: "center",
  },
  headerCenter: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: COLORS.text,
    letterSpacing: 2,
  },
  headerRight: {
    width: 44,
  },
  liveIndicator: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "rgba(0, 230, 118, 0.1)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
  },
  liveText: {
    fontSize: 10,
    fontWeight: "700",
    color: COLORS.accent,
    letterSpacing: 1,
  },
  pulsingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 16,
    paddingTop: 20,
  },

  // Rank section
  rankSection: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 20,
  },
  rankBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: 1.5,
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
  },
  rankEmoji: {
    fontSize: 20,
  },
  rankName: {
    fontSize: 14,
    fontWeight: "700",
  },

  // Timer
  timerContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  timerBlock: {
    alignItems: "center",
    backgroundColor: COLORS.card,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    minWidth: 44,
  },
  timerNumber: {
    fontSize: 18,
    fontWeight: "800",
    color: COLORS.text,
  },
  timerLabel: {
    fontSize: 9,
    fontWeight: "600",
    color: COLORS.subtext,
    letterSpacing: 1,
  },
  timerColon: {
    fontSize: 18,
    fontWeight: "800",
    color: COLORS.subtext,
  },

  // Progress
  progressContainer: {
    marginBottom: 20,
  },
  progressHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 6,
  },
  progressLabel: {
    fontSize: 12,
    color: COLORS.subtext,
    fontWeight: "600",
  },
  progressCount: {
    fontSize: 12,
    color: COLORS.subtext,
    fontWeight: "600",
  },
  progressBar: {
    height: 6,
    backgroundColor: COLORS.card,
    borderRadius: 3,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: COLORS.gold,
    borderRadius: 3,
  },

  // Stats row
  statsRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 24,
  },
  statBox: {
    flex: 1,
    backgroundColor: COLORS.card,
    borderRadius: 12,
    padding: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  statValue: {
    fontSize: 20,
    fontWeight: "800",
    color: COLORS.accent,
  },
  statLabel: {
    fontSize: 10,
    color: COLORS.subtext,
    marginTop: 4,
    fontWeight: "500",
    textAlign: "center",
  },

  // Ladder
  ladderSection: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 16,
  },
  ladderItem: {
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    borderRadius: 12,
    marginBottom: 8,
    borderWidth: 1,
  },
  ladderItemTarget: {
    backgroundColor: "rgba(255, 82, 82, 0.05)",
    borderColor: "rgba(255, 82, 82, 0.2)",
  },
  ladderItemBeaten: {
    backgroundColor: "rgba(0, 230, 118, 0.05)",
    borderColor: "rgba(0, 230, 118, 0.2)",
  },
  ladderItemLeft: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
    gap: 10,
  },
  categoryDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  ladderItemInfo: {
    flex: 1,
  },
  ladderItemName: {
    fontSize: 14,
    fontWeight: "600",
    color: COLORS.text,
  },
  ladderItemGap: {
    fontSize: 11,
    fontWeight: "500",
    marginTop: 2,
  },
  ladderItemRight: {
    alignItems: "center",
    marginRight: 8,
  },
  ladderItemScore: {
    fontSize: 16,
    fontWeight: "800",
    color: COLORS.text,
  },
  ladderItemScoreLabel: {
    fontSize: 9,
    color: COLORS.subtext,
    fontWeight: "600",
  },
  targetBadge: {
    position: "absolute",
    top: 8,
    right: 8,
  },
  beatenBadge: {
    position: "absolute",
    top: 8,
    right: 8,
  },

  // User card (middle of ladder)
  userCard: {
    backgroundColor: COLORS.cardHigh,
    borderRadius: 16,
    padding: 16,
    marginVertical: 12,
    borderWidth: 2,
    alignItems: "center",
  },
  userCardHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 6,
  },
  userCardRankEmoji: {
    fontSize: 16,
  },
  userCardRankName: {
    fontSize: 12,
    fontWeight: "700",
  },
  userCardName: {
    fontSize: 18,
    fontWeight: "800",
    color: COLORS.text,
    marginBottom: 12,
    textAlign: "center",
  },
  userCardStats: {
    flexDirection: "row",
    alignItems: "center",
    gap: 20,
  },
  userCardStat: {
    alignItems: "center",
  },
  userCardStatValue: {
    fontSize: 22,
    fontWeight: "800",
    color: COLORS.text,
  },
  userCardStatLabel: {
    fontSize: 10,
    color: COLORS.subtext,
    fontWeight: "600",
    marginTop: 2,
  },
  userCardDivider: {
    width: 1,
    height: 30,
    backgroundColor: COLORS.border,
  },

  // Rally Cry button
  rallyCryButton: {
    backgroundColor: COLORS.rallyCry,
    borderRadius: 16,
    padding: 18,
    alignItems: "center",
    shadowColor: COLORS.rallyCry,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
  rallyCryButtonInner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  rallyCryButtonText: {
    fontSize: 17,
    fontWeight: "800",
    color: "#FFF",
  },
  rallyCrySubtext: {
    fontSize: 12,
    color: "rgba(255,255,255,0.7)",
    marginTop: 4,
  },

  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.7)",
    justifyContent: "flex-end",
  },
  modalContent: {
    backgroundColor: COLORS.bg,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingTop: 16,
    paddingHorizontal: 20,
    paddingBottom: Platform.OS === "ios" ? 40 : 24,
    maxHeight: "85%",
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  modalCloseBtn: {
    width: 44,
    height: 44,
    justifyContent: "center",
    alignItems: "center",
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: COLORS.text,
  },
  modalStepIndicator: {
    fontSize: 12,
    color: COLORS.subtext,
    fontWeight: "600",
  },
  stepProgress: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 8,
    marginBottom: 20,
  },
  stepDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.border,
  },
  stepDotActive: {
    backgroundColor: COLORS.rallyCry,
    width: 24,
  },
  modalBody: {
    flex: 1,
    marginBottom: 16,
  },
  modalDescription: {
    fontSize: 14,
    color: COLORS.subtext,
    lineHeight: 20,
    marginBottom: 16,
  },

  // Target options
  targetOption: {
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: 10,
    backgroundColor: COLORS.card,
  },
  targetOptionSelected: {
    borderColor: COLORS.accent,
    backgroundColor: "rgba(0, 230, 118, 0.05)",
  },
  targetOptionInfo: {
    flex: 1,
  },
  targetOptionName: {
    fontSize: 15,
    fontWeight: "600",
    color: COLORS.text,
  },
  targetOptionGap: {
    fontSize: 12,
    color: COLORS.accentRed,
    marginTop: 2,
  },
  targetOptionScore: {
    alignItems: "center",
    marginRight: 12,
  },
  targetOptionScoreValue: {
    fontSize: 16,
    fontWeight: "800",
    color: COLORS.text,
  },
  targetOptionScoreLabel: {
    fontSize: 9,
    color: COLORS.subtext,
  },

  // Tones
  tonesGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    justifyContent: "center",
  },
  toneOption: {
    width: "45%",
    alignItems: "center",
    padding: 20,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.card,
  },
  toneOptionSelected: {
    borderColor: COLORS.rallyCry,
    backgroundColor: "rgba(255, 109, 0, 0.1)",
  },
  toneEmoji: {
    fontSize: 28,
    marginBottom: 8,
  },
  toneLabel: {
    fontSize: 13,
    fontWeight: "600",
    color: COLORS.subtext,
  },
  toneLabelSelected: {
    color: COLORS.rallyCry,
  },

  // Message input
  messageInput: {
    backgroundColor: COLORS.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 14,
    fontSize: 15,
    color: COLORS.text,
    minHeight: 80,
    textAlignVertical: "top",
  },
  charCount: {
    fontSize: 11,
    color: COLORS.subtext,
    textAlign: "right",
    marginTop: 6,
  },

  // Confirm card
  confirmCard: {
    backgroundColor: COLORS.card,
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  confirmTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: COLORS.text,
    textAlign: "center",
    marginBottom: 16,
  },
  confirmRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  confirmLabel: {
    fontSize: 13,
    color: COLORS.subtext,
    fontWeight: "500",
  },
  confirmValue: {
    fontSize: 14,
    color: COLORS.text,
    fontWeight: "600",
  },
  confirmMessageBox: {
    backgroundColor: "rgba(255, 109, 0, 0.08)",
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
  },
  confirmMessage: {
    fontSize: 14,
    color: COLORS.rallyCry,
    fontStyle: "italic",
    textAlign: "center",
  },

  // Footer buttons
  modalFooter: {
    flexDirection: "row",
    gap: 12,
  },
  backBtn: {
    flex: 1,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: "center",
  },
  backBtnText: {
    fontSize: 15,
    fontWeight: "600",
    color: COLORS.subtext,
  },
  nextBtn: {
    flex: 2,
    padding: 14,
    borderRadius: 12,
    backgroundColor: COLORS.rallyCry,
    alignItems: "center",
  },
  nextBtnDisabled: {
    opacity: 0.4,
  },
  nextBtnText: {
    fontSize: 15,
    fontWeight: "700",
    color: "#FFF",
  },
});

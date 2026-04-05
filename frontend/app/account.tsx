import React, { useState, useEffect, useCallback } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  Alert,
  Linking,
  ActivityIndicator,
  FlatList,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { CreditsService, type Transaction } from "../services/creditsService";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  border: "#2E6148",
  gold: "#FFD700",
  green: "#2ECC71",
};

const SUPPORT_EMAIL = "contactpopulr@proton.me";
const ACCOUNT_KEY = "popular_account_info";

interface AccountInfo {
  name: string;
  email: string;
  address: string;
  city: string;
  country: string;
}

// ---- Sub-screens ----
type Screen = "main" | "billing" | "invoices" | "help";

export default function AccountScreen() {
  const [accountInfo, setAccountInfo] = useState<AccountInfo>({
    name: "",
    email: "",
    address: "",
    city: "",
    country: "",
  });
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [screen, setScreen] = useState<Screen>("main");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingTx, setLoadingTx] = useState(false);

  useEffect(() => {
    loadAccountInfo();
  }, []);

  const loadAccountInfo = async () => {
    try {
      const stored = await AsyncStorage.getItem(ACCOUNT_KEY);
      if (stored) {
        setAccountInfo(JSON.parse(stored));
      }
    } catch (e) {
      console.error("Failed to load account info:", e);
    }
  };

  const saveAccountInfo = async () => {
    setIsSaving(true);
    try {
      await AsyncStorage.setItem(ACCOUNT_KEY, JSON.stringify(accountInfo));
      Alert.alert("Success", "Account information saved!");
      setIsEditing(false);
    } catch (e) {
      Alert.alert("Error", "Failed to save account information");
    } finally {
      setIsSaving(false);
    }
  };

  const handleChange = (field: keyof AccountInfo, value: string) => {
    setAccountInfo((prev) => ({ ...prev, [field]: value }));
  };

  const loadTransactions = useCallback(async () => {
    setLoadingTx(true);
    try {
      const history = await CreditsService.getHistory(50);
      setTransactions(history);
    } catch (e) {
      console.error("Failed to load transactions:", e);
    } finally {
      setLoadingTx(false);
    }
  }, []);

  const openBilling = () => {
    loadTransactions();
    setScreen("billing");
  };

  const openInvoices = () => {
    loadTransactions();
    setScreen("invoices");
  };

  const contactSupport = () => {
    const subject = encodeURIComponent("Populr App - Support Request");
    const body = encodeURIComponent(
      `Hello,\n\nI need help with:\n\n---\nApp: Populr v1.0.0\nName: ${accountInfo.name || "N/A"}\nEmail: ${accountInfo.email || "N/A"}\n`
    );
    Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`);
  };

  const formatDate = (timestamp: string) => {
    const d = new Date(timestamp);
    return d.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // ---- Billing / Invoices Sub-screen ----
  if (screen === "billing" || screen === "invoices") {
    const isInvoice = screen === "invoices";
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.subHeader}>
          <TouchableOpacity onPress={() => setScreen("main")} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
          </TouchableOpacity>
          <Text style={styles.subTitle}>
            {isInvoice ? "Invoices" : "Billing History"}
          </Text>
          <View style={{ width: 32 }} />
        </View>

        {loadingTx ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={PALETTE.accent2} />
          </View>
        ) : transactions.length === 0 ? (
          <View style={styles.center}>
            <Ionicons
              name={isInvoice ? "document-text-outline" : "receipt-outline"}
              size={64}
              color={PALETTE.border}
            />
            <Text style={styles.emptyText}>
              {isInvoice ? "No invoices yet" : "No transactions yet"}
            </Text>
            <Text style={styles.emptySubtext}>
              Your {isInvoice ? "invoices" : "purchase history"} will appear here after your first boost.
            </Text>
          </View>
        ) : (
          <ScrollView style={{ flex: 1 }}>
            {transactions.map((tx, index) => {
              const tierLabel =
                tx.pack === "golden_booster"
                  ? "Golden Booster"
                  : tx.pack === "super_booster"
                  ? "Super Booster"
                  : tx.pack === "booster"
                  ? "Booster"
                  : tx.pack || "—";

              return (
                <View key={tx._id || index} style={styles.txCard}>
                  <View style={styles.txRow}>
                    <View
                      style={[
                        styles.txIcon,
                        {
                          backgroundColor:
                            tx.type === "purchase"
                              ? PALETTE.green + "20"
                              : PALETTE.accent2 + "20",
                        },
                      ]}
                    >
                      <Ionicons
                        name={
                          isInvoice
                            ? "document-text"
                            : tx.type === "purchase"
                            ? "rocket"
                            : "time"
                        }
                        size={22}
                        color={tx.type === "purchase" ? PALETTE.green : PALETTE.accent2}
                      />
                    </View>
                    <View style={styles.txInfo}>
                      <Text style={styles.txTitle}>{tierLabel}</Text>
                      <Text style={styles.txDesc} numberOfLines={2}>
                        {tx.description}
                      </Text>
                      <Text style={styles.txDate}>{formatDate(tx.timestamp)}</Text>
                    </View>
                    {tx.price !== undefined && tx.price !== null && (
                      <Text style={styles.txPrice}>€{Number(tx.price).toFixed(2)}</Text>
                    )}
                  </View>

                  {isInvoice && (
                    <View style={styles.invoiceFooter}>
                      <Text style={styles.invoiceRef}>
                        Ref: POP-{tx._id ? tx._id.slice(-8).toUpperCase() : index}
                      </Text>
                      <Text style={styles.invoiceStatus}>Paid</Text>
                    </View>
                  )}
                </View>
              );
            })}
            <View style={{ height: 40 }} />
          </ScrollView>
        )}
      </SafeAreaView>
    );
  }

  // ---- Help Center Sub-screen ----
  if (screen === "help") {
    const FAQ = [
      {
        q: "What is Populr?",
        a: "Populr is an app where you can rate and rank public personalities. Discover trending figures, vote for your favorites, and see who's the most popular!",
      },
      {
        q: "How do Boosters work?",
        a: "Boosters let you appear on the Home page as an 'Outsider'. Choose a tier:\n\n• Booster (€0.99) — 1 hour of visibility\n• Super Booster (€9.99) — 24 hours\n• Golden Booster (€49.99) — 1 week at the top",
      },
      {
        q: "How do I vote?",
        a: "Search for a personality or tap on one from the lists. On their page, tap the thumbs up or thumbs down button. You can vote once every 24 hours per personality.",
      },
      {
        q: "What is Personality of the Day?",
        a: "It's the personality with the highest popularity score at the moment. It updates automatically based on votes.",
      },
      {
        q: "Can I add a new personality?",
        a: "Yes! Use the search bar on the Home page. If the person isn't in our database, we'll search Wikipedia and add them automatically.",
      },
      {
        q: "How do I contact support?",
        a: `Send an email to ${SUPPORT_EMAIL} and we'll get back to you within 24 hours.`,
      },
      {
        q: "Is my data private?",
        a: "Yes. We use a device-based anonymous ID. We don't collect personal data unless you choose to provide it in your Account page or when purchasing a Booster.",
      },
    ];

    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.subHeader}>
          <TouchableOpacity onPress={() => setScreen("main")} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
          </TouchableOpacity>
          <Text style={styles.subTitle}>Help Center</Text>
          <View style={{ width: 32 }} />
        </View>

        <ScrollView style={{ flex: 1 }}>
          <View style={{ paddingHorizontal: 16, paddingTop: 8 }}>
            {FAQ.map((item, i) => (
              <FAQItem key={i} question={item.q} answer={item.a} />
            ))}

            <View style={styles.helpFooter}>
              <Text style={styles.helpFooterText}>
                Can't find what you're looking for?
              </Text>
              <TouchableOpacity style={styles.contactBtn} onPress={contactSupport}>
                <Ionicons name="mail-outline" size={18} color={PALETTE.text} />
                <Text style={styles.contactBtnText}>Contact Support</Text>
              </TouchableOpacity>
            </View>
          </View>
          <View style={{ height: 40 }} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ---- Main Account Screen ----
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={{ flex: 1 }}>
        <View style={styles.header}>
          <Ionicons name="person-circle-outline" size={80} color={PALETTE.accent2} />
          <Text style={styles.title}>My Account</Text>
        </View>

        {/* Personal Information */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Personal Information</Text>
            <TouchableOpacity onPress={() => setIsEditing(!isEditing)}>
              <Ionicons
                name={isEditing ? "close" : "create-outline"}
                size={24}
                color={PALETTE.accent2}
              />
            </TouchableOpacity>
          </View>

          <View style={styles.card}>
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Full Name</Text>
              <TextInput
                style={[styles.input, !isEditing && styles.inputDisabled]}
                value={accountInfo.name}
                onChangeText={(v) => handleChange("name", v)}
                placeholder="Enter your name"
                placeholderTextColor={PALETTE.subtext}
                editable={isEditing}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Email</Text>
              <TextInput
                style={[styles.input, !isEditing && styles.inputDisabled]}
                value={accountInfo.email}
                onChangeText={(v) => handleChange("email", v)}
                placeholder="Enter your email"
                placeholderTextColor={PALETTE.subtext}
                keyboardType="email-address"
                autoCapitalize="none"
                editable={isEditing}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Address</Text>
              <TextInput
                style={[styles.input, !isEditing && styles.inputDisabled]}
                value={accountInfo.address}
                onChangeText={(v) => handleChange("address", v)}
                placeholder="Enter your address"
                placeholderTextColor={PALETTE.subtext}
                editable={isEditing}
              />
            </View>

            <View style={styles.row}>
              <View style={[styles.inputGroup, { flex: 1, marginRight: 8 }]}>
                <Text style={styles.label}>City</Text>
                <TextInput
                  style={[styles.input, !isEditing && styles.inputDisabled]}
                  value={accountInfo.city}
                  onChangeText={(v) => handleChange("city", v)}
                  placeholder="City"
                  placeholderTextColor={PALETTE.subtext}
                  editable={isEditing}
                />
              </View>
              <View style={[styles.inputGroup, { flex: 1, marginLeft: 8 }]}>
                <Text style={styles.label}>Country</Text>
                <TextInput
                  style={[styles.input, !isEditing && styles.inputDisabled]}
                  value={accountInfo.country}
                  onChangeText={(v) => handleChange("country", v)}
                  placeholder="Country"
                  placeholderTextColor={PALETTE.subtext}
                  editable={isEditing}
                />
              </View>
            </View>

            {isEditing && (
              <TouchableOpacity
                style={styles.saveButton}
                onPress={saveAccountInfo}
                disabled={isSaving}
              >
                <Text style={styles.saveButtonText}>
                  {isSaving ? "Saving..." : "Save Changes"}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Billing & Payment */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Billing & Payment</Text>
          <View style={styles.card}>
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() =>
                Alert.alert(
                  "Payment Methods",
                  "Purchases are handled securely through the App Store (iOS) or Google Play (Android). No credit card is stored in the app.",
                  [{ text: "OK" }]
                )
              }
            >
              <Ionicons name="card-outline" size={24} color={PALETTE.text} />
              <View style={{ flex: 1 }}>
                <Text style={styles.menuItemText}>Payment Methods</Text>
                <Text style={styles.menuItemSubtext}>
                  Via App Store / Google Play
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>

            <View style={styles.divider} />

            <TouchableOpacity style={styles.menuItem} onPress={openBilling}>
              <Ionicons name="receipt-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Billing History</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>

            <View style={styles.divider} />

            <TouchableOpacity style={styles.menuItem} onPress={openInvoices}>
              <Ionicons name="document-text-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Invoices</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Support */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Support</Text>
          <View style={styles.card}>
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() => setScreen("help")}
            >
              <Ionicons name="help-circle-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Help Center</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>

            <View style={styles.divider} />

            <TouchableOpacity style={styles.menuItem} onPress={contactSupport}>
              <Ionicons name="mail-outline" size={24} color={PALETTE.text} />
              <View style={{ flex: 1 }}>
                <Text style={styles.menuItemText}>Contact Us</Text>
                <Text style={styles.menuItemSubtext}>{SUPPORT_EMAIL}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* App Info */}
        <View style={[styles.section, { marginBottom: 40 }]}>
          <View style={styles.appInfo}>
            <Text style={styles.appVersion}>Populr v1.0.0</Text>
            <Text style={styles.appCopyright}>
              © 2026 Populr App. All rights reserved.
            </Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ---- FAQ Accordion Item ----

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <TouchableOpacity
      style={styles.faqCard}
      onPress={() => setOpen(!open)}
      activeOpacity={0.7}
    >
      <View style={styles.faqHeader}>
        <Text style={styles.faqQuestion}>{question}</Text>
        <Ionicons
          name={open ? "chevron-up" : "chevron-down"}
          size={20}
          color={PALETTE.subtext}
        />
      </View>
      {open && <Text style={styles.faqAnswer}>{answer}</Text>}
    </TouchableOpacity>
  );
}

// ---- Styles ----

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },

  // Main header
  header: { alignItems: "center", paddingVertical: 30 },
  title: { fontSize: 24, fontWeight: "700", color: PALETTE.text, marginTop: 12 },

  // Sub-screen header
  subHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  backBtn: { width: 32 },
  subTitle: { fontSize: 18, fontWeight: "700", color: PALETTE.text },

  // Sections
  section: { marginTop: 8, paddingHorizontal: 16 },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: PALETTE.subtext,
    marginBottom: 12,
  },
  card: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  inputGroup: { marginBottom: 16 },
  label: { fontSize: 14, fontWeight: "500", color: PALETTE.subtext, marginBottom: 6 },
  input: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: PALETTE.text,
    fontSize: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  inputDisabled: { opacity: 0.7 },
  row: { flexDirection: "row" },
  saveButton: {
    backgroundColor: PALETTE.accent,
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  saveButtonText: { color: PALETTE.text, fontSize: 16, fontWeight: "600" },

  // Menu items
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    gap: 12,
  },
  menuItemText: { flex: 1, fontSize: 16, color: PALETTE.text },
  menuItemSubtext: { fontSize: 12, color: PALETTE.subtext, marginTop: 2 },
  divider: { height: 1, backgroundColor: PALETTE.border, marginVertical: 4 },

  // App info
  appInfo: { alignItems: "center", paddingVertical: 20 },
  appVersion: { fontSize: 14, color: PALETTE.subtext },
  appCopyright: { fontSize: 12, color: PALETTE.subtext, marginTop: 4 },

  // Center / Empty
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingTop: 80 },
  emptyText: { color: PALETTE.text, fontSize: 18, fontWeight: "600", marginTop: 16 },
  emptySubtext: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: "center",
    marginTop: 8,
    paddingHorizontal: 40,
  },

  // Transactions
  txCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  txRow: { flexDirection: "row", alignItems: "center" },
  txIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  txInfo: { flex: 1 },
  txTitle: { color: PALETTE.text, fontSize: 16, fontWeight: "700" },
  txDesc: { color: PALETTE.subtext, fontSize: 13, marginTop: 2 },
  txDate: { color: PALETTE.subtext, fontSize: 12, marginTop: 4 },
  txPrice: { color: PALETTE.green, fontSize: 18, fontWeight: "700" },

  // Invoice footer
  invoiceFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: PALETTE.border,
  },
  invoiceRef: { color: PALETTE.subtext, fontSize: 12 },
  invoiceStatus: { color: PALETTE.green, fontSize: 12, fontWeight: "700" },

  // FAQ
  faqCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  faqHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  faqQuestion: { color: PALETTE.text, fontSize: 15, fontWeight: "600", flex: 1, marginRight: 8 },
  faqAnswer: { color: PALETTE.subtext, fontSize: 14, lineHeight: 22, marginTop: 12 },

  // Help footer
  helpFooter: { alignItems: "center", marginTop: 20, paddingVertical: 20 },
  helpFooterText: { color: PALETTE.subtext, fontSize: 14, marginBottom: 12 },
  contactBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  contactBtnText: { color: PALETTE.text, fontSize: 16, fontWeight: "600" },
});

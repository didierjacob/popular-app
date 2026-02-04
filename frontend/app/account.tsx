import React, { useState, useEffect } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  border: "#2E6148",
  gold: "#FFD700",
};

const ACCOUNT_KEY = "popular_account_info";

interface AccountInfo {
  name: string;
  email: string;
  address: string;
  city: string;
  country: string;
  cardLast4?: string;
}

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
    setAccountInfo(prev => ({ ...prev, [field]: value }));
  };

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

        {/* Password Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Security</Text>
          <View style={styles.card}>
            <TouchableOpacity style={styles.menuItem}>
              <Ionicons name="lock-closed-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Change Password</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Billing Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Billing & Payment</Text>
          <View style={styles.card}>
            <TouchableOpacity style={styles.menuItem}>
              <Ionicons name="card-outline" size={24} color={PALETTE.text} />
              <View style={{ flex: 1 }}>
                <Text style={styles.menuItemText}>Payment Methods</Text>
                {accountInfo.cardLast4 && (
                  <Text style={styles.menuItemSubtext}>•••• {accountInfo.cardLast4}</Text>
                )}
              </View>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>

            <View style={styles.divider} />

            <TouchableOpacity style={styles.menuItem}>
              <Ionicons name="receipt-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Billing History</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>

            <View style={styles.divider} />

            <TouchableOpacity style={styles.menuItem}>
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
            <TouchableOpacity style={styles.menuItem}>
              <Ionicons name="help-circle-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Help Center</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>

            <View style={styles.divider} />

            <TouchableOpacity style={styles.menuItem}>
              <Ionicons name="chatbubble-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>Contact Us</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* App Info */}
        <View style={[styles.section, { marginBottom: 40 }]}>
          <View style={styles.appInfo}>
            <Text style={styles.appVersion}>Popular v1.0.0</Text>
            <Text style={styles.appCopyright}>© 2026 Popular App. All rights reserved.</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  header: {
    alignItems: "center",
    paddingVertical: 30,
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: PALETTE.text,
    marginTop: 12,
  },
  section: {
    marginTop: 8,
    paddingHorizontal: 16,
  },
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
  inputGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: "500",
    color: PALETTE.subtext,
    marginBottom: 6,
  },
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
  inputDisabled: {
    opacity: 0.7,
  },
  row: {
    flexDirection: "row",
  },
  saveButton: {
    backgroundColor: PALETTE.accent,
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  saveButtonText: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: "600",
  },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    gap: 12,
  },
  menuItemText: {
    flex: 1,
    fontSize: 16,
    color: PALETTE.text,
  },
  menuItemSubtext: {
    fontSize: 12,
    color: PALETTE.subtext,
    marginTop: 2,
  },
  divider: {
    height: 1,
    backgroundColor: PALETTE.border,
    marginVertical: 4,
  },
  appInfo: {
    alignItems: "center",
    paddingVertical: 20,
  },
  appVersion: {
    fontSize: 14,
    color: PALETTE.subtext,
  },
  appCopyright: {
    fontSize: 12,
    color: PALETTE.subtext,
    marginTop: 4,
  },
});

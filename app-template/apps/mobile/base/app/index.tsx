import { useState, useEffect } from "react";
import { View, Text, Pressable, ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import type { HealthCheckResponse } from "@repo/types";

export default function HomeScreen() {
  const [health, setHealth] = useState<HealthCheckResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const apiUrl = process.env.EXPO_PUBLIC_API_URL || "http://localhost:3000";

  const checkHealth = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${apiUrl}/api/health`);
      const data = await res.json();
      setHealth(data);
    } catch {
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <SafeAreaView className="flex-1 bg-canvas">
      <ScrollView contentContainerClassName="p-6 items-center">
        <View className="w-full max-w-md items-center py-8">
          <View className="px-3 py-1 rounded-full bg-surface-card border border-hairline mb-4">
            <Text className="text-xs text-muted font-mono">React Native · Expo SDK 58</Text>
          </View>

          <Text className="text-3xl font-bold text-ink mb-2 text-center">
            Mobile Client
          </Text>
          <Text className="text-sm text-body text-center mb-8">
            Styled with NativeWind v4 and powered by shared @repo/theme &amp; @repo/types.
          </Text>

          <View className="w-full bg-surface-soft p-5 rounded-2xl border border-hairline mb-6">
            <Text className="text-sm font-semibold text-ink mb-1">Backend Connection</Text>
            <Text className="text-xs text-muted mb-3 font-mono">{apiUrl}</Text>

            <View className="flex-row items-center justify-between">
              <View className="flex-row items-center gap-2">
                <View className={`w-2.5 h-2.5 rounded-full ${health?.status === "ok" ? "bg-success" : "bg-warning"}`} />
                <Text className="text-xs font-mono text-ink">
                  {health ? `Status: ${health.status}` : "Connecting..."}
                </Text>
              </View>

              <Pressable
                onPress={checkHealth}
                disabled={loading}
                className="bg-primary px-3 py-1.5 rounded-lg active:opacity-80"
              >
                <Text className="text-white text-xs font-medium">
                  {loading ? "Checking..." : "Refresh"}
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "auth_session_token";

export const getAuthToken = async (): Promise<string | null> => {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const setAuthToken = async (token: string): Promise<void> => {
  try {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  } catch (error) {
    console.error("Failed to store auth token:", error);
  }
};

export const removeAuthToken = async (): Promise<void> => {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch (error) {
    console.error("Failed to remove auth token:", error);
  }
};

export const getApiUrl = (): string => {
  return process.env.EXPO_PUBLIC_API_URL || "http://localhost:3000";
};

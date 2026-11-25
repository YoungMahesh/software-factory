import { betterAuth } from "better-auth";
import { bearer } from "better-auth/plugins/bearer";
import { loadWorkspaceEnv } from "./env";

loadWorkspaceEnv();

export const auth = betterAuth({
  secret: process.env.BETTER_AUTH_SECRET || "development-insecure-secret-key-32chars!!",
  baseURL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
  emailAndPassword: {
    enabled: true,
  },
  plugins: [
    bearer(),
  ],
});

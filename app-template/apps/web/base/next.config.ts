import type { NextConfig } from "next";
import { loadWorkspaceEnv } from "./lib/env";

loadWorkspaceEnv();

const nextConfig: NextConfig = {
  transpilePackages: ["@repo/theme", "@repo/types"],
};

export default nextConfig;

import type { NextConfig } from "next";
import { loadWorkspaceEnv } from "./lib/env";

loadWorkspaceEnv();

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@dashboard/theme", "@dashboard/types"],
};

export default nextConfig;

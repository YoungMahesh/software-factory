import type { NextConfig } from "next";
import { loadWorkspaceEnv } from "./lib/env";

loadWorkspaceEnv();

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;

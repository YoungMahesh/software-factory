import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@repo/theme", "@repo/types"],
};

export default nextConfig;

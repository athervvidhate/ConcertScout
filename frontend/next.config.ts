import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Dev scripts refuse other hosts, so a phone through a tunnel needs its host named here.
  allowedDevOrigins: process.env.DEV_ORIGINS?.split(","),
  images: {
    remotePatterns: [{ protocol: "https", hostname: "www.jambase.com", port: "", pathname: "/wp-content/uploads/**", search: "" }],
    minimumCacheTTL: 3600,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

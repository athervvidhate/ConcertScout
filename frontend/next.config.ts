import type { NextConfig } from "next";

// Vercel previews do not inherit Production variables. Refuse a broken public
// build instead of shipping the local :8443 fallback and a test bot token.
if (process.env.VERCEL === "1" && process.env.VERCEL_ENV !== "development") {
  const api = process.env.NEXT_PUBLIC_API_URL;
  let validApi = false;
  try {
    const url = new URL(api ?? "");
    validApi =
      url.protocol === "https:" &&
      !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash &&
      !api?.endsWith("/");
  } catch {
    // The required setting is reported below without exposing its value.
  }
  if (!validApi)
    throw new Error(
      "NEXT_PUBLIC_API_URL must be the public HTTPS API base URL, without credentials, query, fragment or a trailing slash.",
    );
  const siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  if (!siteKey?.trim() || /^[123]x0{20}/u.test(siteKey))
    throw new Error(
      "NEXT_PUBLIC_TURNSTILE_SITE_KEY must be a real public widget key for this deployment hostname; published test keys are local-only.",
    );
}

const nextConfig: NextConfig = {
  agentRules: false,
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Dev scripts refuse other hosts, so a phone through a tunnel needs its host named here.
  allowedDevOrigins: process.env.DEV_ORIGINS?.split(","),
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

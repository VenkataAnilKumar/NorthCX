import type { NextConfig } from "next";

// The browser talks to /api/northcx/*, which Next proxies to the NorthCX backend (no CORS needed).
const backend = process.env.NORTHCX_API_URL ?? "http://localhost:3000";

const config: NextConfig = {
  output: "standalone", // a self-contained server for the container image
  async headers() {
    // No inline-script allowance is needed for these, so they can be strict: the console cannot be framed, cannot load plugins, and cannot be re-based or posted elsewhere.
    return [{ source: "/:path*", headers: [
      { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ] }];
  },
  async rewrites() {
    return [{ source: "/api/northcx/:path*", destination: `${backend}/:path*` }];
  },
};

export default config;

import type { NextConfig } from "next";

// The browser talks to /api/northcx/*, which Next proxies to the NorthCX backend (no CORS needed).
const backend = process.env.NORTHCX_API_URL ?? "http://localhost:3000";

const config: NextConfig = {
  output: "standalone", // a self-contained server for the container image
  async rewrites() {
    return [{ source: "/api/northcx/:path*", destination: `${backend}/:path*` }];
  },
};

export default config;

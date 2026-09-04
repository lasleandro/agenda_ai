import type { NextConfig } from "next";

// Server-only. `rewrites()` runs on the server, so the FastAPI address is
// resolved from a non-public variable and never reaches the browser bundle.
// Production sets INTERNAL_API_URL (e.g. http://127.0.0.1:8005, the loopback
// FastAPI process in the same container). NEXT_PUBLIC_API_URL remains a
// fallback for setups that still rely on it; browser code should call
// relative /api/* and let this proxy forward it.
const API_URL =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8005";

const nextConfig: NextConfig = {
  // Self-contained production server (`.next/standalone/server.js`) for the
  // container image. No effect on `next dev`.
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

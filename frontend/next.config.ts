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
      {
        source: "/webhooks/:path*",
        destination: `${API_URL}/webhooks/:path*`,
      },
      {
        source: "/healthz",
        destination: `${API_URL}/health`,
      },
    ];
  },
  async headers() {
    if (process.env.NODE_ENV !== "production") {
      return [];
    }

    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data: blob:; font-src 'self' data: https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self' 'unsafe-inline'; connect-src 'self' https://photon.komoot.io; worker-src 'self' blob:",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains",
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;

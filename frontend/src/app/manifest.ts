import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Tennis OS",
    short_name: "Tennis OS",
    description: "WhatsApp Schedule Copilot for tennis instructors",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#4f46e5",
    icons: [
      {
        src: "/landing/logo.png",
        sizes: "1254x1254",
        type: "image/png",
      },
      {
        src: "/landing/logo.png",
        sizes: "1254x1254",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

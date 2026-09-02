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
        src: "/tennis.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/tennis.png",
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: "/tennis.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

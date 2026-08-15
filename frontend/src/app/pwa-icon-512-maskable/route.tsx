import { ImageResponse } from "next/og";
import { brandIconElement } from "@/lib/brand-icon";

export function GET() {
  return new ImageResponse(brandIconElement({ size: 512, maskable: true }), {
    width: 512,
    height: 512,
  });
}

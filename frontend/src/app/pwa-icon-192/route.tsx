import { ImageResponse } from "next/og";
import { brandIconElement } from "@/lib/brand-icon";

export function GET() {
  return new ImageResponse(brandIconElement({ size: 192 }), {
    width: 192,
    height: 192,
  });
}

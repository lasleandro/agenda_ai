import { ImageResponse } from "next/og";
import { brandIconElement } from "@/lib/brand-icon";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default async function AppleIcon() {
  return new ImageResponse(await brandIconElement(), size);
}

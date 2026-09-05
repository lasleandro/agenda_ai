import { ImageResponse } from "next/og";
import { brandIconElement } from "@/lib/brand-icon";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default async function Icon() {
  return new ImageResponse(await brandIconElement(), size);
}

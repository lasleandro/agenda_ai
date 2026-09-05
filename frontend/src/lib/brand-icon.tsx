import { readFile } from "node:fs/promises";
import { join } from "node:path";

// ImageResponse renders a PNG itself, so next/image optimization is not applicable here.
/* eslint-disable @next/next/no-img-element */
export async function brandIconElement() {
  const logo = await readFile(
    join(process.cwd(), "public", "landing", "logo.png")
  );

  return (
    <img
      alt=""
      src={`data:image/png;base64,${logo.toString("base64")}`}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
      }}
    />
  );
}

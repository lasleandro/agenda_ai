import Image from "next/image";

interface BrandLogoProps {
  size: number;
  className?: string;
  priority?: boolean;
}

export function BrandLogo({
  size,
  className,
  priority = false,
}: BrandLogoProps) {
  return (
    <Image
      src="/landing/logo.png"
      alt=""
      width={size}
      height={size}
      priority={priority}
      className={`shrink-0 rounded-lg ${className ?? ""}`}
    />
  );
}

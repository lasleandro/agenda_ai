// Placeholder app icon — reuses the sidebar's gradient "T" mark
// (see components/layout/sidebar.tsx) until real branding assets exist.
export function brandIconElement({
  size,
  maskable = false,
}: {
  size: number;
  maskable?: boolean;
}) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)",
        borderRadius: maskable ? 0 : Math.round(size * 0.22),
      }}
    >
      <div
        style={{
          display: "flex",
          fontSize: Math.round(size * (maskable ? 0.38 : 0.56)),
          fontWeight: 700,
          color: "#ffffff",
          fontFamily: "sans-serif",
        }}
      >
        T
      </div>
    </div>
  );
}

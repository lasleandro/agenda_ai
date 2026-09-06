import { AppShell } from "@/components/layout/app-shell";
import { AuthGuard } from "@/components/layout/auth-guard";
import { SessionProvider } from "@/lib/session-context";

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <AuthGuard>
        <AppShell>{children}</AppShell>
      </AuthGuard>
    </SessionProvider>
  );
}

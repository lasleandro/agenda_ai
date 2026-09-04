"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, CalendarClock, ClipboardList, LogOut } from "lucide-react";

import { fetchAccountRequestSummary } from "@/lib/api";
import { logout } from "@/lib/auth";
import { cn } from "@/lib/utils";

type AdminSection = "tenants" | "requests" | "tasks";

interface PlatformAdminHeaderProps {
  active: AdminSection;
  adminEmail?: string | null;
  pendingCount?: number;
}

const links = [
  { key: "tenants" as const, href: "/admin/select-tenant", label: "Tenants", icon: Building2 },
  {
    key: "requests" as const,
    href: "/admin/account-requests",
    label: "Solicitações",
    icon: ClipboardList,
  },
  {
    key: "tasks" as const,
    href: "/admin/scheduled-tasks",
    label: "Tarefas agendadas",
    icon: CalendarClock,
  },
];

export function PlatformAdminHeader({
  active,
  adminEmail,
  pendingCount,
}: PlatformAdminHeaderProps) {
  const router = useRouter();
  const [loadedPendingCount, setLoadedPendingCount] = useState<number | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    if (pendingCount !== undefined) return;
    let current = true;
    void fetchAccountRequestSummary()
      .then((result) => {
        if (current) setLoadedPendingCount(result.pending);
      })
      .catch(() => {
        if (current) setLoadedPendingCount(null);
      });
    return () => {
      current = false;
    };
  }, [pendingCount]);

  async function handleLogout() {
    setSigningOut(true);
    try {
      await logout();
      router.replace("/login");
    } finally {
      setSigningOut(false);
    }
  }

  const visiblePendingCount = pendingCount ?? loadedPendingCount;

  return (
    <header className="mb-8 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/admin/select-tenant" className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 text-sm font-bold text-white">
            T
          </span>
          <span>
            <span className="block text-sm font-semibold tracking-tight text-foreground">
              Painel Admin
            </span>
            {adminEmail && (
              <span className="block max-w-48 truncate text-xs text-muted-foreground">
                {adminEmail}
              </span>
            )}
          </span>
        </Link>

        <nav
          className="order-3 flex w-full gap-1 overflow-x-auto border-t border-border pt-3 sm:order-none sm:ml-auto sm:w-auto sm:border-0 sm:pt-0"
          aria-label="Navegação administrativa"
        >
          {links.map(({ key, href, label, icon: Icon }) => (
            <Link
              key={key}
              href={href}
              aria-current={active === key ? "page" : undefined}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium",
                active === key
                  ? "bg-indigo-500/10 text-indigo-700"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
              {key === "requests" && visiblePendingCount !== null && visiblePendingCount > 0 && (
                <span
                  className="min-w-5 rounded-full bg-indigo-600 px-1.5 py-0.5 text-center text-[10px] leading-none text-white"
                  aria-label={`${visiblePendingCount} solicitações pendentes`}
                >
                  {visiblePendingCount > 99 ? "99+" : visiblePendingCount}
                </span>
              )}
            </Link>
          ))}
        </nav>

        <button
          type="button"
          onClick={() => void handleLogout()}
          disabled={signingOut}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50 sm:ml-0"
        >
          <LogOut className="h-4 w-4" />
          {signingOut ? "Saindo..." : "Sair"}
        </button>
      </div>
    </header>
  );
}


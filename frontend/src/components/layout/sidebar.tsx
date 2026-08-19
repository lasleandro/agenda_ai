"use client";

import { useEffect, useState } from "react";
import { Calendar, CircleDollarSign, Users, Settings, LayoutGrid, LogOut, MapPin, MessageSquare, Repeat } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  fetchSession,
  logout,
  sessionHasFeature,
  type SessionUser,
} from "@/lib/auth";

// href: undefined means "not built yet" — rendered but not a real link.
// Mock Chat is a dev-only testing aid (see README "Dev tool — mock WhatsApp
// chat"); remove this entry once real WhatsApp traffic replaces it.
const navItems = [
  { label: "Agenda", icon: Calendar, href: "/" },
  { label: "Clientes", icon: Users, href: "/clientes" },
  { label: "Meus Locais", icon: MapPin, href: "/places" },
  {
    label: "Financeiro",
    icon: CircleDollarSign,
    href: "/financeiro",
    feature: "commercial_financials",
  },
  { label: "Painel", icon: LayoutGrid, href: undefined },
  { label: "Configurações", icon: Settings, href: "/minhas-regras" },
  { label: "Mock Chat", icon: MessageSquare, href: "/dev/mock-chat" },
];

export function Sidebar() {
  return (
    <aside
      className="hidden md:flex md:w-60 md:flex-col shrink-0"
      style={{ background: "var(--sidebar-bg)" }}
    >
      <SidebarContent />
    </aside>
  );
}

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    fetchSession().then(setUser);
  }, []);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  const displayName = user?.professional_name ?? user?.email ?? "";
  const roleLabel = user?.impersonating
    ? "Impersonando (admin)"
    : user?.role === "platform_admin"
      ? "Admin da plataforma"
      : "Profissional";
  const initials = displayName
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <>
      <div className="h-16 flex items-center gap-2 px-5">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white font-bold text-sm">
          T
        </div>
        <span className="text-white font-semibold text-[15px] tracking-tight">
          Tennis OS
        </span>
      </div>

      {user?.impersonating && (
        <Link
          href="/admin/select-tenant"
          title="Trocar de tenant"
          className="mx-3 mb-2 flex items-center gap-2 rounded-md bg-indigo-500/20 px-3 py-2 text-xs font-medium text-indigo-200 hover:bg-indigo-500/30"
          onClick={onNavigate}
        >
          <Repeat className="h-3.5 w-3.5" />
          Trocar tenant
        </Link>
      )}

      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {navItems
          .filter(
            (item) =>
              !("feature" in item) ||
              sessionHasFeature(user, item.feature as string)
          )
          .map((item) => {
          const active =
            item.href != null &&
            (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));
          const className = cn(
            "w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            active ? "text-white" : "text-[var(--sidebar-text)] hover:text-white",
            item.href == null && "cursor-default opacity-60"
          );
          const style = { background: active ? "var(--sidebar-active)" : "transparent" };
          const hoverProps = {
            onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
              if (!active) e.currentTarget.style.background = "var(--sidebar-hover)";
            },
            onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
              if (!active) e.currentTarget.style.background = "transparent";
            },
          };

          if (item.href) {
            return (
              <Link
                key={item.label}
                href={item.href}
                className={className}
                style={style}
                onClick={onNavigate}
                {...hoverProps}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          }

          return (
            <button key={item.label} className={className} style={style} disabled {...hoverProps}>
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          );
          })}
      </nav>

      <div className="px-3 py-4 border-t border-white/10">
        <div className="flex items-center gap-2 px-3 py-2 rounded-md">
          <div className="h-8 w-8 rounded-full bg-indigo-400/80 flex items-center justify-center text-white text-xs font-semibold">
            {initials || "?"}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-white text-sm font-medium truncate">
              {displayName}
            </span>
            <span className="text-[var(--sidebar-text)] text-xs truncate">
              {roleLabel}
            </span>
          </div>
          <button
            onClick={handleLogout}
            title="Sair"
            className="ml-auto text-[var(--sidebar-text)] hover:text-white transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}

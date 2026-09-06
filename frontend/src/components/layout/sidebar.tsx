"use client";

import {
  Calendar,
  CircleDollarSign,
  FlaskConical,
  LogOut,
  MessageSquare,
  Repeat,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import Image, { type StaticImageData } from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { BrandLogo } from "./brand-logo";
import { logout, operationNeedsSetup, sessionHasFeature } from "@/lib/auth";
import { useSession } from "@/lib/session-context";
import whatsappCircular from "../../../assets/whatsapp_circular.png";

type NavItem = {
  label: string;
  icon: LucideIcon;
  href: string;
  imageSrc?: StaticImageData;
  feature?: string;
  exact?: boolean;
  activePrefixes?: string[];
  platformAdminOnly?: boolean;
  badge?: string;
};

const SETUP_HREF = "/minhas-regras";

const primaryNavItems: NavItem[] = [
  { label: "Agenda", icon: Calendar, href: "/agenda", exact: true },
  { label: "Clientes", icon: Users, href: "/clientes" },
  {
    label: "Financeiro",
    icon: CircleDollarSign,
    href: "/financeiro",
    feature: "commercial_financials",
    exact: true,
  },
  {
    label: "Simulador financeiro",
    icon: FlaskConical,
    href: "/financeiro/simulador",
    feature: "commercial_financials",
  },
  {
    label: "Minha Operação",
    icon: Settings,
    href: "/minhas-regras",
    // Locais live inside this area as a tab, but keep their own detail route.
    activePrefixes: ["/places"],
  },
  {
    label: "Mock Chat",
    icon: MessageSquare,
    href: "/dev/mock-chat",
    platformAdminOnly: true,
  },
];

const whatsappNavItem: NavItem = {
  label: "Ative o Whatsapp",
  icon: MessageSquare,
  imageSrc: whatsappCircular,
  href: "/configuracoes/whatsapp",
};

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
  const { user } = useSession();

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
  const visiblePrimaryNavItems = primaryNavItems.filter(
    (item) =>
      (!item.feature || sessionHasFeature(user, item.feature)) &&
      (!item.platformAdminOnly ||
        (user?.role === "platform_admin" && Boolean(user.professional_id)))
  );

  // While first-session setup is unfinished, hoist "Minha Operação" to the top
  // and badge it. Both revert automatically once the operation is configured.
  const needsSetup = operationNeedsSetup(user);
  const orderedPrimaryNavItems = needsSetup
    ? (() => {
        const decorated = visiblePrimaryNavItems.map((item) =>
          item.href === SETUP_HREF
            ? { ...item, badge: "Comece aqui" }
            : item
        );
        const setupIndex = decorated.findIndex(
          (item) => item.href === SETUP_HREF
        );
        if (setupIndex <= 0) return decorated;
        const [setupItem] = decorated.splice(setupIndex, 1);
        return [setupItem, ...decorated];
      })()
    : visiblePrimaryNavItems;

  function renderNavItem(item: NavItem) {
    const active =
      (item.exact ? pathname === item.href : pathname.startsWith(item.href)) ||
      item.activePrefixes?.some((prefix) => pathname.startsWith(prefix));
    const className = cn(
      "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
      active ? "text-white" : "text-[var(--sidebar-text)] hover:text-white"
    );
    const style = {
      background: active ? "var(--sidebar-active)" : "transparent",
    };
    const hoverProps = {
      onMouseEnter: (event: React.MouseEvent<HTMLElement>) => {
        if (!active) event.currentTarget.style.background = "var(--sidebar-hover)";
      },
      onMouseLeave: (event: React.MouseEvent<HTMLElement>) => {
        if (!active) event.currentTarget.style.background = "transparent";
      },
    };

    return (
      <Link
        key={item.label}
        href={item.href}
        className={className}
        style={style}
        onClick={onNavigate}
        {...hoverProps}
      >
        {item.imageSrc ? (
          <Image src={item.imageSrc} alt="" width={16} height={16} />
        ) : (
          <item.icon className="h-4 w-4 shrink-0" />
        )}
        <span className="truncate">{item.label}</span>
        {item.badge && (
          <span className="ml-auto shrink-0 rounded-full bg-[var(--sidebar-active)] px-1.5 py-0.5 text-[11px] font-medium text-white pointer-events-none">
            {item.badge}
          </span>
        )}
      </Link>
    );
  }

  return (
    <>
      <div className="h-16 flex items-center gap-2 px-5">
        <BrandLogo size={32} priority />
        <span className="text-white font-semibold text-[15px] tracking-tight">
          Tennis OS
        </span>
      </div>

      {user?.impersonating && (
        <Link
          href="/admin/select-tenant"
          title="Trocar de conta"
          className="mx-3 mb-2 flex items-center gap-2 rounded-md bg-indigo-500/20 px-3 py-2 text-xs font-medium text-indigo-200 hover:bg-indigo-500/30"
          onClick={onNavigate}
        >
          <Repeat className="h-3.5 w-3.5" />
          Trocar de conta
        </Link>
      )}

      <nav className="flex min-h-0 flex-1 flex-col px-3 py-2">
        <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
          {orderedPrimaryNavItems.map(renderNavItem)}
        </div>
        <div className="mt-2 shrink-0">{renderNavItem(whatsappNavItem)}</div>
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

"use client";

import { Calendar, Users, Settings, LayoutGrid, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { logout } from "@/lib/auth";

const navItems = [
  { label: "Agenda", icon: Calendar, active: true },
  { label: "Contatos", icon: Users, active: false },
  { label: "Painel", icon: LayoutGrid, active: false },
  { label: "Configurações", icon: Settings, active: false },
];

export function Sidebar() {
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <aside
      className="hidden md:flex md:w-60 md:flex-col shrink-0"
      style={{ background: "var(--sidebar-bg)" }}
    >
      <div className="h-16 flex items-center gap-2 px-5">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white font-bold text-sm">
          A
        </div>
        <span className="text-white font-semibold text-[15px] tracking-tight">
          Agenda AI
        </span>
      </div>

      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {navItems.map((item) => (
          <button
            key={item.label}
            className={cn(
              "w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              item.active
                ? "text-white"
                : "text-[var(--sidebar-text)] hover:text-white"
            )}
            style={{
              background: item.active ? "var(--sidebar-active)" : "transparent",
            }}
            onMouseEnter={(e) => {
              if (!item.active)
                e.currentTarget.style.background = "var(--sidebar-hover)";
            }}
            onMouseLeave={(e) => {
              if (!item.active) e.currentTarget.style.background = "transparent";
            }}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </button>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-white/10">
        <div className="flex items-center gap-2 px-3 py-2 rounded-md">
          <div className="h-8 w-8 rounded-full bg-indigo-400/80 flex items-center justify-center text-white text-xs font-semibold">
            JS
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-white text-sm font-medium truncate">
              João Silva
            </span>
            <span className="text-[var(--sidebar-text)] text-xs truncate">
              Profissional
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
    </aside>
  );
}

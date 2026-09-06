"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { operationNeedsSetup } from "@/lib/auth";
import { useSession } from "@/lib/session-context";

/** Redirects to /login if there is no valid session cookie, and a
 * platform_admin with no tenant selected to the tenant tile grid — an
 * admin session is never allowed to render tenant-scoped pages without
 * first impersonating a tenant (multi-tenancy roadmap Phase D).
 *
 * For a tenant whose first-session setup is unfinished, an /agenda *landing*
 * (bookmark, reload, direct URL) is redirected once to /minhas-regras
 * (first-user onboarding roadmap). Only the first resolved render is treated
 * as a landing; later client-side navigation to /agenda is not fought and
 * shows the setup empty state instead. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading } = useSession();
  const needsTenant = user?.role === "platform_admin" && !user.professional_id;
  const initialLandingHandled = useRef(false);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (needsTenant) {
      router.replace("/admin/select-tenant");
      return;
    }
    if (!initialLandingHandled.current) {
      initialLandingHandled.current = true;
      if (pathname === "/agenda" && operationNeedsSetup(user)) {
        router.replace("/minhas-regras");
      }
    }
  }, [loading, user, needsTenant, pathname, router]);

  // Render optimistically as soon as a session (cached or fresh) is known;
  // the effect above still redirects if the authoritative check disagrees.
  if (!user || needsTenant) return null;
  return <>{children}</>;
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchSession } from "@/lib/auth";

/** Redirects to /login if there is no valid session cookie, and a
 * platform_admin with no tenant selected to the tenant tile grid — an
 * admin session is never allowed to render tenant-scoped pages without
 * first impersonating a tenant (multi-tenancy roadmap Phase D). */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let active = true;
    fetchSession().then((user) => {
      if (!active) return;
      if (!user) {
        router.replace("/login");
        return;
      }
      if (user.role === "platform_admin" && !user.professional_id) {
        router.replace("/admin/select-tenant");
        return;
      }
      setChecked(true);
    });
    return () => {
      active = false;
    };
  }, [router]);

  if (!checked) return null;
  return <>{children}</>;
}

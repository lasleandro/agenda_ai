"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchSession } from "@/lib/auth";

/** Redirects to /login if there is no valid session cookie. */
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
      setChecked(true);
    });
    return () => {
      active = false;
    };
  }, [router]);

  if (!checked) return null;
  return <>{children}</>;
}

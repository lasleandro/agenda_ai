"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchSession } from "@/lib/auth";

/** Landing-page call to action that points to /login for anonymous visitors
 * and switches to /agenda once a session cookie is detected, so a logged-in
 * user is never sent back through the login screen. */
export function LandingEnterCta({
  className,
  withArrow = false,
}: {
  className?: string;
  withArrow?: boolean;
}) {
  const router = useRouter();
  const [href, setHref] = useState("/login");
  const [label, setLabel] = useState("Entrar");

  useEffect(() => {
    let active = true;
    fetchSession().then((user) => {
      if (active && user) {
        setHref("/agenda");
        setLabel("Ir para a agenda");
        router.replace("/agenda");
      }
    });
    return () => {
      active = false;
    };
  }, [router]);

  return (
    <a className={className} href={href}>
      {label}
      {withArrow && <span aria-hidden="true">&rarr;</span>}
    </a>
  );
}

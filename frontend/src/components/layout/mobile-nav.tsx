"use client";

import { useState } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SidebarContent } from "./sidebar";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <div
        className="md:hidden h-14 flex items-center gap-2 px-4 shrink-0 border-b border-[var(--border-subtle)]"
      >
        <DialogPrimitive.Trigger
          render={
            <Button variant="ghost" size="icon-sm" aria-label="Abrir menu" />
          }
        >
          <Menu className="h-5 w-5" />
        </DialogPrimitive.Trigger>
        <span className="font-semibold text-[15px] tracking-tight">
          Tennis OS
        </span>
      </div>

      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/30 duration-100 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup
          className="fixed inset-y-0 left-0 z-50 flex h-full w-72 max-w-[80vw] flex-col outline-none duration-150 data-open:animate-in data-open:slide-in-from-left data-closed:animate-out data-closed:slide-out-to-left"
          style={{ background: "var(--sidebar-bg)" }}
        >
          <DialogPrimitive.Title className="sr-only">Menu</DialogPrimitive.Title>
          <SidebarContent onNavigate={() => setOpen(false)} />
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

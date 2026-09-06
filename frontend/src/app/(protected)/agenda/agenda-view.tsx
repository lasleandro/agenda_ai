"use client";

import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { WeekCalendar } from "@/components/calendar/week-calendar";
import { buttonVariants } from "@/components/ui/button";
import { operationNeedsSetup } from "@/lib/auth";
import { useSession } from "@/lib/session-context";

/** Shows a setup prompt instead of the week grid while the tenant's operation
 * is unconfigured (no Local and no work journey). Advisory only — it never
 * blocks navigation, and it clears once setup is complete. */
export function AgendaView() {
  const { user } = useSession();

  if (operationNeedsSetup(user)) {
    return <AgendaSetupPrompt />;
  }
  return <WeekCalendar />;
}

function AgendaSetupPrompt() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 p-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <CalendarClock className="h-6 w-6" />
      </div>
      <div className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">
          Sua agenda aparece aqui
        </h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          Cadastre seu primeiro local de atendimento e sua jornada de trabalho
          para começar a usar a agenda.
        </p>
      </div>
      <Link href="/minhas-regras" className={buttonVariants({ size: "lg" })}>
        Comece aqui
      </Link>
    </div>
  );
}

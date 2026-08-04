"use client";

import { Badge } from "@/components/ui/badge";
import { STATUS_LABELS } from "@/lib/calendar-utils";
import { cn } from "@/lib/utils";

export function StatusBadge({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? status;
  const colorMap: Record<string, string> = {
    tentative: "bg-amber-100 text-amber-800 border-amber-200",
    confirmed: "bg-emerald-100 text-emerald-800 border-emerald-200",
    cancelled: "bg-red-100 text-red-800 border-red-200",
    completed: "bg-violet-100 text-violet-800 border-violet-200",
  };

  return (
    <Badge
      variant="outline"
      className={cn("font-medium", colorMap[status] ?? "")}
    >
      {label}
    </Badge>
  );
}

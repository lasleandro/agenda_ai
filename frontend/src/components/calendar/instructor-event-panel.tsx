"use client";

import { Calendar, CircleDollarSign, Clock, FileText, MapPin, Tag } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { formatFullDate, formatTimeRange } from "@/lib/calendar-utils";
import { formatBrlFromCents } from "@/lib/financial-utils";
import { EVENT_TYPE_LABELS } from "@/lib/ontology-utils";
import type { InstructorEvent } from "@/lib/types";

export function InstructorEventPanel({
  event,
  open,
  onOpenChange,
}: {
  event: InstructorEvent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!event) return null;

  const eventType = EVENT_TYPE_LABELS[event.event_type] ?? event.event_type;
  const title = event.title || eventType;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          <div className="flex items-center gap-3 text-sm">
            <Tag className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span>{eventType}</span>
          </div>

          <Separator />

          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-3">
              <Calendar className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="capitalize">{formatFullDate(event.start_at)}</span>
            </div>
            <div className="flex items-center gap-3">
              <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span>{formatTimeRange(event.start_at, event.end_at)}</span>
            </div>
            {event.place_name && (
              <div className="flex items-center gap-3">
                <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span>{event.place_name}</span>
              </div>
            )}
            {event.income_cents !== null && (
              <div className="flex items-center gap-3">
                <CircleDollarSign className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span>Receita prevista: {formatBrlFromCents(event.income_cents)}</span>
              </div>
            )}
            {event.note && (
              <div className="flex items-start gap-3">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="whitespace-pre-wrap">{event.note}</span>
              </div>
            )}
          </div>

          <Separator />

          <p className="text-xs text-muted-foreground">
            Criado em {new Date(event.created_at).toLocaleString("pt-BR")}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

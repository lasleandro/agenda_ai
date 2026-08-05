"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "./status-badge";
import { fetchAppointment } from "@/lib/api";
import { formatFullDate, formatTimeRange } from "@/lib/calendar-utils";
import type { AppointmentDetail } from "@/lib/types";
import { Calendar, Clock, User, Tag, Link2, MapPin } from "lucide-react";

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function AppointmentPanel({
  appointmentId,
  open,
  onOpenChange,
}: {
  appointmentId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [result, setResult] = useState<{
    appointmentId: string;
    detail: AppointmentDetail | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    if (!appointmentId || !open) return;
    fetchAppointment(appointmentId)
      .then((detail) => setResult({ appointmentId, detail, error: null }))
      .catch((error) =>
        setResult({
          appointmentId,
          detail: null,
          error: error instanceof Error ? error.message : "Falha ao carregar",
        })
      );
  }, [appointmentId, open]);

  const currentResult = result?.appointmentId === appointmentId ? result : null;
  const detail = currentResult?.detail ?? null;
  const error = currentResult?.error ?? null;
  const loading = Boolean(open && appointmentId && !currentResult);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="sr-only">Detalhes do agendamento</DialogTitle>
        </DialogHeader>

        {loading && (
          <div className="py-10 text-center text-sm text-muted-foreground">
            Carregando...
          </div>
        )}

        {error && (
          <div className="py-10 text-center text-sm text-destructive">
            Erro: {error}
          </div>
        )}

        {detail && !loading && (
          <div className="space-y-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <Avatar className="h-11 w-11">
                  <AvatarFallback className="bg-indigo-100 text-indigo-700 font-semibold">
                    {initials(detail.contact_name)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p className="font-semibold text-base leading-tight">
                    {detail.contact_name}
                  </p>
                  <p className="text-sm text-muted-foreground capitalize">
                    {detail.service}
                  </p>
                </div>
              </div>
              <StatusBadge status={detail.status} />
            </div>

            <Separator />

            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-3">
                <Calendar className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="capitalize">
                  {formatFullDate(detail.start_at)}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                <span>{formatTimeRange(detail.start_at, detail.end_at)}</span>
              </div>
              <div className="flex items-center gap-3">
                <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="capitalize">{detail.service}</span>
              </div>
              {detail.place_name && (
                <div className="flex items-center gap-3">
                  <MapPin className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span>{detail.place_name}</span>
                </div>
              )}
              <div className="flex items-center gap-3">
                <User className="h-4 w-4 text-muted-foreground shrink-0" />
                <span>Origem: {detail.source}</span>
              </div>
              {detail.recurrence_rule && (
                <div className="flex items-center gap-3">
                  <Link2 className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span>Recorrência: {detail.recurrence_rule}</span>
                </div>
              )}
            </div>

            <Separator />

            <p className="text-xs text-muted-foreground">
              Criado em{" "}
              {new Date(detail.created_at).toLocaleString("pt-BR")} · Atualizado em{" "}
              {new Date(detail.updated_at).toLocaleString("pt-BR")}
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

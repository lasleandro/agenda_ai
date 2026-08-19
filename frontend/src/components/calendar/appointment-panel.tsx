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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StatusBadge } from "./status-badge";
import { fetchAppointment, fetchRevenuePreview } from "@/lib/api";
import { formatFullDate, formatTimeRange } from "@/lib/calendar-utils";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type { AppointmentDetail } from "@/lib/types";
import {
  Calendar,
  CircleHelp,
  CircleDollarSign,
  Clock,
  Link2,
  MapPin,
  Tag,
  User,
} from "lucide-react";

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
  occurrenceDate,
  open,
  onOpenChange,
}: {
  appointmentId: string | null;
  occurrenceDate?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [result, setResult] = useState<{
    requestKey: string;
    detail: AppointmentDetail | null;
    error: string | null;
  } | null>(null);
  const [revenue, setRevenue] = useState<{
    requestKey: string;
    estimatedRevenueCents: number | null;
    capacityRevenueCents?: number | null;
  } | null>(null);
  const requestKey = `${appointmentId ?? ""}:${occurrenceDate ?? ""}`;

  useEffect(() => {
    if (!appointmentId || !open) return;
    let active = true;
    fetchAppointment(appointmentId, occurrenceDate)
      .then((detail) => {
        if (!active) return;
        setResult({ requestKey, detail, error: null });
        const date = detail.occurrence_date ?? occurrenceDate;
        if (!date) return;
        fetchRevenuePreview("appointment", detail.id, date)
          .then((preview) => {
            if (active) {
              setRevenue({
                requestKey,
                estimatedRevenueCents: preview.estimated_revenue_cents,
                capacityRevenueCents: preview.capacity_revenue_cents,
              });
            }
          })
          .catch(() => {
            // Revenue is optional in the Agenda and must not block its panel.
          });
      })
      .catch((error) =>
        active &&
        setResult({
          requestKey,
          detail: null,
          error: error instanceof Error ? error.message : "Falha ao carregar",
        })
      );
    return () => {
      active = false;
    };
  }, [appointmentId, occurrenceDate, open, requestKey]);

  const currentResult = result?.requestKey === requestKey ? result : null;
  const detail = currentResult?.detail ?? null;
  const error = currentResult?.error ?? null;
  const loading = Boolean(open && appointmentId && !currentResult);
  const currentRevenue = revenue?.requestKey === requestKey ? revenue : null;

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
                    {detail.participants && detail.participants.length > 1
                      ? detail.participants.map((p) => p.display_name).join(" + ")
                      : detail.contact_name}
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
                {detail.is_exception && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                    Reagendado
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                <span>{formatTimeRange(detail.start_at, detail.end_at)}</span>
              </div>
              <div className="flex items-center gap-3">
                <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="capitalize">{detail.service}</span>
              </div>
              {currentRevenue && (
                <div className="flex items-center gap-3">
                  <CircleDollarSign className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span>
                    {detail.class_type === "group" &&
                    (detail.participants?.length ?? 1) < 4
                      ? "Receita corrente"
                      : "Receita estimada"}
                    : {" "}
                    {formatBrlFromCents(currentRevenue.estimatedRevenueCents)}
                  </span>
                  {detail.class_type === "group" &&
                    (detail.participants?.length ?? 1) < 4 && (
                      <Tooltip>
                        <TooltipTrigger
                          className="text-muted-foreground"
                          aria-label="Como a receita corrente é calculada"
                        >
                          <CircleHelp className="h-3.5 w-3.5" />
                        </TooltipTrigger>
                        <TooltipContent>
                          Receita estimada com os participantes atualmente
                          atribuídos a este grupo.
                        </TooltipContent>
                      </Tooltip>
                    )}
                </div>
              )}
              {detail.class_type === "group" &&
                (detail.participants?.length ?? 1) < 4 &&
                currentRevenue?.capacityRevenueCents !== undefined && (
                  <div className="flex items-center gap-3">
                    <CircleDollarSign className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span>
                      Capacidade total de receita: {" "}
                      {formatBrlFromCents(currentRevenue.capacityRevenueCents)}
                    </span>
                    <Tooltip>
                      <TooltipTrigger
                        className="text-muted-foreground"
                        aria-label="Como a capacidade total de receita é calculada"
                      >
                        <CircleHelp className="h-3.5 w-3.5" />
                      </TooltipTrigger>
                      <TooltipContent>
                        Receita estimada para esta mesma aula com quatro clientes,
                        usando as regras de preço do horário e local.
                      </TooltipContent>
                    </Tooltip>
                  </div>
                )}
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

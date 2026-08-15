"use client";

import { useEffect, useState } from "react";
import {
  Calendar,
  CircleDollarSign,
  CircleHelp,
  Clock,
  GraduationCap,
  MapPin,
  Repeat,
  Users,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  fetchGroupFinancials,
  fetchRecurringGroup,
  fetchRevenuePreview,
  updateGroupFinancials,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import {
  CommercialFieldsCard,
  commercialStatusLabel,
  financialSourceLabel,
} from "@/components/financial/commercial-fields-card";
import { formatBrlFromCents } from "@/lib/financial-utils";
import {
  CONTACT_LEVEL_LABELS,
  DAY_LABELS,
  formatTime,
} from "@/lib/ontology-utils";
import type {
  CommercialOverrideInput,
  GroupFinancialDetail,
  RecurringGroupDetail,
  RevenuePreviewDetail,
} from "@/lib/types";

function scheduleLabel(group: RecurringGroupDetail): string {
  if (group.recurrence_type === "once" && group.scheduled_date) {
    return new Date(`${group.scheduled_date}T12:00:00`).toLocaleDateString("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  }
  return `Toda ${DAY_LABELS[group.day_of_week].toLowerCase()}`;
}

export function GroupDetailsDialog({
  groupId,
  occurrenceDate,
  open,
  onOpenChange,
}: {
  groupId: string | null;
  occurrenceDate?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [result, setResult] = useState<{
    groupId: string;
    detail: RecurringGroupDetail | null;
    error: string | null;
  } | null>(null);
  const [financialCapability, setFinancialCapability] = useState<{
    groupId: string;
    enabled: boolean;
  } | null>(null);
  const [financialResult, setFinancialResult] = useState<{
    groupId: string;
    detail: GroupFinancialDetail | null;
  } | null>(null);
  const [financialError, setFinancialError] = useState<string | null>(null);
  const [revenuePreview, setRevenuePreview] = useState<{
    groupId: string;
    occurrenceDate: string;
    detail: RevenuePreviewDetail;
  } | null>(null);

  useEffect(() => {
    if (!groupId || !open) return;
    let active = true;
    fetchRecurringGroup(groupId)
      .then((detail) => {
        if (active) setResult({ groupId, detail, error: null });
      })
      .catch((error) => {
        if (active) {
          setResult({
            groupId,
            detail: null,
            error: error instanceof Error ? error.message : "Falha ao carregar grupo",
          });
        }
      });
    fetchSession().then((user) => {
      if (!active) return;
      setFinancialError(null);
      const enabled = sessionHasFeature(user, "commercial_financials");
      setFinancialCapability({ groupId, enabled });
      if (!enabled) return;
      if (occurrenceDate) {
        fetchRevenuePreview("recurring_slot", groupId, occurrenceDate)
          .then((detail) => {
            if (active) {
              setRevenuePreview({ groupId, occurrenceDate, detail });
            }
          })
          .catch(() => {
            // The financial preview must not block the group details panel.
          });
      }
      fetchGroupFinancials(groupId)
        .then((detail) => {
          if (active) setFinancialResult({ groupId, detail });
        })
        .catch((caught) => {
          if (active) {
            setFinancialError(
              caught instanceof Error
                ? caught.message
                : "Falha ao carregar dados financeiros"
            );
          }
        });
    });
    return () => {
      active = false;
    };
  }, [groupId, occurrenceDate, open]);

  const currentResult = result?.groupId === groupId ? result : null;
  const detail = currentResult?.detail ?? null;
  const error = currentResult?.error ?? null;
  const financialEnabled =
    financialCapability?.groupId === groupId && financialCapability.enabled;
  const financial =
    financialResult?.groupId === groupId ? financialResult.detail : null;
  const currentRevenue =
    revenuePreview?.groupId === groupId &&
    revenuePreview.occurrenceDate === occurrenceDate
      ? revenuePreview.detail
      : null;

  async function handleFinancialSave(input: CommercialOverrideInput) {
    if (!groupId || !financial) return;
    const previous = financial;
    const optimistic: GroupFinancialDetail = {
      ...financial,
      commercial_status: input.commercial_status ?? null,
      hourly_rate_cents: input.hourly_rate_cents ?? null,
      effective_commercial_status:
        input.commercial_status ?? financial.effective_commercial_status,
      commercial_status_source: input.commercial_status
        ? "group"
        : financial.commercial_status_source,
      effective_hourly_rate_cents:
        input.hourly_rate_cents ?? financial.effective_hourly_rate_cents,
      hourly_rate_source:
        input.hourly_rate_cents !== null && input.hourly_rate_cents !== undefined
          ? "group"
          : financial.hourly_rate_source,
      participants: financial.participants.map((participant) => ({
        ...participant,
        effective_commercial_status:
          participant.commercial_status === null && input.commercial_status
            ? input.commercial_status
            : participant.effective_commercial_status,
        commercial_status_source:
          participant.commercial_status === null && input.commercial_status
            ? "group"
            : participant.commercial_status_source,
        effective_hourly_rate_cents:
          participant.hourly_rate_cents === null &&
          input.hourly_rate_cents !== null &&
          input.hourly_rate_cents !== undefined
            ? input.hourly_rate_cents
            : participant.effective_hourly_rate_cents,
        hourly_rate_source:
          participant.hourly_rate_cents === null &&
          input.hourly_rate_cents !== null &&
          input.hourly_rate_cents !== undefined
            ? "group"
            : participant.hourly_rate_source,
      })),
    };
    setFinancialError(null);
    setFinancialResult({ groupId, detail: optimistic });
    try {
      const updated = await updateGroupFinancials(groupId, input);
      setFinancialResult({ groupId, detail: updated });
    } catch (caught) {
      setFinancialResult({ groupId, detail: previous });
      setFinancialError(
        caught instanceof Error ? caught.message : "Falha ao salvar comercial"
      );
      throw caught;
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{detail?.label || "Detalhes do grupo"}</DialogTitle>
        </DialogHeader>

        {!currentResult && (
          <p className="py-8 text-center text-sm text-muted-foreground">Carregando...</p>
        )}

        {error && <p className="py-8 text-center text-sm text-destructive">{error}</p>}

        {detail && (
          <div className="space-y-5">
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-3">
                <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span>{detail.place_name}</span>
              </div>
              <div className="flex items-center gap-3">
                <Calendar className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="capitalize">{scheduleLabel(detail)}</span>
              </div>
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span>
                  {formatTime(detail.start_time)}–{formatTime(detail.end_time)}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <Repeat className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span>
                  {detail.recurrence_type === "weekly" ? "Recorrente semanal" : "Esporádico"}
                </span>
              </div>
              {detail.level && (
                <div className="flex items-center gap-3">
                  <GraduationCap className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span>{CONTACT_LEVEL_LABELS[detail.level] ?? detail.level}</span>
                </div>
              )}
            </div>

            <Separator />

            {currentRevenue && (
              <div className="space-y-3 text-sm">
                <div className="flex items-center gap-3">
                  <CircleDollarSign className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span>
                    Receita corrente: {" "}
                    {formatBrlFromCents(currentRevenue.estimated_revenue_cents)}
                  </span>
                  <Tooltip>
                    <TooltipTrigger
                      className="text-muted-foreground"
                      aria-label="Como a receita corrente é calculada"
                    >
                      <CircleHelp className="h-3.5 w-3.5" />
                    </TooltipTrigger>
                    <TooltipContent>
                      Receita estimada com os participantes atualmente atribuídos
                      a este grupo.
                    </TooltipContent>
                  </Tooltip>
                </div>
                {currentRevenue.capacity_revenue_cents !== undefined && (
                  <div className="flex items-center gap-3">
                    <CircleDollarSign className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>
                      Capacidade total de receita: {" "}
                      {formatBrlFromCents(currentRevenue.capacity_revenue_cents)}
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
              </div>
            )}

            {currentRevenue && <Separator />}

            {financialEnabled && financial && (
              <>
                <CommercialFieldsCard
                  values={financial}
                  title="Comercial do grupo"
                  description="Estes valores são propagados aos participantes sem override próprio."
                  onSave={handleFinancialSave}
                />
                {financialError && (
                  <p className="text-sm text-destructive">{financialError}</p>
                )}
                <Separator />
              </>
            )}

            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <Users className="h-4 w-4" />
                  Participantes
                </p>
                <span className="text-xs text-muted-foreground">
                  {detail.participant_count}/{detail.max_participants}
                </span>
              </div>
              {detail.participants.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum participante atribuído.</p>
              ) : (
                <div className="space-y-1.5">
                  {detail.participants.map((participant) => {
                    const participantFinancial = financial?.participants.find(
                      (item) => item.contact_id === participant.contact_id
                    );
                    return (
                      <div
                        key={participant.id}
                        className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm"
                      >
                        <p>{participant.contact_name}</p>
                        {financialEnabled && participantFinancial && (
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                            <span>
                              {commercialStatusLabel(
                                participantFinancial.effective_commercial_status
                              )}{" "}
                              ·{" "}
                              {financialSourceLabel(
                                participantFinancial.commercial_status_source
                              )}
                            </span>
                            <span>
                              {formatBrlFromCents(
                                participantFinancial.effective_hourly_rate_cents
                              )}
                              /h ·{" "}
                              {financialSourceLabel(
                                participantFinancial.hourly_rate_source
                              )}
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

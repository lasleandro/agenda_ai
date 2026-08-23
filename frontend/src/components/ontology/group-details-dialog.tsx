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
  addOccurrenceParticipant,
  fetchGroupFinancials,
  fetchRecurringGroup,
  fetchRecurringGroupOccurrence,
  fetchRevenuePreview,
  fulfillWaitlistEntryWithGroup,
  updateGroupFinancials,
  updateOccurrenceClassFormat,
  removeOccurrenceParticipant,
} from "@/lib/api";
import { AGENDA_REFRESH_EVENT } from "@/lib/agenda-events";
import { Button } from "@/components/ui/button";
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
  ContactSummary,
  GroupFinancialDetail,
  RecurringGroupDetail,
  RecurringGroupOccurrenceDetail,
  RevenuePreviewDetail,
  WaitlistEntry,
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
  occurrenceParticipantCount,
  contacts = [],
  waitlistEntries = [],
  onOccurrenceParticipantAdded,
  onWaitlistFulfilled,
  open,
  onOpenChange,
}: {
  groupId: string | null;
  occurrenceDate?: string;
  occurrenceParticipantCount?: number;
  contacts?: ContactSummary[];
  waitlistEntries?: WaitlistEntry[];
  onOccurrenceParticipantAdded?: () => void;
  onWaitlistFulfilled?: (entryId: string) => void;
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
  const [occurrenceContactId, setOccurrenceContactId] = useState("");
  const [waitlistEntryId, setWaitlistEntryId] = useState("");
  const [waitlistEnrollmentScope, setWaitlistEnrollmentScope] = useState<"occurrence" | "series">("occurrence");
  const [occurrenceSaving, setOccurrenceSaving] = useState(false);
  const [occurrenceError, setOccurrenceError] = useState<string | null>(null);
  const [formatSaving, setFormatSaving] = useState(false);
  const [occurrenceCapacity, setOccurrenceCapacity] = useState<number | null>(null);
  const [occurrenceResult, setOccurrenceResult] = useState<{
    key: string;
    detail: RecurringGroupOccurrenceDetail | null;
  } | null>(null);
  const occurrenceKey = `${groupId ?? ""}:${occurrenceDate ?? ""}`;

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
    if (occurrenceDate) {
      fetchRecurringGroupOccurrence(groupId, occurrenceDate)
        .then((detail) => {
          if (active) setOccurrenceResult({ key: occurrenceKey, detail });
        })
        .catch(() => {
          if (active) setOccurrenceResult({ key: occurrenceKey, detail: null });
        });
    }
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
  }, [groupId, occurrenceDate, occurrenceKey, open]);

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
  const occurrenceDetail = occurrenceResult?.key === occurrenceKey
    ? occurrenceResult.detail
    : null;
  const effectiveClassType = occurrenceDetail?.class_type ?? detail?.class_type;
  const effectiveParticipantCount = occurrenceDetail?.participant_count
    ?? occurrenceParticipantCount
    ?? detail?.participant_count
    ?? 0;
  const effectiveCapacity = occurrenceDetail?.max_participants ?? detail?.max_participants ?? 1;
  const selectedCapacity = occurrenceCapacity ?? effectiveCapacity;
  const displayedParticipants = occurrenceDetail?.participants ?? detail?.participants ?? [];
  const eligibleWaitlistEntries = waitlistEntries.filter((entry) =>
    (entry.status === "open" || entry.status === "matched")
    && entry.desired_date === occurrenceDate
    && (entry.class_type === null || entry.class_type === "group")
    && (entry.place_id === null || entry.place_id === detail?.place_id)
    && (detail?.start_time ?? "") <= entry.desired_start_time
    && (detail?.end_time ?? "") >= entry.desired_end_time
    && !displayedParticipants.some((participant) => participant.contact_id === entry.contact_id)
  );

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

  async function handleAddOccurrenceParticipant() {
    if (!groupId || !occurrenceDate || !occurrenceContactId) return;
    setOccurrenceSaving(true);
    setOccurrenceError(null);
    try {
      const participant = await addOccurrenceParticipant(
        groupId,
        occurrenceDate,
        occurrenceContactId
      );
      setOccurrenceResult((current) => current?.key === occurrenceKey && current.detail
        ? {
            ...current,
            detail: {
              ...current.detail,
              participant_count: current.detail.participant_count + 1,
              available_seats: current.detail.available_seats - 1,
              participants: [
                ...current.detail.participants,
                { ...participant, enrollment_scope: "occurrence" },
              ],
            },
          }
        : current
      );
      setOccurrenceContactId("");
      window.dispatchEvent(new Event(AGENDA_REFRESH_EVENT));
    } catch (caught) {
      setOccurrenceError(
        caught instanceof Error ? caught.message : "Falha ao adicionar participante"
      );
    } finally {
      setOccurrenceSaving(false);
    }
  }

  async function handleFulfillWaitlistEntry() {
    if (!groupId || !occurrenceDate || !waitlistEntryId) return;
    const entry = waitlistEntries.find((item) => item.id === waitlistEntryId);
    if (!entry) return;
    setOccurrenceSaving(true);
    setOccurrenceError(null);
    try {
      await fulfillWaitlistEntryWithGroup(
        entry.id,
        groupId,
        occurrenceDate,
        waitlistEnrollmentScope
      );
      setOccurrenceResult((current) => current?.key === occurrenceKey && current.detail
        ? {
            ...current,
            detail: {
              ...current.detail,
              participant_count: current.detail.participant_count + 1,
              available_seats: current.detail.available_seats - 1,
              participants: [
                ...current.detail.participants,
                {
                  id: entry.id,
                  contact_id: entry.contact_id,
                  contact_name: entry.contact_name,
                  occurrence_date: occurrenceDate,
                  enrollment_scope: "occurrence",
                },
              ],
            },
          }
        : current
      );
      setWaitlistEntryId("");
      onWaitlistFulfilled?.(entry.id);
      onOccurrenceParticipantAdded?.();
      window.dispatchEvent(new Event(AGENDA_REFRESH_EVENT));
    } catch (caught) {
      setOccurrenceError(
        caught instanceof Error ? caught.message : "Falha ao preencher vaga da fila"
      );
    } finally {
      setOccurrenceSaving(false);
    }
  }

  async function handleRemoveOccurrenceParticipant(contactId: string) {
    if (!groupId || !occurrenceDate) return;
    setOccurrenceSaving(true);
    setOccurrenceError(null);
    try {
      await removeOccurrenceParticipant(groupId, occurrenceDate, contactId);
      setOccurrenceResult((current) => current?.key === occurrenceKey && current.detail
        ? {
            ...current,
            detail: {
              ...current.detail,
              participant_count: current.detail.participant_count - 1,
              available_seats: current.detail.available_seats + 1,
              participants: current.detail.participants.filter(
                (participant) => participant.contact_id !== contactId
              ),
            },
          }
        : current
      );
      onOccurrenceParticipantAdded?.();
      window.dispatchEvent(new Event(AGENDA_REFRESH_EVENT));
    } catch (caught) {
      setOccurrenceError(
        caught instanceof Error ? caught.message : "Falha ao remover participante"
      );
    } finally {
      setOccurrenceSaving(false);
    }
  }

  async function handlePromoteOccurrence() {
    if (!groupId || !occurrenceDate) return;
    setFormatSaving(true);
    setOccurrenceError(null);
    try {
      const updated = await updateOccurrenceClassFormat("recurring_slot", groupId, occurrenceDate, {
        class_type: "group",
        max_participants: 4,
      });
      setOccurrenceResult((current) => current?.key === occurrenceKey && current.detail
        ? { ...current, detail: { ...current.detail, ...updated } }
        : current
      );
      window.dispatchEvent(new Event(AGENDA_REFRESH_EVENT));
    } catch (caught) {
      setOccurrenceError(
        caught instanceof Error ? caught.message : "Falha ao transformar esta aula"
      );
    } finally {
      setFormatSaving(false);
    }
  }

  async function handleUpdateOccurrenceCapacity() {
    if (!groupId || !occurrenceDate || effectiveClassType !== "group") return;
    setFormatSaving(true);
    setOccurrenceError(null);
    try {
      const updated = await updateOccurrenceClassFormat(
        "recurring_slot",
        groupId,
        occurrenceDate,
        { class_type: "group", max_participants: selectedCapacity }
      );
      setOccurrenceResult((current) => current?.key === occurrenceKey && current.detail
        ? { ...current, detail: { ...current.detail, ...updated } }
        : current
      );
      setOccurrenceCapacity(null);
      window.dispatchEvent(new Event(AGENDA_REFRESH_EVENT));
    } catch (caught) {
      setOccurrenceError(
        caught instanceof Error ? caught.message : "Falha ao alterar capacidade"
      );
    } finally {
      setFormatSaving(false);
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
            {occurrenceDate && effectiveClassType !== "group" && (
              <Button
                className="w-full"
                variant="outline"
                disabled={formatSaving}
                onClick={handlePromoteOccurrence}
              >
                {formatSaving
                  ? "Transformando..."
                  : "Transformar esta aula em grupo (4 vagas)"}
              </Button>
            )}
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
                  {effectiveParticipantCount}/{effectiveCapacity}
                </span>
              </div>
              {displayedParticipants.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum participante atribuído.</p>
              ) : (
                <div className="space-y-1.5">
                  {displayedParticipants.map((participant) => {
                    const participantFinancial = financial?.participants.find(
                      (item) => item.contact_id === participant.contact_id
                    );
                    return (
                      <div
                        key={participant.id}
                        className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm"
                      >
                        <p>{participant.contact_name}</p>
                        {"enrollment_scope" in participant && (
                          <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                            <span>
                              {participant.enrollment_scope === "series"
                                ? "Turma fixa"
                                : "Somente esta aula"}
                            </span>
                            {participant.enrollment_scope === "occurrence" && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-6 px-1.5 text-destructive"
                                disabled={occurrenceSaving}
                                onClick={() => handleRemoveOccurrenceParticipant(participant.contact_id)}
                              >
                                Remover
                              </Button>
                            )}
                          </div>
                        )}
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

            {occurrenceDate && effectiveClassType === "group" && (
              <div className="space-y-2 rounded-lg border border-border p-3">
                <p className="text-sm font-medium">Adicionar somente nesta aula</p>
                <p className="text-xs text-muted-foreground">
                  A presença é válida apenas em {new Date(`${occurrenceDate}T12:00:00`).toLocaleDateString("pt-BR")} e não altera a turma fixa.
                </p>
                <div className="flex gap-2">
                  <select
                    value={occurrenceContactId}
                    onChange={(event) => setOccurrenceContactId(event.target.value)}
                    className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm"
                    aria-label="Cliente para esta aula"
                  >
                    <option value="">Selecionar cliente</option>
                    {contacts.map((contact) => (
                      !displayedParticipants.some((participant) => participant.contact_id === contact.id) && (
                        <option key={contact.id} value={contact.id}>
                          {contact.display_name}
                        </option>
                      )
                    ))}
                  </select>
                  <Button
                    size="sm"
                    disabled={
                      !occurrenceContactId ||
                      occurrenceSaving ||
                      effectiveParticipantCount >= effectiveCapacity
                    }
                    onClick={handleAddOccurrenceParticipant}
                  >
                    {occurrenceSaving ? "Adicionando..." : "Adicionar"}
                  </Button>
                </div>
                {eligibleWaitlistEntries.length > 0 && (
                  <div className="flex gap-2 border-t border-border pt-2">
                    <select
                      value={waitlistEntryId}
                      onChange={(event) => setWaitlistEntryId(event.target.value)}
                      className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm"
                      aria-label="Cliente da fila de espera"
                    >
                      <option value="">Preencher vaga da fila</option>
                      {eligibleWaitlistEntries.map((entry) => (
                        <option key={entry.id} value={entry.id}>{entry.contact_name}</option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!waitlistEntryId || occurrenceSaving || effectiveParticipantCount >= effectiveCapacity}
                      onClick={handleFulfillWaitlistEntry}
                    >
                      Preencher
                    </Button>
                    <select
                      value={waitlistEnrollmentScope}
                      onChange={(event) => setWaitlistEnrollmentScope(
                        event.target.value as "occurrence" | "series"
                      )}
                      className="h-9 rounded-md border border-input bg-background px-2 text-xs"
                      aria-label="Escopo da matrícula da fila"
                    >
                      <option value="occurrence">Nesta aula</option>
                      <option value="series">Todas as semanas</option>
                    </select>
                  </div>
                )}
                {occurrenceError && <p className="text-xs text-destructive">{occurrenceError}</p>}
              </div>
            )}

            {occurrenceDate && effectiveClassType === "group" && (
              <div className="flex items-center gap-2 rounded-lg border border-border p-3">
                <label className="text-sm font-medium" htmlFor="occurrence-capacity">
                  Vagas nesta aula
                </label>
                <select
                  id="occurrence-capacity"
                  value={selectedCapacity}
                  onChange={(event) => setOccurrenceCapacity(Number(event.target.value))}
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {[1, 2, 3, 4].map((capacity) => (
                    <option
                      key={capacity}
                      value={capacity}
                      disabled={capacity < effectiveParticipantCount}
                    >
                      {capacity}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={formatSaving || selectedCapacity === effectiveCapacity}
                  onClick={handleUpdateOccurrenceCapacity}
                >
                  Salvar
                </Button>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

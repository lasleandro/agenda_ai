"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SchedulerPlaceSelect } from "@/components/ontology/scheduler-place-select";
import { EVENT_TYPE_LABELS } from "@/lib/ontology-utils";
import { EVENT_TYPES } from "@/lib/types";
import type {
  AppointmentCreateInput,
  ContactSummary,
  EventType,
  InstructorEventInput,
  Place,
  RecurringSlotInput,
} from "@/lib/types";

function formatSelection(start: Date, end: Date): string {
  const date = start.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
  const time = (value: Date) =>
    value.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time(start)}–${time(end)}`;
}

function localDateValue(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function localTimeValue(value: Date): string {
  const hours = String(value.getHours()).padStart(2, "0");
  const minutes = String(value.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}:00`;
}

function toPythonDay(value: Date): number {
  return (value.getDay() + 6) % 7;
}

export function AppointmentFormDialog({
  open,
  onOpenChange,
  start,
  end,
  suggestedPlaceId,
  initialContactId,
  contacts,
  places,
  onPlaceCreated,
  onCreate,
  onCreateGroupSlot,
  onCreateEvent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  start: Date;
  end: Date;
  suggestedPlaceId: string | null;
  initialContactId?: string;
  contacts: ContactSummary[];
  places: Place[];
  onPlaceCreated: (place: Place) => void;
  onCreate: (input: AppointmentCreateInput) => Promise<void>;
  onCreateGroupSlot: (input: RecurringSlotInput) => Promise<void>;
  onCreateEvent: (input: InstructorEventInput) => Promise<void>;
}) {
  const [mode, setMode] = useState<"class" | "event">("class");
  const [classType, setClassType] = useState<"individual" | "group">("individual");
  const [contactId, setContactId] = useState(initialContactId ?? "");
  const [groupContactIds, setGroupContactIds] = useState<string[]>(
    initialContactId ? [initialContactId] : []
  );
  const [maxParticipants, setMaxParticipants] = useState(4);
  const [placeId, setPlaceId] = useState(suggestedPlaceId ?? "");
  const [service, setService] = useState("Aula de tênis");
  const [isRecurring, setIsRecurring] = useState(false);
  const [isCourtesy, setIsCourtesy] = useState(false);
  const [eventType, setEventType] = useState<EventType>("clinic");
  const [eventTitle, setEventTitle] = useState("");
  const [eventIncome, setEventIncome] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSaveClass() {
    const participantIds =
      classType === "group" ? groupContactIds : contactId ? [contactId] : [];
    if (!placeId || !service.trim()) {
      setError("Selecione o cliente, o local e informe o serviço");
      return;
    }
    if (classType === "individual" && !participantIds.length) {
      setError("Selecione um cliente");
      return;
    }
    if (participantIds.length > maxParticipants) {
      setError("A capacidade deve comportar todos os clientes selecionados");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      if (classType === "group" && participantIds.length === 0) {
        await onCreateGroupSlot({
          place_id: placeId,
          day_of_week: toPythonDay(start),
          start_time: localTimeValue(start),
          end_time: localTimeValue(end),
          label: service.trim(),
          class_type: "group",
          slot_kind: "class",
          max_participants: maxParticipants,
          recurrence_type: isRecurring ? "weekly" : "once",
          scheduled_date: isRecurring ? null : localDateValue(start),
          valid_from: isRecurring ? localDateValue(start) : null,
        });
        onOpenChange(false);
        return;
      }
      await onCreate({
        contact_id: participantIds[0],
        contact_ids: participantIds,
        place_id: placeId,
        service: service.trim(),
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        is_recurring: isRecurring,
        class_type: classType,
        max_participants: classType === "group" ? maxParticipants : 1,
        billing_type: isCourtesy ? "courtesy" : "billable",
      });
      onOpenChange(false);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao criar agendamento"
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveEvent() {
    setSaving(true);
    setError(null);
    try {
      await onCreateEvent({
        event_type: eventType,
        title: eventTitle.trim() || null,
        place_id: placeId || null,
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        income_cents: eventIncome ? Math.round(Number(eventIncome) * 100) : null,
      });
      onOpenChange(false);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Falha ao criar evento"
      );
    } finally {
      setSaving(false);
    }
  }

  const canBook = classType === "group"
    ? places.length > 0
    : contacts.length > 0 && places.length > 0;

  function handleClassTypeChange(nextType: "individual" | "group") {
    setClassType(nextType);
    if (nextType === "group" && !groupContactIds.length && contactId) {
      setGroupContactIds([contactId]);
    }
    if (nextType === "individual" && !contactId && groupContactIds[0]) {
      setContactId(groupContactIds[0]);
    }
  }

  function toggleGroupContact(contactIdToToggle: string) {
    if (groupContactIds.includes(contactIdToToggle)) {
      setGroupContactIds((current) =>
        current.filter((id) => id !== contactIdToToggle)
      );
      return;
    }
    if (groupContactIds.length >= maxParticipants) {
      setError("A capacidade da turma foi atingida");
      return;
    }
    setError(null);
    setGroupContactIds((current) => [...current, contactIdToToggle]);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{mode === "class" ? "Novo agendamento" : "Novo evento"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex rounded-lg border border-border p-1">
            <button
              type="button"
              onClick={() => setMode("class")}
              className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
                mode === "class" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
              }`}
            >
              Aula
            </button>
            <button
              type="button"
              onClick={() => setMode("event")}
              className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
                mode === "event" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
              }`}
            >
              Evento
            </button>
          </div>

          <p className="rounded-lg bg-muted px-3 py-2 text-sm capitalize text-muted-foreground">
            {formatSelection(start, end)}
          </p>

          {mode === "class" ? (
            <>
              <div className="space-y-1.5">
                <Label>Formato da aula</Label>
                <div className="flex rounded-lg border border-border p-1">
                  <button
                    type="button"
                    onClick={() => handleClassTypeChange("individual")}
                    className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
                      classType === "individual"
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    Individual
                  </button>
                  <button
                    type="button"
                    onClick={() => handleClassTypeChange("group")}
                    className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
                      classType === "group"
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    Grupo
                  </button>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>
                  {classType === "group" ? "Clientes (0 a 4)" : "Cliente"}
                </Label>
                {classType === "group" ? (
                  <>
                    <div
                      id="booking-contact"
                      className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-input p-2"
                    >
                      {contacts.map((contact) => (
                        <label
                          key={contact.id}
                          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"
                        >
                          <input
                            type="checkbox"
                            checked={groupContactIds.includes(contact.id)}
                            onChange={() => toggleGroupContact(contact.id)}
                            className="h-4 w-4 accent-primary"
                          />
                          {contact.display_name}
                        </label>
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Selecione os clientes atuais. A turma pode começar sem alunos.
                    </p>
                  </>
                ) : (
                  <select
                    id="booking-contact"
                    value={contactId}
                    onChange={(event) => setContactId(event.target.value)}
                    className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  >
                    <option value="">Selecione um cliente</option>
                    {contacts.map((contact) => (
                      <option key={contact.id} value={contact.id}>
                        {contact.display_name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <SchedulerPlaceSelect
                id="booking-place"
                value={placeId}
                places={places}
                onChange={setPlaceId}
                onPlaceCreated={onPlaceCreated}
              />
              {suggestedPlaceId && placeId === suggestedPlaceId ? (
                <p className="text-xs text-muted-foreground">
                  Local preenchido pela permanência que cobre todo este horário.
                </p>
              ) : (
                <p className="text-xs text-amber-700">
                  Não há uma única permanência para este horário. Confirme o local
                  selecionado como exceção.
                </p>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="booking-service">Serviço</Label>
                <Input
                  id="booking-service"
                  value={service}
                  onChange={(event) => setService(event.target.value)}
                />
              </div>

              {classType === "group" && (
                <div className="space-y-1.5">
                  <Label htmlFor="booking-capacity">Máx. alunos</Label>
                  <Input
                    id="booking-capacity"
                    type="number"
                    min={Math.max(1, groupContactIds.length)}
                    max={4}
                    value={maxParticipants}
                    onChange={(event) => {
                      const nextCapacity = Number(event.target.value);
                      if (nextCapacity >= groupContactIds.length && nextCapacity <= 4) {
                        setMaxParticipants(nextCapacity);
                      }
                    }}
                  />
                </div>
              )}

              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-2">
                <span>
                  <span className="block text-sm font-medium">Repetir semanalmente</span>
                  <span className="block text-xs text-muted-foreground">
                    O agendamento aparecerá neste dia e horário toda semana.
                  </span>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  checked={isRecurring}
                  onChange={(event) => setIsRecurring(event.target.checked)}
                  className="h-4 w-4 accent-primary"
                />
              </label>

              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-2">
                <span>
                  <span className="block text-sm font-medium">Aula Cortesia</span>
                  <span className="block text-xs text-muted-foreground">
                    Agendamento sem cobranca para o cliente.
                  </span>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  checked={isCourtesy}
                  onChange={(event) => setIsCourtesy(event.target.checked)}
                  className="h-4 w-4 accent-primary"
                />
              </label>

              {!canBook && (
                <p className="text-sm text-muted-foreground">
                  Cadastre ao menos um cliente e um local antes de criar um agendamento.
                </p>
              )}
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="event-type">Tipo de evento</Label>
                <select
                  id="event-type"
                  value={eventType}
                  onChange={(event) => setEventType(event.target.value as EventType)}
                  className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                >
                  {EVENT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {EVENT_TYPE_LABELS[type] ?? type}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="event-title">Título (opcional)</Label>
                <Input
                  id="event-title"
                  value={eventTitle}
                  onChange={(event) => setEventTitle(event.target.value)}
                  placeholder="Ex: Clínica de saque"
                />
              </div>

              <SchedulerPlaceSelect
                id="event-place"
                value={placeId}
                places={places}
                onChange={setPlaceId}
                onPlaceCreated={onPlaceCreated}
              />

              <div className="space-y-1.5">
                <Label htmlFor="event-income">Renda (R$, opcional)</Label>
                <Input
                  id="event-income"
                  type="number"
                  min="0"
                  step="0.01"
                  value={eventIncome}
                  onChange={(event) => setEventIncome(event.target.value)}
                  placeholder="0,00"
                />
              </div>
            </>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          {mode === "class" ? (
            <Button onClick={handleSaveClass} disabled={saving || !canBook}>
              {saving ? "Salvando..." : "Agendar"}
            </Button>
          ) : (
            <Button onClick={handleSaveEvent} disabled={saving}>
              {saving ? "Salvando..." : "Criar evento"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

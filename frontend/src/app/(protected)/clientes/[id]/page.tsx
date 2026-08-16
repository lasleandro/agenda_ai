"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Gift, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { AddressAutocomplete } from "@/components/ontology/address-autocomplete";
import { AssignSlotDialog } from "@/components/ontology/assign-slot-dialog";
import { CommercialFieldsCard } from "@/components/financial/commercial-fields-card";
import {
  fetchContact,
  fetchCustomerFinancials,
  fetchPlaces,
  removeSlotParticipant,
  updateContact,
  updateCustomerFinancials,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import type { GeocodeResult } from "@/lib/geocode";
import { CLASS_TYPE_LABELS, CONTACT_LEVEL_LABELS, DAY_LABELS, formatTime } from "@/lib/ontology-utils";
import type {
  CommercialOverrideInput,
  ContactDetailData,
  CustomerFinancialDetail,
  Place,
  RecurringSlot,
} from "@/lib/types";
import { CONTACT_LEVELS } from "@/lib/types";

function formatSlotDay(slot: RecurringSlot): string {
  if (slot.recurrence_type === "once" && slot.scheduled_date) {
    return new Date(`${slot.scheduled_date}T12:00:00`).toLocaleDateString("pt-BR");
  }
  return DAY_LABELS[slot.day_of_week];
}

export default function ContactDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const contactId = params.id;

  const [contact, setContact] = useState<ContactDetailData | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [assignDialogOpen, setAssignDialogOpen] = useState(false);
  const [financialEnabled, setFinancialEnabled] = useState(false);
  const [financial, setFinancial] = useState<CustomerFinancialDetail | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    fetchContact(contactId).then(setContact);
    fetchPlaces().then((res) => setPlaces(res.places));
  }

  useEffect(() => {
    reload();
    fetchSession().then((user) => {
      const enabled = sessionHasFeature(user, "commercial_financials");
      setFinancialEnabled(enabled);
      if (enabled) {
        fetchCustomerFinancials(contactId)
          .then(setFinancial)
          .catch((caught) =>
            setError(
              caught instanceof Error
                ? caught.message
                : "Falha ao carregar dados financeiros"
            )
          );
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactId]);

  async function handleFieldSave(fields: Partial<ContactDetailData>) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateContact(contactId, fields);
      setContact(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddressSelect(result: GeocodeResult) {
    await handleFieldSave({
      address_line: result.address_line,
      city: result.city,
      state: result.state,
      postal_code: result.postal_code,
      country: result.country,
      latitude: result.latitude,
      longitude: result.longitude,
    });
  }

  async function handleFinancialSave(input: CommercialOverrideInput) {
    if (!financial) return;
    const previous = financial;
    setError(null);
    setFinancial({
      ...financial,
      commercial_status: input.commercial_status ?? null,
      hourly_rate_cents: input.hourly_rate_cents ?? null,
      effective_commercial_status:
        input.commercial_status ?? financial.effective_commercial_status,
      commercial_status_source: input.commercial_status
        ? "customer"
        : financial.commercial_status_source,
      effective_hourly_rate_cents:
        input.hourly_rate_cents ?? financial.effective_hourly_rate_cents,
      hourly_rate_source:
        input.hourly_rate_cents !== null && input.hourly_rate_cents !== undefined
          ? "customer"
          : financial.hourly_rate_source,
    });
    try {
      setFinancial(await updateCustomerFinancials(contactId, input));
    } catch (caught) {
      setFinancial(previous);
      setError(caught instanceof Error ? caught.message : "Falha ao salvar comercial");
      throw caught;
    }
  }

  const handleSlotAssigned = useCallback(
    (slot: RecurringSlot) => {
      // Optimistic: add the slot to the contact's fixed_slots immediately
      setContact((prev) => {
        if (!prev) return prev;
        const alreadyThere = prev.fixed_slots.some((s) => s.id === slot.id);
        if (alreadyThere) return prev;
        return { ...prev, fixed_slots: [...prev.fixed_slots, slot] };
      });
    },
    []
  );

  async function handleRemoveSlot(slotId: string) {
    setSaving(true);
    try {
      await removeSlotParticipant(slotId, contactId);
      reload();
    } finally {
      setSaving(false);
    }
  }

  if (!contact) {
    return <div className="p-6 text-sm text-muted-foreground">Carregando...</div>;
  }

  const assignedSlotIds = new Set(contact.fixed_slots.map((s) => s.id));

  return (
    <div className="flex-1 flex flex-col min-h-0 p-4 md:p-6 gap-5 overflow-auto max-w-2xl">
      <button
        onClick={() => router.push("/clientes")}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground w-fit"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Clientes
      </button>

      <div>
        <h1 className="text-xl font-semibold tracking-tight">{contact.display_name}</h1>
        <p className="text-sm text-muted-foreground">{contact.phone ?? "—"}</p>
      </div>

      {contact.makeup_credits_available > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
          <RotateCcw className="h-4 w-4" />
          <span>
            {contact.makeup_credits_available}{" "}
            {contact.makeup_credits_available === 1
              ? "crédito de reposição disponível"
              : "créditos de reposição disponíveis"}
          </span>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="contact-level">Nível</Label>
          <select
            id="contact-level"
            value={contact.level ?? ""}
            onChange={(e) => handleFieldSave({ level: e.target.value || null })}
            disabled={saving}
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="">Não definido</option>
            {CONTACT_LEVELS.map((level) => (
              <option key={level} value={level}>
                {CONTACT_LEVEL_LABELS[level]}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="contact-place">Local habitual</Label>
          <select
            id="contact-place"
            value={contact.home_place_id ?? ""}
            onChange={(e) => handleFieldSave({ home_place_id: e.target.value || null })}
            disabled={saving}
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="">Não definido</option>
            {places.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {financialEnabled && financial && (
        <CommercialFieldsCard
          values={financial}
          description="Valores próprios substituem o grupo. Deixe vazio para usar a herança."
          onSave={handleFinancialSave}
        />
      )}

      <div className="space-y-1.5">
        <Label>Endereço</Label>
        <AddressAutocomplete
          value={contact.address_line ?? ""}
          onSelect={handleAddressSelect}
        />
      </div>

      {contact.courtesy_appointments.length > 0 && (
        <div className="space-y-2">
          <Label>Aulas cortesia</Label>
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <div className="space-y-1.5">
              {contact.courtesy_appointments.map((appt) => {
                const startDate = new Date(appt.start_at);
                const endDate = new Date(appt.end_at);
                const dateLabel = startDate.toLocaleDateString("pt-BR", {
                  day: "2-digit",
                  month: "2-digit",
                  year: "numeric",
                });
                const timeLabel = `${startDate.toLocaleTimeString("pt-BR", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}–${endDate.toLocaleTimeString("pt-BR", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}`;
                const placeLabel = appt.place_name ? ` · ${appt.place_name}` : "";
                const statusLabel =
                  appt.status === "cancelled"
                    ? " (Cancelada)"
                    : appt.status === "completed"
                      ? ""
                      : "";
                return (
                  <div
                    key={appt.id}
                    className="flex items-center gap-2 text-sm text-amber-800"
                  >
                    <Gift className="h-3.5 w-3.5 shrink-0" />
                    <span>
                      {dateLabel} {timeLabel}{placeLabel} · {appt.service}
                      {statusLabel}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <Label>Aulas recorrentes</Label>
        {contact.fixed_slots.length === 0 && (
          <p className="text-sm text-muted-foreground">Nenhuma aula recorrente atribuída.</p>
        )}
        <div className="space-y-2">
          {contact.fixed_slots.map((slot) => (
            <div
              key={slot.id}
              className="flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2 text-sm"
            >
              <span>
                {formatSlotDay(slot)} {formatTime(slot.start_time)}–
                {formatTime(slot.end_time)} · {slot.place_name}
                {slot.label ? ` (${slot.label})` : ""} ·{" "}
                <span className="text-muted-foreground">
                  {CLASS_TYPE_LABELS[slot.class_type]}
                  {slot.level
                    ? ` · ${CONTACT_LEVEL_LABELS[slot.level] ?? slot.level}`
                    : ""}
                </span>
              </span>
              <button
                onClick={() => handleRemoveSlot(slot.id)}
                disabled={saving}
                title="Remover"
                className="text-muted-foreground hover:text-destructive"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAssignDialogOpen(true)}
          >
            Adicionar a aula recorrente...
          </Button>
        </div>
      </div>

      <Button variant="outline" onClick={() => router.push("/clientes")} className="w-fit">
        Concluído
      </Button>

      {contact && (
        <AssignSlotDialog
          contact={contact}
          assignedSlotIds={assignedSlotIds}
          open={assignDialogOpen}
          onOpenChange={setAssignDialogOpen}
          onAssigned={handleSlotAssigned}
        />
      )}
    </div>
  );
}

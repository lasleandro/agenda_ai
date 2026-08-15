"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CircleDollarSign,
  Pencil,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PlaceRateEditor } from "@/components/financial/place-rates-section";
import { PlaceFormDialog } from "@/components/ontology/place-form-dialog";
import { RecurringSlotFormDialog } from "@/components/ontology/recurring-slot-form-dialog";
import {
  deletePlace,
  fetchFinancialConfiguration,
  fetchPlace,
  fetchRecurringSlots,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import {
  CLASS_TYPE_LABELS,
  CONTACT_LEVEL_LABELS,
  DAY_LABELS,
  formatTime,
} from "@/lib/ontology-utils";
import type {
  Place,
  PlaceRateMatrixDetail,
  RecurringSlot,
} from "@/lib/types";

function formatSlotDay(slot: RecurringSlot): string {
  if (slot.recurrence_type === "once" && slot.scheduled_date) {
    return new Date(`${slot.scheduled_date}T12:00:00`).toLocaleDateString("pt-BR");
  }
  return DAY_LABELS[slot.day_of_week];
}

export default function PlaceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const placeId = params.id;

  const [place, setPlace] = useState<Place | null>(null);
  const [slots, setSlots] = useState<RecurringSlot[] | null>(null);
  const [editPlaceOpen, setEditPlaceOpen] = useState(false);
  const [slotDialogOpen, setSlotDialogOpen] = useState(false);
  const [editingSlot, setEditingSlot] = useState<RecurringSlot | null>(null);
  const [financialEnabled, setFinancialEnabled] = useState(false);
  const [placeRates, setPlaceRates] =
    useState<PlaceRateMatrixDetail | null>(null);
  const [financialError, setFinancialError] = useState<string | null>(null);

  function reload() {
    fetchPlace(placeId).then(setPlace);
    fetchRecurringSlots(placeId).then((res) => setSlots(res.slots));
  }

  useEffect(() => {
    reload();
    let active = true;
    fetchSession().then(async (user) => {
      if (!active || !sessionHasFeature(user, "commercial_financials")) return;
      setFinancialEnabled(true);
      try {
        const configuration = await fetchFinancialConfiguration();
        if (!active) return;
        setPlaceRates(
          configuration.places.find(
            (matrix) => matrix.place_id === placeId
          ) ?? null
        );
      } catch (caught) {
        if (!active) return;
        setFinancialError(
          caught instanceof Error
            ? caught.message
            : "Falha ao carregar os valores financeiros"
        );
      }
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placeId]);

  async function handleDeletePlace() {
    if (!confirm("Remover este local? Os horários fixos associados também serão removidos.")) return;
    await deletePlace(placeId);
    router.push("/places");
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 p-4 md:p-6 gap-4 overflow-auto">
      <button
        onClick={() => router.push("/places")}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground w-fit"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Meus Locais
      </button>

      {place && (
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{place.name}</h1>
            {place.address_line && (
              <p className="text-sm text-muted-foreground">
                {place.address_line}
                {place.city ? `, ${place.city}` : ""}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setEditPlaceOpen(true)}>
              <Pencil className="h-3.5 w-3.5" />
              Editar
            </Button>
            <Button variant="destructive" size="sm" onClick={handleDeletePlace}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {financialEnabled && (
        <Card className="mt-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CircleDollarSign className="size-4 text-primary" />
              Valores R$/hora
            </CardTitle>
            <CardDescription>
              Defina valores por participante para horários regulares e nobres.
              Campos vazios herdam a configuração global do Financeiro.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {financialError && (
              <p className="text-sm text-destructive">{financialError}</p>
            )}
            {!financialError && !placeRates && (
              <p className="text-sm text-muted-foreground">
                Carregando valores do local...
              </p>
            )}
            {placeRates && (
              <PlaceRateEditor
                key={placeRates.place_id}
                matrix={placeRates}
                onSaved={setPlaceRates}
              />
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex items-center justify-between mt-2">
        <h2 className="text-sm font-semibold text-foreground">Horários fixos</h2>
        <Button
          size="sm"
          onClick={() => {
            setEditingSlot(null);
            setSlotDialogOpen(true);
          }}
        >
          <Plus className="h-3.5 w-3.5" />
          Novo horário
        </Button>
      </div>

      {slots !== null && slots.length === 0 && (
        <p className="text-sm text-muted-foreground">Nenhum horário fixo cadastrado neste local.</p>
      )}

      <div className="space-y-2">
        {slots?.map((slot) => (
          <button
            key={slot.id}
            onClick={() => {
              setEditingSlot(slot);
              setSlotDialogOpen(true);
            }}
            className="flex w-full flex-col items-start gap-2 rounded-lg border border-border bg-card px-4 py-3 text-left text-sm hover:border-indigo-400 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium">{formatSlotDay(slot)}</span>
              <span className="text-muted-foreground">
                {formatTime(slot.start_time)}–{formatTime(slot.end_time)}
              </span>
              {slot.label && <span className="text-muted-foreground">· {slot.label}</span>}
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span className="rounded-full bg-muted px-2 py-0.5">
                {CLASS_TYPE_LABELS[slot.class_type]}
              </span>
              {slot.level && (
                <span className="rounded-full bg-muted px-2 py-0.5">
                  {CONTACT_LEVEL_LABELS[slot.level] ?? slot.level}
                </span>
              )}
              {slot.class_type === "group" && (
                <span className="flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {slot.participant_count}/{slot.max_participants}
                </span>
              )}
            </div>
          </button>
        ))}
      </div>

      {place && (
        <PlaceFormDialog
          open={editPlaceOpen}
          onOpenChange={setEditPlaceOpen}
          place={place}
          onSaved={(saved) => setPlace(saved)}
        />
      )}

      <RecurringSlotFormDialog
        key={`${editingSlot?.id ?? "new"}-${slotDialogOpen ? "open" : "closed"}`}
        open={slotDialogOpen}
        onOpenChange={setSlotDialogOpen}
        slot={editingSlot}
        fixedPlaceId={placeId}
        onSaved={() => reload()}
        onDeleted={() => reload()}
      />
    </div>
  );
}

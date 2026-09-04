"use client";

import { useCallback, useEffect, useState } from "react";
import { Clock, MapPin, Users } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  addSlotParticipant,
  fetchPlaces,
  fetchRecurringSlots,
} from "@/lib/api";
import { DAY_LABELS, formatTime } from "@/lib/ontology-utils";
import type { ContactDetailData, Place, RecurringSlot } from "@/lib/types";

interface AssignSlotDialogProps {
  contact: ContactDetailData;
  assignedSlotIds: Set<string>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAssigned: (slot: RecurringSlot) => void;
}

export function AssignSlotDialog({
  contact,
  assignedSlotIds,
  open,
  onOpenChange,
  onAssigned,
}: AssignSlotDialogProps) {
  const [places, setPlaces] = useState<Place[]>([]);
  const [allSlots, setAllSlots] = useState<RecurringSlot[]>([]);
  const [selectedPlaceId, setSelectedPlaceId] = useState(contact.home_place_id ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assigningId, setAssigningId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [placesResult, slotsResult] = await Promise.all([
        fetchPlaces(),
        fetchRecurringSlots(),
      ]);
      setPlaces(placesResult.places);
      setAllSlots(slotsResult.slots);
      if (!selectedPlaceId && contact.home_place_id) {
        setSelectedPlaceId(contact.home_place_id);
      }
    } catch (caught) {
          setError(caught instanceof Error ? caught.message : "Não foi possível carregar as aulas. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }, [contact.home_place_id, selectedPlaceId]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      void loadData();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open, loadData]);

  // Filter: exclude assigned, full, and filter by selected place
  const filteredSlots = allSlots.filter((s) => {
    if (s.slot_kind !== "class") return false;
    if (assignedSlotIds.has(s.id)) return false;
    if (s.participant_count >= s.max_participants) return false;
    if (selectedPlaceId && s.place_id !== selectedPlaceId) return false;
    return true;
  });

  // Group by day of week (0=Monday..6=Sunday)
  const slotsByDay = new Map<number, RecurringSlot[]>();
  for (const s of filteredSlots) {
    const day = s.day_of_week;
    if (!slotsByDay.has(day)) slotsByDay.set(day, []);
    slotsByDay.get(day)!.push(s);
  }

  const sortedDays = Array.from(slotsByDay.keys()).sort((a, b) => a - b);

  async function handleAssign(slot: RecurringSlot) {
    setAssigningId(slot.id);
    setError(null);
    try {
      await addSlotParticipant(slot.id, contact.id);
      onAssigned(slot);
      onOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Não foi possível atribuir o horário. Tente novamente.");
    } finally {
      setAssigningId(null);
    }
  }

  const homePlace = places.find((p) => p.id === contact.home_place_id);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Adicionar a aula recorrente</DialogTitle>
            <DialogDescription>
              Selecione uma aula recorrente com vaga para{" "}
              <span className="font-medium text-foreground">{contact.display_name}</span>
              {homePlace ? (
                <> em <span className="font-medium text-foreground">{homePlace.name}</span></>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {error && (
            <p className="text-sm text-destructive bg-destructive/5 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          {/* Place filter */}
          <div className="space-y-1.5">
            <Label htmlFor="assign-place-filter">Filtrar por local</Label>
            <select
              id="assign-place-filter"
              value={selectedPlaceId}
              onChange={(e) => setSelectedPlaceId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
            >
              <option value="">Todos os locais</option>
              {places.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          {/* Slot list grouped by day */}
          <div className="flex-1 overflow-auto -mx-1 px-1">
            {loading && (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Carregando horários...
              </p>
            )}

            {!loading && filteredSlots.length === 0 && (
              <div className="text-center py-8 space-y-3">
                <p className="text-sm text-muted-foreground">
                  Nenhuma aula recorrente com vaga{selectedPlaceId ? " neste local" : ""}.
                </p>
              </div>
            )}

            {!loading &&
              sortedDays.map((day) => {
                const slots = slotsByDay.get(day)!;
                // Sort by start_time
                slots.sort((a, b) => a.start_time.localeCompare(b.start_time));
                return (
                  <div key={day} className="mb-3">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 px-1">
                      {DAY_LABELS[day]}
                    </p>
                    <div className="space-y-1">
                      {slots.map((slot) => (
                        <button
                          key={slot.id}
                          type="button"
                          disabled={assigningId === slot.id}
                          onClick={() => handleAssign(slot)}
                          className="w-full text-left flex items-center gap-3 rounded-lg border border-border bg-card hover:bg-accent hover:border-accent-foreground/20 px-3 py-2.5 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="font-medium tabular-nums min-w-[5rem]">
                            {formatTime(slot.start_time)}–{formatTime(slot.end_time)}
                          </span>
                          <span className="text-muted-foreground truncate flex items-center gap-1">
                            <MapPin className="h-3 w-3 shrink-0" />
                            {slot.place_name}
                          </span>
                          {slot.class_type === "group" && (
                            <span className="text-muted-foreground flex items-center gap-1 ml-auto shrink-0">
                              <Users className="h-3 w-3" />
                              {slot.participant_count}/{slot.max_participants}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
          </div>

        </DialogContent>
      </Dialog>
    </>
  );
}

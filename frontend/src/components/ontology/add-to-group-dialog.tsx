"use client";

import { useEffect, useMemo, useState } from "react";
import { Calendar, Clock, MapPin, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { fetchContact } from "@/lib/api";
import {
  CONTACT_LEVEL_LABELS,
  DAY_LABELS,
  formatTime,
} from "@/lib/ontology-utils";
import type { ContactDetailData, ContactSummary, RecurringSlot } from "@/lib/types";

function scheduleLabel(group: RecurringSlot): string {
  if (group.recurrence_type === "once" && group.scheduled_date) {
    return new Date(`${group.scheduled_date}T12:00:00`).toLocaleDateString("pt-BR");
  }
  return `${DAY_LABELS[group.day_of_week]} · semanal`;
}

export function AddToGroupDialog({
  contact,
  groups,
  onOpenChange,
  onAdd,
}: {
  contact: ContactSummary;
  groups: RecurringSlot[];
  onOpenChange: (open: boolean) => void;
  onAdd: (group: RecurringSlot) => void;
}) {
  const [detail, setDetail] = useState<ContactDetailData | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchContact(contact.id)
      .then((result) => {
        if (active) setDetail(result);
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Não foi possível carregar os grupos. Tente novamente.");
        }
      });
    return () => {
      active = false;
    };
  }, [contact.id]);

  const membershipIds = useMemo(
    () => new Set(detail?.fixed_slots.map((slot) => slot.id) ?? []),
    [detail]
  );
  const selectedGroup = groups.find((group) => group.id === selectedGroupId) ?? null;
  const levelMismatch =
    selectedGroup &&
    contact.level &&
    selectedGroup.level &&
    contact.level !== selectedGroup.level;

  function groupUnavailableReason(group: RecurringSlot): string | null {
    if (membershipIds.has(group.id)) return "Cliente já participa";
    if (group.participant_count >= group.max_participants) return "Grupo lotado";
    if (group.status === "paused" || group.status === "inactive") return "Grupo indisponível";
    return null;
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Adicionar a um grupo</DialogTitle>
          <DialogDescription>
            Selecione o grupo para incluir {contact.display_name}.
          </DialogDescription>
        </DialogHeader>

        {!detail && !error && (
          <p className="py-8 text-center text-sm text-muted-foreground">Carregando grupos...</p>
        )}

        {error && <p className="py-8 text-center text-sm text-destructive">{error}</p>}

        {detail && groups.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Nenhum grupo foi criado ainda.
          </p>
        )}

        {detail && groups.length > 0 && (
          <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
            {groups.map((group) => {
              const unavailableReason = groupUnavailableReason(group);
              return (
                <label
                  key={group.id}
                  className={`flex rounded-lg border p-3 ${
                    unavailableReason
                      ? "cursor-not-allowed opacity-60"
                      : "cursor-pointer hover:border-indigo-400"
                  } ${selectedGroupId === group.id ? "border-primary bg-primary/5" : "border-border"}`}
                >
                  <input
                    type="radio"
                    name="existing-group"
                    value={group.id}
                    checked={selectedGroupId === group.id}
                    disabled={Boolean(unavailableReason)}
                    onChange={() => setSelectedGroupId(group.id)}
                    className="mt-1 h-4 w-4 accent-primary"
                  />
                  <span className="ml-3 min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-3">
                      <span className="truncate font-medium">{group.label || "Grupo"}</span>
                      <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                        <Users className="h-3.5 w-3.5" />
                        {group.participant_count}/{group.max_participants}
                      </span>
                    </span>
                    <span className="mt-1 grid gap-1 text-xs text-muted-foreground sm:grid-cols-3">
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3.5 w-3.5" />
                        <span className="truncate">{group.place_name}</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3.5 w-3.5" />
                        {scheduleLabel(group)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {formatTime(group.start_time)}–{formatTime(group.end_time)}
                      </span>
                    </span>
                    <span className="mt-1 block text-xs">
                      {unavailableReason ??
                        (group.level
                          ? `Nível: ${CONTACT_LEVEL_LABELS[group.level] ?? group.level}`
                          : "Sem nível definido")}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}

        {levelMismatch && (
          <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            O nível do cliente é{" "}
            {CONTACT_LEVEL_LABELS[contact.level as string] ?? contact.level}, enquanto o grupo é{" "}
            {CONTACT_LEVEL_LABELS[selectedGroup.level as string] ?? selectedGroup.level}. A inclusão
            não altera nenhum dos níveis.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            disabled={!selectedGroup}
            onClick={() => {
              if (selectedGroup) onAdd(selectedGroup);
            }}
          >
            Adicionar ao grupo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

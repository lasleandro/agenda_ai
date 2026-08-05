"use client";

import { useMemo, useState } from "react";
import { Calendar, Clock, GraduationCap, MapPin, Search, Users } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  CONTACT_LEVEL_LABELS,
  DAY_LABELS,
  formatTime,
} from "@/lib/ontology-utils";
import type { RecurringSlot } from "@/lib/types";
import { GroupDetailsDialog } from "./group-details-dialog";

function groupSchedule(group: RecurringSlot): string {
  if (group.recurrence_type === "once" && group.scheduled_date) {
    return new Date(`${group.scheduled_date}T12:00:00`).toLocaleDateString("pt-BR");
  }
  return DAY_LABELS[group.day_of_week];
}

export function GroupsTab({ groups }: { groups: RecurringSlot[] | null }) {
  const [query, setQuery] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);

  const filteredGroups = useMemo(() => {
    if (!groups) return [];
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return groups;
    return groups.filter(
      (group) =>
        (group.label ?? "grupo").toLowerCase().includes(normalizedQuery) ||
        group.place_name.toLowerCase().includes(normalizedQuery) ||
        (group.level &&
          (CONTACT_LEVEL_LABELS[group.level] ?? group.level)
            .toLowerCase()
            .includes(normalizedQuery))
    );
  }, [groups, query]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="relative w-full max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar por grupo, local ou nível..."
          className="pl-9"
        />
      </div>

      {groups === null && <p className="text-sm text-muted-foreground">Carregando...</p>}

      {groups !== null && filteredGroups.length === 0 && (
        <p className="text-sm text-muted-foreground">Nenhum grupo encontrado.</p>
      )}

      {filteredGroups.length > 0 && (
        <div className="grid min-h-0 flex-1 auto-rows-min grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-2 xl:grid-cols-3">
          {filteredGroups.map((group) => (
            <button
              key={group.id}
              type="button"
              onClick={() => setSelectedGroupId(group.id)}
              className="space-y-3 rounded-xl border border-border bg-card p-4 text-left shadow-sm hover:border-indigo-400"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="font-semibold text-foreground">{group.label || "Grupo"}</p>
                <span className="flex shrink-0 items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  <Users className="h-3.5 w-3.5" />
                  {group.participant_count}/{group.max_participants}
                </span>
              </div>

              <div className="space-y-2 text-xs text-muted-foreground">
                <p className="flex items-center gap-2">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  {group.place_name}
                </p>
                <p className="flex items-center gap-2">
                  <Calendar className="h-3.5 w-3.5 shrink-0" />
                  {groupSchedule(group)}
                  {group.recurrence_type === "weekly" ? " · semanal" : " · esporádico"}
                </p>
                <p className="flex items-center gap-2">
                  <Clock className="h-3.5 w-3.5 shrink-0" />
                  {formatTime(group.start_time)}–{formatTime(group.end_time)}
                </p>
                {group.level && (
                  <p className="flex items-center gap-2">
                    <GraduationCap className="h-3.5 w-3.5 shrink-0" />
                    {CONTACT_LEVEL_LABELS[group.level] ?? group.level}
                  </p>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      <GroupDetailsDialog
        groupId={selectedGroupId}
        open={selectedGroupId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedGroupId(null);
        }}
      />
    </div>
  );
}

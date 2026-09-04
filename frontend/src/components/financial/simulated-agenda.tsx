"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { EventClickArg, EventInput } from "@fullcalendar/core";
import { CalendarDays } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatBrlFromCents } from "@/lib/financial-utils";
import { fetchCalendar, fetchRecurringSlots } from "@/lib/api";
import { STATUS_COLORS } from "@/lib/calendar-utils";
import type {
  FinancialScenarioScheduleEvent,
  RecurringSlot,
} from "@/lib/types";

function formatClassLabel(participantCount: number) {
  return participantCount === 1 ? "Individual" : `${participantCount} pessoas`;
}

function formatTime(value: string) {
  return value.slice(0, 5);
}

function formatDate(value: string) {
  return value.split("-").reverse().join("/");
}

function dayAfter(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function durationMinutes(event: FinancialScenarioScheduleEvent) {
  const toMinutes = (value: string) => {
    const [hours, minutes] = value.split(":").map(Number);
    return hours * 60 + minutes;
  };
  return toMinutes(event.end_time) - toMinutes(event.start_time);
}

function realSlotEvent(slot: RecurringSlot): EventInput | null {
  if (
    slot.status !== "active" ||
    slot.slot_kind !== "class" ||
    slot.participant_count === 0
  ) return null;
  const title = `${slot.label || (slot.class_type === "group" ? "Grupo" : "Aula")} · ${slot.place_name}`;
  if (slot.recurrence_type === "once" && slot.scheduled_date) {
    return {
      id: `slot-${slot.id}`,
      title,
      start: `${slot.scheduled_date}T${slot.start_time}`,
      end: `${slot.scheduled_date}T${slot.end_time}`,
      backgroundColor: "#4f46e5",
      borderColor: "#4338ca",
      textColor: "#ffffff",
    };
  }
  return {
    id: `slot-${slot.id}`,
    title,
    daysOfWeek: [(slot.day_of_week + 1) % 7],
    startTime: slot.start_time.slice(0, 5),
    endTime: slot.end_time.slice(0, 5),
    startRecur: slot.valid_from ?? undefined,
    endRecur: slot.valid_until ? dayAfter(slot.valid_until) : undefined,
    backgroundColor: "#4f46e5",
    borderColor: "#4338ca",
    textColor: "#ffffff",
  };
}

export function SimulatedAgenda({
  events,
  period,
  estimated = false,
}: {
  events: FinancialScenarioScheduleEvent[];
  period: { from: string; to: string };
  estimated?: boolean;
}) {
  const [selectedEvent, setSelectedEvent] =
    useState<FinancialScenarioScheduleEvent | null>(null);
  const [agendaView, setAgendaView] = useState<"simulated" | "real">("simulated");
  const [realEvents, setRealEvents] = useState<EventInput[]>([]);
  const [realLoading, setRealLoading] = useState(false);
  const [realError, setRealError] = useState<string | null>(null);
  const calendarEvents: EventInput[] = events.map((event) => ({
    id: event.id,
    title: `Simulado · ${formatClassLabel(event.participant_count)} · ${event.place_name}`,
    start: `${event.local_date}T${event.start_time}`,
    end: `${event.local_date}T${event.end_time}`,
    backgroundColor: event.time_category === "prime" ? "#7c3aed" : "#4f46e5",
    borderColor: event.time_category === "prime" ? "#6d28d9" : "#4338ca",
    textColor: "#ffffff",
    extendedProps: { simulatedEvent: event },
  }));

  function handleEventClick(arg: EventClickArg) {
    setSelectedEvent(
      arg.event.extendedProps.simulatedEvent as FinancialScenarioScheduleEvent
    );
  }

  function showRealAgenda() {
    setRealLoading(true);
    setRealError(null);
    setAgendaView("real");
  }

  useEffect(() => {
    if (agendaView !== "real") return;
    let active = true;
    Promise.all([fetchCalendar(period.from, period.to), fetchRecurringSlots()])
      .then(([calendar, slots]) => {
        if (!active) return;
        const appointments = calendar.appointments.map((appointment) => {
          const colors = STATUS_COLORS[appointment.status];
          const names = appointment.participants?.length
            ? appointment.participants.map((participant) => participant.display_name).join(" + ")
            : appointment.contact_name;
          return {
            id: appointment.id,
            title: `${names} · ${appointment.service}${appointment.place_name ? ` · ${appointment.place_name}` : ""}`,
            start: appointment.start_at,
            end: appointment.end_at,
            backgroundColor: colors.bg,
            borderColor: colors.border,
            textColor: colors.text,
          };
        });
        const instructorEvents = calendar.events.map((event) => ({
          id: `event-${event.id}`,
          title: `${event.title || event.event_type}${event.place_name ? ` · ${event.place_name}` : ""}`,
          start: event.start_at,
          end: event.end_at,
          backgroundColor: "#f59e0b",
          borderColor: "#b45309",
          textColor: "#ffffff",
        }));
        setRealEvents([
          ...appointments,
          ...instructorEvents,
          ...slots.slots.map(realSlotEvent).filter((event): event is EventInput => event !== null),
        ]);
      })
      .catch((caught) => {
        if (active) {
          setRealError(caught instanceof Error ? caught.message : "Não foi possível carregar a agenda real. Tente novamente.");
        }
      })
      .finally(() => {
        if (active) setRealLoading(false);
      });
    return () => {
      active = false;
    };
  }, [agendaView, period.from, period.to]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="size-4 text-primary" />
          Agenda
        </CardTitle>
        <CardDescription>
          {agendaView === "simulated"
            ? estimated
              ? "A estimativa usa apenas os horários e locais que você já configurou."
              : "Alocação ilustrativa da capacidade do cenário. Não altera a agenda real."
            : "Agenda atual do período selecionado, em modo somente leitura."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex w-fit gap-1 rounded-lg border bg-muted/30 p-1">
          <Button
            size="sm"
            variant={agendaView === "simulated" ? "secondary" : "ghost"}
            onClick={() => setAgendaView("simulated")}
          >
            Simulada
          </Button>
          <Button
            size="sm"
            variant={agendaView === "real" ? "secondary" : "ghost"}
            onClick={showRealAgenda}
          >
            Real
          </Button>
        </div>
        {agendaView === "simulated" && estimated ? (
          <div className="space-y-2 py-8 text-center text-sm text-muted-foreground">
            <p>
              A capacidade estimada aparece nos resultados, mas uma agenda
              simulada por horário e local exige sua jornada configurada.
            </p>
            <Link
              href="/minhas-regras"
              className="inline-flex h-8 items-center rounded-md border px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted"
            >
              Configurar jornada
            </Link>
          </div>
        ) : agendaView === "simulated" && calendarEvents.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Este cenário não preenche horários reservados no período selecionado.
          </p>
        ) : agendaView === "real" && realLoading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Carregando agenda real...</p>
        ) : agendaView === "real" && realError ? (
          <p className="py-8 text-center text-sm text-destructive">{realError}</p>
        ) : (
          <FullCalendar
            key={`${agendaView}-${period.from}-${period.to}`}
            plugins={[dayGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            initialDate={period.from}
            headerToolbar={{ left: "prev,next today", center: "title", right: "" }}
            buttonText={{ today: "Hoje" }}
            locale="pt-br"
            firstDay={1}
            height="auto"
            fixedWeekCount={false}
            events={agendaView === "simulated" ? calendarEvents : realEvents}
            eventClick={agendaView === "simulated" ? handleEventClick : undefined}
          />
        )}
      </CardContent>

      <Dialog
        open={selectedEvent !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedEvent(null);
        }}
      >
        <DialogContent>
          {selectedEvent && (
            <>
              <DialogHeader>
                <DialogTitle>Horário reservado no cenário</DialogTitle>
                <DialogDescription>
                  Este bloco é uma projeção e não cria um compromisso na agenda real.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-3 text-sm">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Data</span>
                  <span className="font-medium">{formatDate(selectedEvent.local_date)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Horário</span>
                  <span className="font-medium">
                    {formatTime(selectedEvent.start_time)} – {formatTime(selectedEvent.end_time)}
                    {" · "}{durationMinutes(selectedEvent)} min
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Local</span>
                  <span className="font-medium">{selectedEvent.place_name}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Formato</span>
                  <span className="font-medium">
                    {formatClassLabel(selectedEvent.participant_count)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Categoria</span>
                  <Badge variant="secondary">
                    {selectedEvent.time_category === "prime" ? "Horário nobre" : "Horário regular"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">R$/pessoa/hora</span>
                  <span className="font-medium">
                    {formatBrlFromCents(selectedEvent.hourly_rate_cents)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Receita do horário</span>
                  <span className="font-medium">
                    {formatBrlFromCents(selectedEvent.total_revenue_cents)}
                  </span>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

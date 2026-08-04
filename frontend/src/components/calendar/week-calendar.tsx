"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { EventClickArg, DatesSetArg } from "@fullcalendar/core";
import { fetchCalendar } from "@/lib/api";
import { STATUS_COLORS } from "@/lib/calendar-utils";
import type { CalendarEvent } from "@/lib/types";
import { AppointmentPanel } from "./appointment-panel";

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function WeekCalendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const calendarRef = useRef<FullCalendar | null>(null);

  const loadRange = useCallback(async (start: Date, end: Date) => {
    const startDate = toISODate(start);
    const endDate = toISODate(new Date(end.getTime() - 1));
    try {
      const data = await fetchCalendar(startDate, endDate);
      const mapped: CalendarEvent[] = data.appointments.map((a) => {
        const colors = STATUS_COLORS[a.status] ?? STATUS_COLORS.tentative;
        return {
          id: a.id,
          title: `${a.contact_name} · ${a.service}`,
          start: a.start_at,
          end: a.end_at,
          backgroundColor: colors.bg,
          borderColor: colors.border,
          textColor: colors.text,
          extendedProps: {
            contactName: a.contact_name,
            service: a.service,
            status: a.status,
            source: a.source,
          },
        };
      });
      setEvents(mapped);
    } catch (err) {
      console.error("Failed to load calendar range", err);
    }
  }, []);

  const handleDatesSet = useCallback(
    (arg: DatesSetArg) => {
      loadRange(arg.start, arg.end);
    },
    [loadRange]
  );

  const handleEventClick = useCallback((arg: EventClickArg) => {
    setSelectedId(arg.event.id);
    setPanelOpen(true);
  }, []);

  const eventCountLabel = useMemo(
    () => `${events.length} agendamento${events.length === 1 ? "" : "s"}`,
    [events]
  );

  return (
    <div className="flex-1 flex flex-col min-h-0 p-4 md:p-6 gap-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Agenda</h1>
        <span className="text-sm text-muted-foreground">{eventCountLabel}</span>
      </div>

      <div className="flex-1 min-h-0 bg-[var(--bg-surface)] rounded-xl p-3 shadow-sm border border-[var(--border-subtle)]">
        <FullCalendar
          ref={calendarRef}
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          headerToolbar={{
            left: "prev,next today",
            center: "title",
            right: "timeGridWeek,timeGridDay,dayGridMonth",
          }}
          locale="pt-br"
          firstDay={1}
          height="100%"
          allDaySlot={false}
          slotMinTime="07:00:00"
          slotMaxTime="21:00:00"
          nowIndicator
          events={events}
          eventClick={handleEventClick}
          datesSet={handleDatesSet}
          buttonText={{
            today: "Hoje",
            week: "Semana",
            day: "Dia",
            month: "Mês",
          }}
        />
      </div>

      <AppointmentPanel
        appointmentId={selectedId}
        open={panelOpen}
        onOpenChange={setPanelOpen}
      />
    </div>
  );
}

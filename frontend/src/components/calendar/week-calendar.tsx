"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";
import type {
  DateSelectArg,
  DatesSetArg,
  EventClickArg,
  EventInput,
  EventMountArg,
} from "@fullcalendar/core";
import {
  createAppointment,
  fetchCalendar,
  fetchContacts,
  fetchPlaces,
  fetchRecurringSlots,
} from "@/lib/api";
import { STATUS_COLORS } from "@/lib/calendar-utils";
import { CONTACT_LEVEL_LABELS } from "@/lib/ontology-utils";
import type {
  AppointmentCreateInput,
  AppointmentSummary,
  ContactSummary,
  Place,
  RecurringSlot,
} from "@/lib/types";
import { AppointmentFormDialog } from "./appointment-form-dialog";
import { AppointmentPanel } from "./appointment-panel";
import { GroupDetailsDialog } from "@/components/ontology/group-details-dialog";

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// FullCalendar's daysOfWeek uses JS Date.getDay() (Sunday=0..Saturday=6);
// our day_of_week uses Python's date.weekday() (Monday=0..Sunday=6).
function toFullCalendarDay(dayOfWeek: number): number {
  return (dayOfWeek + 1) % 7;
}

function slotToEvent(slot: RecurringSlot): EventInput {
  const courtLabel = slot.label ? ` · ${slot.label}` : "";
  const isScheduledClass = slot.participant_count > 0;
  const levelLabel = slot.level
    ? ` · ${CONTACT_LEVEL_LABELS[slot.level] ?? slot.level}`
    : "";
  const schedule = slot.recurrence_type === "once" && slot.scheduled_date
    ? {
        start: `${slot.scheduled_date}T${slot.start_time}`,
        end: `${slot.scheduled_date}T${slot.end_time}`,
      }
    : {
        daysOfWeek: [toFullCalendarDay(slot.day_of_week)],
        startTime: slot.start_time.slice(0, 5),
        endTime: slot.end_time.slice(0, 5),
      };

  return {
    id: `slot-${slot.id}`,
    title: isScheduledClass
      ? `${slot.label || (slot.class_type === "group" ? "Grupo" : "Aula")} · ${slot.place_name}${levelLabel}`
      : `${slot.place_name}${courtLabel}`,
    ...schedule,
    display: isScheduledClass ? "auto" : "background",
    overlap: !isScheduledClass,
    backgroundColor: isScheduledClass ? "#4f46e5" : "#c7d2fe",
    borderColor: isScheduledClass ? "#4338ca" : undefined,
    textColor: isScheduledClass ? "#ffffff" : undefined,
    classNames: isScheduledClass
      ? ["agenda-scheduled-group", "cursor-pointer"]
      : ["agenda-place-slot"],
    extendedProps: { kind: "recurring_slot", slot },
  };
}

function appointmentToEvent(appointment: AppointmentSummary): EventInput {
  const colors = STATUS_COLORS[appointment.status] ?? STATUS_COLORS.tentative;
  const placeLabel = appointment.place_name ? ` · ${appointment.place_name}` : "";
  const schedule = appointment.recurrence_rule === "FREQ=WEEKLY"
    ? {
        daysOfWeek: [new Date(appointment.start_at).getDay()],
        startTime: new Date(appointment.start_at).toTimeString().slice(0, 5),
        endTime: new Date(appointment.end_at).toTimeString().slice(0, 5),
        startRecur: appointment.start_at.slice(0, 10),
      }
    : {
        start: appointment.start_at,
        end: appointment.end_at,
      };
  return {
    id: appointment.id,
    title: `${appointment.contact_name} · ${appointment.service}${placeLabel}`,
    ...schedule,
    backgroundColor: colors.bg,
    borderColor: colors.border,
    textColor: colors.text,
    extendedProps: {
      contactName: appointment.contact_name,
      service: appointment.service,
      placeName: appointment.place_name,
      status: appointment.status,
      source: appointment.source,
    },
  };
}

function timeToMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function suggestedPlaceForRange(
  start: Date,
  end: Date,
  slots: RecurringSlot[]
): string | null {
  if (start.toDateString() !== end.toDateString()) return null;
  const dayOfWeek = (start.getDay() + 6) % 7;
  const startMinutes = start.getHours() * 60 + start.getMinutes();
  const endMinutes = end.getHours() * 60 + end.getMinutes();
  const matchingSlot = slots.find(
    (slot) =>
      slot.status === "active" &&
      slot.day_of_week === dayOfWeek &&
      startMinutes >= timeToMinutes(slot.start_time) &&
      endMinutes <= timeToMinutes(slot.end_time)
  );
  return matchingSlot?.place_id ?? null;
}

interface BookingSelection {
  start: Date;
  end: Date;
  suggestedPlaceId: string | null;
}

export function WeekCalendar() {
  const [events, setEvents] = useState<EventInput[]>([]);
  const [slots, setSlots] = useState<RecurringSlot[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [contacts, setContacts] = useState<ContactSummary[]>([]);
  const [bookingSelection, setBookingSelection] = useState<BookingSelection | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupPanelOpen, setGroupPanelOpen] = useState(false);
  const calendarRef = useRef<FullCalendar | null>(null);

  const reloadSlots = useCallback(() => {
    fetchRecurringSlots().then((res) => setSlots(res.slots));
  }, []);

  useEffect(() => {
    reloadSlots();
    fetchPlaces().then((res) => setPlaces(res.places));
    fetchContacts().then((res) => setContacts(res.contacts));
  }, [reloadSlots]);

  const loadRange = useCallback(async (start: Date, end: Date) => {
    const startDate = toISODate(start);
    const endDate = toISODate(new Date(end.getTime() - 1));
    try {
      const data = await fetchCalendar(startDate, endDate);
      const mapped = data.appointments.map(appointmentToEvent);
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
    if (arg.event.extendedProps.kind === "recurring_slot") {
      const slot = arg.event.extendedProps.slot as RecurringSlot;
      if (slot.participant_count === 0) return;
      setSelectedGroupId(slot.id);
      setGroupPanelOpen(true);
      return;
    }
    setSelectedId(arg.event.id);
    setPanelOpen(true);
  }, []);

  const handleEventMount = useCallback((arg: EventMountArg) => {
    if (arg.event.extendedProps.kind !== "recurring_slot") return;
    if (arg.event.extendedProps.slot.participant_count > 0) return;
    const label = document.createElement("span");
    label.className = "agenda-place-slot-label";
    label.textContent = arg.event.title;
    arg.el.appendChild(label);
    arg.el.setAttribute("aria-label", `Local reservado: ${arg.event.title}`);
  }, []);

  const openBooking = useCallback(
    (start: Date, end: Date) => {
      setBookingSelection({
        start,
        end,
        suggestedPlaceId: suggestedPlaceForRange(start, end, slots),
      });
    },
    [slots]
  );

  const handleSelect = useCallback(
    (selection: DateSelectArg) => {
      openBooking(selection.start, selection.end);
    },
    [openBooking]
  );

  const handleDateClick = useCallback(
    (selection: DateClickArg) => {
      const start = new Date(selection.date);
      if (selection.allDay) start.setHours(8, 0, 0, 0);
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      openBooking(start, end);
    },
    [openBooking]
  );

  const handleCreateBooking = useCallback(
    async (input: AppointmentCreateInput) => {
      const contact = contacts.find((item) => item.id === input.contact_id);
      const place = places.find((item) => item.id === input.place_id);
      const temporaryId = `booking-${crypto.randomUUID()}`;
      const optimistic = appointmentToEvent({
        id: temporaryId,
        contact_id: input.contact_id,
        contact_name: contact?.display_name ?? "Cliente",
        place_id: input.place_id,
        place_name: place?.name ?? null,
        service: input.service,
        start_at: input.start_at,
        end_at: input.end_at,
        status: "confirmed",
        source: "dashboard",
        recurrence_rule: input.is_recurring ? "FREQ=WEEKLY" : null,
      });
      setEvents((current) => [...current, optimistic]);

      try {
        const saved = await createAppointment(input);
        setEvents((current) =>
          current.map((event) =>
            event.id === temporaryId ? appointmentToEvent(saved) : event
          )
        );
        calendarRef.current?.getApi().unselect();
      } catch (requestError) {
        setEvents((current) => current.filter((event) => event.id !== temporaryId));
        throw requestError;
      }
    },
    [contacts, places]
  );

  const eventCountLabel = useMemo(
    () => {
      const scheduledCount =
        events.length + slots.filter((slot) => slot.participant_count > 0).length;
      return `${scheduledCount} agendamento${scheduledCount === 1 ? "" : "s"}`;
    },
    [events, slots]
  );

  const calendarEvents: EventInput[] = useMemo(
    () => [...events, ...slots.map(slotToEvent)],
    [events, slots]
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
          selectable
          selectMirror
          events={calendarEvents}
          selectOverlap={(event) =>
            event.display === "background" ||
            event.extendedProps.status === "cancelled"
          }
          select={handleSelect}
          dateClick={handleDateClick}
          eventClick={handleEventClick}
          eventDidMount={handleEventMount}
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

      <GroupDetailsDialog
        groupId={selectedGroupId}
        open={groupPanelOpen}
        onOpenChange={setGroupPanelOpen}
      />

      {bookingSelection && (
        <AppointmentFormDialog
          key={bookingSelection.start.getTime()}
          open
          onOpenChange={(open) => {
            if (!open) setBookingSelection(null);
          }}
          start={bookingSelection.start}
          end={bookingSelection.end}
          suggestedPlaceId={bookingSelection.suggestedPlaceId}
          contacts={contacts}
          places={places}
          onPlaceCreated={(place) =>
            setPlaces((current) => [...current, place])
          }
          onCreate={handleCreateBooking}
        />
      )}

    </div>
  );
}

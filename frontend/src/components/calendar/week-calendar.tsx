"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Clock, RefreshCw } from "lucide-react";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import dayGridPlugin from "@fullcalendar/daygrid";
import listPlugin from "@fullcalendar/list";
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
  createInstructorEvent,
  fetchCalendar,
  fetchContacts,
  fetchPlaces,
  fetchRecurringSlots,
  fetchWaitlistEntries,
  fulfillWaitlistEntry,
} from "@/lib/api";
import { AGENDA_REFRESH_EVENT } from "@/lib/agenda-events";
import { Button } from "@/components/ui/button";
import { STATUS_COLORS } from "@/lib/calendar-utils";
import { CONTACT_LEVEL_LABELS, EVENT_TYPE_LABELS } from "@/lib/ontology-utils";
import type {
  AppointmentCreateInput,
  AppointmentSummary,
  ContactSummary,
  InstructorEvent,
  InstructorEventInput,
  Place,
  RecurringSlot,
  WaitlistEntry,
} from "@/lib/types";
import { AppointmentFormDialog } from "./appointment-form-dialog";
import { AppointmentPanel } from "./appointment-panel";
import { InstructorEventPanel } from "./instructor-event-panel";
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
  const isScheduledClass = slot.slot_kind === "class";
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
  const participantNames = appointment.participants?.length
    ? appointment.participants.map((p) => p.display_name).join(" + ")
    : appointment.contact_name;
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
  const courtesyTag = appointment.billing_type === "courtesy" ? " (Cortesia)" : "";
  return {
    id: appointment.id,
    title: `${participantNames} · ${appointment.service}${placeLabel}${courtesyTag}`,
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
      occurrenceDate: appointment.occurrence_date,
      classType: appointment.class_type ?? "individual",
      participantCount: appointment.participants?.length ?? 1,
    },
  };
}

// Grey "ghost" card for a Fila de Espera entry — deliberately distinct from
// every STATUS_COLORS entry so it reads unmistakably as "not a real
// booking" (waitlist roadmap v0.1, Phase 3).
function waitlistEntryToEvent(entry: WaitlistEntry): EventInput {
  const placeLabel = entry.place_name ? ` · ${entry.place_name}` : "";
  return {
    id: `waitlist-${entry.id}`,
    title: `Fila de espera · ${entry.contact_name}${placeLabel}`,
    start: `${entry.desired_date}T${entry.desired_start_time}`,
    end: `${entry.desired_date}T${entry.desired_end_time}`,
    backgroundColor: "#e5e7eb",
    borderColor: "#9ca3af",
    textColor: "#374151",
    classNames: ["agenda-waitlist-entry", "cursor-pointer"],
    extendedProps: { kind: "waitlist_entry", entry },
  };
}

// Non-class calendar occupant — refereeing, workshop, clinic (instructor
// events roadmap v0.1). Distinct amber color, not confusable with
// appointment-status colors or the grey waitlist ghost cards.
function instructorEventToEvent(event: InstructorEvent): EventInput {
  const typeLabel = EVENT_TYPE_LABELS[event.event_type] ?? event.event_type;
  const placeLabel = event.place_name ? ` · ${event.place_name}` : "";
  return {
    id: `event-${event.id}`,
    title: `${event.title || typeLabel}${placeLabel}`,
    start: event.start_at,
    end: event.end_at,
    backgroundColor: "#f59e0b",
    borderColor: "#b45309",
    textColor: "#ffffff",
    classNames: ["agenda-instructor-event"],
    extendedProps: { kind: "instructor_event", event },
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
  const localDate = [
    start.getFullYear(),
    String(start.getMonth() + 1).padStart(2, "0"),
    String(start.getDate()).padStart(2, "0"),
  ].join("-");
  const dayOfWeek = (start.getDay() + 6) % 7;
  const startMinutes = start.getHours() * 60 + start.getMinutes();
  const endMinutes = end.getHours() * 60 + end.getMinutes();
  const matchingPlaceIds = new Set(
    slots.filter(
      (slot) =>
        slot.status === "active" &&
        slot.slot_kind === "availability" &&
        slot.day_of_week === dayOfWeek &&
        (slot.recurrence_type === "weekly"
          ? (!slot.valid_from || slot.valid_from <= localDate) &&
            (!slot.valid_until || slot.valid_until >= localDate)
          : slot.scheduled_date === localDate) &&
        startMinutes >= timeToMinutes(slot.start_time) &&
        endMinutes <= timeToMinutes(slot.end_time)
    ).map((slot) => slot.place_id)
  );
  return matchingPlaceIds.size === 1
    ? [...matchingPlaceIds][0]
    : null;
}

interface BookingSelection {
  start: Date;
  end: Date;
  suggestedPlaceId: string | null;
  initialContactId?: string;
  fulfillsWaitlistEntryId?: string;
}

export function WeekCalendar() {
  const [events, setEvents] = useState<EventInput[]>([]);
  const [slots, setSlots] = useState<RecurringSlot[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [contacts, setContacts] = useState<ContactSummary[]>([]);
  const [waitlistEntries, setWaitlistEntries] = useState<WaitlistEntry[]>([]);
  const [showWaitlist, setShowWaitlist] = useState(false);
  const [showIncompleteGroups, setShowIncompleteGroups] = useState(false);
  const [bookingSelection, setBookingSelection] = useState<BookingSelection | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedOccurrenceDate, setSelectedOccurrenceDate] = useState<string | undefined>(
    undefined
  );
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedInstructorEvent, setSelectedInstructorEvent] =
    useState<InstructorEvent | null>(null);
  const [instructorEventPanelOpen, setInstructorEventPanelOpen] = useState(false);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [selectedGroupOccurrenceDate, setSelectedGroupOccurrenceDate] = useState<
    string | undefined
  >(undefined);
  const [groupPanelOpen, setGroupPanelOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches
  );
  const calendarRef = useRef<FullCalendar | null>(null);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const api = calendarRef.current?.getApi();
    if (!api) return;
    api.changeView(isMobile ? "listWeek" : "timeGridWeek");
  }, [isMobile]);

  const reloadSlots = useCallback(() => {
    return fetchRecurringSlots().then((res) => setSlots(res.slots));
  }, []);

  useEffect(() => {
    reloadSlots();
    fetchPlaces().then((res) => setPlaces(res.places));
    fetchContacts().then((res) => setContacts(res.contacts));
    fetchWaitlistEntries().then((res) =>
      setWaitlistEntries(res.entries.filter((entry) => entry.status === "open" || entry.status === "matched"))
    );
  }, [reloadSlots]);

  const loadRange = useCallback(async (start: Date, end: Date) => {
    const startDate = toISODate(start);
    const endDate = toISODate(new Date(end.getTime() - 1));
    try {
      const data = await fetchCalendar(startDate, endDate);
      const mapped = [
        ...data.appointments.map(appointmentToEvent),
        ...data.events.map(instructorEventToEvent),
      ];
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

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    const api = calendarRef.current?.getApi();
    try {
      await Promise.all([
        reloadSlots(),
        api ? loadRange(api.view.activeStart, api.view.activeEnd) : Promise.resolve(),
      ]);
    } finally {
      setRefreshing(false);
    }
  }, [reloadSlots, loadRange]);

  const handleToday = useCallback(() => {
    calendarRef.current?.getApi().gotoDate(new Date());
  }, []);

  useEffect(() => {
    window.addEventListener(AGENDA_REFRESH_EVENT, handleRefresh);
    return () => window.removeEventListener(AGENDA_REFRESH_EVENT, handleRefresh);
  }, [handleRefresh]);

  const handleEventClick = useCallback((arg: EventClickArg) => {
    if (arg.event.extendedProps.kind === "recurring_slot") {
      const slot = arg.event.extendedProps.slot as RecurringSlot;
      if (slot.slot_kind !== "class") return;
      setSelectedGroupId(slot.id);
      setSelectedGroupOccurrenceDate(arg.event.startStr.slice(0, 10));
      setGroupPanelOpen(true);
      return;
    }
    if (arg.event.extendedProps.kind === "instructor_event") {
      setSelectedInstructorEvent(arg.event.extendedProps.event as InstructorEvent);
      setInstructorEventPanelOpen(true);
      return;
    }
    if (arg.event.extendedProps.kind === "waitlist_entry") {
      const entry = arg.event.extendedProps.entry as WaitlistEntry;
      setBookingSelection({
        start: new Date(`${entry.desired_date}T${entry.desired_start_time}`),
        end: new Date(`${entry.desired_date}T${entry.desired_end_time}`),
        suggestedPlaceId: entry.place_id,
        initialContactId: entry.contact_id,
        fulfillsWaitlistEntryId: entry.id,
      });
      return;
    }
    setSelectedId(arg.event.id);
    setSelectedOccurrenceDate(arg.event.extendedProps.occurrenceDate as string | undefined);
    setPanelOpen(true);
  }, []);

  const handleEventMount = useCallback((arg: EventMountArg) => {
    if (arg.event.extendedProps.kind !== "recurring_slot") return;
    if (arg.event.extendedProps.slot.slot_kind === "class") return;
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
        class_type: input.class_type,
        participants: input.contact_ids?.map((id) => ({
          contact_id: id,
          display_name: contacts.find((item) => item.id === id)?.display_name ?? "Cliente",
        })),
        occurrence_date: input.start_at.slice(0, 10),
        billing_type: input.billing_type,
      });
      setEvents((current) => [...current, optimistic]);

      try {
        const saved = await createAppointment(input);
        setEvents((current) =>
          current.map((event) =>
            event.id === temporaryId
              ? appointmentToEvent({
                  ...saved,
                  occurrence_date: saved.occurrence_date ?? saved.start_at.slice(0, 10),
                })
              : event
          )
        );
        calendarRef.current?.getApi().unselect();

        if (bookingSelection?.fulfillsWaitlistEntryId) {
          const entryId = bookingSelection.fulfillsWaitlistEntryId;
          const fulfilledEntry = waitlistEntries.find((entry) => entry.id === entryId);
          setWaitlistEntries((current) => current.filter((entry) => entry.id !== entryId));
          void fulfillWaitlistEntry(entryId, saved.id).catch((caught) => {
            console.error("Failed to mark waitlist entry as fulfilled", caught);
            if (fulfilledEntry) {
              setWaitlistEntries((current) => [...current, fulfilledEntry]);
            }
          });
        }
      } catch (requestError) {
        setEvents((current) => current.filter((event) => event.id !== temporaryId));
        throw requestError;
      }
    },
    [contacts, places, bookingSelection, waitlistEntries]
  );

  const handleCreateEvent = useCallback(
    async (input: InstructorEventInput) => {
      const place = places.find((item) => item.id === input.place_id);
      const temporaryId = `event-pending-${crypto.randomUUID()}`;
      const optimistic = instructorEventToEvent({
        id: temporaryId,
        event_type: input.event_type,
        title: input.title ?? null,
        place_id: input.place_id ?? null,
        place_name: place?.name ?? null,
        start_at: input.start_at,
        end_at: input.end_at,
        income_cents: input.income_cents ?? null,
        note: input.note ?? null,
        status: "confirmed",
        created_at: new Date().toISOString(),
      });
      setEvents((current) => [...current, optimistic]);

      try {
        const saved = await createInstructorEvent(input);
        setEvents((current) =>
          current.map((event) =>
            event.id === optimistic.id ? instructorEventToEvent(saved) : event
          )
        );
        calendarRef.current?.getApi().unselect();
      } catch (requestError) {
        setEvents((current) => current.filter((event) => event.id !== optimistic.id));
        throw requestError;
      }
    },
    [places]
  );

  const eventCountLabel = useMemo(
    () => {
      const scheduledCount =
        events.length + slots.filter((slot) => slot.slot_kind === "class").length;
      return `${scheduledCount} agendamento${scheduledCount === 1 ? "" : "s"}`;
    },
    [events, slots]
  );

  const calendarEvents: EventInput[] = useMemo(
    () => {
      const allEvents = [
        ...events,
        ...slots.map(slotToEvent),
        ...(showWaitlist ? waitlistEntries.map(waitlistEntryToEvent) : []),
      ];
      if (!showIncompleteGroups) return allEvents;
      return allEvents.filter((event) => {
        if (event.extendedProps?.kind === "recurring_slot") {
          const slot = event.extendedProps.slot as RecurringSlot;
          return (
            slot.slot_kind === "class" &&
            slot.class_type === "group" &&
            slot.participant_count > 0 &&
            slot.participant_count < 4
          );
        }
        return (
          event.extendedProps?.classType === "group" &&
          event.extendedProps?.participantCount > 0 &&
          event.extendedProps?.participantCount < 4
        );
      });
    },
    [events, slots, showWaitlist, waitlistEntries, showIncompleteGroups]
  );

  return (
    <div className="flex-1 flex flex-col min-h-0 p-4 md:p-6 gap-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Agenda</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{eventCountLabel}</span>
          <button
            type="button"
            onClick={() => setShowWaitlist((current) => !current)}
            aria-pressed={showWaitlist}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              showWaitlist
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            <Clock className="h-3.5 w-3.5" />
            Fila de espera
            {waitlistEntries.length > 0 && (
              <span className="rounded-full bg-muted px-1.5 py-0.5">
                {waitlistEntries.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setShowIncompleteGroups((current) => !current)}
            aria-pressed={showIncompleteGroups}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              showIncompleteGroups
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            Grupos incompletos
          </button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Atualizar agenda"
            aria-label="Atualizar agenda"
          >
            <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-[var(--bg-surface)] rounded-xl p-3 shadow-sm border border-[var(--border-subtle)]">
        <FullCalendar
          ref={calendarRef}
          plugins={[timeGridPlugin, dayGridPlugin, listPlugin, interactionPlugin]}
          initialView={isMobile ? "listWeek" : "timeGridWeek"}
          headerToolbar={
            isMobile
              ? { left: "prev,next goToday", center: "", right: "title" }
              : {
                  left: "prev,next goToday",
                  center: "title",
                  right: "timeGridWeek,timeGridDay,dayGridMonth",
                }
          }
          customButtons={{
            goToday: {
              text: "Hoje",
              click: handleToday,
            },
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
            week: "Semana",
            day: "Dia",
            month: "Mês",
          }}
        />
      </div>

      <AppointmentPanel
        appointmentId={selectedId}
        occurrenceDate={selectedOccurrenceDate}
        open={panelOpen}
        onOpenChange={setPanelOpen}
      />

      <InstructorEventPanel
        event={selectedInstructorEvent}
        open={instructorEventPanelOpen}
        onOpenChange={setInstructorEventPanelOpen}
      />

      <GroupDetailsDialog
        groupId={selectedGroupId}
        occurrenceDate={selectedGroupOccurrenceDate}
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
          initialContactId={bookingSelection.initialContactId}
          contacts={contacts}
          places={places}
          onPlaceCreated={(place) =>
            setPlaces((current) => [...current, place])
          }
          onCreate={handleCreateBooking}
          onCreateEvent={handleCreateEvent}
        />
      )}

    </div>
  );
}

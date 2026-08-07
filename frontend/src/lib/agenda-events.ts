/**
 * Cross-component signal for "schedule data changed elsewhere" — e.g. the
 * assistant panel executing a propose_* mutation. No shared state/store
 * exists in this app yet, so a plain window CustomEvent is the simplest
 * way to let WeekCalendar refetch without prop-drilling or a new dependency.
 */
export const AGENDA_REFRESH_EVENT = "agenda:refresh";

export function notifyAgendaChanged() {
  window.dispatchEvent(new CustomEvent(AGENDA_REFRESH_EVENT));
}

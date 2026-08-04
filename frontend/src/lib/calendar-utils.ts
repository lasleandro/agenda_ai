export const STATUS_LABELS: Record<string, string> = {
  tentative: "Tentativo",
  confirmed: "Confirmado",
  cancelled: "Cancelado",
  completed: "Concluído",
};

export const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  tentative: { bg: "#fdcb6e", border: "#e6b656", text: "#5c4400" },
  confirmed: { bg: "#00b894", border: "#00a382", text: "#ffffff" },
  cancelled: { bg: "#e17055", border: "#c85f45", text: "#ffffff" },
  completed: { bg: "#6c5ce7", border: "#5c4bd1", text: "#ffffff" },
};

export function formatTimeRange(startIso: string, endIso: string): string {
  const start = new Date(startIso);
  const end = new Date(endIso);
  const fmt = (d: Date) =>
    d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${fmt(start)} – ${fmt(end)}`;
}

export function formatFullDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

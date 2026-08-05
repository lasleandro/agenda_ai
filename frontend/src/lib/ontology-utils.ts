// day_of_week follows Python's date.weekday(): Monday=0 .. Sunday=6.
export const DAY_LABELS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

export const CONTACT_LEVEL_LABELS: Record<string, string> = {
  beginner: "Iniciante",
  intermediate: "Intermediário",
  advanced: "Avançado",
};

export const CLASS_TYPE_LABELS: Record<string, string> = {
  individual: "Individual",
  group: "Grupo",
};

export function formatTime(value: string): string {
  return value.slice(0, 5);
}

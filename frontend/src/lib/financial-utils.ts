export function formatBrlFromCents(value: number | null): string {
  if (value === null) return "Não definido";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value / 100);
}

export function centsToRateInput(value: number | null): string {
  return value === null ? "" : (value / 100).toFixed(2).replace(".", ",");
}

export function parseRateToCents(value: string): number | null {
  const normalized = value.trim().replace(",", ".");
  if (!normalized) return null;
  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount < 0 || amount > 1_000_000) {
    throw new Error("Informe um valor entre R$ 0 e R$ 1.000.000 por hora");
  }
  return Math.round(amount * 100);
}

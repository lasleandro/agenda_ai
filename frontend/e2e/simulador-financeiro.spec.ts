import { expect, test, type Page } from "@playwright/test";

const PLACE_ID = "00000000-0000-4000-8000-0000000000c1";

const session = {
  user_id: "00000000-0000-4000-8000-000000000001",
  email: "pro@example.com",
  role: "professional",
  professional_id: "00000000-0000-4000-8000-000000000002",
  professional_name: "Tenant Teste",
  impersonating: false,
  features: ["commercial_financials"],
};

const rates = (["regular", "prime"] as const).flatMap((category) =>
  [1, 2, 3, 4].map((participant_count) => ({
    time_category: category,
    participant_count,
    hourly_rate_cents: 18000,
    effective_hourly_rate_cents: 18000,
    source: "place" as const,
  }))
);

const configuration = {
  prime_time_windows: [],
  default_rates: { place_id: null, place_name: null, rates },
  places: [{ place_id: PLACE_ID, place_name: "PlayTennis Morumbi", rates }],
};

const dashboard = {
  assumptions: {
    period_start: "2026-09-01",
    period_end: "2026-09-30",
    timezone: "America/Sao_Paulo",
    revenue_basis: "projected",
    capacity_basis: "configured",
    excluded_constraints: [],
  },
  capacity_source: {
    mode: "configured",
    configured: true,
    working_days: [1, 2, 3, 4, 5],
    minutes_per_working_day: 480,
    rate_basis: "configured",
    configuration_path: "/minhas-regras",
  },
  available_minutes: 10000,
  booked_minutes: 4000,
  unused_minutes: 6000,
  occupancy_pct: 40,
  participant_hours: 120,
  projected_revenue_cents: 5000000,
  unpriced_booking_count: 0,
  makeup_booking_count: 0,
  makeup_booked_minutes: 0,
  makeup_opportunity_cost_cents: 0,
  observed_participant_mix: [
    { participant_count: 1, percentage: 60 },
    { participant_count: 2, percentage: 20 },
    { participant_count: 3, percentage: 10 },
    { participant_count: 4, percentage: 10 },
  ],
  time_series: [],
  by_place: [],
  by_part_of_day: [],
  by_weekday: [],
  by_time_category: [],
  capacity_presets: [
    {
      key: "all_individual",
      label: "Todos os horários individuais",
      participant_mix: [{ participant_count: 1, percentage: 100 }],
      occupancy_pct: 100,
      participant_hours: 200,
      projected_revenue_cents: 6000000,
      customer_estimate: {
        calendar_weeks: 4,
        weekly_participant_hours: 50,
        minimum_customers: 17,
        maximum_customers: 50,
      },
    },
  ],
  capacity_sources: [],
};

async function stubJson(page: Page, url: string, body: object): Promise<void> {
  await page.route(url, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

async function stubSimulator(page: Page): Promise<void> {
  await stubJson(page, "**/api/auth/me", session);
  await stubJson(page, "**/api/financial/configuration", configuration);
  await stubJson(page, "**/api/financial/dashboard?**", dashboard);
  await stubJson(page, "**/api/financial/scenarios", { scenarios: [] });
}

const localSelect = (page: Page) =>
  page.locator('select:has(option:text-is("Todos os locais"))');

test("simulador: no period picker, premises block on top, all-locations price note", async ({
  page,
}) => {
  await stubSimulator(page);
  await page.goto("/financeiro/simulador");

  await expect(page.getByText("Premissas da simulação")).toBeVisible();

  // The inherited Financeiro period presets are gone; the window is stated.
  await expect(page.getByRole("button", { name: "Este mês" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Últimos 30 dias" })
  ).toHaveCount(0);
  await expect(
    page.getByText(/\d{2}\/\d{2}\/\d{4} – \d{2}\/\d{2}\/\d{4}/)
  ).toBeVisible();
  await expect(
    page.getByText("O simulador projeta sempre um mês.")
  ).toBeAttached();

  // No price editing anywhere.
  await expect(page.getByRole("button", { name: "Editar preços" })).toHaveCount(
    0
  );

  // With "Todos os locais" selected there is only the one-line note, no matrix.
  await expect(localSelect(page)).toHaveValue("");
  await expect(
    page.getByText("Usando os preços configurados de cada local.")
  ).toBeAttached();
  await expect(
    page.getByText("Preços configurados para este local.")
  ).toHaveCount(0);

  // Potencial tiles carry an active-customer range.
  await expect(page.getByText("17–50 clientes")).toBeVisible();
});

test("simulador: selecting a location shows the read-only price matrix", async ({
  page,
}) => {
  await stubSimulator(page);
  await page.goto("/financeiro/simulador");

  await expect(page.getByText("Premissas da simulação")).toBeVisible();
  await localSelect(page).selectOption(PLACE_ID);
  await expect(localSelect(page)).toHaveValue(PLACE_ID);

  await expect(
    page.getByRole("link", { name: "Minhas Regras" })
  ).toBeAttached();
  await expect(
    page.getByText("Usando os preços configurados de cada local.")
  ).toHaveCount(0);

  // The matrix is read-only: values render as cells, no editable fields.
  const priceSection = page
    .locator("section")
    .filter({ hasText: "Preços usados na simulação" });
  await expect(priceSection.getByRole("textbox")).toHaveCount(0);
  await expect(
    priceSection.getByRole("cell", { name: "R$ 180,00" }).first()
  ).toBeVisible();
});

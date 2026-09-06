import { expect, test, type Page } from "@playwright/test";

const PLACE_ID = "00000000-0000-4000-8000-0000000000a1";

const session = {
  user_id: "00000000-0000-4000-8000-000000000001",
  email: "pro@example.com",
  role: "professional",
  professional_id: "00000000-0000-4000-8000-000000000002",
  professional_name: "Tenant Teste",
  impersonating: false,
  features: ["commercial_financials"],
};

const place = {
  id: PLACE_ID,
  name: "PlayTennis Morumbi",
  address_line: null,
  city: null,
  state: null,
  postal_code: null,
  country: null,
  latitude: null,
  longitude: null,
  created_at: "2026-01-01T12:00:00Z",
  updated_at: "2026-01-01T12:00:00Z",
};

// One availability slot per weekday — the crowded layout that used to clip the
// rate matrix.
const slots = Array.from({ length: 7 }, (_, dayOfWeek) => ({
  id: `00000000-0000-4000-8000-00000000b00${dayOfWeek}`,
  place_id: PLACE_ID,
  place_name: place.name,
  day_of_week: dayOfWeek,
  start_time: "06:00:00",
  end_time: "12:00:00",
  label: null,
  group_name: null,
  class_type: "individual",
  slot_kind: "availability",
  level: null,
  max_participants: 1,
  recurrence_type: "weekly",
  scheduled_date: null,
  valid_from: null,
  valid_until: null,
  status: "active",
  participant_count: 0,
}));

const rates = (["regular", "prime"] as const).flatMap((category) =>
  [1, 2, 3, 4].map((participant_count) => ({
    time_category: category,
    participant_count,
    hourly_rate_cents: null,
    effective_hourly_rate_cents: 18000,
    source: "default" as const,
  }))
);

const placeMatrix = { place_id: PLACE_ID, place_name: place.name, rates };

async function stubJson(page: Page, url: string, body: object): Promise<void> {
  await page.route(url, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

async function stubPlacePage(page: Page): Promise<void> {
  await stubJson(page, "**/api/auth/me", session);
  await stubJson(page, `**/api/places/${PLACE_ID}`, place);
  await stubJson(page, "**/api/recurring-slots?**", { slots });
  await stubJson(page, "**/api/financial/configuration", {
    prime_time_windows: [],
    default_rates: { place_id: null, rates },
    places: [placeMatrix],
  });
}

test("mobile: rate matrix stays reachable with a full week of permanências", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await stubPlacePage(page);

  await page.goto(`/places/${PLACE_ID}`);

  // All seven weekday rows render.
  await expect(page.getByRole("button", { name: /Duplicar/ })).toHaveCount(7);

  // Valores section is collapsed by default on mobile.
  const toggle = page.getByRole("button", { name: "Valores R$/hora" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  const rateRegion = page.getByRole("region", {
    name: "Valores por período e formato",
  });
  await expect(rateRegion).toBeHidden();

  // Expanding it reveals the full matrix — every input rendered at its natural
  // height, nothing clipped to a sliver by the surrounding flex layout.
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(rateRegion).toBeVisible();

  const inputs = rateRegion.getByRole("textbox");
  await expect(inputs).toHaveCount(8);
  for (const input of await inputs.all()) {
    await input.scrollIntoViewIfNeeded();
    await expect(input).toBeVisible();
    await expect(input).toBeEditable();
    const box = await input.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThan(20);
  }
});

test("mobile: financial load error auto-expands the Valores section", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await stubJson(page, "**/api/auth/me", session);
  await stubJson(page, `**/api/places/${PLACE_ID}`, place);
  await stubJson(page, "**/api/recurring-slots?**", { slots });
  await page.route("**/api/financial/configuration", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Falha ao carregar valores" } }),
    });
  });

  await page.goto(`/places/${PLACE_ID}`);

  // On mobile the section starts collapsed; a load error must force it open so
  // the message is not buried inside a closed card.
  const toggle = page.getByRole("button", { name: "Valores R$/hora" });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("Falha ao carregar valores")).toBeAttached();
});

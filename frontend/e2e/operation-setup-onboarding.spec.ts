import { expect, test, type Locator, type Page } from "@playwright/test";

const baseProfessional = {
  user_id: "00000000-0000-4000-8000-000000000101",
  email: "pro@example.com",
  role: "professional",
  professional_id: "00000000-0000-4000-8000-000000000102",
  professional_name: "Tenant Onboarding",
  impersonating: false,
  features: [],
};

const unconfigured = { ...baseProfessional, operation_configured: false };
const configured = { ...baseProfessional, operation_configured: true };
const impersonatingUnconfigured = {
  ...baseProfessional,
  role: "platform_admin",
  impersonating: true,
  operation_configured: false,
};

async function stubSession(page: Page, session: object): Promise<void> {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(session),
    });
  });
}

// Base UI's Input ignores Playwright's synthesized key events under the
// headless shell; set the value through the native setter and fire `input`
// so React's onChange still runs (mirrors e2e/account-request.spec.ts).
async function setValue(locator: Locator, value: string): Promise<void> {
  await expect(async () => {
    await locator.evaluate((node, next) => {
      const el = node as HTMLInputElement;
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value"
      )?.set;
      setter?.call(el, next);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, value);
    await expect(locator).toHaveValue(value, { timeout: 500 });
  }).toPass({ timeout: 5000 });
}

test("unconfigured tenant sees Minha Operação first with a Comece aqui badge", async ({
  page,
}) => {
  await stubSession(page, unconfigured);
  await page.goto("/minhas-regras");

  await expect(page.locator("aside nav a").first()).toContainText(
    "Minha Operação"
  );
  await expect(
    page.locator("aside nav").getByText("Comece aqui")
  ).toBeVisible();
});

test("impersonating admin sees the badge when the tenant is unconfigured", async ({
  page,
}) => {
  await stubSession(page, impersonatingUnconfigured);
  await page.goto("/minhas-regras");

  await expect(page.locator("aside nav a").first()).toContainText(
    "Minha Operação"
  );
  await expect(
    page.locator("aside nav").getByText("Comece aqui")
  ).toBeVisible();
});

test("configured tenant keeps the normal order and no badge", async ({
  page,
}) => {
  await stubSession(page, configured);
  await page.goto("/agenda");

  await expect(page.locator("aside nav a").first()).toContainText("Agenda");
  await expect(page.locator("aside nav").getByText("Comece aqui")).toHaveCount(
    0
  );
});

test("login redirects an unconfigured tenant to Minha Operação", async ({
  page,
}) => {
  await stubSession(page, unconfigured);
  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ email: baseProfessional.email, role: "professional" }),
    });
  });

  await page.goto("/login");
  await setValue(page.locator("#email"), baseProfessional.email);
  await setValue(page.locator("#password"), "correct-password");
  await page.locator('form button[type="submit"]').click();

  // Cold-compiling /minhas-regras on the dev server can exceed the default 5s,
  // especially under parallel workers.
  await expect(page).toHaveURL(/\/minhas-regras$/, { timeout: 30000 });
});

test("direct /agenda landing bounces an unconfigured tenant to setup", async ({
  page,
}) => {
  await stubSession(page, unconfigured);
  await page.goto("/agenda");

  await expect(page).toHaveURL(/\/minhas-regras$/);
});

test("deliberate navigation to /agenda shows the setup empty state", async ({
  page,
}) => {
  await stubSession(page, unconfigured);
  await page.goto("/minhas-regras");

  await page.locator("aside nav a", { hasText: "Agenda" }).click();

  await expect(page).toHaveURL(/\/agenda$/);
  const cta = page.getByRole("link", { name: "Comece aqui", exact: true });
  await expect(cta).toBeVisible({ timeout: 15000 });
  await expect(cta).toHaveAttribute("href", "/minhas-regras");
  // Text nodes render zero-width under the e2e dev server (webfont not
  // loaded), so assert heading content rather than its visual box.
  await expect(page.locator("h1")).toHaveText("Sua agenda aparece aqui");
});

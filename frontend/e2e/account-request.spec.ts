import { expect, test, type Locator, type Page } from "@playwright/test";

// Browser regression for the shared "Solicitar uma conta" form (login view +
// /solicitar-conta), the landing CTAs, and the generic confirmation. The POST
// is stubbed, so no FastAPI backend is required.
//
// Text nodes are asserted with toBeAttached rather than toBeVisible: the CI
// sandbox has no network, so next/font web fonts fall back and some pure-text
// blocks measure zero height in headless Chromium. Form controls have explicit
// heights and are still asserted visible.

const GENERIC_CONFIRMATION = "Solicitação recebida.";

async function stubSubmit(page: Page, status = 202): Promise<void> {
  await page.route("**/api/account-requests", async (route) => {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(
        status === 202
          ? { message: "Solicitação recebida. Nossa equipe analisará os dados informados." }
          : { error: { code: "RATE_LIMITED", message: "Tente novamente mais tarde." } }
      ),
    });
  });
}

// Base UI's Input does not accept Playwright's synthesized key/insertText events
// under the sandbox's headless shell. Set the value through the native setter
// and fire `input` so React's onChange still runs. Retry the whole set until it
// sticks — the autofocused field can be wiped by a hydration re-render. The
// WhatsApp field reformats its own value, so callers verify "not empty".
async function setValue(
  locator: Locator,
  value: string,
  options: { exact?: boolean } = {}
): Promise<void> {
  const exact = options.exact ?? true;
  await expect(async () => {
    await locator.evaluate((node, next) => {
      const el = node as HTMLInputElement | HTMLTextAreaElement;
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement;
      const setter = Object.getOwnPropertyDescriptor(proto.prototype, "value")?.set;
      setter?.call(el, next);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, value);
    if (exact) {
      await expect(locator).toHaveValue(value, { timeout: 500 });
    } else {
      await expect(locator).not.toHaveValue("", { timeout: 500 });
    }
  }).toPass({ timeout: 5000 });
}

async function fillRequestForm(scope: Page, prefix: string): Promise<void> {
  await expect(scope.getByRole("button", { name: "Enviar solicitação" })).toBeVisible();
  await setValue(scope.locator(`#${prefix}-email`), "joao@example.com");
  await setValue(scope.locator(`#${prefix}-whatsapp`), "11987654321", { exact: false });
  await setValue(scope.locator(`#${prefix}-message`), "Dou aulas em São Paulo.");
  await setValue(scope.locator(`#${prefix}-name`), "João Silva");
  await scope.getByRole("button", { name: "Enviar solicitação" }).click();
}

test("/solicitar-conta renders the shared form and links back to login", async ({ page }) => {
  await page.goto("/solicitar-conta");

  await expect(page.getByRole("heading", { name: "Solicitar uma conta" })).toBeAttached();
  await expect(page.locator("#request-page-name")).toBeVisible();
  await expect(page.locator("#request-page-email")).toBeVisible();
  await expect(page.locator("#request-page-whatsapp")).toBeVisible();
  await expect(page.locator("#request-page-message")).toBeVisible();
  await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);

  await page.getByRole("link", { name: "Já tenho uma conta" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("login 'Solicitar uma conta' tab reveals the same form, no mailto", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Solicitar uma conta" }).click();

  await expect(page.locator("#login-request-name")).toBeVisible();
  await expect(page.locator("#login-request-email")).toBeVisible();
  await expect(page.locator("#login-request-whatsapp")).toBeVisible();
  await expect(page.locator("#login-request-message")).toBeVisible();
  await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);
});

test("a successful submission shows the generic confirmation", async ({ page }) => {
  await stubSubmit(page);
  await page.goto("/solicitar-conta");
  await fillRequestForm(page, "request-page");

  await expect(page.getByText(GENERIC_CONFIRMATION)).toBeAttached();
  await expect(page.locator("#request-page-email")).toHaveCount(0);
});

test("a rejected submission keeps the form and shows a safe error", async ({ page }) => {
  await stubSubmit(page, 429);
  await page.goto("/solicitar-conta");
  await fillRequestForm(page, "request-page");

  await expect(page.locator('p[role="alert"]')).toContainText("Tente novamente mais tarde.");
  await expect(page.locator("#request-page-email")).toBeVisible();
});

test("landing page request CTAs point to /solicitar-conta", async ({ page }) => {
  await page.goto("/");

  const ctas = page.getByRole("link", { name: "Solicitar uma conta" });
  const count = await ctas.count();
  expect(count).toBeGreaterThanOrEqual(1);
  for (let i = 0; i < count; i += 1) {
    await expect(ctas.nth(i)).toHaveAttribute("href", "/solicitar-conta");
  }
});

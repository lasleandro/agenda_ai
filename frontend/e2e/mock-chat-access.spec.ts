import { expect, test, type Page } from "@playwright/test";

const adminSession = {
  user_id: "00000000-0000-4000-8000-000000000001",
  email: "admin@example.com",
  role: "platform_admin",
  professional_id: "00000000-0000-4000-8000-000000000002",
  professional_name: "Tenant Teste",
  impersonating: true,
  features: [],
};

async function stubSession(page: Page, session: object): Promise<void> {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(session),
    });
  });
}

async function stubMockChatData(page: Page): Promise<void> {
  await page.route("**/api/dev/mock-customers", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ customers: [] }),
    });
  });
  await page.route("**/api/dev/mock-conversation", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        conversation_id: "00000000-0000-4000-8000-000000000003",
        instructor_phone: "+5511999990001",
        customer_phone: "+5511999000001",
      }),
    });
  });
  await page.route("**/api/conversations/00000000-0000-4000-8000-000000000003", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ messages: [], candidates: [] }),
    });
  });
}

async function setAssistantDraft(page: Page, value: string): Promise<void> {
  const input = page.getByPlaceholder("Pergunte algo sobre sua agenda...");
  await input.evaluate((node, next) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value"
    )?.set;
    setter?.call(node, next);
    node.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
  await expect(input).toHaveValue(value);
}

test("scoped platform admin sees Mock Chat, bottom WhatsApp, and can minimize Lob", async ({ page }) => {
  await stubSession(page, adminSession);
  await stubMockChatData(page);
  await page.goto("/dev/mock-chat");

  await expect(page.getByRole("link", { name: "Mock Chat" })).toBeVisible();
  const navigationLabels = await page.locator("aside nav a").allTextContents();
  expect(navigationLabels.at(-1)).toBe("Ative o Whatsapp");

  const launcher = page.locator('button[title="Assistente"]');
  const assistantInput = page.getByPlaceholder("Pergunte algo sobre sua agenda...");
  await launcher.click();
  await setAssistantDraft(page, "Tenho uma aula amanhã?");

  await page.getByRole("button", { name: "Minimizar assistente" }).click();
  await expect(assistantInput).toBeHidden();

  await launcher.click();
  await expect(assistantInput).toHaveValue("Tenho uma aula amanhã?");
  await page.keyboard.press("Escape");
  await expect(assistantInput).toBeHidden();
});

test("professional is redirected away from Mock Chat", async ({ page }) => {
  await stubSession(page, {
    ...adminSession,
    role: "professional",
    professional_id: "00000000-0000-4000-8000-000000000002",
    impersonating: false,
  });

  await page.goto("/dev/mock-chat");

  await expect(page).toHaveURL(/\/agenda$/);
  await expect(page.getByRole("link", { name: "Mock Chat" })).toHaveCount(0);
});

test("unscoped platform admin is redirected to tenant selection", async ({ page }) => {
  await stubSession(page, { ...adminSession, professional_id: null, impersonating: false });

  await page.goto("/dev/mock-chat");

  await expect(page).toHaveURL(/\/admin\/select-tenant$/);
});

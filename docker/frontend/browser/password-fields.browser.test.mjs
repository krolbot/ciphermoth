import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import en from "../../../frontend/src/i18n/en.js";
import ru from "../../../frontend/src/i18n/ru.js";
import { startFrontend, stopFrontend } from "./frontend.mjs";

let frontend;
let browser;
before(async () => {
  browser = await chromium.launch();
  frontend = await startFrontend("/api");
});
after(async () => {
  await browser?.close();
  stopFrontend(frontend);
});

// Entirely synthetic sessions and intercepted API calls; never open a real vault.
async function openPage(width, language, path, authenticated = true, initialized = true) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  const writes = [];
  const user = { id: 1, username: "synthetic-admin", role: "admin", active: true };
  const t = language === "ru" ? ru : en;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(
    ({ authenticated, user, language }) => {
      if (authenticated) {
        sessionStorage.setItem("ciphermothSession", "synthetic-password-fields-session");
        sessionStorage.setItem("ciphermothUser", JSON.stringify(user));
      }
      localStorage.setItem("ciphermoth-language", language);
      localStorage.setItem("ciphermoth-theme", "dark");
    },
    { authenticated, user, language }
  );
  const data = {
    "/api/auth/status": { initialized },
    "/api/auth/me": user,
    "/api/meta": { version: "3.1.0", features: [] },
    "/api/users": [user, { id: 2, username: "synthetic-member", role: "member", active: true }],
    "/api/passwords": [
      {
        id: 1,
        password_name: "Synthetic entry",
        password_value: "synthetic-only",
        kind: "login",
        access: "owner",
        tags: [],
        custom_fields: [],
      },
    ],
    "/api/passwords/trash": [],
    "/api/vault/damaged": { entries: [], attachments: [] },
    "/api/settings": {
      update_check_enabled: false,
      inactivity_ms: 3600000,
      hidden_ms: 3600000,
      warn_before_ms: 60000,
      debounce_ms: 1000,
      clipboard_clear_ms: 30000,
    },
    "/api/master_password/session": { idle_timeout_ms: 3600000, expires_in_ms: 3600000 },
  };
  await page.route("**/api/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/master_password/session") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(data[path]),
      });
    }
    if (request.method() !== "GET") writes.push({ path, body: request.postDataJSON() });
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(request.method() === "GET" ? (data[path] ?? {}) : { id: 3 }),
    });
  });
  await page.goto(`${frontend.url}${path}`);
  return { context, page, t, errors, writes };
}

function strong(password) {
  assert.equal(password.length, 16);
  for (const pattern of [/[A-Z]/, /[a-z]/, /[0-9]/, /[^A-Za-z0-9]/])
    assert.match(password, pattern);
}

async function fits(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const bad = await page
    .getByRole("button", { name: /^(Generate password|Сгенерировать пароль)$/ })
    .evaluateAll((buttons) =>
      buttons.some((button) => {
        const rect = button.getBoundingClientRect();
        return rect.width < 44 || rect.height < 44 || rect.left < 0 || rect.right > innerWidth;
      })
    );
  assert.equal(bad, false, "generator targets must fit and be at least 44px");
}

async function screenshot(page, name) {
  if (!process.env.CIPHERMOTH_SCREENSHOT_DIR) return;
  await mkdir(process.env.CIPHERMOTH_SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: resolve(process.env.CIPHERMOTH_SCREENSHOT_DIR, name),
    fullPage: true,
  });
}

for (const [width, language] of [
  [320, "en"],
  [375, "ru"],
  [1440, "en"],
]) {
  test(`create/reset user password: opt-in generation and explicit submission at ${width}px`, async () => {
    const { context, page, t, errors, writes } = await openPage(width, language, "/users");
    try {
      const create = page.locator("form");
      const password = create.getByLabel(t.users.temporaryPassword, { exact: false });
      const generate = create.getByRole("button", {
        name: t.entry.actions.generatePassword,
        exact: true,
      });
      await generate.waitFor();
      await create.getByLabel(t.auth.username, { exact: false }).fill("synthetic-new");
      await generate.click();
      const first = await password.inputValue();
      strong(first);
      await generate.click();
      const generated = await password.inputValue();
      strong(generated);
      assert.notEqual(generated, first);
      assert.equal(await password.getAttribute("type"), "password");
      await create.getByRole("button", { name: t.passwordField.show, exact: true }).click();
      assert.equal(await password.getAttribute("type"), "text");
      assert.equal(await password.inputValue(), generated);
      assert.deepEqual(writes, [], "generation/show must not submit a form");
      await fits(page);
      // Do not include even synthetic generated passwords in screenshots.
      await create.getByRole("button", { name: t.passwordField.hide, exact: true }).click();
      await screenshot(page, `users-password-generator-${width}-${language}.png`);
      let release;
      const pending = new Promise((resolve) => {
        release = resolve;
      });
      await page.route("**/api/users", async (route) => {
        if (route.request().method() === "POST") await pending;
        await route.fallback();
      });
      const request = page.waitForRequest(
        (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/users"
      );
      await create.getByRole("button", { name: t.common.actions.create, exact: true }).click();
      assert.equal((await request).postDataJSON().temporary_password, generated);
      assert.equal(
        await generate.isDisabled(),
        true,
        "do not replace a password during submission"
      );
      release();
      await page.waitForFunction(
        () => document.querySelector('form input[autocomplete="new-password"]')?.value === ""
      );

      await page.getByRole("button", { name: t.users.resetPassword, exact: true }).last().click();
      const reset = page.getByRole("dialog");
      await reset
        .getByRole("button", { name: t.entry.actions.generatePassword, exact: true })
        .click();
      const resetPassword = await reset
        .getByLabel(t.users.temporaryPassword, { exact: false })
        .inputValue();
      strong(resetPassword);
      assert.equal(writes.length, 1);
      const resetRequest = page.waitForRequest(
        (r) => r.method() === "PUT" && new URL(r.url()).pathname === "/api/users/2/password"
      );
      await reset.getByRole("button", { name: t.users.resetPassword, exact: true }).click();
      assert.equal((await resetRequest).postDataJSON().temporary_password, resetPassword);
      await reset.waitFor({ state: "hidden" });
      await create.getByRole("combobox", { name: t.users.role, exact: true }).click();
      await page.getByRole("option", { name: t.users.roles.service, exact: true }).click();
      assert.equal(
        await create
          .getByRole("button", { name: t.entry.actions.generatePassword, exact: true })
          .count(),
        0
      );
      assert.equal(await create.locator('input[type="password"]').count(), 0);
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  });

  test(`password change generates only the new password at ${width}px`, async () => {
    const { context, page, t, errors, writes } = await openPage(width, language, "/users");
    try {
      await page.getByRole("button", { name: t.auth.changePassword, exact: true }).click();
      const dialog = page.getByRole("dialog");
      const generate = dialog.getByRole("button", {
        name: t.entry.actions.generatePassword,
        exact: true,
      });
      await generate.waitFor();
      assert.equal(await generate.count(), 1);
      await generate.click();
      strong(await dialog.getByLabel(t.auth.newPassword, { exact: true }).inputValue());
      assert.equal(
        await dialog.getByLabel(t.auth.currentPassword, { exact: true }).inputValue(),
        ""
      );
      assert.equal(
        await dialog.getByLabel(t.auth.confirmNewPassword, { exact: true }).inputValue(),
        ""
      );
      await fits(page);
      await screenshot(page, `change-password-generator-${width}-${language}.png`);
      assert.deepEqual(writes, []);
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  });

  test(`bootstrap has generation, ordinary login does not at ${width}px`, async () => {
    for (const initialized of [false, true]) {
      const { context, page, t, errors, writes } = await openPage(
        width,
        language,
        "/login",
        false,
        initialized
      );
      try {
        const password = page
          .getByLabel(t.auth.masterPassword, { exact: false })
          .and(page.locator("input"))
          .first();
        await password.waitFor();
        const generate = page.getByRole("button", {
          name: t.entry.actions.generatePassword,
          exact: true,
        });
        assert.equal(await generate.count(), initialized ? 0 : 1);
        if (!initialized) {
          await generate.click();
          strong(await password.inputValue());
          assert.equal(
            await page.getByLabel(t.auth.confirmMasterPassword, { exact: false }).inputValue(),
            ""
          );
          await fits(page);
        }
        assert.deepEqual(writes, []);
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
  });
}

test("existing vault generator stays singular; backup, restore and TOTP never generate", async () => {
  const { context, page, t, errors, writes } = await openPage(375, "ru", "/passwords");
  try {
    const tools = page.getByRole("button", { name: t.vault.browser.tools, exact: true });
    for (const [menu, label] of [
      [t.vault.backup, t.auth.masterPassword],
      [t.vault.import, t.importDialog.backupPassword],
    ]) {
      await tools.click();
      await page.getByRole("menuitem", { name: menu, exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel(label, { exact: false }).waitFor();
      assert.equal(
        await dialog
          .getByRole("button", { name: t.entry.actions.generatePassword, exact: true })
          .count(),
        0
      );
      await page.keyboard.press("Escape");
      await dialog.waitFor({ state: "hidden" });
    }
    await page.getByRole("button", { name: t.common.actions.add, exact: true }).click();
    const dialog = page.getByRole("dialog");
    const generate = dialog.getByRole("button", {
      name: t.entry.actions.generatePassword,
      exact: true,
    });
    await generate.waitFor();
    assert.equal(await generate.count(), 1);
    await generate.click();
    strong(
      await dialog
        .getByLabel(t.common.fields.password, { exact: false })
        .and(page.locator("input"))
        .first()
        .inputValue()
    );
    await dialog.getByRole("button", { name: t.entry.labels.twoFactor, exact: false }).click();
    const totp = dialog.getByLabel(t.entry.labels.twoFactorSecret, { exact: false });
    await totp.waitFor();
    assert.equal(await totp.inputValue(), "");
    assert.equal(
      await totp
        .locator("..")
        .getByRole("button", { name: t.entry.actions.generatePassword, exact: true })
        .count(),
      0
    );
    await fits(page);
    assert.deepEqual(writes, []);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

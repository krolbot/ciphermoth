import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { startFrontend, stopFrontend } from "./frontend.mjs";
import { GLOW, INK, SURFACE } from "../../../frontend/src/lib/brand.js";

const rgb = (hex) =>
  `rgb(${hex
    .match(/[a-f0-9]{2}/gi)
    .map((part) => parseInt(part, 16))
    .join(", ")})`;

// Synthetic records only. Exercise the shipped bundle without a real vault/session.
const entries = [
  {
    id: 1,
    created: "2026-01-01T12:00:00Z",
    updated: "2026-10-24T12:00:00Z",
    password_name: "GitHub",
    username: "nikita@example.test",
    password_value: "Synthetic-secret!2026",
    kind: "login",
    access: "owner",
    favorite: true,
    folder: "Work",
    tags: ["development"],
    url: "github.com",
    totp_secret: "JBSWY3DPEHPK3PXP",
    custom_fields: [
      {
        label: "Recovery code",
        value: "Synthetic-recovery",
        hidden: true,
      },
    ],
    password_history: [],
    attachment_count: 0,
  },
  {
    id: 2,
    created: "2026-03-31T23:30:00Z",
    password_name: "Read-only account",
    username: "reader@example.test",
    password_value: "Synthetic-read-only",
    kind: "login",
    access: "read",
    favorite: false,
    folder: "Shared",
    attachment_count: 1,
    tags: [],
    custom_fields: [],
  },
  {
    id: 3,
    created: "2026-04-01T01:00:00+03:00",
    password_name: "Recovery notes",
    password_value: "Synthetic private note\nSecond line",
    kind: "note",
    access: "write",
    folder: "Personal",
    tags: [],
    custom_fields: [],
  },
  {
    id: 4,
    created: "2026-03-31T23:00:00Z",
    password_name: "Very long entry name / ".repeat(8),
    username: "long".repeat(40),
    password_value: "Long-secret-".repeat(40),
    kind: "login",
    access: "owner",
    favorite: false,
    folder: "Work",
    tags: ["long-tag".repeat(30)],
    custom_fields: [],
  },
];
let frontend;
let browser;
let origin;

before(async () => {
  browser = await chromium.launch();
  frontend = await startFrontend("/api");
  origin = frontend.url;
});
after(async () => {
  await browser?.close();
  stopFrontend(frontend);
});

async function vault(width, language = "en", theme = "dark") {
  const context = await browser.newContext({
    viewport: { width, height: width < 600 ? 812 : 900 },
    permissions: ["clipboard-read", "clipboard-write"],
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(
    ({ language, theme }) => {
      sessionStorage.setItem("ciphermothSession", "synthetic-browser-session");
      sessionStorage.setItem(
        "ciphermothUser",
        JSON.stringify({
          id: 1,
          username: "synthetic",
          role: "member",
        })
      );
      localStorage.setItem("ciphermoth-language", language);
      localStorage.setItem("ciphermoth-theme", theme);
    },
    { language, theme }
  );
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    let data = {};
    if (path === "/api/passwords") data = entries;
    else if (path === "/api/passwords/trash")
      data = [
        {
          id: 11,
          password_name: "Deleted / account",
          username: "old@example.test",
          deleted: "2026-10-20T12:00:00Z",
        },
      ];
    else if (path === "/api/vault/damaged") data = { entries: [], attachments: [] };
    else if (path === "/api/settings")
      data = {
        update_check_enabled: false,
        inactivity_ms: 3600000,
        hidden_ms: 3600000,
        warn_before_ms: 60000,
        debounce_ms: 1000,
        clipboard_clear_ms: 30000,
      };
    else if (path === "/api/master_password/session")
      data = { idle_timeout_ms: 3600000, expires_in_ms: 3600000 };
    else if (path.endsWith("/attachments"))
      data = [{ id: 8, filename: "Readme.txt", size_bytes: 100 }];
    else if (path.endsWith("/shares") || path === "/api/users/share-targets") data = [];
    else if (path === "/api/auth/me") data = { id: 1, username: "synthetic", role: "member" };
    else if (path === "/api/meta") data = { version: "3.1.0", features: [] };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await page.goto(`${origin}/passwords`);
  await page
    .getByPlaceholder(language === "ru" ? "Поиск по хранилищу…" : "Search vault…")
    .waitFor();
  await page.getByText("GitHub", { exact: true }).first().waitFor();
  return { context, page, errors };
}

async function fits(page) {
  const geometry = await page.evaluate(() => ({
    width: innerWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  assert.equal(geometry.scroll, geometry.width, JSON.stringify(geometry));
  const overflowing = await page
    .locator('[role="dialog"], [role="list"], section')
    .evaluateAll((nodes) =>
      nodes
        .filter((node) => node.scrollWidth > node.clientWidth + 1)
        .map((node) => node.getAttribute("aria-label") || node.tagName)
    );
  assert.deepEqual(overflowing, []);
}

test("mobile vault is a vertical list, with a full-screen read view and no hidden actions", async () => {
  const { context, page, errors } = await vault(375);
  try {
    assert.equal(await page.getByRole("grid").count(), 0);
    const list = page.getByRole("list", { name: "Vault entries" });
    assert.equal(await list.count(), 1);
    await list.getByRole("button", { name: "Open GitHub", exact: true }).click();
    const detail = page.getByRole("dialog", {
      name: "GitHub",
      exact: true,
    });
    await detail.waitFor();
    assert.equal(await detail.getByText(entries[0].password_value, { exact: true }).count(), 0);
    assert.equal(await detail.getByText("Synthetic-recovery", { exact: true }).count(), 0);
    await detail.getByRole("button", { name: "Copy 2FA code", exact: true }).click();
    assert.match(await page.evaluate(() => navigator.clipboard.readText()), /^\d{6}$/);
    await detail.getByRole("button", { name: "Reveal password", exact: true }).click();
    await detail.getByText(entries[0].password_value, { exact: true }).waitFor();
    await detail.getByRole("button", { name: "Copy password", exact: true }).click();
    assert.equal(
      await page.evaluate(() => navigator.clipboard.readText()),
      entries[0].password_value
    );
    await fits(page);
    await detail.getByRole("button", { name: "Remove from favorites", exact: true }).click();
    await detail.waitFor();
    await detail.getByRole("button", { name: "Edit", exact: true }).click();

    await page.getByRole("textbox", { name: /^Name/ }).waitFor();
    await fits(page);
    await page.keyboard.press("Escape");
    await detail.getByRole("button", { name: "Manage sharing" }).click();
    await page.getByRole("heading", { name: "Manage sharing" }).waitFor();
    await fits(page);
    await page.keyboard.press("Escape");
    await detail.getByRole("button", { name: "Back to entries" }).click();
    await list
      .getByRole("button", {
        name: "Open Read-only account",
        exact: true,
      })
      .click();
    const readOnly = page.getByRole("dialog", {
      name: "Read-only account",
      exact: true,
    });
    await readOnly.waitFor();
    assert.equal(await readOnly.getByRole("button", { name: "Edit", exact: true }).count(), 0);
    assert.equal(await readOnly.getByRole("button", { name: "Delete", exact: true }).count(), 0);
    assert.equal(await readOnly.getByRole("button", { name: "Manage sharing" }).count(), 0);
    await readOnly.getByText("Attachments (1)", { exact: true }).click();
    await readOnly.getByText("Readme.txt", { exact: true }).waitFor();
    assert.equal(await readOnly.locator('input[type="file"]').count(), 0);
    assert.equal(await readOnly.getByRole("button", { name: "Remove file" }).count(), 0);
    await fits(page);
    await readOnly.getByRole("button", { name: "Back to entries" }).click();
    await list.getByRole("button", { name: "Open Recovery notes", exact: true }).click();
    const note = page.getByRole("dialog", {
      name: "Recovery notes",
      exact: true,
    });
    assert.equal(await note.getByText(entries[2].password_value, { exact: true }).count(), 0);
    await note.getByRole("button", { name: "Copy note", exact: true }).click();
    assert.equal(
      await page.evaluate(() => navigator.clipboard.readText()),
      entries[2].password_value
    );
    await fits(page);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

async function screenshot(page, filename) {
  if (!process.env.CIPHERMOTH_SCREENSHOT_DIR) return;
  await mkdir(process.env.CIPHERMOTH_SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: resolve(process.env.CIPHERMOTH_SCREENSHOT_DIR, filename),
    fullPage: true,
  });
}

for (const [width, language, theme] of [
  [320, "en", "dark"],
  [375, "ru", "light"],
  [375, "ru", "dark"],
  [768, "ru", "dark"],
  [1280, "en", "dark"],
  [1440, "ru", "light"],
  [1440, "ru", "dark"],
]) {
  test(`vault fits ${width}px / ${language} / ${theme}, including long values and trash`, async () => {
    const { context, page, errors } = await vault(width, language, theme);
    try {
      const ru = language === "ru";
      const list = page.getByRole("list", {
        name: ru ? "Записи хранилища" : "Vault entries",
      });
      const detailsRegion = page.getByRole("region", {
        name: ru ? "Просмотр записи" : "Entry details",
      });
      const listFillsBrowser = () =>
        list.evaluate((node) => {
          const pane = node.parentElement;
          return (
            Math.abs(pane.getBoundingClientRect().width - pane.parentElement.clientWidth) < 1 &&
            getComputedStyle(pane).borderRightWidth === "0px"
          );
        });
      assert.equal(
        await detailsRegion.count(),
        0,
        "details stay hidden until a record is selected"
      );
      assert.equal(await listFillsBrowser(), true, "the unselected list fills the browser");
      assert.equal(await list.getByRole("listitem").count(), entries.length);
      assert.equal(
        await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
        rgb(theme === "dark" ? INK : SURFACE)
      );
      assert.equal(
        await list
          .getByLabel(ru ? "Избранное" : "Favorite", { exact: true })
          .evaluate((icon) => getComputedStyle(icon).color),
        rgb(GLOW)
      );
      await fits(page);
      const lastCopy = list
        .getByRole("button", {
          name: /^(Copy password|Скопировать пароль):/,
        })
        .last();
      await lastCopy.scrollIntoViewIfNeeded();
      assert.equal(
        await lastCopy.evaluate((button) => {
          const rect = button.getBoundingClientRect();
          return button.contains(
            document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
          );
        }),
        true,
        "the theme switch must not cover the last copy action"
      );
      if (width === 375) await screenshot(page, `vault-mobile-ru-${theme}.png`);
      if (width === 1440) await screenshot(page, `vault-list-${language}-${theme}.png`);
      const longName = entries[3].password_name;
      await list
        .getByRole("button", {
          name: `${ru ? "Открыть" : "Open"} ${longName}`,
          exact: true,
        })
        .click();
      const detail =
        width >= 900
          ? page.getByRole("region", {
              name: ru ? "Просмотр записи" : "Entry details",
            })
          : page.getByRole("dialog", { name: longName, exact: true });
      await detail.waitFor();
      if (width >= 900) assert.equal(await listFillsBrowser(), false);
      assert.equal(await detail.getByText(entries[3].password_value, { exact: true }).count(), 0);
      await detail
        .getByRole("button", {
          name: ru ? "Показать пароль" : "Reveal password",
          exact: true,
        })
        .click();
      await fits(page);
      if (width >= 900) {
        await list
          .getByRole("button", {
            name: `${ru ? "Открыть" : "Open"} GitHub`,
            exact: true,
          })
          .click();
        await detail.getByRole("heading", { name: "GitHub", exact: true }).waitFor();
        assert.equal(
          await detail
            .getByRole("button", {
              name: ru ? "Убрать из избранного" : "Remove from favorites",
              exact: true,
            })
            .locator("svg")
            .evaluate((icon) => getComputedStyle(icon).color),
          rgb(GLOW)
        );
        await screenshot(page, `vault-desktop-${language}-${theme}.png`);
      } else {
        await page.keyboard.press("Escape");
        await detail.waitFor({ state: "hidden" });
      }
      await list.waitFor();
      await page.getByRole("combobox", { name: ru ? "Порядок" : "Sort", exact: true }).click();
      const byDate = page.getByRole("option", {
        name: ru ? "По времени добавления" : "Date added",
        exact: true,
      });
      await byDate.waitFor();
      if ((width === 375 || width === 1440) && theme === "dark") {
        await screenshot(page, `vault-sort-${width}-${language}.png`);
      }
      await byDate.click();
      assert.deepEqual(
        await list
          .getByRole("button", { name: /^(Open|Открыть) / })
          .evaluateAll((buttons) => buttons.map((button) => button.getAttribute("aria-label"))),
        [entries[1], entries[3], entries[2], entries[0]].map(
          (entry) => `${ru ? "Открыть" : "Open"} ${entry.password_name}`
        )
      );
      await fits(page);
      if (width === 1280) {
        await page.getByRole("combobox", { name: "Sort", exact: true }).click();
        await page.getByRole("option", { name: "Name Z–A", exact: true }).click();
        assert.equal(
          await list
            .getByRole("listitem")
            .first()
            .getByRole("button", {
              name: `Open ${entries[3].password_name}`,
              exact: true,
            })
            .count(),
          1
        );
        await page.getByRole("combobox", { name: "Folder", exact: true }).click();
        await page.getByRole("option", { name: "Shared", exact: true }).click();
        assert.equal(await list.getByRole("listitem").count(), 1);
        await page.getByRole("combobox", { name: "Folder", exact: true }).click();
        await page.getByRole("option", { name: "All folders", exact: true }).click();
      }
      const search = page.getByPlaceholder(ru ? "Поиск по хранилищу…" : "Search vault…");
      await search.fill("reader@example.test");
      assert.equal(await list.getByRole("listitem").count(), 1);
      assert.equal(await detailsRegion.count(), 0);
      assert.equal(await listFillsBrowser(), true);
      await search.fill("no-such-entry");
      await page.getByRole("status").waitFor();
      assert.equal(await list.count(), 0);
      assert.equal(await detailsRegion.count(), 0);
      await search.fill("");
      await page
        .getByRole("button", {
          name: ru ? "Действия с хранилищем" : "Vault tools",
        })
        .click();
      await page.getByRole("menuitem", { name: /^(Корзина|Trash)/ }).click();
      const trash = page.getByRole("dialog", {
        name: ru ? "Корзина" : "Trash",
        exact: true,
      });
      await trash.waitFor();
      assert.equal(await trash.getByRole("grid").count(), 0);
      await trash.getByRole("button", { name: /^(Восстановить|Restore)/ }).waitFor();
      await fits(page);
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  });
}

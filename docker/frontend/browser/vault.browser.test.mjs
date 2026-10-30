import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { startFrontend, stopFrontend } from "./frontend.mjs";
const require = createRequire(import.meta.url);
const axePath = require.resolve("axe-core/axe.min.js");
import enText from "../../../frontend/src/i18n/en.js";
import ruText from "../../../frontend/src/i18n/ru.js";
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
        folder_id: 1,
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
        folder_id: 2,
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
        folder_id: 3,
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
        folder_id: 1,
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

async function vault(
    width,
    language = "en",
    theme = "dark",
    records = entries,
    options = {},
) {
    const context = await browser.newContext({
        viewport: { width, height: width < 600 ? 812 : 900 },
        bypassCSP: true,
        permissions: ["clipboard-read", "clipboard-write"],
    });
    const page = await context.newPage();
    if (options.clock) await page.clock.install();
    const errors = [];
    const userFolderAccess = structuredClone(options.userFolderAccess ?? []);
    const folderGrants = structuredClone(options.folderGrants ?? []);
    const folderAudit = structuredClone(options.folderAudit ?? []);
    page.on("pageerror", (error) => errors.push(error.stack ?? error.message));
    await page.addInitScript(
        ({ language, theme, role }) => {
            if (!sessionStorage.getItem("synthetic-fixture-initialized")) {
                sessionStorage.setItem("synthetic-fixture-initialized", "true");
                sessionStorage.setItem(
                    "ciphermothSession",
                    "synthetic-browser-session",
                );
                sessionStorage.setItem(
                    "ciphermothUser",
                    JSON.stringify({ id: 1, username: "synthetic", role }),
                );
            }
            localStorage.setItem("ciphermoth-language", language);
            localStorage.setItem("ciphermoth-theme", theme);
        },
        { language, theme, role: options.role ?? "member" },
    );
    await page.route("**/api/**", (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        const method = request.method();
        const grantMatch = path.match(
            /^\/api\/folders\/(\d+)\/grants\/(users|groups)\/(\d+)$/,
        );
        let data = {};
        if (grantMatch && method === "PUT") {
            const [, folderIdText, targetTypePlural, targetIdText] = grantMatch;
            const folderId = Number(folderIdText);
            const targetId = Number(targetIdText);
            const targetType = targetTypePlural === "users" ? "user" : "group";
            const body = request.postDataJSON();
            const target =
                targetType === "user"
                    ? (options.users ?? []).find((item) => item.id === targetId)
                    : (options.groups ?? []).find(
                          (item) => item.id === targetId,
                      );
            const grant = {
                target_type: targetType,
                target_id: targetId,
                target_name:
                    target?.username ?? target?.name ?? String(targetId),
                permission: body.permission,
                expires_at: body.expires_at,
                expired: false,
            };
            const grantIndex = folderGrants.findIndex(
                (item) =>
                    item.target_type === targetType &&
                    item.target_id === targetId,
            );
            if (grantIndex === -1) folderGrants.push(grant);
            else folderGrants[grantIndex] = grant;
            if (targetType === "user") {
                const access = userFolderAccess.find(
                    (item) => item.folder.id === folderId,
                );
                if (access) {
                    access.direct_permission = body.permission;
                    access.direct_expires_at = body.expires_at;
                    access.effective_permission = body.permission;
                    access.sources = [
                        {
                            source: "direct",
                            source_id: targetId,
                            name: target?.username ?? "",
                            permission: body.permission,
                            expires_at: body.expires_at,
                            expired: false,
                        },
                    ];
                }
            }
            folderAudit.unshift({
                id: Math.max(0, ...folderAudit.map((item) => item.id)) + 1,
                created: "2026-10-27T12:01:00",
                actor_user_id: 1,
                actor_username: "synthetic",
                action: `folder_${targetType}_grant_created`,
                resource_type: "folder",
                resource_id: folderId,
                target_user_id: targetType === "user" ? targetId : null,
                target_username:
                    targetType === "user" ? grant.target_name : null,
                target_group_id: targetType === "group" ? targetId : null,
                target_group_name:
                    targetType === "group" ? grant.target_name : null,
            });
            data = grant;
        } else if (path === "/api/passwords") data = records;
        else if (path === "/api/users")
            data = options.users ?? [
                {
                    id: 1,
                    username: "synthetic",
                    role: options.role ?? "member",
                    active: true,
                },
            ];
        else if (/^\/api\/users\/\d+\/folder-access$/.test(path))
            data = userFolderAccess;
        else if (path === "/api/folders")
            data = [
                {
                    id: 1,
                    name: "Work",
                    owner_id: 1,
                    owner_username: "synthetic",
                    access: "owner",
                    can_manage: true,
                },
                {
                    id: 2,
                    name: "Shared",
                    owner_id: 2,
                    owner_username: "owner",
                    access: "read",
                    can_manage: false,
                },
                {
                    id: 3,
                    name: "Personal",
                    owner_id: 2,
                    owner_username: "owner",
                    access: "write",
                    can_manage: false,
                },
            ];
        else if (path === "/api/groups") data = options.groups ?? [];
        else if (/^\/api\/groups\/\d+\/members$/.test(path))
            data = options.groupMembers ?? [];
        else if (/^\/api\/groups\/\d+\/audit$/.test(path))
            data = options.groupAudit ?? [];
        else if (/^\/api\/folders\/\d+\/grants$/.test(path))
            data = folderGrants;
        else if (/^\/api\/folders\/\d+\/audit$/.test(path)) data = folderAudit;
        else if (path === "/api/passwords/trash")
            data = [
                {
                    id: 11,
                    password_name: "Deleted / account",
                    username: "old@example.test",
                    deleted: "2026-10-20T12:00:00Z",
                },
            ];
        else if (path === "/api/vault/damaged")
            data = { entries: [], attachments: [] };
        else if (path === "/api/settings")
            data = {
                update_check_enabled: false,
                inactivity_ms: options.clock ? 30000 : 3600000,
                hidden_ms: options.clock ? 10000 : 3600000,
                warn_before_ms: options.clock ? 5000 : 60000,
                debounce_ms: 1000,
                clipboard_clear_ms: 30000,
            };
        else if (path === "/api/master_password/session")
            data = {
                idle_timeout_ms: options.clock ? 30000 : 3600000,
                expires_in_ms: options.clock ? 30000 : 3600000,
            };
        else if (path === "/api/auth/status") data = { initialized: true };
        else if (path === "/api/auth/login")
            data = {
                valid: true,
                session_token: "synthetic-unlocked-session",
                user: {
                    id: 1,
                    username: "synthetic",
                    role: "member",
                    active: true,
                },
                idle_timeout_ms: 30000,
            };
        else if (path.endsWith("/attachments"))
            data = [{ id: 8, filename: "Readme.txt", size_bytes: 100 }];
        else if (path.endsWith("/shares")) data = [];
        else if (path === "/api/users/share-targets")
            data = options.shareTargets ?? [];
        else if (path === "/api/auth/me")
            data = {
                id: 1,
                username: "synthetic",
                role: options.role ?? "member",
            };
        else if (path === "/api/auth/entry-draft-key")
            data = { user_id: 1, key: Buffer.alloc(32, 7).toString("base64") };
        else if (path === "/api/meta")
            data = { version: "3.1.0", features: [] };
        return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(data),
        });
    });
    await page.goto(`${origin}/passwords`);
    await page
        .getByPlaceholder(
            language === "ru" ? "Поиск записей…" : "Search entries…",
        )
        .waitFor();
    await page.getByText("GitHub", { exact: true }).first().waitFor();
    assert.equal(
        await page.evaluate(() => document.documentElement.dataset.theme),
        theme,
    );
    return { context, page, errors };
}

async function fits(page) {
    await page.waitForTimeout(300);
    const geometry = await page.evaluate(() => ({
        width: innerWidth,
        scroll: document.documentElement.scrollWidth,
        outliers: [...document.querySelectorAll("body *")]
            .map((node) => {
                const rect = node.getBoundingClientRect();
                return {
                    tag: node.tagName,
                    className:
                        typeof node.className === "string"
                            ? node.className
                            : "",
                    parentClass:
                        typeof node.parentElement?.className === "string"
                            ? node.parentElement.className
                            : "",
                    parentHtml:
                        node.parentElement?.outerHTML.slice(0, 180) ?? "",
                    transform: getComputedStyle(node).transform,
                    position: getComputedStyle(node).position,
                    left: rect.left,
                    right: rect.right,
                    width: rect.width,
                };
            })
            .filter((item) => item.left < -1 || item.right > innerWidth + 1)
            .slice(-12),
    }));
    assert.equal(geometry.scroll, geometry.width, JSON.stringify(geometry));
    const overflowing = await page
        .locator('[role="dialog"], [role="list"], section')
        .evaluateAll((nodes) =>
            nodes
                .filter((node) => node.scrollWidth > node.clientWidth + 1)
                .map((node) => ({
                    name: node.getAttribute("aria-label") || node.tagName,
                    className: node.className,
                    clientWidth: node.clientWidth,
                    scrollWidth: node.scrollWidth,
                    children: [...node.children].map((child) => ({
                        className: child.className,
                        width: child.getBoundingClientRect().width,
                        scrollWidth: child.scrollWidth,
                    })),
                })),
        );
    assert.deepEqual(overflowing, []);
    const invalidActions = await page
        .locator('[data-qa="entry-list"]')
        .locator("button")
        .evaluateAll((buttons) =>
            buttons.flatMap((button) => {
                if (button.offsetParent === null) return [];
                const rect = button.getBoundingClientRect();
                return rect.width < 44 ||
                    rect.height < 44 ||
                    rect.left < 0 ||
                    rect.right > innerWidth
                    ? [
                          {
                              name: button.getAttribute("aria-label"),
                              width: rect.width,
                              height: rect.height,
                          },
                      ]
                    : [];
            }),
        );
    assert.deepEqual(
        invalidActions,
        [],
        "list actions stay touch-sized and within the viewport",
    );
}

async function settleAnimations(page) {
    await page.evaluate(async () => {
        await new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve)),
        );
        await Promise.all(
            document
                .getAnimations()
                .map((animation) => animation.finished.catch(() => undefined)),
        );
    });
}

async function axe(page) {
    await settleAnimations(page);
    await page.addScriptTag({ path: axePath });
    const violations = await page.evaluate(async () =>
        (
            await window.axe.run(document, {
                runOnly: {
                    type: "tag",
                    values: [
                        "wcag2a",
                        "wcag2aa",
                        "wcag21a",
                        "wcag21aa",
                        "wcag22aa",
                    ],
                },
            })
        ).violations.map(({ id, impact, nodes }) => ({
            id,
            impact,
            nodes: nodes.map(({ target, failureSummary, any }) => ({
                target,
                failureSummary,
                any,
            })),
        })),
    );
    assert.deepEqual(violations, []);
}

async function visibleTouchAction(page, locator) {
    await page.waitForTimeout(300);
    const box = await locator.boundingBox();
    const viewport = page.viewportSize();
    assert.ok(
        box &&
            viewport &&
            box.y >= 0 &&
            box.y + box.height <= viewport.height &&
            box.width >= 40 &&
            box.height >= (viewport.width < 600 ? 44 : 36),
        JSON.stringify({ box, viewport }),
    );
}

async function openAdd(page) {
    await page.getByRole("button", { name: "Add", exact: true }).click();
}

function entryEditor(page, width) {
    return page.getByRole(width >= 1080 ? "dialog" : "region", {
        name: "Add entry",
    });
}

async function mobileToastFits(page, text, width) {
    if (width >= 600) return;
    await page.waitForFunction(
        ({ text, width }) => {
            const content = [...document.querySelectorAll(".g-toast")].find(
                (node) => node.textContent?.includes(text),
            );
            if (!content) return false;
            const box = content.getBoundingClientRect();
            return box.x >= 8 && box.right <= width - 8;
        },
        { text, width },
    );
}

async function screenshot(page, filename) {
    if (!process.env.CIPHERMOTH_SCREENSHOT_DIR) return;
    await mkdir(process.env.CIPHERMOTH_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({
        path: resolve(process.env.CIPHERMOTH_SCREENSHOT_DIR, filename),
        fullPage: true,
    });
}

async function viewportScreenshot(page, filename) {
    if (!process.env.CIPHERMOTH_SCREENSHOT_DIR) return;
    await mkdir(process.env.CIPHERMOTH_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({
        path: resolve(process.env.CIPHERMOTH_SCREENSHOT_DIR, filename),
    });
}

for (const [width, reason] of [
    [375, "hidden"],
    [1440, "idle"],
    [1440, "renderer-reset"],
]) {
    test(`encrypted new-entry draft survives ${reason} locking and unlock at ${width}px`, async () => {
        const { context, page, errors } = await vault(
            width,
            "en",
            "dark",
            entries,
            { clock: true },
        );
        let secret = "Synthetic-unsaved-secret-2026!";
        try {
            const mutations = [];
            page.on("request", (request) => {
                if (new URL(request.url()).pathname === "/api/passwords/create")
                    mutations.push(request);
            });
            await openAdd(page, width);
            const editor = entryEditor(page, width);
            await editor
                .getByRole("textbox", { name: /^Name/ })
                .fill("Unsaved synthetic entry");
            await editor
                .getByRole("textbox", { name: /^Username/ })
                .fill("unsaved@example.test");
            await editor
                .locator('input[autocomplete="new-password"]')
                .fill(secret);
            await fits(page);
            assert.deepEqual(
                mutations,
                [],
                "a draft must not create a real entry",
            );
            if (reason === "hidden") {
                await page.evaluate(() => {
                    Object.defineProperty(document, "hidden", {
                        configurable: true,
                        get: () => true,
                    });
                    document.dispatchEvent(new Event("visibilitychange"));
                });
            }
            if (reason === "renderer-reset") {
                secret = "Last-input-before-native-reset!";
                // Reproduce native navigation without endSession or a flush callback.
                // Inspect storage in the input task: waiting a tick hides the old race.
                await page.evaluate((value) => {
                    const storageKey = "ciphermoth-entry-draft:v1:1";
                    const before = sessionStorage.getItem(storageKey);
                    const input = document.querySelector(
                        'input[autocomplete="new-password"]',
                    );
                    Object.getOwnPropertyDescriptor(
                        HTMLInputElement.prototype,
                        "value",
                    ).set.call(input, value);
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                    if (sessionStorage.getItem(storageKey) === before)
                        throw new Error(
                            "The last input was not persisted in the input task",
                        );
                    sessionStorage.removeItem("ciphermothSession");
                    sessionStorage.removeItem("ciphermothUser");
                    window.location.replace("/login");
                }, secret);
            } else {
                await page.clock.fastForward(
                    reason === "hidden" ? 10001 : 30001,
                );
            }
            await page
                .getByRole("button", { name: "Unlock vault", exact: true })
                .waitFor();
            const stored = await page.evaluate(() =>
                JSON.stringify({ ...sessionStorage }),
            );
            assert.match(stored, /ciphermoth-entry-draft:v1:1/);
            assert.ok(
                !stored.includes(secret) &&
                    !stored.includes("unsaved@example.test"),
            );
            await page
                .getByRole("textbox", { name: "Username", exact: true })
                .fill("synthetic");
            await page
                .locator('input[autocomplete="current-password"]')
                .fill("Synthetic-login-only!");
            await page
                .getByRole("button", { name: "Unlock vault", exact: true })
                .click();
            await editor.waitFor();
            assert.equal(
                await editor
                    .getByRole("textbox", { name: /^Name/ })
                    .inputValue(),
                "Unsaved synthetic entry",
            );
            assert.equal(
                await editor
                    .getByRole("textbox", { name: /^Username/ })
                    .inputValue(),
                "unsaved@example.test",
            );
            assert.equal(
                await editor
                    .locator('input[autocomplete="new-password"]')
                    .inputValue(),
                secret,
            );
            assert.equal(
                await editor
                    .locator('input[autocomplete="new-password"]')
                    .getAttribute("type"),
                "password",
            );
            assert.deepEqual(mutations, []);
            await screenshot(page, `draft-restored-${width}-${reason}.png`);
            await editor
                .getByRole("button", { name: "Create", exact: true })
                .click();
            await editor.waitFor({ state: "hidden" });
            assert.equal(mutations.length, 1);
            assert.equal(mutations[0].postDataJSON().password_value, secret);
            assert.equal(
                await page.evaluate(() =>
                    sessionStorage.getItem("ciphermoth-entry-draft:v1:1"),
                ),
                null,
            );
            await openAdd(page, width);
            assert.equal(
                await editor
                    .getByRole("textbox", { name: /^Name/ })
                    .inputValue(),
                "",
            );
            await editor
                .getByRole("textbox", { name: /^Name/ })
                .fill("Cancel this draft");
            await editor
                .getByRole("button", { name: "Cancel", exact: true })
                .click();
            assert.equal(
                await page.evaluate(() =>
                    sessionStorage.getItem("ciphermoth-entry-draft:v1:1"),
                ),
                null,
            );
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

test("a damaged draft is kept until explicit discard, and does not permanently block creation", async () => {
    const { context, page, errors } = await vault(375);
    try {
        await page.evaluate(() =>
            sessionStorage.setItem("ciphermoth-entry-draft:v1:1", "damaged"),
        );
        await page.reload();
        await page
            .getByText("Could not create or restore an encrypted draft.", {
                exact: false,
            })
            .waitFor();
        assert.equal(
            await page
                .getByRole("button", { name: "Add", exact: true })
                .isDisabled(),
            true,
        );
        assert.equal(
            await page.evaluate(() =>
                sessionStorage.getItem("ciphermoth-entry-draft:v1:1"),
            ),
            "damaged",
        );
        await fits(page);
        await page
            .getByRole("button", { name: "Try again", exact: true })
            .click();
        await page
            .getByRole("button", { name: "Discard draft", exact: true })
            .waitFor();
        assert.equal(
            await page.evaluate(() =>
                sessionStorage.getItem("ciphermoth-entry-draft:v1:1"),
            ),
            "damaged",
        );
        await page
            .getByRole("button", { name: "Discard draft", exact: true })
            .click();
        await openAdd(page, 375);
        const editor = entryEditor(page, 375);
        await editor.waitFor();
        await editor
            .getByRole("button", { name: "Cancel", exact: true })
            .click();
        assert.deepEqual(errors, []);
    } finally {
        await context.close();
    }
});

for (const width of [375, 1440]) {
    test(`new entry inherits the active folder and uses responsive editor at ${width}px`, async () => {
        const { context, page, errors } = await vault(width);
        try {
            const creates = [];
            page.on("request", (request) => {
                if (new URL(request.url()).pathname === "/api/passwords/create")
                    creates.push(request.postDataJSON());
            });
            await page.getByRole("combobox", { name: /^Folder/ }).click();
            await page.getByRole("option", { name: /^Work/ }).click();
            await openAdd(page, width);

            const editor = entryEditor(page, width);
            await editor.waitFor();
            assert.equal(
                await page.getByRole("dialog").count(),
                width >= 1080 ? 1 : 0,
            );
            const folder = editor.getByRole("combobox", {
                name: "Folder (optional)",
                exact: true,
            });
            assert.equal((await folder.textContent()).trim(), "Work");
            await folder.click();
            assert.deepEqual(await page.getByRole("option").allTextContents(), [
                "Work",
                "Personal",
            ]);
            await page.keyboard.press("Escape");
            await screenshot(page, `entry-create-${width}.png`);

            const createButton = editor.getByRole("button", {
                name: "Create",
                exact: true,
            });
            assert.equal(await createButton.isDisabled(), true);
            await editor
                .getByRole("textbox", { name: /^Name/ })
                .fill("Inherited folder entry");
            assert.equal(await createButton.isDisabled(), true);
            await editor
                .locator('input[autocomplete="new-password"]')
                .fill("Synthetic-folder-secret");
            assert.equal(await createButton.isEnabled(), true);
            await createButton.click();
            await editor.waitFor({ state: "hidden" });
            assert.equal(creates.length, 1);
            assert.equal(creates[0].folder_id, 1);
            assert.equal(creates[0].folder, "Work");
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [375, 1440]) {
    test(`new entry does not inherit a read-only folder at ${width}px`, async () => {
        const { context, page, errors } = await vault(width);
        try {
            await page.getByRole("combobox", { name: /^Folder/ }).click();
            await page.getByRole("option", { name: /^Shared/ }).click();
            await openAdd(page, width);
            const editor = entryEditor(page, width);
            const folder = editor.getByRole("combobox", {
                name: "Folder (optional)",
                exact: true,
            });
            await folder.waitFor();
            assert.equal((await folder.textContent()).trim(), "Work, Personal");
            await folder.click();
            assert.deepEqual(await page.getByRole("option").allTextContents(), [
                "Work",
                "Personal",
            ]);
            await page.keyboard.press("Escape");
            await editor
                .getByRole("button", { name: "Cancel", exact: true })
                .click();
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [375, 1440]) {
    test(`administrator grants folder access from user management at ${width}px`, async () => {
        const folder = {
            id: 1,
            name: "Work",
            owner_id: 1,
            owner_username: "synthetic",
            access: null,
            can_manage: true,
        };
        const { context, page, errors } = await vault(
            width,
            "en",
            "dark",
            entries,
            {
                role: "admin",
                users: [
                    {
                        id: 1,
                        username: "synthetic",
                        role: "admin",
                        active: true,
                    },
                    {
                        id: 2,
                        username: "team-member",
                        role: "member",
                        active: true,
                    },
                ],
                userFolderAccess: [
                    {
                        folder,
                        direct_permission: null,
                        direct_expires_at: null,
                        effective_permission: null,
                        sources: [],
                    },
                ],
                groups: [{ id: 10, name: "Operations", member_count: 1 }],
                groupMembers: [
                    { user_id: 2, username: "team-member", role: "member" },
                ],
                groupAudit: [
                    {
                        id: 1,
                        created: "2026-10-27T12:00:00",
                        actor_user_id: 1,
                        actor_username: "synthetic",
                        action: "group_created",
                        resource_type: "group",
                        resource_id: 10,
                        target_user_id: null,
                        target_username: null,
                    },
                ],
            },
        );
        try {
            const grants = [];
            page.on("request", (request) => {
                if (
                    request.method() === "PUT" &&
                    new URL(request.url()).pathname ===
                        "/api/folders/1/grants/users/2"
                )
                    grants.push(request.postDataJSON());
            });
            await page.goto(`${origin}/users`);
            await page
                .getByRole("heading", { name: "Accounts and service access" })
                .waitFor();
            await page
                .getByRole("button", { name: "Groups", exact: true })
                .click();
            const groupsDialog = page.getByRole("dialog", {
                name: "Groups",
                exact: true,
            });
            await groupsDialog.waitFor();
            await groupsDialog
                .getByText("team-member", { exact: true })
                .waitFor();
            await groupsDialog
                .getByText("synthetic created the group.", { exact: true })
                .waitFor();
            assert.equal(
                await groupsDialog.evaluate(
                    (node) => node.scrollWidth <= node.clientWidth + 1,
                ),
                true,
            );
            const groupsClose = groupsDialog.getByRole("button", {
                name: "Close",
                exact: true,
            });
            await visibleTouchAction(page, groupsClose);
            await viewportScreenshot(page, `group-management-${width}.png`);
            await groupsClose.click();
            await groupsDialog.waitFor({ state: "hidden" });

            await page
                .getByRole("button", { name: "More: team-member", exact: true })
                .click();
            await page
                .getByRole("menuitem", {
                    name: "Manage folders and access",
                    exact: true,
                })
                .click();
            const dialog = page.getByRole("dialog", {
                name: "Folder access for team-member",
                exact: true,
            });
            await dialog.waitFor();
            const noAccess = dialog.getByText("No access", { exact: true });
            await noAccess.waitFor();
            assert.equal(await noAccess.count(), 1);
            await dialog
                .getByRole("button", { name: "Save changes", exact: true })
                .click();
            await page
                .getByText("Folder access saved.", { exact: true })
                .waitFor();
            await mobileToastFits(page, "Folder access saved.", width);
            assert.deepEqual(grants, [
                { permission: "read", expires_at: null },
            ]);
            await dialog
                .getByText("Direct grant: team-member (Read)", { exact: true })
                .waitFor();
            const bounds = await dialog.boundingBox();
            assert.ok(
                bounds && bounds.x >= 0 && bounds.x + bounds.width <= width,
            );
            assert.equal(
                await dialog.evaluate(
                    (node) => node.scrollWidth <= node.clientWidth + 1,
                ),
                true,
            );
            const close = dialog.getByRole("button", {
                name: "Close",
                exact: true,
            });
            await visibleTouchAction(page, close);
            await viewportScreenshot(page, `user-folder-access-${width}.png`);

            await close.click();
            await dialog.waitFor({ state: "hidden" });
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [375, 1440]) {
    test(`folder owner grants group access and sees audit at ${width}px`, async () => {
        const { context, page, errors } = await vault(
            width,
            "en",
            "dark",
            entries,
            {
                groups: [{ id: 10, name: "Operations", member_count: 1 }],
                shareTargets: [
                    { id: 2, username: "team-member", role: "member" },
                ],
                folderAudit: [
                    {
                        id: 1,
                        created: "2026-10-27T12:00:00",
                        actor_user_id: 1,
                        actor_username: "synthetic",
                        action: "folder_created",
                        resource_type: "folder",
                        resource_id: 1,
                    },
                ],
            },
        );
        try {
            const grants = [];
            page.on("request", (request) => {
                if (
                    request.method() === "PUT" &&
                    new URL(request.url()).pathname ===
                        "/api/folders/1/grants/groups/10"
                )
                    grants.push(request.postDataJSON());
            });
            const mobileNavigation = await page
                .locator('[data-qa="mobile-header"]')
                .count();
            if (mobileNavigation) {
                await page
                    .getByRole("button", { name: "More", exact: true })
                    .click();
            }
            await page.locator('a[href="/passwords?tool=folders"]').click();
            if (mobileNavigation) {
                await page
                    .getByRole("dialog", { name: "Workspace", exact: true })
                    .waitFor({ state: "hidden" });
            }
            const dialog = page.getByRole("dialog", {
                name: "Folder access",
                exact: true,
            });
            await dialog.waitFor();
            await settleAnimations(page);
            await dialog
                .getByText("synthetic created the folder.", { exact: true })
                .waitFor();
            const [renameBox, grantsBox] = await Promise.all([
                dialog
                    .getByLabel("Rename folder", { exact: true })
                    .boundingBox(),
                dialog
                    .getByRole("heading", {
                        name: "Access grants",
                        exact: true,
                    })
                    .boundingBox(),
            ]);
            assert.ok(
                renameBox &&
                    grantsBox &&
                    grantsBox.y >= renameBox.y + renameBox.height,
                JSON.stringify({ renameBox, grantsBox }),
            );
            await dialog.getByLabel("Grant to", { exact: true }).click();
            await page
                .getByRole("option", { name: "Group", exact: true })
                .click();
            await dialog
                .getByLabel("Account or group", { exact: true })
                .click();
            await page
                .getByRole("option", { name: "Operations", exact: true })
                .click();
            assert.match(
                await dialog
                    .getByLabel("Expires (optional)", { exact: true })
                    .getAttribute("min"),
                /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/,
            );
            const expiry = dialog.getByLabel("Expires (optional)", {
                exact: true,
            });
            assert.equal(await expiry.getAttribute("type"), "datetime-local");
            await dialog
                .getByRole("button", { name: "Grant access", exact: true })
                .click();
            await page
                .getByText("Folder access saved.", { exact: true })
                .waitFor();
            await mobileToastFits(page, "Folder access saved.", width);
            assert.deepEqual(grants, [
                { permission: "read", expires_at: null },
            ]);
            await dialog
                .getByText("Operations", { exact: true })
                .first()
                .waitFor();
            const grantAudit = dialog.getByText(
                "synthetic granted folder access to group Operations.",
                {
                    exact: true,
                },
            );
            await grantAudit.waitFor();
            assert.equal(
                await dialog.evaluate(
                    (node) => node.scrollWidth <= node.clientWidth + 1,
                ),
                true,
            );
            await visibleTouchAction(
                page,
                dialog.getByRole("button", { name: "Close", exact: true }),
            );
            await viewportScreenshot(page, `folder-group-access-${width}.png`);
            await grantAudit.scrollIntoViewIfNeeded();
            await viewportScreenshot(page, `folder-group-audit-${width}.png`);
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [375, 1440]) {
    test(`sidebar navigation keeps native spacing and one active item at ${width}px`, async () => {
        const { context, page, errors } = await vault(width, "ru");
        try {
            if (await page.locator('[data-qa="mobile-header"]').count()) {
                await page
                    .getByRole("button", { name: "Ещё", exact: true })
                    .click();
            }
            const items = page.locator(
                '[data-qa="navigation-items"] [data-navigation-id]',
            );
            const boxes = await items.evaluateAll((nodes) =>
                nodes.map((node) => {
                    const rect = node.getBoundingClientRect();
                    return { top: rect.top, bottom: rect.bottom };
                }),
            );
            assert.ok(boxes.length >= 6, JSON.stringify(boxes));
            for (let index = 1; index < boxes.length; index += 1) {
                assert.ok(
                    boxes[index].top - boxes[index - 1].bottom >= 4,
                    JSON.stringify(boxes),
                );
            }
            const current = page.locator(
                '[data-qa="navigation-items"] [aria-current="page"]',
            );
            assert.equal(await current.count(), 1);
            assert.equal(
                await current.getAttribute("data-navigation-id"),
                "/passwords",
            );
            await page
                .locator('a[data-navigation-id="/passwords?tool=backup"]')
                .click();
            const backupDialog = page.getByRole("dialog", {
                name: "Создать резервную копию",
                exact: true,
            });
            await backupDialog.waitFor();
            assert.equal(await current.count(), 1);
            assert.equal(
                await current.getAttribute("data-navigation-id"),
                "/passwords?tool=backup",
            );
            await page.goBack();
            await backupDialog.waitFor({ state: "hidden" });
            assert.equal(new URL(page.url()).searchParams.has("tool"), false);
            await page.goForward();
            await backupDialog.waitFor();
            await page.goto(`${origin}/passwords?tool=health`);
            await backupDialog.waitFor({ state: "hidden" });
            await page
                .getByRole("dialog", {
                    name: "Проверка паролей",
                    exact: true,
                })
                .waitFor();
            assert.equal(
                await page.locator('[role="dialog"]:visible').count(),
                1,
            );
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [375, 899, 900, 1024, 1440]) {
    test(`vault tools stay reachable without duplicate page actions at ${width}px`, async () => {
        const { context, page, errors } = await vault(width, "ru");
        try {
            assert.equal(
                await page
                    .getByRole("button", {
                        name: "Действия с хранилищем",
                        exact: true,
                    })
                    .count(),
                0,
            );
            for (const [name, tool] of [
                ["Папки", "folders"],
                ["Проверка паролей", "health"],
                ["Резервная копия", "backup"],
                ["Импорт", "import"],
                ["Корзина", "trash"],
            ]) {
                if (await page.locator('[data-qa="mobile-header"]').count()) {
                    await page
                        .getByRole("button", { name: "Ещё", exact: true })
                        .click();
                }
                const action = page.locator(
                    `a[href="/passwords?tool=${tool}"]`,
                );
                assert.equal(await action.textContent(), name);
                await visibleTouchAction(page, action);
                assert.equal(
                    await page
                        .getByText(name, { exact: true })
                        .evaluate(
                            (node) => node.scrollWidth <= node.clientWidth,
                        ),
                    true,
                );
                await action.click();
                const dialog = page.locator(
                    '[role="dialog"]:not([aria-label="Рабочая область"])',
                );
                await dialog.waitFor();
                await fits(page);
                await page.keyboard.press("Escape");
                await dialog.waitFor({ state: "hidden" });
            }
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [375, 1440]) {
    test(`password health keeps one readable scroll flow at ${width}px`, async () => {
        const records = [
            entries[0],
            ...Array.from({ length: 10 }, (_, index) => ({
                ...entries[0],
                id: 200 + index,
                password_name:
                    index === 9
                        ? "Very long weak credential name ".repeat(8)
                        : `Weak credential ${index + 1}`,
                username:
                    index === 9
                        ? "very-long-username-".repeat(12)
                        : `weak-${index + 1}@example.test`,
                password_value: `x${index}`,
                updated: "2026-10-28T12:00:00Z",
            })),
        ];
        const { context, page, errors } = await vault(
            width,
            "ru",
            "dark",
            records,
        );
        try {
            await page.goto(`${origin}/passwords?tool=health`);
            const dialog = page.getByRole("dialog", {
                name: "Проверка паролей",
                exact: true,
            });
            await dialog.waitFor();
            const groups = dialog.locator('[data-qa="health-issue-group"]');
            assert.equal(await groups.count(), 1);
            const rows = groups.getByRole("button");
            assert.equal(await rows.count(), 10);
            const geometry = await dialog.evaluate((node) => {
                const body = node.querySelector(".g-dialog-body");
                const footer = node.querySelector(".g-dialog-footer");
                const group = node.querySelector(
                    '[data-qa="health-issue-group"]',
                );
                const rect = (element) => {
                    const bounds = element.getBoundingClientRect();
                    return {
                        top: bounds.top,
                        right: bounds.right,
                        bottom: bounds.bottom,
                        left: bounds.left,
                    };
                };
                return {
                    dialog: rect(node),
                    body: rect(body),
                    footer: rect(footer),
                    group: rect(group),
                    bodyScrollable: body.scrollHeight > body.clientHeight,
                    bodyOverflow: body.scrollWidth > body.clientWidth,
                };
            });
            assert.equal(
                geometry.bodyOverflow,
                false,
                JSON.stringify(geometry),
            );
            assert.ok(
                geometry.group.left >= geometry.body.left,
                JSON.stringify(geometry),
            );
            assert.ok(
                geometry.group.right <= geometry.body.right,
                JSON.stringify(geometry),
            );
            assert.ok(
                geometry.footer.top >= geometry.body.bottom - 1,
                JSON.stringify(geometry),
            );
            assert.ok(
                geometry.footer.bottom <= geometry.dialog.bottom + 1,
                JSON.stringify(geometry),
            );
            assert.equal(
                geometry.bodyScrollable,
                true,
                JSON.stringify(geometry),
            );
            if (process.env.CIPHERMOTH_SCREENSHOT_DIR) {
                await mkdir(process.env.CIPHERMOTH_SCREENSHOT_DIR, {
                    recursive: true,
                });
                await page.screenshot({
                    path: resolve(
                        process.env.CIPHERMOTH_SCREENSHOT_DIR,
                        `health-${width}-top.png`,
                    ),
                });
            }
            await rows.last().scrollIntoViewIfNeeded();
            await rows.last().waitFor({ state: "visible" });
            await page
                .getByRole("button", { name: "Готово", exact: true })
                .waitFor({ state: "visible" });
            if (process.env.CIPHERMOTH_SCREENSHOT_DIR) {
                await page.screenshot({
                    path: resolve(
                        process.env.CIPHERMOTH_SCREENSHOT_DIR,
                        `health-${width}-bottom.png`,
                    ),
                });
            }
            await fits(page);
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

for (const width of [320, 375, 430, 768, 1024, 1440]) {
    test(`vault rows keep a touch-safe open action and responsive quick actions at ${width}px`, async () => {
        const { context, page, errors } = await vault(width, "en", "dark", [
            { ...entries[0], totp_secret: null },
        ]);
        try {
            const item = page
                .locator('[data-qa="entry-list"]')
                .getByRole("row");
            const open = item;
            await visibleTouchAction(page, open);
            const actions = item.getByRole("button");
            const visible = await actions.evaluateAll((buttons) =>
                buttons
                    .filter((button) => button.offsetParent !== null)
                    .map((button) => {
                        const { x, width, height } =
                            button.getBoundingClientRect();
                        return { x, width, height };
                    }),
            );
            if (width < 1280) {
                assert.deepEqual(visible, []);
            } else {
                assert.ok(visible.length >= 4);
                for (const box of visible) {
                    assert.ok(
                        box.width >= 44 && box.height >= 44,
                        JSON.stringify(box),
                    );
                    assert.ok(
                        box.x >= 0 && box.x + box.width <= width,
                        JSON.stringify(box),
                    );
                }
            }
            await fits(page);
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

test("desktop vault keeps the screen fixed and scrolls the entry list", async () => {
    const records = [
        entries[0],
        ...Array.from({ length: 39 }, (_, index) => ({
            ...entries[0],
            id: 100 + index,
            password_name: `Scrollable entry ${index + 1}`,
        })),
    ];
    const { context, page, errors } = await vault(1440, "ru", "dark", records);
    try {
        const region = page.locator('[data-qa="entry-scroll-region"]');
        const title = page.locator('[data-qa="vault-page"] h1');
        const before = await region.evaluate((node) => ({
            clientHeight: node.clientHeight,
            scrollHeight: node.scrollHeight,
            windowScrollY: window.scrollY,
            documentScrollHeight: document.documentElement.scrollHeight,
            viewportHeight: innerHeight,
        }));
        assert.ok(
            before.scrollHeight > before.clientHeight,
            JSON.stringify(before),
        );
        assert.ok(
            before.documentScrollHeight <= before.viewportHeight + 1,
            JSON.stringify(before),
        );
        await viewportScreenshot(page, "desktop-vault-scroll-top.png");
        const titleTop = await title.evaluate(
            (node) => node.getBoundingClientRect().top,
        );
        await region.evaluate((node) => {
            node.scrollTop = node.scrollHeight;
        });
        await page.waitForTimeout(100);
        const after = await region.evaluate((node) => ({
            scrollTop: node.scrollTop,
            windowScrollY: window.scrollY,
        }));
        assert.ok(after.scrollTop > 0, JSON.stringify(after));
        assert.equal(after.windowScrollY, 0);
        assert.equal(
            await title.evaluate((node) => node.getBoundingClientRect().top),
            titleTop,
        );
        await viewportScreenshot(page, "desktop-vault-scroll-bottom.png");
        assert.deepEqual(errors, []);
    } finally {
        await context.close();
    }
});

test("mobile vault opens an accessible read view without exposing secrets", async () => {
    const { context, page, errors } = await vault(375);
    try {
        const list = page.locator('[data-qa="entry-list"]');
        await list.getByRole("row", { name: /^GitHub/ }).click();
        const detail = page.getByRole("dialog", {
            name: "GitHub",
            exact: true,
        });
        await detail.waitFor();
        assert.equal(
            await detail
                .getByText(entries[0].password_value, { exact: true })
                .count(),
            0,
        );
        assert.equal(
            await detail
                .getByText("Synthetic-recovery", { exact: true })
                .count(),
            0,
        );
        await detail
            .getByRole("button", { name: "Show password", exact: true })
            .click();
        await detail
            .getByText(entries[0].password_value, { exact: true })
            .waitFor();
        await detail
            .getByRole("button", { name: "Copy password", exact: true })
            .click();
        assert.equal(
            await page.evaluate(() => navigator.clipboard.readText()),
            entries[0].password_value,
        );
        await detail.getByRole("button", { name: /^Copy 2FA code/ }).click();
        assert.match(
            await page.evaluate(() => navigator.clipboard.readText()),
            /^\d{6}$/,
        );
        await detail
            .getByRole("button", { name: "Back to entries", exact: true })
            .click();

        await list.getByRole("row", { name: /^Read-only account/ }).click();
        const readOnly = page.getByRole("dialog", {
            name: "Read-only account",
            exact: true,
        });
        await readOnly.waitFor();
        for (const name of ["Edit", "Delete", "Manage access"]) {
            assert.equal(
                await readOnly
                    .getByRole("button", { name, exact: true })
                    .count(),
                0,
            );
        }
        await readOnly.getByText("Attachments (1)", { exact: true }).click();
        await readOnly.getByText("Readme.txt", { exact: true }).waitFor();
        assert.equal(await readOnly.locator('input[type="file"]').count(), 0);
        await readOnly
            .getByRole("button", { name: "Back to entries", exact: true })
            .click();

        await list.getByRole("row", { name: /^Recovery notes/ }).click();
        const note = page.getByRole("dialog", {
            name: "Recovery notes",
            exact: true,
        });
        assert.equal(
            await note
                .getByText(entries[2].password_value, { exact: true })
                .count(),
            0,
        );
        await note
            .getByRole("button", { name: "Copy note", exact: true })
            .click();
        assert.equal(
            await page.evaluate(() => navigator.clipboard.readText()),
            entries[2].password_value,
        );
        await fits(page);
        assert.deepEqual(errors, []);
    } finally {
        await context.close();
    }
});

test("desktop quick actions and details preserve ACL and confirmation boundaries", async () => {
    const { context, page, errors } = await vault(1440);
    try {
        const list = page.locator('[data-qa="entry-list"]');
        const github = list.getByRole("row").filter({ hasText: "GitHub" });
        await github
            .getByRole("button", { name: "Copy username", exact: true })
            .click();
        assert.equal(
            await page.evaluate(() => navigator.clipboard.readText()),
            entries[0].username,
        );
        await github
            .getByRole("button", { name: "Show password", exact: true })
            .click();
        await github
            .getByText(entries[0].password_value, { exact: true })
            .waitFor();
        assert.equal(
            await github
                .locator('[data-qa="entry-revealed-separator"]')
                .count(),
            1,
        );
        const revealedGeometry = await github.evaluate((row) => {
            const metadata = row
                .querySelector('[data-qa="entry-metadata"]')
                .getBoundingClientRect();
            const revealed = row
                .querySelector('[data-qa="entry-revealed-value"]')
                .getBoundingClientRect();
            return {
                metadataBottom: metadata.bottom,
                metadataLeft: metadata.left,
                revealedTop: revealed.top,
                revealedLeft: revealed.left,
            };
        });
        assert.ok(
            revealedGeometry.revealedTop >= revealedGeometry.metadataBottom,
            JSON.stringify(revealedGeometry),
        );
        assert.ok(
            Math.abs(
                revealedGeometry.revealedLeft - revealedGeometry.metadataLeft,
            ) <= 1,
            JSON.stringify(revealedGeometry),
        );
        await viewportScreenshot(page, "entry-row-revealed-1440.png");
        await github
            .getByRole("button", { name: "Copy password", exact: true })
            .click();
        assert.equal(
            await page.evaluate(() => navigator.clipboard.readText()),
            entries[0].password_value,
        );
        await github
            .getByRole("button", { name: "More: GitHub", exact: true })
            .click();
        for (const name of [
            "Open website",
            "Remove from favorites",
            "Edit",
            "Manage access",
            "Delete",
        ]) {
            const item = page.getByRole("menuitem", { name, exact: true });
            await item.waitFor();
            await item.hover();
            assert.match(
                await github.getAttribute("class"),
                /g-list-item-view_hovered_yes/,
            );
        }
        await viewportScreenshot(page, "entry-menu-hover-1440.png");
        await page.keyboard.press("Escape");
        assert.doesNotMatch(
            (await github.getAttribute("class")) ?? "",
            /g-list-item-view_hovered_yes/,
        );

        const trigger = github;
        await trigger.click({ position: { x: 24, y: 24 } });
        const detail = page.getByRole("region", { name: "Entry details" });
        await detail
            .getByRole("heading", { name: "GitHub", exact: true })
            .waitFor();
        const back = detail.getByRole("button", {
            name: "Back to entries",
            exact: true,
        });
        await visibleTouchAction(page, back);
        assert.ok((await back.locator("svg").count()) >= 1);
        const headerGeometry = await detail.evaluate((region) => {
            const backBox = region
                .querySelector('[data-qa="entry-details-back"]')
                .getBoundingClientRect();
            const headerBox = region
                .querySelector('[data-qa="entry-details-header"]')
                .getBoundingClientRect();
            return {
                backBottom: backBox.bottom,
                headerTop: headerBox.top,
                gap: headerBox.top - backBox.bottom,
            };
        });
        assert.ok(headerGeometry.headerTop >= headerGeometry.backBottom);
        assert.ok(headerGeometry.gap <= 24, JSON.stringify(headerGeometry));
        assert.equal(
            await detail
                .getByText(entries[0].password_value, { exact: true })
                .count(),
            0,
        );
        await detail
            .getByRole("button", { name: "Delete", exact: true })
            .click();
        const confirmation = page.getByRole("dialog", {
            name: "Move entry to trash?",
            exact: true,
        });
        await confirmation.waitFor();
        await confirmation
            .getByRole("button", { name: "Cancel", exact: true })
            .click();
        await confirmation.waitFor({ state: "hidden" });
        await page.keyboard.press("Escape");
        assert.equal(await detail.count(), 0);
        await page.waitForFunction(
            (row) => document.activeElement === row,
            await trigger.elementHandle(),
        );
        assert.equal(
            await trigger.evaluate(
                (button) => document.activeElement === button,
            ),
            true,
        );

        const readOnlyTrigger = list
            .getByRole("row")
            .filter({ hasText: "Read-only account" });
        await readOnlyTrigger.click();
        const readOnly = page.getByRole("region", { name: "Entry details" });
        await readOnly
            .getByRole("heading", { name: "Read-only account" })
            .waitFor();
        for (const name of ["Edit", "Delete", "Manage access"]) {
            assert.equal(
                await readOnly
                    .getByRole("button", { name, exact: true })
                    .count(),
                0,
            );
        }
        await fits(page);
        assert.deepEqual(errors, []);
    } finally {
        await context.close();
    }
});

test("entry editor keeps favorite beside the dialog close action", async () => {
    const { context, page, errors } = await vault(1440, "en", "dark");
    try {
        await page
            .locator('[data-qa="entry-list"]')
            .getByRole("row")
            .filter({ hasText: "GitHub" })
            .click({ position: { x: 24, y: 24 } });
        const details = page.getByRole("region", { name: "Entry details" });
        await details
            .getByRole("button", { name: "Edit", exact: true })
            .click();
        const dialog = page.getByRole("dialog", {
            name: "Edit login",
            exact: true,
        });
        await dialog.waitFor();
        await settleAnimations(page);
        const favorite = dialog.locator('[data-qa="entry-favorite-toggle"]');
        const close = dialog.locator("button[aria-label]").first();
        await visibleTouchAction(page, favorite);
        assert.equal(await favorite.count(), 1);
        const geometry = await Promise.all(
            [favorite, close].map((control) => control.boundingBox()),
        );
        assert.ok(geometry.every(Boolean), JSON.stringify(geometry));
        const [favoriteBox, closeBox] = geometry;
        assert.ok(favoriteBox.x < closeBox.x, JSON.stringify(geometry));
        assert.ok(
            Math.abs(favoriteBox.y - closeBox.y) <= 1,
            JSON.stringify(geometry),
        );
        assert.ok(
            closeBox.x - (favoriteBox.x + favoriteBox.width) <= 12,
            JSON.stringify(geometry),
        );
        await viewportScreenshot(page, "entry-editor-header.png");
        assert.deepEqual(errors, []);
    } finally {
        await context.close();
    }
});

for (const [width, language, theme] of [
    [320, "en", "dark"],
    [375, "ru", "light"],
    [430, "en", "dark"],
    [768, "ru", "dark"],
    [900, "ru", "dark"],
    [1024, "en", "dark"],
    [1280, "en", "dark"],
    [1440, "ru", "light"],
]) {
    test(`vault layout, filtering, details and trash fit ${width}px / ${language} / ${theme}`, async () => {
        const { context, page, errors } = await vault(width, language, theme);
        try {
            const ru = language === "ru";
            const t = ru ? ruText : enText;
            const list = page.locator('[data-qa="entry-list"]');
            assert.equal(await list.getByRole("row").count(), entries.length);
            await fits(page);
            await axe(page);

            const expectedOrder = [
                entries[1],
                entries[3],
                entries[2],
                entries[0],
            ].map((entry) => entry.password_name);
            assert.deepEqual(
                await list
                    .getByRole("row")
                    .evaluateAll((rows) =>
                        rows.map(
                            (row) =>
                                row.querySelector('[role="gridcell"]')
                                    .textContent,
                        ),
                    ),
                expectedOrder,
            );

            const search = page.getByPlaceholder(
                ru ? "Поиск записей…" : "Search entries…",
            );
            assert.equal(
                await page.locator('[data-qa="vault-search"] svg').count(),
                0,
            );
            const sort = page.getByRole("combobox", {
                name: t.vault.browser.sort,
                exact: true,
            });
            assert.equal(
                (await sort.textContent()).trim(),
                t.vault.browser.dateAdded,
            );
            const folder = page.getByRole("combobox", {
                name: t.common.fields.folder,
                exact: true,
            });
            assert.equal(
                (await folder.textContent()).trim(),
                t.vault.allFolders,
            );
            await search.fill("reader@example.test");
            assert.equal(await list.getByRole("row").count(), 1);
            await search.fill("");

            await page
                .getByRole("combobox", {
                    name: ru ? /^Папка/ : /^Folder/,
                })
                .click();
            await page.getByRole("option", { name: /^(Shared|Общ)/ }).click();
            assert.equal(await list.getByRole("row").count(), 1);
            await page
                .getByRole("combobox", {
                    name: ru ? /^Папка/ : /^Folder/,
                })
                .click();
            await page
                .getByRole("option", {
                    name: ru ? "Все папки" : "All folders",
                    exact: true,
                })
                .click();

            const longName = entries[3].password_name;
            await list.getByRole("row").filter({ hasText: longName }).click();
            const detail =
                width >= 1280
                    ? page.getByRole("region", {
                          name: ru ? "Просмотр записи" : "Entry details",
                      })
                    : page.getByRole("dialog", { name: longName, exact: true });
            await detail.waitFor();
            await axe(page);
            assert.equal(
                await detail
                    .getByText(entries[3].password_value, { exact: true })
                    .count(),
                0,
            );
            await detail
                .getByRole("button", {
                    name: ru ? "Показать пароль" : "Show password",
                    exact: true,
                })
                .click();
            await detail
                .getByText(entries[3].password_value, { exact: true })
                .waitFor();
            await page.keyboard.press("Escape");
            await detail.waitFor({ state: "hidden" });

            if (await page.locator('[data-qa="mobile-header"]').count()) {
                await page
                    .getByRole("button", {
                        name: t.navigation.more,
                        exact: true,
                    })
                    .click();
            }
            await page.locator('a[href="/passwords?tool=trash"]').click();
            const trash = page.getByRole("dialog", {
                name: ru ? "Корзина" : "Trash",
                exact: true,
            });
            await trash.waitFor();
            await trash
                .getByRole("button", { name: /^(Восстановить|Restore)/ })
                .waitFor();
            await fits(page);
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}

test("profile footer shows and applies current language and theme", async () => {
    const { context, page, errors } = await vault(375, "ru", "dark", entries, {
        role: "admin",
    });
    try {
        await page
            .getByRole("button", { name: ruText.navigation.more, exact: true })
            .click();
        await settleAnimations(page);
        const footer = page.locator('[data-qa="navigation-footer"]');
        assert.equal(
            await footer.locator('[data-qa="navigation-account"]').count(),
            1,
        );
        await footer
            .getByRole("button", {
                name: new RegExp(
                    `^${ruText.language.label}\\s+${ruText.language.russian}$`,
                ),
            })
            .click();
        await page
            .getByRole("menuitemcheckbox", {
                name: ruText.language.english,
                exact: true,
            })
            .click();
        await footer
            .getByRole("button", {
                name: new RegExp(
                    `^${enText.language.label}\\s+${enText.language.english}$`,
                ),
            })
            .waitFor();

        await footer
            .getByRole("button", {
                name: new RegExp(
                    `^${enText.theme.label}\\s+${enText.theme.dark}$`,
                ),
            })
            .click();
        await page
            .getByRole("menuitemcheckbox", {
                name: enText.theme.light,
                exact: true,
            })
            .click();
        await footer
            .getByRole("button", {
                name: new RegExp(
                    `^${enText.theme.label}\\s+${enText.theme.light}$`,
                ),
            })
            .waitFor();
        assert.deepEqual(
            await page.evaluate(() => ({
                mode: document.documentElement.dataset.theme,
                saved: localStorage.getItem("ciphermoth-theme"),
            })),
            { mode: "light", saved: "light" },
        );
        assert.deepEqual(errors, []);
    } finally {
        await context.close();
    }
});

// Opt-in visual matrix uses exactly the synthetic API/session fixture above.
// No backend, native runtime, real unlock, or external service is involved.
if (process.env.CIPHERMOTH_LAYOUT_MATRIX) {
    const combinations =
        process.env.CIPHERMOTH_LAYOUT_MATRIX === "baseline"
            ? [
                  [375, "ru", "dark"],
                  [1440, "en", "light"],
              ]
            : [320, 375, 768, 1440].flatMap((width) =>
                  ["ru", "en"].flatMap((language) =>
                      ["light", "dark"].map((theme) => [
                          width,
                          language,
                          theme,
                      ]),
                  ),
              );
    for (const [width, language, theme] of combinations) {
        test(`composition matrix ${width} ${language} ${theme}`, async () => {
            const t = language === "ru" ? ruText : enText;
            const options = {
                role: "admin",
                users: [
                    {
                        id: 1,
                        username: "synthetic",
                        role: "admin",
                        active: true,
                    },
                    {
                        id: 2,
                        username: "team-member",
                        role: "member",
                        active: true,
                    },
                    {
                        id: 3,
                        username: "automation",
                        role: "service",
                        active: false,
                    },
                ],
                groups: [{ id: 10, name: "Operations", member_count: 1 }],
                groupMembers: [
                    { user_id: 2, username: "team-member", role: "member" },
                ],
                shareTargets: [
                    { id: 2, username: "team-member", role: "member" },
                ],
                folderGrants: [
                    {
                        target_type: "group",
                        target_id: 10,
                        target_name: "Operations",
                        permission: "read",
                        expires_at: null,
                    },
                ],
                userFolderAccess: [
                    {
                        folder: {
                            id: 1,
                            name: "Work",
                            owner_id: 1,
                            owner_username: "synthetic",
                            can_manage: true,
                        },
                        direct_permission: null,
                        direct_expires_at: null,
                        effective_permission: null,
                        sources: [],
                    },
                ],
            };
            const { context, page, errors } = await vault(
                width,
                language,
                theme,
                entries,
                options,
            );
            const metrics = [];
            const prefix = `matrix-${width}-${language}-${theme}`;
            const capture = async (name) => {
                await page.evaluate(() => document.fonts.ready);
                await settleAnimations(page);
                await fits(page);
                // Dialogs and drawers are viewport overlays. A full-page capture
                // stitches fixed layers over scrolled content and invents visual
                // overlaps that are not present in the rendered viewport.
                await viewportScreenshot(page, `${prefix}-${name}.png`);
                metrics.push({
                    state: name,
                    ...(await page.evaluate(() => ({
                        width: innerWidth,
                        height: innerHeight,
                        scrollWidth: document.documentElement.scrollWidth,
                        dialogs: [
                            ...document.querySelectorAll('[role="dialog"]'),
                        ].map((node) => ({
                            name: node.getAttribute("aria-label"),
                            scrollWidth: node.scrollWidth,
                            clientWidth: node.clientWidth,
                        })),
                    }))),
                });
            };
            const button = (name) =>
                page.getByRole("button", { name, exact: true });
            const dismiss = async () => {
                await page.keyboard.press("Escape");
                await page.getByRole("dialog").waitFor({ state: "hidden" });
            };
            const utility = async (name) => {
                if (width < 1080) await button(t.navigation.more).click();
                // Utility rows have the same native List view as primary navigation.
                await page.getByText(name, { exact: true }).click();
            };
            try {
                await capture("vault");
                if (width < 1080) {
                    await button(t.navigation.more).click();
                    await capture("drawer");
                    if (process.env.CIPHERMOTH_LAYOUT_MATRIX !== "baseline") {
                        for (const height of [480, 900]) {
                            await page.setViewportSize({ width, height });
                            await page.waitForTimeout(300);
                            const geometry = await page
                                .locator('[data-qa="navigation-shell"]')
                                .evaluate((shell) => {
                                    const rect = (name) => {
                                        const r = shell
                                            .querySelector(
                                                `[data-qa="${name}"]`,
                                            )
                                            .getBoundingClientRect();
                                        return {
                                            top: r.top,
                                            bottom: r.bottom,
                                            height: r.height,
                                        };
                                    };
                                    return {
                                        header: rect("navigation-header"),
                                        body: rect("navigation-body"),
                                        footer: rect("navigation-footer"),
                                        height: innerHeight,
                                        preferences: (() => {
                                            const preferences =
                                                shell.querySelector(
                                                    '[data-qa="navigation-preferences"]',
                                                );
                                            const buttons = [
                                                ...preferences.querySelectorAll(
                                                    "button",
                                                ),
                                            ];
                                            const logout = shell.querySelector(
                                                '[data-qa="navigation-footer"] > button',
                                            );
                                            const intrinsicWidths = buttons.map(
                                                (button) => {
                                                    const clone =
                                                        button.cloneNode(true);
                                                    clone.style.position =
                                                        "fixed";
                                                    clone.style.visibility =
                                                        "hidden";
                                                    clone.style.width =
                                                        "max-content";
                                                    clone.style.maxWidth =
                                                        "none";
                                                    document.body.append(clone);
                                                    const width =
                                                        clone.getBoundingClientRect()
                                                            .width;
                                                    clone.remove();
                                                    return width;
                                                },
                                            );
                                            return {
                                                width: preferences.getBoundingClientRect()
                                                    .width,
                                                buttonWidths: buttons.map(
                                                    (button) =>
                                                        button.getBoundingClientRect()
                                                            .width,
                                                ),
                                                buttonRects: buttons.map(
                                                    (button) => {
                                                        const rect =
                                                            button.getBoundingClientRect();
                                                        return {
                                                            top: rect.top,
                                                            bottom: rect.bottom,
                                                        };
                                                    },
                                                ),
                                                intrinsicWidths,
                                                logoutWidth:
                                                    logout.getBoundingClientRect()
                                                        .width,
                                            };
                                        })(),
                                        controls: [
                                            ...shell.querySelectorAll(
                                                '[data-qa="navigation-preferences"] button',
                                            ),
                                        ].map(
                                            (node) =>
                                                node.getBoundingClientRect()
                                                    .height,
                                        ),
                                    };
                                });
                            assert.ok(
                                geometry.header.bottom <= geometry.body.top + 1,
                            );
                            assert.ok(
                                geometry.body.bottom <= geometry.footer.top + 1,
                            );
                            assert.ok(
                                Math.abs(geometry.footer.bottom - height) <= 1,
                                JSON.stringify(geometry),
                            );
                            assert.deepEqual(geometry.controls, [44, 44]);
                            assert.ok(
                                geometry.preferences.buttonWidths.every(
                                    (buttonWidth, index) =>
                                        buttonWidth + 1 >=
                                        geometry.preferences.intrinsicWidths[
                                            index
                                        ],
                                ),
                                JSON.stringify(geometry.preferences),
                            );
                            assert.ok(
                                geometry.preferences.buttonWidths.every(
                                    (buttonWidth) =>
                                        Math.abs(
                                            buttonWidth -
                                                geometry.preferences.width,
                                        ) <= 1,
                                ),
                                JSON.stringify(geometry.preferences),
                            );
                            assert.ok(
                                geometry.preferences.buttonRects[0].bottom <=
                                    geometry.preferences.buttonRects[1].top,
                                JSON.stringify(geometry.preferences),
                            );
                            assert.ok(
                                Math.abs(
                                    geometry.preferences.logoutWidth -
                                        geometry.preferences.width,
                                ) <= 1,
                                JSON.stringify(geometry.preferences),
                            );
                            metrics.push({
                                state: `drawer-${height}`,
                                ...geometry,
                            });
                            await capture(`drawer-${height}`);
                        }
                    }
                    await dismiss();
                    await page.setViewportSize({
                        width,
                        height: width < 600 ? 812 : 900,
                    });
                    if (process.env.CIPHERMOTH_LAYOUT_MATRIX !== "baseline") {
                        const centers = await page
                            .locator('[data-qa="mobile-header"]')
                            .evaluate((header) =>
                                ["burger", "brand-mark", "brand-title"].map(
                                    (qa) => {
                                        const r = header
                                            .querySelector(`[data-qa="${qa}"]`)
                                            .getBoundingClientRect();
                                        return {
                                            qa,
                                            center: r.top + r.height / 2,
                                        };
                                    },
                                ),
                            );
                        assert.ok(
                            Math.max(...centers.map((r) => r.center)) -
                                Math.min(...centers.map((r) => r.center)) <=
                                1,
                            JSON.stringify(centers),
                        );
                        metrics.push({ state: "header-axis", centers });
                    }
                }
                const list = page.locator('[data-qa="entry-list"]');
                const longRow = list
                    .getByRole("row")
                    .filter({ hasText: entries[3].password_name });
                await longRow.scrollIntoViewIfNeeded();
                const wrappedValues = await longRow.evaluate((row) => {
                    const measure = (qa) => {
                        const node = row.querySelector(`[data-qa="${qa}"]`);
                        const bounds = node.getBoundingClientRect();
                        return {
                            height: bounds.height,
                            lineHeight: Number.parseFloat(
                                getComputedStyle(node).lineHeight,
                            ),
                            scrollWidth: node.scrollWidth,
                            clientWidth: node.clientWidth,
                        };
                    };
                    return {
                        name: measure("entry-name"),
                        primaryValue: measure("entry-primary-value"),
                    };
                });
                for (const value of Object.values(wrappedValues)) {
                    assert.ok(
                        value.height >= value.lineHeight * 2 - 1,
                        JSON.stringify(wrappedValues),
                    );
                    assert.ok(
                        value.scrollWidth <= value.clientWidth + 1,
                        JSON.stringify(wrappedValues),
                    );
                }
                for (const [name, state] of [
                    ["GitHub", "details"],
                    ["Read-only account", "readonly"],
                    ["Recovery notes", "note"],
                    [entries[3].password_name, "long-details"],
                ]) {
                    await list
                        .getByRole("row")
                        .filter({ hasText: name })
                        .click({ position: { x: 24, y: 24 } });
                    await capture(state);
                    await page.keyboard.press("Escape");
                }
                await list
                    .getByRole("row")
                    .filter({ hasText: "GitHub" })
                    .click();
                await button(t.sharing.manage).click();
                await capture("share");
                await dismiss();
                await page.keyboard.press("Escape");
                await list
                    .getByRole("row")
                    .filter({ hasText: "GitHub" })
                    .click();
                await button(t.common.actions.delete).click();
                await capture("delete-confirm");
                await dismiss();
                await page.keyboard.press("Escape");
                for (const tool of [
                    "backup",
                    "health",
                    "trash",
                    "folders",
                    "import",
                ]) {
                    await page.goto(`${origin}/passwords?tool=${tool}`);
                    await page.getByRole("dialog").waitFor();
                    await capture(tool);
                    if (tool === "trash") {
                        await page
                            .getByRole("button", {
                                name: /^(Удалить навсегда|Delete forever):/,
                            })
                            .click();
                        await capture("purge-confirm");
                        await page.keyboard.press("Escape");
                    }
                    await dismiss();
                }
                await utility(t.topMenu.settings);
                await capture("settings");
                await dismiss();
                await utility(t.auth.changePassword);
                await capture("change-password");
                await dismiss();
                await button(t.common.actions.add).click();
                await capture("editor");
                await button(t.entry.actions.generatePassword).click();
                await capture("generator");
                await button(t.common.actions.cancel).click();
                await page.goto(`${origin}/users`);
                await page.getByText("team-member", { exact: true }).waitFor();
                if (width < 600) {
                    const cards = await page
                        .locator('[data-qa="user-card"]')
                        .evaluateAll((nodes) =>
                            nodes.map((card) => {
                                const bounds = (node) => {
                                    const rect = node.getBoundingClientRect();
                                    return {
                                        top: rect.top,
                                        bottom: rect.bottom,
                                        left: rect.left,
                                        right: rect.right,
                                        width: rect.width,
                                        height: rect.height,
                                        center: rect.top + rect.height / 2,
                                    };
                                };
                                const controls = card.querySelector(
                                    '[data-qa="user-controls"]',
                                );
                                const actions = card.querySelector(
                                    '[data-qa="user-actions"]',
                                );
                                const role = card.querySelector(
                                    '[data-qa="user-role-control"]',
                                );
                                const roleText =
                                    role.querySelector('[role="combobox"]');
                                const status = card
                                    .querySelector('[role="switch"]')
                                    .closest("label");
                                const more =
                                    card.querySelector("[data-user-menu]");
                                return {
                                    card: bounds(card),
                                    controls: bounds(controls),
                                    role: bounds(role),
                                    roleText: {
                                        clientWidth: roleText.clientWidth,
                                        scrollWidth: roleText.scrollWidth,
                                    },
                                    actions: bounds(actions),
                                    actionCenters: [
                                        bounds(status).center,
                                        bounds(more).center,
                                    ],
                                };
                            }),
                        );
                    assert.equal(cards.length, 3);
                    for (const geometry of cards) {
                        assert.ok(
                            geometry.card.left >= 0 &&
                                geometry.card.right <= width &&
                                geometry.card.height <= 220,
                            JSON.stringify(geometry),
                        );
                        assert.ok(
                            Math.abs(
                                geometry.role.width - geometry.controls.width,
                            ) <= 1,
                            JSON.stringify(geometry),
                        );
                        assert.ok(
                            geometry.roleText.scrollWidth <=
                                geometry.roleText.clientWidth,
                            JSON.stringify(geometry),
                        );
                        assert.ok(
                            Math.abs(
                                geometry.actions.width -
                                    geometry.controls.width,
                            ) <= 1,
                            JSON.stringify(geometry),
                        );
                        assert.ok(
                            Math.max(...geometry.actionCenters) -
                                Math.min(...geometry.actionCenters) <=
                                1,
                            JSON.stringify(geometry),
                        );
                    }
                    metrics.push({ state: "user-cards", cards });
                }
                if (width >= 768) {
                    const cards = await page
                        .locator('[data-qa="user-card"]')
                        .evaluateAll((nodes) =>
                            nodes.map((card) => {
                                const bounds = (node) => {
                                    const rect = node.getBoundingClientRect();
                                    return {
                                        left: rect.left,
                                        right: rect.right,
                                        width: rect.width,
                                    };
                                };
                                const controls = card.querySelector(
                                    '[data-qa="user-controls"]',
                                );
                                const role = card.querySelector(
                                    '[data-qa="user-role-control"]',
                                );
                                const actions = card.querySelector(
                                    '[data-qa="user-actions"]',
                                );
                                const roleText =
                                    role.querySelector('[role="combobox"]');
                                return {
                                    card: {
                                        ...bounds(card),
                                        clientWidth: card.clientWidth,
                                        scrollWidth: card.scrollWidth,
                                    },
                                    controls: bounds(controls),
                                    role: bounds(role),
                                    actions: bounds(actions),
                                    roleText: {
                                        clientWidth: roleText.clientWidth,
                                        scrollWidth: roleText.scrollWidth,
                                    },
                                };
                            }),
                        );
                    assert.equal(cards.length, 3);
                    for (const card of cards) {
                        assert.ok(
                            card.card.scrollWidth <= card.card.clientWidth,
                            JSON.stringify(card),
                        );
                        assert.ok(
                            card.roleText.scrollWidth <=
                                card.roleText.clientWidth,
                            JSON.stringify(card),
                        );
                    }
                    for (const key of ["left", "right", "width"]) {
                        assert.ok(
                            Math.max(...cards.map((card) => card.role[key])) -
                                Math.min(
                                    ...cards.map((card) => card.role[key]),
                                ) <=
                                1,
                            JSON.stringify(cards),
                        );
                    }
                    assert.ok(
                        Math.max(...cards.map((card) => card.actions.right)) -
                            Math.min(
                                ...cards.map((card) => card.actions.right),
                            ) <=
                            1,
                        JSON.stringify(cards),
                    );
                    metrics.push({ state: "user-cards-wide", cards });
                }
                await capture("users");
                await button(t.groups.title).click();
                await page
                    .getByRole("dialog")
                    .getByText("team-member", { exact: true })
                    .waitFor();
                await capture("groups");
                await dismiss();
                await button(`${t.navigation.more}: team-member`).click();
                await page
                    .getByRole("menuitem", {
                        name: t.folderAccess.manage,
                        exact: true,
                    })
                    .click();
                await page
                    .getByRole("dialog")
                    .getByText("Work", { exact: true })
                    .waitFor();
                await capture("user-acl");
                await dismiss();
                await button(`${t.navigation.more}: team-member`).click();
                await page
                    .getByRole("menuitem", {
                        name: t.users.resetPassword,
                        exact: true,
                    })
                    .click();
                await capture("reset-password");
                await dismiss();
                await page.route("**/api/passwords", (route) =>
                    route.fulfill({ json: [] }),
                );
                await page.goto(`${origin}/passwords`);
                await page
                    .getByText(t.vault.subtitle.empty, { exact: true })
                    .first()
                    .waitFor();
                await capture("empty");
                await page.route("**/api/passwords", (route) =>
                    route.fulfill({
                        status: 503,
                        json: { detail: "Synthetic UI request failure" },
                    }),
                );
                await page.reload();
                await page
                    .getByText("Synthetic UI request failure", { exact: false })
                    .first()
                    .waitFor();
                await capture("error");
                assert.deepEqual(errors, []);
            } finally {
                if (process.env.CIPHERMOTH_SCREENSHOT_DIR)
                    await writeFile(
                        resolve(
                            process.env.CIPHERMOTH_SCREENSHOT_DIR,
                            `${prefix}-metrics.json`,
                        ),
                        JSON.stringify(metrics, null, 2),
                    );
                await context.close();
            }
        });
    }
}

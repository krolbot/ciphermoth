import { createStore } from "easy-peasy";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../api/client";
import { routes } from "../test/adapter";
import { stubBrowser } from "../test/globals";
import { getCurrentUser, getSessionToken, isAuth } from "../utils";
import MasterPassword from "./masterPassword";

const KEY = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWY=";
const TOKEN = "kM3x1y8Qe0bWv7c2Z9pL4tR6sN5aH1jD0fG3uY8iO2w";
const USER = { id: 7, username: "moth-admin", role: "admin", active: true };
const originalAdapter = apiClient.defaults.adapter;

let browser;
let seen;

beforeEach(() => {
  vi.unstubAllGlobals();
  browser = stubBrowser();
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

const build = (table) => {
  seen = [];
  apiClient.defaults.adapter = routes(table, seen);
  const instance = createStore({ masterPassword: MasterPassword });
  return {
    actions: instance.getActions().masterPassword,
    state: () => instance.getState().masterPassword,
  };
};

const authenticate = (actions, endpoint = "/auth/login", password = "Moth-Test-Vault-2026!") =>
  actions.authenticate({ endpoint, username: USER.username, password });

describe("authenticate", () => {
  it("stores the opaque session and current user, then opens the vault", async () => {
    const { actions, state: current } = build({
      "POST /auth/login": [
        200,
        { valid: true, session_token: TOKEN, user: USER, idle_timeout_ms: 180000 },
      ],
    });

    await authenticate(actions);

    expect(getSessionToken()).toBe(TOKEN);
    expect(getCurrentUser()).toEqual(USER);
    expect(browser.storage.entries()).toEqual({
      ciphermothSession: TOKEN,
      ciphermothUser: JSON.stringify(USER),
    });
    expect(browser.location.replace).toHaveBeenCalledWith("/passwords");
    expect(current().error).toBeNull();
    expect(current().loading).toBe(false);
    expect(JSON.parse(seen[0].data)).toEqual({
      username: USER.username,
      password: "Moth-Test-Vault-2026!",
    });
  });

  it.each(["/users", "/users/?view=accounts#selected", "/passwords?folder=Work#entry"])(
    "returns to the requested local protected route %s without sending it to the server",
    async (returnTo) => {
      const { actions } = build({
        "POST /auth/login": [200, { valid: true, session_token: TOKEN, user: USER }],
      });
      await actions.authenticate({
        endpoint: "/auth/login",
        username: USER.username,
        password: "synthetic-only",
        returnTo,
      });
      expect(browser.location.replace).toHaveBeenCalledWith(returnTo);
      expect(JSON.parse(seen[0].data)).not.toHaveProperty("returnTo");
    }
  );

  it.each([
    undefined,
    null,
    {},
    "",
    "/login",
    "/unknown",
    "//evil.example/users",
    "https://evil.example/users",
    ["javascript", "alert(1)"].join(":"),
    "/\\evil.example/users",
    "/users/../../login",
    "/users%2f..%2f..%2flogin",
  ])("rejects unsafe or unrecognized return targets: %s", async (returnTo) => {
    const { actions } = build({
      "POST /auth/login": [200, { valid: true, session_token: TOKEN, user: USER }],
    });
    await actions.authenticate({
      endpoint: "/auth/login",
      username: USER.username,
      password: "synthetic-only",
      returnTo,
    });
    expect(browser.location.replace).toHaveBeenCalledWith("/passwords");
  });

  it("never stores vault key material even if a server sends it", async () => {
    const { actions } = build({
      "POST /auth/login": [
        200,
        { valid: true, session_token: TOKEN, user: USER, key_derivation: KEY },
      ],
    });

    await authenticate(actions);

    expect(JSON.stringify(browser.storage.entries())).not.toContain(KEY);
  });

  it("stays locked when credentials are rejected", async () => {
    const { actions, state: current } = build({
      "POST /auth/login": [200, { valid: false, session_token: null, user: null }],
    });

    await authenticate(actions, "/auth/login", "wrong");

    expect(isAuth()).toBe(false);
    expect(browser.location.replace).not.toHaveBeenCalled();
    expect(current().error).toBe("Invalid username or password.");
  });

  it("stays locked when the server omits either the session or user", async () => {
    const { actions } = build({
      "POST /auth/login": [200, { valid: true, session_token: TOKEN, user: null }],
    });

    await authenticate(actions);

    expect(browser.storage.entries()).toEqual({});
    expect(isAuth()).toBe(false);
    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it("explains rate limiting", async () => {
    const { actions, state: current } = build({
      "POST /auth/login": [429, { detail: "Too many attempts." }],
    });

    await authenticate(actions, "/auth/login", "wrong");

    expect(isAuth()).toBe(false);
    expect(current().error).toBe("Too many attempts. Please try again in an hour.");
  });

  it("shows the server detail on other errors", async () => {
    const { actions, state: current } = build({
      "POST /auth/login": [403, { detail: "Account disabled." }],
    });

    await authenticate(actions);

    expect(current().error).toBe("Account disabled.");
    expect(current().loading).toBe(false);
  });

  it("uses the closed-registration bootstrap endpoint for the first administrator", async () => {
    const { actions } = build({
      "POST /auth/bootstrap": [
        200,
        { valid: true, session_token: TOKEN, user: USER, idle_timeout_ms: 180000 },
      ],
    });

    await authenticate(actions, "/auth/bootstrap");

    expect(getSessionToken()).toBe(TOKEN);
    expect(getCurrentUser()).toEqual(USER);
    expect(seen.map((config) => config.url)).toEqual(["/auth/bootstrap"]);
    expect(browser.location.replace).toHaveBeenCalledWith("/passwords");
  });

  it("surfaces the backend password policy error and stays locked", async () => {
    const { actions, state: current } = build({
      "POST /auth/bootstrap": [
        422,
        { detail: [{ msg: "Value error, Master password must be at least 12 characters long." }] },
      ],
    });

    await authenticate(actions, "/auth/bootstrap", "short");

    expect(isAuth()).toBe(false);
    expect(current().error).toBe("Master password must be at least 12 characters long.");
  });
});

describe("status", () => {
  it("reports whether account bootstrap has completed", async () => {
    const { actions, state: current } = build({
      "GET /auth/status": [200, { initialized: false }],
    });

    await actions.fetchStatus();

    expect(current().initialized).toBe(false);
  });

  it("fails closed to the login screen when the status call fails", async () => {
    const { actions, state: current } = build({});

    await actions.fetchStatus();

    expect(current().initialized).toBe(true);
  });
});

import { createStore } from "easy-peasy";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../api/client";
import { routes } from "../test/adapter";
import { stubBrowser } from "../test/globals";
import { getSessionToken, isAuth } from "../utils";
import MasterPassword from "./masterPassword";

const KEY = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWY=";
const TOKEN = "kM3x1y8Qe0bWv7c2Z9pL4tR6sN5aH1jD0fG3uY8iO2w";
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

describe("unlock", () => {
  it("stores only the session token and opens the vault on a valid password", async () => {
    const { actions, state: current } = build({
      "POST /master_password/unlock": [200, { valid: true, session_token: TOKEN }],
    });
    await actions.unlock({ master_password: "Moth-Test-Vault-2026!" });
    expect(getSessionToken()).toBe(TOKEN);
    expect(browser.storage.entries()).toEqual({ ciphermothSession: TOKEN });
    expect(browser.location.replace).toHaveBeenCalledWith("/passwords");
    expect(current().error).toBeNull();
    expect(current().loading).toBe(false);
    expect(JSON.parse(seen[0].data)).toEqual({ master_password: "Moth-Test-Vault-2026!" });
  });

  it("never stores a vault key, even if a server sends one", async () => {
    const { actions } = build({
      "POST /master_password/unlock": [
        200,
        { valid: true, session_token: TOKEN, key_derivation: KEY },
      ],
    });
    await actions.unlock({ master_password: "Moth-Test-Vault-2026!" });
    expect(JSON.stringify(browser.storage.entries())).not.toContain(KEY);
  });

  it("never asks the deprecated endpoint for the key", async () => {
    const { actions } = build({
      "POST /master_password/unlock": [200, { valid: true, session_token: TOKEN }],
    });
    await actions.unlock({ master_password: "x" });
    expect(seen.map((config) => config.url)).toEqual(["/master_password/unlock"]);
  });

  it("stays locked on a wrong password", async () => {
    const { actions, state: current } = build({
      "POST /master_password/unlock": [200, { valid: false, session_token: null }],
    });
    await actions.unlock({ master_password: "wrong" });
    expect(isAuth()).toBe(false);
    expect(browser.location.replace).not.toHaveBeenCalled();
    expect(current().error).toBe("Invalid master password.");
  });

  it("stays locked when the server answers valid without a session", async () => {
    const { actions } = build({
      "POST /master_password/unlock": [200, { valid: true, key_derivation: KEY }],
    });
    await actions.unlock({ master_password: "x" });
    expect(browser.storage.entries()).toEqual({});
    expect(isAuth()).toBe(false);
    expect(browser.location.replace).not.toHaveBeenCalled();
  });

  it("explains rate limiting", async () => {
    const { actions, state: current } = build({
      "POST /master_password/unlock": [429, { detail: "Too many attempts." }],
    });
    await actions.unlock({ master_password: "x" });
    expect(isAuth()).toBe(false);
    expect(current().error).toBe("Too many attempts. Please try again in an hour.");
  });

  it("shows the server detail on other errors", async () => {
    const { actions, state: current } = build({
      "POST /master_password/unlock": [404, { detail: "No master password found." }],
    });
    await actions.unlock({ master_password: "x" });
    expect(current().error).toBe("No master password found.");
    expect(current().loading).toBe(false);
  });
});

describe("create", () => {
  it("stores the returned session and opens the vault", async () => {
    const { actions } = build({
      "POST /master_password/create": [
        200,
        { created: true, detail: "ok", session_token: TOKEN, idle_timeout_ms: 180000 },
      ],
    });
    await actions.create({ master_password: "Moth-Test-Vault-2026!" });
    expect(browser.storage.entries()).toEqual({ ciphermothSession: TOKEN });
    expect(browser.location.replace).toHaveBeenCalledWith("/passwords");
  });

  it("asks for an unlock instead of storing a key from an older server", async () => {
    const { actions, state: current } = build({
      "POST /master_password/create": [200, { created: true, detail: "ok", key_derivation: KEY }],
    });
    await actions.create({ master_password: "Moth-Test-Vault-2026!" });
    expect(browser.storage.entries()).toEqual({});
    expect(browser.location.replace).not.toHaveBeenCalled();
    expect(current().initialized).toBe(true);
  });

  it("surfaces the strength policy error and stays locked", async () => {
    const { actions, state: current } = build({
      "POST /master_password/create": [
        422,
        { detail: [{ msg: "Value error, Master password must be at least 12 characters long." }] },
      ],
    });
    await actions.create({ master_password: "short" });
    expect(isAuth()).toBe(false);
    expect(current().error).toBe("Master password must be at least 12 characters long.");
  });
});

describe("status", () => {
  it("reports the vault status", async () => {
    const { actions, state: current } = build({
      "GET /master_password/status": [200, { initialized: false }],
    });
    await actions.fetchStatus();
    expect(current().initialized).toBe(false);
  });

  it("assumes an existing vault when the status call fails", async () => {
    const { actions, state: current } = build({});
    await actions.fetchStatus();
    expect(current().initialized).toBe(true);
  });
});

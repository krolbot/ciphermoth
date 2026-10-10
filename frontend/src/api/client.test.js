import { beforeEach, describe, expect, it, vi } from "vitest";

import { replyWith } from "../test/adapter";
import { stubBrowser } from "../test/globals";
import { getKeyDerivation, isAuth, removeKeyDerivation, setKeyDerivation } from "../utils";
import apiClient from "./client";

const KEY = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWY=";
const HEADER = "x-ciphermoth-key-derivation";

let browser;

beforeEach(() => {
  vi.unstubAllGlobals();
  browser = stubBrowser();
});

const failWith = async (status, data) => {
  const error = await apiClient
    .get("/passwords", { adapter: replyWith(status, data) })
    .catch((err) => err);
  expect(error.response.status).toBe(status);
  return error;
};

describe("session key helpers", () => {
  it("stores, reads and removes the key in sessionStorage only", () => {
    expect(isAuth()).toBe(false);
    setKeyDerivation(KEY);
    expect(isAuth()).toBe(true);
    expect(getKeyDerivation()).toBe(KEY);
    expect(browser.storage.getItem("keyDerivation")).toBe(KEY);
    removeKeyDerivation();
    expect(isAuth()).toBe(false);
  });

  it("ignores empty keys", () => {
    setKeyDerivation("");
    setKeyDerivation(undefined);
    expect(isAuth()).toBe(false);
  });
});

describe("request interceptor", () => {
  it("sends the vault key header when unlocked", async () => {
    setKeyDerivation(KEY);
    const seen = [];
    await apiClient.get("/passwords", { adapter: replyWith(200, [], seen) });
    expect(seen[0].headers[HEADER]).toBe(KEY);
  });

  it("sends no key header when locked", async () => {
    const seen = [];
    await apiClient.get("/master_password/status", { adapter: replyWith(200, {}, seen) });
    expect(seen[0].headers[HEADER]).toBeUndefined();
  });
});

describe("response interceptor", () => {
  it("locks and reloads on an invalid_key 403", async () => {
    setKeyDerivation(KEY);
    const error = await failWith(403, {
      detail: "Invalid or expired vault key.",
      code: "invalid_key",
    });
    expect(error.response.data.code).toBe("invalid_key");
    expect(isAuth()).toBe(false);
    expect(browser.location.reload).toHaveBeenCalledTimes(1);
  });

  it("reads the code from a Blob body as well", async () => {
    setKeyDerivation(KEY);
    const body = new Blob([JSON.stringify({ detail: "x", code: "invalid_key" })], {
      type: "application/json",
    });
    await failWith(403, body);
    expect(isAuth()).toBe(false);
    expect(browser.location.reload).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["a 403 without the code", 403, { detail: "Incorrect master password." }],
    ["a 403 with another code", 403, { detail: "x", code: "other" }],
    ["a 403 with a non-JSON Blob", 403, new Blob(["<html>"])],
    ["a 401", 401, { code: "invalid_key" }],
    ["a 500", 500, { detail: "An internal server error occurred." }],
    ["a 429", 429, { detail: "Too many attempts." }],
  ])("keeps the session on %s", async (_, status, data) => {
    setKeyDerivation(KEY);
    await failWith(status, data);
    expect(getKeyDerivation()).toBe(KEY);
    expect(browser.location.reload).not.toHaveBeenCalled();
  });

  it("does not reload when the vault is already locked", async () => {
    await failWith(403, { code: "invalid_key" });
    expect(browser.location.reload).not.toHaveBeenCalled();
  });

  it("passes successful responses through untouched", async () => {
    setKeyDerivation(KEY);
    const { data } = await apiClient.get("/meta", { adapter: replyWith(200, { version: "1" }) });
    expect(data).toEqual({ version: "1" });
    expect(isAuth()).toBe(true);
  });
});

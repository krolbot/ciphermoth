import { createStore } from "easy-peasy";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../api/client";
import { routes } from "../test/adapter";
import { stubBrowser } from "../test/globals";
import { setKeyDerivation } from "../utils";
import Passwords from "./passwords";

const KEY = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWY=";
const RESULT = { imported: 2, skipped: 1, overwritten: 0, total: 3 };
const originalAdapter = apiClient.defaults.adapter;

let seen;

const build = (table) => {
  seen = [];
  apiClient.defaults.adapter = routes(
    { "GET /passwords": [200, []], "GET /passwords/trash": [200, []], ...table },
    seen
  );
  return createStore({ passwords: Passwords }).getActions().passwords;
};

const fields = (formData) => Object.fromEntries(formData.entries());

beforeEach(() => {
  vi.unstubAllGlobals();
  stubBrowser();
  setKeyDerivation(KEY);
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe("imports", () => {
  it("sends a backup ZIP with the master password and conflict mode", async () => {
    const actions = build({ "POST /passwords/import": [200, RESULT] });
    const file = new File([new Uint8Array([80, 75, 3, 4])], "backup.zip");
    await expect(
      actions.importPasswords({ file, masterPassword: "Moth-Test-Vault-2026!", onConflict: "skip" })
    ).resolves.toEqual(RESULT);

    const [request, refresh] = seen;
    expect(request.data).toBeInstanceOf(FormData);
    const sent = fields(request.data);
    expect(Object.keys(sent).sort()).toEqual(["file", "master_password", "on_conflict"]);
    expect(sent.master_password).toBe("Moth-Test-Vault-2026!");
    expect(sent.on_conflict).toBe("skip");
    expect(sent.file.name).toBe("backup.zip");
    expect(request.headers["x-ciphermoth-key-derivation"]).toBe(KEY);
    expect(`${refresh.method} ${refresh.url}`).toBe("get /passwords");
  });

  it("sends a CSV without the master password", async () => {
    const actions = build({ "POST /passwords/import/csv": [200, RESULT] });
    const file = new File(["name,password\na,b\n"], "export.csv", { type: "text/csv" });
    await expect(actions.importCsv({ file, onConflict: "overwrite" })).resolves.toEqual(RESULT);

    const sent = fields(seen[0].data);
    expect(Object.keys(sent).sort()).toEqual(["file", "on_conflict"]);
    expect(sent.on_conflict).toBe("overwrite");
  });

  it("turns a rejected import into the server message", async () => {
    const actions = build({
      "POST /passwords/import/csv": [400, { detail: "CSV must have a name/title column." }],
    });
    const file = new File(["x"], "export.csv");
    await expect(actions.importCsv({ file, onConflict: "skip" })).rejects.toThrow(
      "CSV must have a name/title column."
    );
    expect(seen).toHaveLength(1);
  });

  it("falls back to a generic message on an unexpected failure", async () => {
    const actions = build({ "POST /passwords/import": [500, "<html>"] });
    const file = new File(["x"], "backup.zip");
    await expect(
      actions.importPasswords({ file, masterPassword: "x", onConflict: "skip" })
    ).rejects.toThrow("Import failed.");
  });
});

describe("backup", () => {
  it("downloads the archive as a zip file", async () => {
    const actions = build({ "POST /passwords/backup": [200, new Blob(["zip"])] });
    const link = { click: vi.fn() };
    vi.stubGlobal("document", { createElement: vi.fn(() => link) });
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:backup");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await actions.backup("Moth-Test-Vault-2026!");

    const [request] = seen;
    expect(request.responseType).toBe("blob");
    expect(JSON.parse(request.data)).toEqual({ master_password: "Moth-Test-Vault-2026!" });
    expect(link.download).toMatch(/^ciphermoth_backup_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.zip$/);
    expect(link.click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:backup");
    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
  });

  it("reports a wrong master password from the Blob error body", async () => {
    const body = new Blob([JSON.stringify({ detail: "Incorrect master password." })]);
    const actions = build({ "POST /passwords/backup": [403, body] });
    await expect(actions.backup("wrong")).rejects.toThrow("Incorrect master password.");
  });
});

describe("entry names in URLs", () => {
  it.each([
    ["notes#2024", "/passwords/notes%232024"],
    ["a/b", "/passwords/a%2Fb"],
    ["x/purge", "/passwords/x%2Fpurge"],
    ["../settings", "/passwords/..%2Fsettings"],
    ["what?", "/passwords/what%3F"],
    ["...", "/passwords/..."],
    ["Wi-Fi ключ", "/passwords/Wi-Fi%20%D0%BA%D0%BB%D1%8E%D1%87"],
  ])("encodes %s", async (name, path) => {
    const actions = build({ [`DELETE ${path}`]: [200, { deleted: true }] });
    await actions.remove(name);
    expect(seen[0].url).toBe(path);
    expect(seen[0].headers["x-ciphermoth-entry"]).toBe(encodeURIComponent(name));
  });

  it("names the entry in a header on every entry request", async () => {
    const name = "x/purge";
    const base = "/passwords/x%2Fpurge";
    const actions = build({
      [`POST ${base}/restore`]: [200, {}],
      [`DELETE ${base}/purge`]: [200, {}],
      [`PATCH ${base}/favorite`]: [200, {}],
      [`GET ${base}/attachments`]: [200, []],
      [`POST ${base}/attachments`]: [200, {}],
      [`GET ${base}/attachments/7`]: [200, new Blob(["x"])],
      [`DELETE ${base}/attachments/7`]: [200, {}],
    });
    vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: () => {} });
    vi.stubGlobal("document", { createElement: () => ({ click: () => {} }) });
    await actions.restore(name);
    await actions.purge(name);
    await actions.toggleFavorite({ passwordName: name, favorite: true });
    await actions.fetchAttachments(name);
    await actions.uploadAttachment({ passwordName: name, file: new Blob(["f"]) });
    await actions.downloadAttachment({ passwordName: name, attachmentId: 7, filename: "f" });
    await actions.deleteAttachment({ passwordName: name, attachmentId: 7 });
    const entryRequests = seen.filter((config) => config.url.startsWith(base));
    expect(entryRequests).toHaveLength(7);
    for (const config of entryRequests) {
      expect(config.headers["x-ciphermoth-entry"]).toBe("x%2Fpurge");
    }
  });

  it.each([".", ".."])("refuses %s, which a browser would route to another URL", async (name) => {
    const actions = build({});
    await expect(actions.remove(name)).rejects.toThrow("rename it");
    await expect(actions.purge(name)).rejects.toThrow("rename it");
    await expect(actions.restore(name)).rejects.toThrow("rename it");
    await expect(actions.toggleFavorite({ passwordName: name, favorite: true })).rejects.toThrow(
      "rename it"
    );
    await expect(actions.fetchAttachments(name)).rejects.toThrow("rename it");
    expect(seen).toEqual([]);
  });
});

// Only imported by a dedicated QA frontend build. Runs inside the native webview.
import { invoke } from "@tauri-apps/api/core";
import api from "../api/client";
import { coreStatus, coreRequest } from "./core";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(fn) {
  for (let n = 0; n < 200; n++) {
    const result = fn();
    if (result) return result;
    await pause(100);
  }
  throw new Error("UI condition timed out");
}
function input(label, value) {
  const node = [...document.querySelectorAll("label")].find(
    (x) => x.textContent.replace(/\s*\*$/, "") === label
  );
  const field = node && document.getElementById(node.htmlFor);
  if (!field) throw new Error(`Missing field: ${label}`);
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(field, value);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}
const button = (label) =>
  [...document.querySelectorAll("button")].find((x) => x.textContent === label && !x.disabled);
const checks = [];
try {
  await until(
    () =>
      button("Create Vault") ||
      button("Unlock Vault") ||
      document.querySelector('input[type="checkbox"]')
  );
  const fresh = !!document.querySelector('input[type="checkbox"]');
  input("Master Password", "Desktop-GUI-Canary-2026!");
  if (fresh) {
    input("Confirm Master Password", "Desktop-GUI-Canary-2026!");
    document.querySelector('input[type="checkbox"]').click();
  }
  await pause(100);
  (await until(() => button(fresh ? "Create Vault" : "Unlock Vault"))).click();
  await until(() => button("Log out"));
  checks.push(fresh ? "create vault through UI" : "unlock persisted vault through UI");
  if (fresh) {
    (await until(() => button("Add First Password"))).click();
    await until(() =>
      [...document.querySelectorAll("label")].some((x) => x.textContent.startsWith("Name"))
    );
    input("Name", "Native GUI entry");
    input("Password", "Native-GUI-password-canary!");
    await pause(100);
    (await until(() => button("Create"))).click();
    await until(() => !button("Create"));
    checks.push("create password through UI");
  }
  const { data } = await api.get("/passwords");
  if (
    !data.some(
      (row) =>
        row.password_name === "Native GUI entry" &&
        row.password_value === "Native-GUI-password-canary!"
    )
  )
    throw new Error("saved entry not found");
  checks.push("retrieve password through native IPC");
  if (import.meta.env.VITE_DESKTOP_DIALOG_QA === "1" && !sessionStorage.getItem("qa-files")) {
    const { getSessionToken } = await import("../utils");
    const session = getSessionToken();
    await invoke("qa_report", { result: { stage: "backup_save" } });
    const saved = await invoke("backup_export", {
      session,
      password: "Desktop-GUI-Canary-2026!",
    });
    if (!saved.saved) throw new Error("native backup not saved");
    await invoke("qa_report", { result: { stage: "backup_open" } });
    const selected = await invoke("choose_backup");
    if (!selected?.ticket || selected.path) throw new Error("invalid native file grant");
    const restored = await invoke("backup_import", {
      session,
      password: "Desktop-GUI-Canary-2026!",
      ticket: selected.ticket,
      onConflict: "skip",
    });
    if (restored.skipped < 1) throw new Error("native backup did not restore");
    sessionStorage.setItem("qa-files", "done");
    checks.push("native backup save/open dialogs and restore");
  }
  const denied = ["plugin:shell|execute", "plugin:fs|read_file", "plugin:window|close"];
  for (const command of denied) {
    let refused = false;
    try {
      await invoke(command, {});
    } catch {
      refused = true;
    }
    if (!refused) throw new Error("capability accepted");
  }
  checks.push("ungranted capabilities refused");
  let timeout = false;
  try {
    await coreRequest({
      method: "POST",
      path: "/api/master_password/unlock",
      headers: [["content-type", "application/json"]],
      body: new TextEncoder().encode(
        JSON.stringify({ master_password: "Desktop-GUI-Canary-2026!" })
      ),
      timeoutMs: 1,
    });
  } catch (error) {
    timeout = error.code === "timeout";
  }
  if (!timeout) throw new Error("native timeout not enforced");
  checks.push("native timeout cancels real KDF request");
  await invoke("clipboard_write", { value: "Native-clipboard-canary", timeoutMs: 1000 });
  await invoke("qa_report", { result: { stage: "clipboard_timeout" } });
  await pause(1800);
  await invoke("clipboard_write", { value: "Native-clipboard-canary", timeoutMs: 1000 });
  await invoke("qa_report", { result: { stage: "clipboard_replaced" } });
  await pause(1800);
  checks.push("native clipboard command");
  await pause(1200);
  const stage = sessionStorage.getItem("qa-lock-stage");
  if (!stage) {
    sessionStorage.setItem("qa-checks", JSON.stringify(checks));
    sessionStorage.setItem("qa-fresh", JSON.stringify(fresh));
    sessionStorage.setItem("qa-lock-stage", "manual");
    button("Log out").click();
  } else if (stage === "manual") {
    sessionStorage.setItem("qa-lock-stage", "native");
    await invoke("qa_lock");
  } else {
    await invoke("qa_report", {
      result: {
        ok: true,
        fresh: JSON.parse(sessionStorage.getItem("qa-fresh")),
        checks: [
          ...JSON.parse(sessionStorage.getItem("qa-checks")),
          "manual lock then UI unlock",
          "native lock callback then UI unlock",
        ],
        core: await coreStatus(),
      },
    });
  }
} catch (error) {
  await invoke("qa_report", {
    result: {
      ok: false,
      checks,
      error: error.message,
      text: document.body.innerText.slice(0, 1500),
    },
  });
}

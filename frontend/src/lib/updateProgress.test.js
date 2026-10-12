import { describe, expect, it } from "vitest";

import { failureMessage, progressOutcome, updaterMode } from "./updateProgress";

describe("updaterMode", () => {
  it.each([
    [null, "unknown"],
    [{ updater_present: false, updater_protocol: null }, "absent"],
    [{ updater_present: true, updater_protocol: 1, updater_upgrade_required: true }, "upgrade"],
    [{ updater_present: false, updater_protocol: 2 }, "stopped"],
    [{ updater_present: true, updater_protocol: 2 }, "ready"],
  ])("%j is %s", (apply, mode) => {
    expect(updaterMode(apply)).toBe(mode);
  });
});

describe("progressOutcome with a protocol 2 updater", () => {
  const base = { requestId: "a".repeat(32), protocol: 2, boot: "1.5.1", target: "v1.5.2" };

  it("waits while the new version is still being checked", () => {
    expect(
      progressOutcome({
        ...base,
        live: "1.5.2",
        status: { state: "validating", id: base.requestId },
      })
    ).toBe("waiting");
  });

  it("waits while the backend is down", () => {
    expect(progressOutcome({ ...base, live: null, status: null })).toBe("waiting");
  });

  it("finishes only on the updater's answer", () => {
    expect(
      progressOutcome({ ...base, live: "1.5.2", status: { state: "success", id: base.requestId } })
    ).toBe("success");
  });

  it("ignores a result that belongs to another request", () => {
    expect(
      progressOutcome({ ...base, live: "1.5.1", status: { state: "failed", id: "b".repeat(32) } })
    ).toBe("waiting");
  });

  it.each(["failed", "rolled_back", "intervention"])("reports %s as a failure", (state) => {
    expect(progressOutcome({ ...base, status: { state, id: base.requestId } })).toBe("failed");
  });
});

describe("progressOutcome with an older updater", () => {
  it("treats a new running version as done", () => {
    expect(progressOutcome({ protocol: 1, boot: "1.5.0", live: "1.5.1", status: null })).toBe(
      "success"
    );
  });

  it("reports a rollback", () => {
    expect(
      progressOutcome({
        protocol: 1,
        boot: "1.5.0",
        live: "1.5.0",
        status: { state: "rolled_back" },
      })
    ).toBe("failed");
  });
});

describe("failureMessage", () => {
  it("prefers the updater's explanation", () => {
    expect(failureMessage({ state: "rolled_back", detail: "v1.5.2 failed (x)." })).toBe(
      "v1.5.2 failed (x)."
    );
  });

  it("falls back to the state's copy", () => {
    expect(failureMessage({ state: "failed" })).toMatch(/untouched/);
  });
});

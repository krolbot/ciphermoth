import { describe, expect, it } from "vitest";

import { errorDetail } from "./http";

const withData = (data) => ({ response: { status: 400, data } });

describe("errorDetail", () => {
  it("returns a string detail as is", async () => {
    await expect(errorDetail(withData({ detail: "Name taken." }), "fallback")).resolves.toBe(
      "Name taken."
    );
  });

  it("joins pydantic validation messages without the value error prefix", async () => {
    const detail = [
      { loc: ["body", "url"], msg: "String should have at most 2048 characters" },
      { loc: ["body", "totp_secret"], msg: "Value error, TOTP secret must be valid base32." },
      { loc: ["body"], msg: 42 },
    ];
    await expect(errorDetail(withData({ detail }), "fallback")).resolves.toBe(
      "String should have at most 2048 characters; TOTP secret must be valid base32."
    );
  });

  it("reads JSON error bodies delivered as Blobs", async () => {
    const blob = new Blob([JSON.stringify({ detail: "Incorrect master password." })]);
    await expect(errorDetail(withData(blob), "Backup failed.")).resolves.toBe(
      "Incorrect master password."
    );
  });

  it.each([
    ["no response", {}],
    ["an empty body", withData(undefined)],
    ["an object detail", withData({ detail: { nested: true } })],
    ["an empty list", withData({ detail: [] })],
    ["a non-JSON Blob", withData(new Blob(["Bad Gateway"]))],
  ])("falls back on %s", async (_, err) => {
    await expect(errorDetail(err, "fallback")).resolves.toBe("fallback");
  });
});

import { describe, expect, it } from "vitest";

import { isInvalidExpiry, toUtcExpiry } from "./accessExpiry";

describe("access expiry", () => {
  it("accepts blank or future values and rejects malformed or expired values", () => {
    const localMinute = (offset) => {
      const date = new Date(Date.now() + offset);
      return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
        .toISOString()
        .slice(0, 16);
    };

    expect(isInvalidExpiry("")).toBe(false);
    expect(isInvalidExpiry("not-a-date")).toBe(true);
    expect(isInvalidExpiry(localMinute(-60_000))).toBe(true);
    expect(isInvalidExpiry(localMinute(3_600_000))).toBe(false);
    expect(toUtcExpiry("")).toBeNull();
  });
});

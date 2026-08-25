import assert from "node:assert/strict";
import test from "node:test";

import { SETTINGS_DEFAULTS } from "../src/lib/settings.js";

test("vault stays unlocked for thirty minutes by default", () => {
  assert.equal(SETTINGS_DEFAULTS.inactivity_ms, 30 * 60 * 1000);
  assert.equal(SETTINGS_DEFAULTS.hidden_ms, 30 * 60 * 1000);
  assert.equal(SETTINGS_DEFAULTS.warn_before_ms, 60 * 1000);
});

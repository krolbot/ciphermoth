import assert from "node:assert/strict";
import test from "node:test";

import { SETTINGS_DEFAULTS } from "../src/lib/settings.js";

test("vault uses balanced inactivity and hidden-tab defaults", () => {
  assert.equal(SETTINGS_DEFAULTS.inactivity_ms, 15 * 60 * 1000);
  assert.equal(SETTINGS_DEFAULTS.hidden_ms, 10 * 60 * 1000);
  assert.equal(SETTINGS_DEFAULTS.warn_before_ms, 60 * 1000);
});

import assert from "node:assert/strict";
import test from "node:test";

import { planServiceAccessChanges } from "../src/lib/sharing.js";

test("service access reconciliation only applies changed grants", () => {
  const current = [
    { user_id: 1, permission: "read" },
    { user_id: 2, permission: "write" },
    { user_id: 3, permission: "read" },
  ];
  const desired = [
    { user_id: 1, permission: "read" },
    { user_id: 2, permission: "read" },
    { user_id: 3, permission: "none" },
    { user_id: 4, permission: "write" },
  ];

  assert.deepEqual(planServiceAccessChanges(current, desired), [
    { type: "set", user_id: 2, permission: "read" },
    { type: "revoke", user_id: 3, permission: "none" },
    { type: "set", user_id: 4, permission: "write" },
  ]);
});

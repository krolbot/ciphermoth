import assert from "node:assert/strict";
import test from "node:test";

import { userAdminActions } from "../src/lib/userAdmin.js";

test("user admin actions respect self and service account boundaries", () => {
  assert.deepEqual(userAdminActions({ id: 1, role: "admin" }, 1), {
    canDelete: false,
    canRequirePasswordChange: false,
    canRevokeSessions: false,
  });
  assert.deepEqual(userAdminActions({ id: 2, role: "service" }, 1), {
    canDelete: true,
    canRequirePasswordChange: false,
    canRevokeSessions: false,
  });
});

import assert from "node:assert/strict";
import test from "node:test";

import { initialFolderForEntry } from "../src/lib/entryForm.js";

test("new entries inherit the selected folder while edits preserve their folder", () => {
  assert.equal(initialFolderForEntry(null, "strike"), "strike");
  assert.equal(initialFolderForEntry({ folder: "servers" }, "strike"), "servers");
  assert.equal(initialFolderForEntry({ folder: "" }, "strike"), "");
});

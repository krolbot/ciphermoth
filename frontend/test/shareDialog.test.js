import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/components/vault/ShareDialog.jsx", import.meta.url),
  "utf8"
);

test("share dialog uses one responsive account-permission-action layout", () => {
  assert.match(source, /const ACCESS_GRID_COLUMNS/);
  assert.equal((source.match(/gridTemplateColumns: ACCESS_GRID_COLUMNS/g) || []).length, 2);
  assert.match(source, /gridColumn: \{ xs: "1 \/ -1", sm: "1" \}/);
  assert.match(source, /t\("common\.actions\.add"\)/);
  assert.doesNotMatch(source, /t\("common\.actions\.save"\)/);
});

test("password editor embeds general sharing instead of agent-only access", () => {
  const editor = readFileSync(
    new URL("../src/components/vault/PasswordFormDialog.jsx", import.meta.url),
    "utf8"
  );
  const page = readFileSync(new URL("../src/pages/PasswordsPage.jsx", import.meta.url), "utf8");
  const passwordsModel = readFileSync(
    new URL("../src/model/passwords.js", import.meta.url),
    "utf8"
  );

  assert.match(editor, /import \{ ShareAccessPanel \} from "\.\/ShareDialog"/);
  assert.match(editor, /const canManageAccess = !editTarget \|\| editTarget\.access === "owner"/);
  assert.match(editor, /canManageAccess &&/);
  assert.match(editor, /<ShareAccessPanel[\s\S]*draft[\s\S]*onChange=\{handleSharesChange\}/);
  assert.match(editor, /payload\.shares = accessDraft \?\? \[\]/);
  assert.doesNotMatch(editor, /agentAccess|agentTargets|service_access/);
  assert.doesNotMatch(page, /syncServiceAccess|service_access/);
  assert.doesNotMatch(passwordsModel, /syncServiceAccess|planServiceAccessChanges/);
});

test("create closes once and reveals the saved entry in the list", () => {
  const page = readFileSync(new URL("../src/pages/PasswordsPage.jsx", import.meta.url), "utf8");
  const passwordsModel = readFileSync(
    new URL("../src/model/passwords.js", import.meta.url),
    "utf8"
  );

  assert.match(page, /const created = await create\(password\)/);
  assert.match(page, /setRevealEntryId\(created\.id\)/);
  assert.match(page, /entry\.id === revealEntryId/);
  assert.match(page, /setPage\(Math\.floor\(index \/ PAGE_SIZE\) \+ 1\)/);
  assert.match(page, /setDialogOpen\(false\)/);
  assert.doesNotMatch(page, /setEditTarget\(created\)/);
  assert.match(passwordsModel, /return decryptPasswordRecord\(data\)/);
});

test("draft access changes are submitted with the entry instead of mutating immediately", () => {
  assert.match(source, /draft = false/);
  assert.match(source, /onChange\?\.\(next, true\)/);
  assert.match(source, /if \(draft\)/);
});

test("stale share loads cannot update a different form instance", () => {
  assert.match(source, /async \(isCurrent = \(\) => true\) =>/);
  assert.match(source, /if \(!isCurrent\(\)\) return/);
  assert.match(source, /const lifecycle = \+\+lifecycleRef\.current/);
  assert.match(source, /current && lifecycleRef\.current === lifecycle/);
  assert.match(source, /load\(\(\) => lifecycleRef\.current === lifecycle\)/);
});

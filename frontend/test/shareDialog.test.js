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
  assert.match(editor, /canManageAccess && editTarget/);
  assert.match(
    editor,
    /<ShareAccessPanel entry=\{editTarget\} active=\{open && sections\.access\} \/>/
  );
  assert.doesNotMatch(editor, /agentAccess|agentTargets|service_access/);
  assert.doesNotMatch(page, /syncServiceAccess|service_access/);
  assert.doesNotMatch(passwordsModel, /syncServiceAccess|planServiceAccessChanges/);
});

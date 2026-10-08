import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("user administration has a dedicated protected page and top-menu link", () => {
  const routes = source("../src/routes.jsx");
  const topMenu = source("../src/components/TopMenu.jsx");

  assert.equal(existsSync(new URL("../src/pages/UsersPage.jsx", import.meta.url)), true);
  assert.match(routes, /path: "\/users"/);
  assert.match(
    routes,
    /<ProtectedRoute role="admin">[\s\S]*<UsersPage \/>[\s\S]*<\/ProtectedRoute>/
  );
  assert.match(topMenu, /to="\/users"/);
  assert.doesNotMatch(topMenu, /UsersDialog/);
});

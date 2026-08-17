import assert from "node:assert/strict";
import test from "node:test";

import {
  clearAuth,
  getAuthToken,
  getAuthPrivateKey,
  getCurrentUser,
  getPrivateKey,
  getPublicKey,
  getVaultKey,
  getVaultSalt,
  isAuth,
  setAuthSession,
  shouldClearAuth,
} from "../src/utils.js";

const storage = new Map();
globalThis.sessionStorage = {
  getItem: (key) => storage.get(key) ?? null,
  removeItem: (key) => storage.delete(key),
  setItem: (key, value) => storage.set(key, value),
};

test("auth sessions retain browser-only vault keys until cleared", () => {
  const user = { id: 7, username: "moth", role: "member", active: true, must_change_password: false };

  setAuthSession({
    token: "session-token",
    vaultKey: "derived-key",
    vaultSalt: "public-salt",
    privateKey: "private-key",
    authPrivateKey: "auth-private-key",
    publicKey: "public-key",
    user,
  });

  assert.equal(isAuth(), true);
  assert.equal(getAuthToken(), "session-token");
  assert.equal(getVaultKey(), "derived-key");
  assert.equal(getVaultSalt(), "public-salt");
  assert.equal(getPrivateKey(), "private-key");
  assert.equal(getAuthPrivateKey(), "auth-private-key");
  assert.equal(getPublicKey(), "public-key");
  assert.deepEqual(getCurrentUser(), user);

  clearAuth();
  assert.equal(isAuth(), false);
  assert.equal(getAuthToken(), null);
  assert.equal(getCurrentUser(), null);
});

test("only public credential failures preserve auth state", () => {
  assert.equal(shouldClearAuth(401, "/passwords"), true);
  assert.equal(shouldClearAuth(401, "/auth/password"), true);
  assert.equal(shouldClearAuth(401, "/auth/me"), true);
  assert.equal(shouldClearAuth(403, "/passwords/1"), false);
  assert.equal(shouldClearAuth(401, "/auth/login"), false);
  assert.equal(shouldClearAuth(401, "/auth/bootstrap"), false);
});

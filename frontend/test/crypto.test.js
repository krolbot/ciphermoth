import assert from "node:assert/strict";
import test from "node:test";

import {
  decryptJson,
  decryptBytes,
  deriveVaultKey,
  encryptJson,
  encryptBytes,
  fromBase64Url,
  generateEntryKey,
  generateUserKeyMaterial,
  signAuthChallenge,
  unwrapEntryKey,
  wrapEntryKey,
} from "../src/lib/crypto.js";
import { mergePasswordUpdate } from "../src/lib/vault.js";

const vector = {
  password: "Correct-Horse_42!",
  salt: "AAECAwQFBgcICQoLDA0ODw",
  key: "DJgQIRryYnfPglnzsbK9PYICfnh1pVNyT2gXRJHJbm0=",
  privateRaw: "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA",
  entryKey: "wO0OT-Talkkuh8CR-O_7fYxDZDyCaQtxMh7HY0VJrUo=",
  wrapped:
    "AYx7xZrgPIbeSRMRXX6QMVL-bQf0DWrRR_D_9udK5th05xgRiYEN6dP6r7AeFQplbWlcreC7uOiAtEgYfOr7Fsses6nokkcgk4fxCAcSriUjegBogNcNthRk_mR5izg1APcFfNEX3mPi",
};

test("Argon2id derivation matches the backend parameters byte for byte", async () => {
  assert.equal(await deriveVaultKey(vector.password, vector.salt), vector.key);
});

test("Fernet encrypts and decrypts bytes in the browser", async () => {
  const plaintext = new TextEncoder().encode("ciphermoth interoperability");
  const token = await encryptBytes(vector.key, plaintext);

  assert.deepEqual(await decryptBytes(vector.key, token), plaintext);
});

test("browser unwraps an entry key produced by the Python backend", async () => {
  assert.equal(
    await unwrapEntryKey(vector.privateRaw, vector.wrapped, "entry-42"),
    vector.entryKey
  );
});

test("browser-generated user keys wrap and unwrap encrypted JSON", async () => {
  const material = await generateUserKeyMaterial(vector.password);
  const entryKey = generateEntryKey();
  const wrapped = await wrapEntryKey(material.publicKey, entryKey, "new-entry");
  const unwrapped = await unwrapEntryKey(material.privateKey, wrapped, "new-entry");
  const payload = { password_name: "example", username: "alice", favorite: true };

  assert.equal(unwrapped, entryKey);
  assert.deepEqual(await decryptJson(unwrapped, await encryptJson(entryKey, payload)), payload);
});

test("browser auth key signs a server challenge without exposing the master password", async () => {
  const material = await generateUserKeyMaterial(vector.password);
  const challenge = "Y2lwaGVybW90aC1jaGFsbGVuZ2U";
  const signature = await signAuthChallenge(material.authPrivateKey, challenge);
  const publicKey = await crypto.subtle.importKey(
    "raw",
    fromBase64Url(material.authPublicKey),
    "Ed25519",
    false,
    ["verify"]
  );

  assert.equal(
    await crypto.subtle.verify(
      "Ed25519",
      publicKey,
      fromBase64Url(signature),
      fromBase64Url(challenge)
    ),
    true
  );
});

test("entry updates preserve history and append the replaced password", () => {
  const current = {
    password_name: "entry",
    password_value: "old",
    password_history: [{ value: "older", changed_at: "2026-01-01T00:00:00Z" }],
    description: "keep me",
  };
  assert.deepEqual(mergePasswordUpdate(current, { password_value: "old" }), current);
  assert.deepEqual(
    mergePasswordUpdate(current, { password_value: "new" }, "2026-08-17T00:00:00Z"),
    {
      ...current,
      password_value: "new",
      password_history: [
        ...current.password_history,
        { value: "old", changed_at: "2026-08-17T00:00:00Z" },
      ],
    }
  );
  assert.deepEqual(
    mergePasswordUpdate(
      current,
      {
        password_value: "restored",
        password_history: [{ value: "from-backup", changed_at: "2025-01-01" }],
      },
      "2026-08-17T00:00:00Z",
      true
    ).password_history,
    [{ value: "from-backup", changed_at: "2025-01-01" }]
  );
  const fullHistory = Array.from({ length: 20 }, (_, index) => ({
    value: `history-${index}`,
    changed_at: "2025-01-01",
  }));
  const capped = mergePasswordUpdate(
    { ...current, password_history: fullHistory },
    { password_value: "new" },
    "2026-08-17T00:00:00Z"
  ).password_history;
  assert.equal(capped.length, 20);
  assert.equal(capped[0].value, "history-1");
  assert.equal(capped.at(-1).value, "old");
});

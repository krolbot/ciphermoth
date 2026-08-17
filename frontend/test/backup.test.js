import assert from "node:assert/strict";
import test from "node:test";

import { createBackupArchive, parsePasswordCsv, readBackupArchive } from "../src/lib/backup.js";

const password = {
  password_name: "Mail",
  kind: "login",
  username: "moth@example.com",
  password_value: "secret",
  url: "https://example.com",
  totp_secret: null,
  description: "private note",
  tags: ["personal"],
  custom_fields: [],
  folder: "Home",
  favorite: true,
  password_history: [{ value: "old", changed_at: "2026-01-01T00:00:00Z" }],
  attachments: [
    {
      filename: "proof.txt",
      content_type: "text/plain",
      blob: new Blob(["proof"], { type: "text/plain" }),
    },
  ],
};

test("AES backup archive round-trips without the backend", async () => {
  const archive = await createBackupArchive([password], "archive password");
  const restored = await readBackupArchive(archive, "archive password");

  assert.deepEqual(restored, [
    {
      ...password,
      attachments: [
        {
          filename: "proof.txt",
          content_type: "text/plain",
          data: "cHJvb2Y",
        },
      ],
    },
  ]);
  await assert.rejects(() => readBackupArchive(archive, "wrong password"));
});

test("CSV parser handles quoted commas and escaped quotes", () => {
  const [parsed] = parsePasswordCsv(
    'name,username,password,notes\r\n"Mail, personal",moth,secret,"uses ""alias"""\r\n'
  );

  assert.equal(parsed.password_name, "Mail, personal");
  assert.equal(parsed.description, 'uses "alias"');
  assert.equal(parsed.password_value, "secret");
});

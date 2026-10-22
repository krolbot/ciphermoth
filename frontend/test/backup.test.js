import assert from "node:assert/strict";
import test from "node:test";
import { BlobReader, TextWriter, ZipReader } from "@zip.js/zip.js";

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

test("migration archive keeps ownership, trash, grants, history, and attachment time", async () => {
  const source = {
    ...password,
    legacy_id: 42,
    owner_username: "owner",
    access: "owner",
    created: "2026-01-01T00:00:00Z",
    updated: "2026-02-01T00:00:00Z",
    deleted: "2026-03-01T00:00:00Z",
    shares: [{ username: "service", role: "service", permission: "write" }],
    attachments: [
      {
        ...password.attachments[0],
        created: "2026-01-02T00:00:00Z",
      },
    ],
  };
  const archive = await createBackupArchive([source], "archive password");
  const reader = new ZipReader(new BlobReader(archive));
  try {
    const [entry] = await reader.getEntries();
    const payload = JSON.parse(
      await entry.getData(new TextWriter(), { password: "archive password" })
    );
    assert.equal(payload.migration_version, 1);
    assert.deepEqual(payload.passwords, [
      {
        legacy_id: 42,
        owner_username: "owner",
        access: "owner",
        created: "2026-01-01T00:00:00Z",
        updated: "2026-02-01T00:00:00Z",
        deleted: "2026-03-01T00:00:00Z",
        name: "Mail",
        kind: "login",
        username: "moth@example.com",
        value: "secret",
        url: "https://example.com",
        totp_secret: null,
        description: "private note",
        tags: ["personal"],
        custom_fields: [],
        folder: "Home",
        favorite: true,
        password_history: [{ value: "old", changed_at: "2026-01-01T00:00:00Z" }],
        shares: [{ username: "service", role: "service", permission: "write" }],
        attachments: [
          {
            filename: "proof.txt",
            content_type: "text/plain",
            created: "2026-01-02T00:00:00Z",
            data: "cHJvb2Y",
          },
        ],
      },
    ]);
  } finally {
    await reader.close();
  }
});

test("CSV parser handles quoted commas and escaped quotes", () => {
  const [parsed] = parsePasswordCsv(
    'name,username,password,notes\r\n"Mail, personal",moth,secret,"uses ""alias"""\r\n'
  );

  assert.equal(parsed.password_name, "Mail, personal");
  assert.equal(parsed.description, 'uses "alias"');
  assert.equal(parsed.password_value, "secret");
});

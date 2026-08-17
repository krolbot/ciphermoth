import {
  BlobReader,
  BlobWriter,
  TextReader,
  TextWriter,
  ZipReader,
  ZipWriter,
} from "@zip.js/zip.js";
import { deriveVaultKey, toBase64Url } from "./crypto.js";
import { getVaultKey, getVaultSalt } from "../utils.js";

const BACKUP_ENTRY = "ciphermoth_backup.json";

export const verifyCurrentVaultPassword = async (password) =>
  (await deriveVaultKey(password, getVaultSalt())) === getVaultKey();

export const createBackupArchive = async (passwords, password) => {
  const entries = await Promise.all(
    passwords.map(async (entry) => ({
      name: entry.password_name,
      kind: entry.kind,
      username: entry.username,
      value: entry.password_value,
      url: entry.url,
      totp_secret: entry.totp_secret,
      description: entry.description,
      tags: entry.tags,
      custom_fields: entry.custom_fields,
      folder: entry.folder,
      favorite: entry.favorite,
      password_history: entry.password_history ?? [],
      attachments: await Promise.all(
        (entry.attachments ?? []).map(async (attachment) => ({
          filename: attachment.filename,
          content_type: attachment.content_type,
          data: toBase64Url(new Uint8Array(await attachment.blob.arrayBuffer())),
        }))
      ),
    }))
  );
  const payload = JSON.stringify(
    {
      exported_at: new Date().toISOString(),
      passwords: entries,
    },
    null,
    2
  );
  const writer = new ZipWriter(new BlobWriter("application/zip"), {
    password,
    encryptionStrength: 3,
  });
  await writer.add(BACKUP_ENTRY, new TextReader(payload));
  return writer.close();
};

export const readBackupArchive = async (file, password) => {
  const reader = new ZipReader(new BlobReader(file));
  try {
    const entry = (await reader.getEntries()).find(
      (candidate) => candidate.filename === BACKUP_ENTRY
    );
    if (!entry) throw new Error("Invalid CipherMoth backup.");
    const text = await entry.getData(new TextWriter(), { password });
    const parsed = JSON.parse(text);
    if (!Array.isArray(parsed.passwords)) throw new Error("Invalid CipherMoth backup.");
    return parsed.passwords.map((item) => ({
      password_name: item.name,
      kind: item.kind || "login",
      username: item.username ?? null,
      password_value: item.value,
      url: item.url ?? null,
      totp_secret: item.totp_secret ?? null,
      description: item.description ?? null,
      tags: item.tags ?? [],
      custom_fields: item.custom_fields ?? [],
      folder: item.folder ?? null,
      favorite: item.favorite ?? false,
      ...(Array.isArray(item.password_history)
        ? { password_history: item.password_history }
        : {}),
      ...(Array.isArray(item.attachments) ? { attachments: item.attachments } : {}),
    }));
  } finally {
    await reader.close();
  }
};

const parseCsvRows = (text) => {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      row.push(value);
      value = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      row.push(value);
      if (row.some(Boolean)) rows.push(row);
      row = [];
      value = "";
    } else {
      value += char;
    }
  }
  if (quoted) throw new Error("Invalid CSV quoting.");
  row.push(value);
  if (row.some(Boolean)) rows.push(row);
  return rows;
};

const aliases = {
  password_name: ["name", "title", "account", "login_name", "item name"],
  username: ["username", "login_username", "user", "email", "login", "e-mail"],
  password_value: ["password", "login_password", "pass"],
  url: ["url", "uri", "login_uri", "website", "web site", "site", "link"],
  description: ["notes", "note", "description", "comment", "comments", "extra"],
  folder: ["folder", "grouping", "group", "category", "collection"],
  totp_secret: ["totp", "login_totp", "otpauth", "otp", "2fa", "otp_auth", "totpauth"],
};

export const parsePasswordCsv = (text) => {
  const [headers, ...rows] = parseCsvRows(text);
  if (!headers) return [];
  const normalized = headers.map((header) => header.trim().toLowerCase());
  const indexFor = (field) => normalized.findIndex((header) => aliases[field].includes(header));
  const indexes = Object.fromEntries(Object.keys(aliases).map((field) => [field, indexFor(field)]));
  if (indexes.password_name < 0 || indexes.password_value < 0) {
    throw new Error("CSV must contain name and password columns.");
  }
  return rows.map((row) => {
    const field = (name) => (indexes[name] < 0 ? null : row[indexes[name]]?.trim() || null);
    return {
      password_name: field("password_name"),
      kind: "login",
      username: field("username"),
      password_value: field("password_value") || "",
      url: field("url"),
      totp_secret: field("totp_secret"),
      description: field("description"),
      tags: [],
      custom_fields: [],
      folder: field("folder"),
      favorite: false,
    };
  });
};

import {
  decryptJson,
  encryptJson,
  fromBase64Url,
  generateEntryKey,
  toBase64Url,
  unwrapEntryKey,
  wrapEntryKey,
} from "./crypto.js";
import { getPrivateKey, getPublicKey } from "../utils.js";

export const entryKeyFor = (record) => unwrapEntryKey(getPrivateKey(), record.wrapped_key, "");

export const decryptPasswordRecord = async (record) => {
  const entryKey = await entryKeyFor(record);
  const payload = await decryptJson(entryKey, record.encrypted_payload);
  const preferences = record.encrypted_preferences
    ? await decryptJson(entryKey, record.encrypted_preferences)
    : {};
  return {
    ...payload,
    favorite: preferences.favorite ?? false,
    id: record.id,
    owner_id: record.owner_id,
    owner_username: record.owner_username,
    access: record.access,
    backed_up: payload.backed_up ?? false,
    created: record.created,
    updated: record.updated,
    deleted: record.deleted,
  };
};

const splitPassword = (password) => {
  const payload = { ...password };
  for (const key of [
    "id",
    "owner_id",
    "owner_username",
    "access",
    "created",
    "updated",
    "deleted",
    "favorite",
    "attachments",
  ]) {
    delete payload[key];
  }
  return { payload, preferences: { favorite: password.favorite ?? false } };
};

export const encryptNewPassword = async (password) => {
  const entryKey = generateEntryKey();
  const { payload, preferences } = splitPassword(password);
  return {
    encrypted_payload: await encryptJson(entryKey, payload),
    wrapped_key: await wrapEntryKey(getPublicKey(), entryKey),
    encrypted_preferences: await encryptJson(entryKey, preferences),
    encrypted_attachments: await Promise.all(
      (password.attachments ?? []).map((attachment) =>
        encryptJson(entryKey, {
          filename: attachment.filename || "attachment",
          content_type: attachment.content_type || null,
          data: attachment.data,
        })
      )
    ),
  };
};

export const mergePasswordUpdate = (
  current,
  changes,
  changedAt = new Date().toISOString(),
  restoring = false
) => {
  const merged = { ...current, ...changes };
  if (
    !restoring &&
    changes.password_value !== undefined &&
    changes.password_value !== current.password_value
  ) {
    merged.password_history = [
      ...(current.password_history ?? []),
      { value: current.password_value, changed_at: changedAt },
    ].slice(-20);
  }
  return merged;
};

export const encryptUpdatedPassword = async (record, password, restoring = false) => {
  const entryKey = await entryKeyFor(record);
  const current = await decryptPasswordRecord(record);
  const merged = mergePasswordUpdate(current, password, undefined, restoring);
  const { payload, preferences } = splitPassword(merged);
  const result = { encrypted_payload: await encryptJson(entryKey, payload) };
  if (restoring) {
    result.encrypted_preferences = await encryptJson(entryKey, preferences);
    if (Array.isArray(password.attachments)) {
      result.encrypted_attachments = await Promise.all(
        password.attachments.map(
          async (attachment) => (await encryptAttachmentData(record, attachment)).encrypted_payload
        )
      );
    }
  }
  return result;
};

export const encryptPreferences = async (record, favorite) => {
  const entryKey = await entryKeyFor(record);
  return { encrypted_preferences: await encryptJson(entryKey, { favorite }) };
};

export const wrapPasswordForTarget = async (record, targetPublicKey) =>
  wrapEntryKey(targetPublicKey, await entryKeyFor(record));

export const encryptAttachmentData = async (record, attachment) => {
  const entryKey = await entryKeyFor(record);
  return {
    encrypted_payload: await encryptJson(entryKey, {
      filename: attachment.filename || "attachment",
      content_type: attachment.content_type || null,
      data: attachment.data,
    }),
  };
};

export const encryptAttachment = async (record, file) =>
  encryptAttachmentData(record, {
    filename: file.name,
    content_type: file.type,
    data: toBase64Url(new Uint8Array(await file.arrayBuffer())),
  });

export const decryptAttachment = async (record, attachment) => {
  const entryKey = await entryKeyFor(record);
  const payload = await decryptJson(entryKey, attachment.encrypted_payload);
  const data = fromBase64Url(payload.data);
  return {
    ...attachment,
    filename: payload.filename,
    content_type: payload.content_type,
    size_bytes: data.length,
    blob: new Blob([data], {
      type: payload.content_type || "application/octet-stream",
    }),
  };
};

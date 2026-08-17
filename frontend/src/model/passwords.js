import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import {
  createBackupArchive,
  parsePasswordCsv,
  readBackupArchive,
  verifyCurrentVaultPassword,
} from "../lib/backup";
import { errorDetail, triggerDownload } from "../lib/http";
import { planServiceAccessChanges } from "../lib/sharing";
import {
  decryptAttachment,
  decryptPasswordRecord,
  encryptAttachment,
  encryptNewPassword,
  encryptPreferences,
  encryptUpdatedPassword,
  wrapPasswordForTarget,
} from "../lib/vault";
import i18n from "../i18n";

const importEntries = async (entries, existingPasswords, onConflict) => {
  const existing = new Map(existingPasswords.map((entry) => [entry.password_name, entry]));
  const result = { imported: 0, skipped: 0, overwritten: 0, total: entries.length };
  for (const entry of entries) {
    if (!entry.password_name || !entry.password_value) throw new Error("Invalid password entry.");
    const current = existing.get(entry.password_name);
    if (current && onConflict === "skip") {
      result.skipped += 1;
      continue;
    }
    if (current) {
      const { data: record } = await apiClient.get(`/passwords/${current.id}`);
      await apiClient.put(
        `/passwords/${current.id}`,
        await encryptUpdatedPassword(record, entry, true)
      );
      result.overwritten += 1;
      continue;
    }
    const { data: created } = await apiClient.post("/passwords", await encryptNewPassword(entry));
    existing.set(entry.password_name, { ...entry, id: created.id });
    result.imported += 1;
  }
  return result;
};

const Passwords = {
  error: null,
  loading: false,
  passwords: [],
  trash: [],

  setError: action((state, error) => {
    state.error = error;
  }),
  setLoading: action((state, loading) => {
    state.loading = loading;
  }),
  setPasswords: action((state, passwords) => {
    state.passwords = passwords;
  }),
  setTrash: action((state, trash) => {
    state.trash = trash;
  }),

  get: thunk(async (actions) => {
    actions.setLoading(true);
    actions.setError(null);
    try {
      const { data } = await apiClient.get("/passwords");
      actions.setPasswords(await Promise.all(data.map(decryptPasswordRecord)));
    } catch (err) {
      actions.setError(await errorDetail(err, i18n.t("errors.loadPasswords")));
    } finally {
      actions.setLoading(false);
    }
  }),

  create: thunk(async (actions, payload) => {
    try {
      const { data } = await apiClient.post("/passwords", await encryptNewPassword(payload));
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.createPassword")));
    }
  }),

  update: thunk(async (actions, { passwordId, password }) => {
    try {
      const { data: record } = await apiClient.get(`/passwords/${passwordId}`);
      await apiClient.put(
        `/passwords/${passwordId}`,
        await encryptUpdatedPassword(record, password)
      );
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.updatePassword")));
    }
  }),

  remove: thunk(async (actions, passwordId) => {
    try {
      await apiClient.delete(`/passwords/${passwordId}`);
      await actions.get();
      await actions.getTrash();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.deletePassword")));
    }
  }),

  getTrash: thunk(async (actions) => {
    try {
      const { data } = await apiClient.get("/passwords/trash");
      actions.setTrash(await Promise.all(data.map(decryptPasswordRecord)));
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.loadTrash")));
    }
  }),

  restore: thunk(async (actions, passwordId) => {
    try {
      await apiClient.post(`/passwords/${passwordId}/restore`);
      await actions.get();
      await actions.getTrash();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.restorePassword")));
    }
  }),

  purge: thunk(async (actions, passwordId) => {
    try {
      await apiClient.delete(`/passwords/${passwordId}/purge`);
      await actions.getTrash();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.deletePassword")));
    }
  }),

  toggleFavorite: thunk(async (actions, { passwordId, favorite }) => {
    try {
      const { data: record } = await apiClient.get(`/passwords/${passwordId}`);
      await apiClient.patch(
        `/passwords/${passwordId}/preferences`,
        await encryptPreferences(record, favorite)
      );
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.updateFavorite")));
    }
  }),

  fetchAttachments: thunk(async (actions, passwordId) => {
    try {
      const { data } = await apiClient.get(`/passwords/${passwordId}/attachments`);
      const { data: record } = await apiClient.get(`/passwords/${passwordId}`);
      return Promise.all(data.map((attachment) => decryptAttachment(record, attachment)));
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.loadAttachments")));
    }
  }),

  uploadAttachment: thunk(async (actions, { passwordId, file }) => {
    try {
      const { data: record } = await apiClient.get(`/passwords/${passwordId}`);
      const { data } = await apiClient.post(
        `/passwords/${passwordId}/attachments`,
        await encryptAttachment(record, file)
      );
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.uploadAttachment")));
    }
  }),

  downloadAttachment: thunk(async (actions, { passwordId, attachmentId, filename }) => {
    try {
      const [{ data: record }, { data: attachment }] = await Promise.all([
        apiClient.get(`/passwords/${passwordId}`),
        apiClient.get(`/passwords/${passwordId}/attachments/${attachmentId}`),
      ]);
      const decrypted = await decryptAttachment(record, attachment);
      triggerDownload(decrypted.blob, filename || decrypted.filename || "attachment");
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.downloadAttachment")));
    }
  }),

  deleteAttachment: thunk(async (actions, { passwordId, attachmentId }) => {
    try {
      await apiClient.delete(`/passwords/${passwordId}/attachments/${attachmentId}`);
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.deleteAttachment")));
    }
  }),

  listShares: thunk(async (actions, passwordId) => {
    try {
      const { data } = await apiClient.get(`/passwords/${passwordId}/shares`);
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.loadShares")));
    }
  }),

  setShare: thunk(async (actions, { passwordId, userId, permission }) => {
    try {
      const [{ data: record }, { data: targets }] = await Promise.all([
        apiClient.get(`/passwords/${passwordId}`),
        apiClient.get("/users/share-targets"),
      ]);
      const target = targets.find((candidate) => candidate.id === userId);
      if (!target) throw new Error(i18n.t("errors.saveShare"));
      await apiClient.put(`/passwords/${passwordId}/shares/${userId}`, {
        permission,
        wrapped_key: await wrapPasswordForTarget(record, target.public_key),
      });
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.saveShare")));
    }
  }),

  revokeShare: thunk(async (actions, { passwordId, userId }) => {
    try {
      await apiClient.delete(`/passwords/${passwordId}/shares/${userId}`);
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.revokeShare")));
    }
  }),

  syncServiceAccess: thunk(async (actions, { passwordId, desired }) => {
    const current = (await actions.listShares(passwordId)).filter(
      (share) => share.role === "service"
    );
    for (const grant of planServiceAccessChanges(current, desired)) {
      if (grant.type === "revoke") {
        await actions.revokeShare({ passwordId, userId: grant.user_id });
      } else {
        await actions.setShare({
          passwordId,
          userId: grant.user_id,
          permission: grant.permission,
        });
      }
    }
  }),

  importPasswords: thunk(async (actions, { file, masterPassword, onConflict }, { getState }) => {
    try {
      const entries = await readBackupArchive(file, masterPassword);
      const data = await importEntries(entries, getState().passwords, onConflict);
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.importFailed")));
    }
  }),

  importCsv: thunk(async (actions, { file, onConflict }, { getState }) => {
    try {
      const entries = parsePasswordCsv(await file.text());
      const data = await importEntries(entries, getState().passwords, onConflict);
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.importFailed")));
    }
  }),

  backup: thunk(async (actions, masterPassword, { getState }) => {
    try {
      if (!(await verifyCurrentVaultPassword(masterPassword))) {
        throw new Error(i18n.t("errors.backupFailed"));
      }
      const passwords = await Promise.all(
        getState().passwords.map(async (password) => {
          const [{ data: record }, { data: attachments }] = await Promise.all([
            apiClient.get(`/passwords/${password.id}`),
            apiClient.get(`/passwords/${password.id}/attachments`),
          ]);
          return {
            ...password,
            attachments: await Promise.all(
              attachments.map((attachment) => decryptAttachment(record, attachment))
            ),
          };
        })
      );
      const archive = await createBackupArchive(passwords, masterPassword);
      const stamp = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
      triggerDownload(archive, `ciphermoth_backup_${stamp}.zip`);
      for (const password of passwords) {
        const { data: record } = await apiClient.get(`/passwords/${password.id}`);
        await apiClient.put(
          `/passwords/${password.id}`,
          await encryptUpdatedPassword(record, { ...password, backed_up: true })
        );
      }
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.backupFailed")));
    }
  }),
};

export default Passwords;

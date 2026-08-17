import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import { errorDetail, triggerDownload } from "../lib/http";
import i18n from "../i18n";

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
      actions.setPasswords(data);
    } catch (err) {
      actions.setError(await errorDetail(err, i18n.t("errors.loadPasswords")));
    } finally {
      actions.setLoading(false);
    }
  }),

  create: thunk(async (actions, payload) => {
    try {
      await apiClient.post("/passwords", payload);
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.createPassword")));
    }
  }),

  update: thunk(async (actions, { passwordId, password }) => {
    try {
      await apiClient.put(`/passwords/${passwordId}`, password);
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
      actions.setTrash(data);
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
      await apiClient.patch(`/passwords/${passwordId}/favorite`, {
        favorite,
      });
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.updateFavorite")));
    }
  }),

  fetchAttachments: thunk(async (actions, passwordId) => {
    try {
      const { data } = await apiClient.get(`/passwords/${passwordId}/attachments`);
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.loadAttachments")));
    }
  }),

  uploadAttachment: thunk(async (actions, { passwordId, file }) => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await apiClient.post(`/passwords/${passwordId}/attachments`, formData);
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.uploadAttachment")));
    }
  }),

  downloadAttachment: thunk(async (actions, { passwordId, attachmentId, filename }) => {
    try {
      const response = await apiClient.get(`/passwords/${passwordId}/attachments/${attachmentId}`, { responseType: "blob" }
      );
      triggerDownload(response.data, filename || "attachment");
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
      await apiClient.put(`/passwords/${passwordId}/shares/${userId}`, { permission });
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

  importPasswords: thunk(async (actions, { file, masterPassword, onConflict }) => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("master_password", masterPassword);
      formData.append("on_conflict", onConflict);
      const { data } = await apiClient.post("/passwords/import", formData);
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.importFailed")));
    }
  }),

  importCsv: thunk(async (actions, { file, onConflict }) => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("on_conflict", onConflict);
      const { data } = await apiClient.post("/passwords/import/csv", formData);
      await actions.get();
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.importFailed")));
    }
  }),

  backup: thunk(async (actions, masterPassword) => {
    try {
      const response = await apiClient.post(
        "/passwords/backup",
        { master_password: masterPassword },
        { responseType: "blob" }
      );
      const stamp = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
      triggerDownload(response.data, `ciphermoth_backup_${stamp}.zip`);
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.backupFailed")));
    }
  }),
};

export default Passwords;

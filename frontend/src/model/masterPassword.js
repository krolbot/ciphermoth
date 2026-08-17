import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import { errorDetail } from "../lib/http";
import i18n from "../i18n";
import { setAuthSession } from "../utils";

const MasterPassword = {
  initialized: null,
  legacyVault: false,
  error: null,
  loading: false,
  username: "",
  value: "",
  confirm: "",

  setInitialized: action((state, val) => {
    state.initialized = val;
  }),
  setLegacyVault: action((state, value) => {
    state.legacyVault = value;
  }),
  setUsername: action((state, value) => {
    state.username = value;
  }),
  setValue: action((state, value) => {
    state.value = value;
  }),
  setConfirm: action((state, value) => {
    state.confirm = value;
  }),
  setError: action((state, error) => {
    state.error = error;
  }),
  setLoading: action((state, loading) => {
    state.loading = loading;
  }),

  fetchStatus: thunk(async (actions) => {
    try {
      const { data } = await apiClient.get("/auth/status");
      actions.setInitialized(data.initialized);
      actions.setLegacyVault(data.legacy_vault);
    } catch {
      actions.setInitialized(true);
    }
  }),

  authenticate: thunk(async (actions, { endpoint, username, master_password }) => {
    actions.setError(null);
    actions.setLoading(true);
    try {
      const { data } = await apiClient.post(endpoint, { username, master_password });
      setAuthSession(data);
      window.location.replace("/passwords");
    } catch (err) {
      const msg =
        err.response?.status === 429
          ? i18n.t("errors.tooManyAttempts")
          : await errorDetail(err, i18n.t("errors.generic"));
      actions.setError(msg);
    } finally {
      actions.setLoading(false);
    }
  }),
};

export default MasterPassword;

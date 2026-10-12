import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import { errorDetail } from "../lib/http";
import { setSessionToken } from "../utils";

const MasterPassword = {
  initialized: null,
  error: null,
  loading: false,
  value: "",
  confirm: "",

  setInitialized: action((state, val) => {
    state.initialized = val;
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
      const { data } = await apiClient.get("/master_password/status");
      actions.setInitialized(data.initialized);
    } catch {
      actions.setInitialized(true);
    }
  }),

  unlock: thunk(async (actions, masterPasswordPayload) => {
    actions.setError(null);
    actions.setLoading(true);
    try {
      const { data } = await apiClient.post("/master_password/unlock", masterPasswordPayload);
      if (data.valid && data.session_token) {
        setSessionToken(data.session_token);
        window.location.replace("/passwords");
      } else {
        actions.setError("Invalid master password.");
      }
    } catch (err) {
      const msg =
        err.response?.status === 429
          ? "Too many attempts. Please try again in an hour."
          : await errorDetail(err, "An error occurred.");
      actions.setError(msg);
    } finally {
      actions.setLoading(false);
    }
  }),

  create: thunk(async (actions, masterPasswordPayload) => {
    actions.setError(null);
    actions.setLoading(true);
    try {
      const { data } = await apiClient.post("/master_password/create", masterPasswordPayload);
      if (!data.session_token) {
        actions.setError("The vault was created, but it could not be unlocked. Unlock it now.");
        actions.setInitialized(true);
        return;
      }
      setSessionToken(data.session_token);
      window.location.replace("/passwords");
    } catch (err) {
      actions.setError(await errorDetail(err, "An error occurred."));
    } finally {
      actions.setLoading(false);
    }
  }),
};

export default MasterPassword;

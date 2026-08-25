import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import { errorDetail } from "../lib/http";
import { SETTINGS_DEFAULTS } from "../lib/settings";
import i18n from "../i18n";

const Settings = {
  loading: false,
  error: null,
  settings: SETTINGS_DEFAULTS,

  setSettings: action((state, settings) => {
    state.settings = settings;
  }),
  setLoading: action((state, loading) => {
    state.loading = loading;
  }),
  setError: action((state, error) => {
    state.error = error;
  }),

  get: thunk(async (actions) => {
    actions.setLoading(true);
    try {
      const { data } = await apiClient.get("/settings");
      actions.setSettings(data);
    } catch {
      // the UI keeps the local defaults if settings can't be fetched.
    } finally {
      actions.setLoading(false);
    }
  }),

  update: thunk(async (actions, payload) => {
    try {
      const { data } = await apiClient.patch("/settings", payload);
      actions.setSettings(data);
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.saveSettings")));
    }
  }),
};

export default Settings;

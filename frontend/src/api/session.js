import { LOGOUT_NOTICE, clearSession, getSessionToken } from "../utils";
import apiClient, { SESSION_HEADER } from "./client";

const LOCK_TIMEOUT_MS = 3000;

export const touchSession = () =>
  apiClient
    .post("/master_password/session")
    .then(({ data }) => data)
    .catch(() => null);

export const readSession = () =>
  apiClient
    .get("/master_password/session")
    .then(({ data }) => data)
    .catch(() => null);

export const endSession = async (notice) => {
  const token = getSessionToken();
  clearSession();
  if (notice) sessionStorage.setItem(LOGOUT_NOTICE, notice);
  if (token) {
    await apiClient
      .post("/master_password/lock", null, {
        headers: { [SESSION_HEADER]: token },
        timeout: LOCK_TIMEOUT_MS,
      })
      .catch(() => undefined);
  }
  window.location.replace("/login");
};

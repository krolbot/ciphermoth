import axios from "axios";

import { LOGOUT_NOTICE, clearSession, getSessionToken, isAuth } from "../utils";

export const SESSION_ENDED = "Your vault was locked. Unlock it to continue.";
export const SESSION_HEADER = "x-ciphermoth-session";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
});

apiClient.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token && !config.headers[SESSION_HEADER]) {
    config.headers[SESSION_HEADER] = token;
  }
  return config;
});

const errorCode = async (data) => {
  if (data instanceof Blob) {
    try {
      return JSON.parse(await data.text()).code;
    } catch {
      return undefined;
    }
  }
  return data?.code;
};

const endsSession = async (response) => {
  if (!response || ![401, 403].includes(response.status)) return false;
  const code = await errorCode(response.data);
  return (
    (response.status === 401 && code === "invalid_session") ||
    (response.status === 403 && code === "invalid_key")
  );
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (isAuth() && (await endsSession(error.response))) {
      clearSession();
      sessionStorage.setItem(LOGOUT_NOTICE, SESSION_ENDED);
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

export default apiClient;

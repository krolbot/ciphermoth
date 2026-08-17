import axios from "axios";

import { clearAuth, getAuthToken, getKeyDerivation, shouldClearAuth } from "../utils";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
});

apiClient.interceptors.request.use((config) => {
  const token = getAuthToken();
  const keyDerivation = getKeyDerivation();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (keyDerivation) config.headers["x-ciphermoth-key-derivation"] = keyDerivation;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url ?? "";
    if (shouldClearAuth(error.response?.status, url)) {
      clearAuth();
      if (window.location.pathname !== "/login") window.location.replace("/login");
    }
    return Promise.reject(error);
  }
);

export default apiClient;

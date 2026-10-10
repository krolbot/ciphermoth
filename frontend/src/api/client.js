import axios from "axios";

import { getKeyDerivation, isAuth, removeKeyDerivation } from "../utils";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
});

apiClient.interceptors.request.use((config) => {
  const keyDerivation = getKeyDerivation();
  if (keyDerivation) {
    config.headers["x-ciphermoth-key-derivation"] = keyDerivation;
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

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (
      error.response?.status === 403 &&
      isAuth() &&
      (await errorCode(error.response.data)) === "invalid_key"
    ) {
      removeKeyDerivation();
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

export default apiClient;

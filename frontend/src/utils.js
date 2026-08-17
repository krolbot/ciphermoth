const KEY = "keyDerivation";
const TOKEN = "authToken";
const USER = "authUser";

export const setKeyDerivation = (value) => {
  if (value) sessionStorage.setItem(KEY, value);
};

export const setAuthSession = ({ token, key_derivation: keyDerivation, user }) => {
  sessionStorage.setItem(TOKEN, token);
  setKeyDerivation(keyDerivation);
  sessionStorage.setItem(USER, JSON.stringify(user));
};

export const getAuthToken = () => sessionStorage.getItem(TOKEN);
export const getKeyDerivation = () => sessionStorage.getItem(KEY);
export const getCurrentUser = () => {
  try {
    return JSON.parse(sessionStorage.getItem(USER));
  } catch {
    return null;
  }
};
export const isAuth = () => !!getAuthToken() && !!getKeyDerivation();
export const shouldClearAuth = (status, url = "") =>
  status === 401 && !["/auth/login", "/auth/bootstrap"].includes(url);
export const clearAuth = () => [KEY, TOKEN, USER].forEach((key) => sessionStorage.removeItem(key));
export const removeKeyDerivation = clearAuth;

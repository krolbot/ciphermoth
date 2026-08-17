const TOKEN = "authToken";
const VAULT_KEY = "vaultKey";
const PRIVATE_KEY = "privateKey";
const AUTH_PRIVATE_KEY = "authPrivateKey";
const PUBLIC_KEY = "publicKey";
const VAULT_SALT = "vaultSalt";
const USER = "authUser";

export const setAuthSession = ({
  token,
  vaultKey,
  vaultSalt,
  privateKey,
  authPrivateKey,
  publicKey,
  user,
}) => {
  sessionStorage.setItem(TOKEN, token);
  sessionStorage.setItem(VAULT_KEY, vaultKey);
  sessionStorage.setItem(PRIVATE_KEY, privateKey);
  sessionStorage.setItem(AUTH_PRIVATE_KEY, authPrivateKey);
  sessionStorage.setItem(PUBLIC_KEY, publicKey);
  sessionStorage.setItem(VAULT_SALT, vaultSalt);
  sessionStorage.setItem(USER, JSON.stringify(user));
};

export const getAuthToken = () => sessionStorage.getItem(TOKEN);
export const getVaultKey = () => sessionStorage.getItem(VAULT_KEY);
export const getPrivateKey = () => sessionStorage.getItem(PRIVATE_KEY);
export const getAuthPrivateKey = () => sessionStorage.getItem(AUTH_PRIVATE_KEY);
export const getPublicKey = () => sessionStorage.getItem(PUBLIC_KEY);
export const getVaultSalt = () => sessionStorage.getItem(VAULT_SALT);
export const getCurrentUser = () => {
  try {
    return JSON.parse(sessionStorage.getItem(USER));
  } catch {
    return null;
  }
};
export const isAuth = () =>
  !!getAuthToken() && !!getVaultKey() && !!getPrivateKey() && !!getAuthPrivateKey();
export const shouldClearAuth = (status, url = "") =>
  status === 401 && !["/auth/login", "/auth/bootstrap"].includes(url);
export const clearAuth = () =>
  [TOKEN, VAULT_KEY, PRIVATE_KEY, AUTH_PRIVATE_KEY, PUBLIC_KEY, VAULT_SALT, USER].forEach((key) =>
    sessionStorage.removeItem(key)
  );
export const removeKeyDerivation = clearAuth;

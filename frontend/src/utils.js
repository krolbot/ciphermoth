import { IS_DESKTOP } from "./platform";
let desktopSession = null;
const SESSION = "ciphermothSession";
const USER = "ciphermothUser";
const LEGACY_KEY = "keyDerivation";
export const LOGOUT_NOTICE = "logout_notice";

export const setSessionToken = (token) => {
  if (!token) return;
  if (IS_DESKTOP) desktopSession = token;
  else sessionStorage.setItem(SESSION, token);
};

export const getSessionToken = () =>
  IS_DESKTOP ? desktopSession : sessionStorage.getItem(SESSION);
export const isAuth = () => !!getSessionToken();
export const setCurrentUser = (user) => {
  if (user) sessionStorage.setItem(USER, JSON.stringify(user));
  else sessionStorage.removeItem(USER);
};
export const getCurrentUser = () => {
  try {
    return JSON.parse(sessionStorage.getItem(USER));
  } catch {
    return null;
  }
};

export const forgetLegacyKey = () => sessionStorage.removeItem(LEGACY_KEY);

export const clearSession = () => {
  desktopSession = null;
  sessionStorage.removeItem(SESSION);
  sessionStorage.removeItem(USER);
  forgetLegacyKey();
};

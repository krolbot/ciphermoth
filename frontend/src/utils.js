import { IS_DESKTOP } from "./platform";
let desktopSession = null;
const SESSION = "ciphermothSession";
const LEGACY_KEY = "keyDerivation";
export const LOGOUT_NOTICE = "logout_notice";

export const formatDuration = (ms) => {
  const secs = Math.round(ms / 1000);
  if (secs >= 60 && secs % 60 === 0) {
    const mins = secs / 60;
    return `${mins} minute${mins !== 1 ? "s" : ""}`;
  }
  return `${secs} second${secs !== 1 ? "s" : ""}`;
};

export const setSessionToken = (token) => {
  if (!token) return;
  if (IS_DESKTOP) desktopSession = token;
  else sessionStorage.setItem(SESSION, token);
};

export const getSessionToken = () =>
  IS_DESKTOP ? desktopSession : sessionStorage.getItem(SESSION);
export const isAuth = () => !!getSessionToken();

export const forgetLegacyKey = () => sessionStorage.removeItem(LEGACY_KEY);

export const clearSession = () => {
  desktopSession = null;
  sessionStorage.removeItem(SESSION);
  forgetLegacyKey();
};

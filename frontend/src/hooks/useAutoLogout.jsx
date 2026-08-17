import { useCallback, useEffect, useRef, useState } from "react";
import { useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

import apiClient from "../api/client";
import { isAuth, removeKeyDerivation } from "../utils";

const CountdownMessage = ({ seconds }) => {
  const { t } = useTranslation();
  const [remaining, setRemaining] = useState(seconds);
  useEffect(() => {
    if (remaining <= 0) return;
    const timer = setTimeout(() => setRemaining((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [remaining]);
  return t("autoLogout.countdown", { seconds: remaining });
};

const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];

const useAutoLogout = () => {
  const { enqueueSnackbar, closeSnackbar } = useSnackbar();

  const settings = useStoreState((s) => s.ciphermothModels.settings.settings);
  const inactivityMs = settings.inactivity_ms;
  const warnBeforeMs = settings.warn_before_ms;
  const hiddenMs = settings.hidden_ms;
  const debounceMs = settings.debounce_ms;

  const inactivityRef = useRef(null);
  const warnRef = useRef(null);
  const hiddenRef = useRef(null);
  const warnKeyRef = useRef(null);
  const lastResetRef = useRef(0);

  const logout = useCallback(async () => {
    clearTimeout(inactivityRef.current);
    clearTimeout(warnRef.current);
    clearTimeout(hiddenRef.current);
    if (warnKeyRef.current) closeSnackbar(warnKeyRef.current);
    try {
      await apiClient.post("/auth/logout", null, { timeout: 2000 });
    } catch {
      // Local key removal must not depend on network availability.
    } finally {
      removeKeyDerivation();
      sessionStorage.setItem("logout_notice", "autoLogout.loggedOut");
      window.location.replace("/login");
    }
  }, [closeSnackbar]);

  const reset = useCallback(() => {
    if (!isAuth()) return;

    const now = Date.now();
    if (now - lastResetRef.current < debounceMs) return;
    lastResetRef.current = now;

    clearTimeout(inactivityRef.current);
    clearTimeout(warnRef.current);

    if (warnKeyRef.current) {
      closeSnackbar(warnKeyRef.current);
      warnKeyRef.current = null;
    }

    warnRef.current = setTimeout(() => {
      warnKeyRef.current = enqueueSnackbar(
        <CountdownMessage seconds={Math.round(warnBeforeMs / 1000)} />,
        { variant: "warning", persist: true }
      );
    }, inactivityMs - warnBeforeMs);

    inactivityRef.current = setTimeout(logout, inactivityMs);
  }, [inactivityMs, warnBeforeMs, debounceMs, enqueueSnackbar, closeSnackbar, logout]);

  useEffect(() => {
    if (!isAuth()) return;
    reset();
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => {
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset));
      clearTimeout(inactivityRef.current);
      clearTimeout(warnRef.current);
      if (warnKeyRef.current) closeSnackbar(warnKeyRef.current);
    };
  }, [reset, closeSnackbar]);

  useEffect(() => {
    if (!isAuth()) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        hiddenRef.current = setTimeout(logout, hiddenMs);
      } else {
        clearTimeout(hiddenRef.current);
        if (!isAuth()) {
          logout();
        } else {
          reset();
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      clearTimeout(hiddenRef.current);
    };
  }, [logout, reset, hiddenMs]);
};

export default useAutoLogout;

import { useEffect, useState } from "react";
import { Text, Button } from "@gravity-ui/uikit";
import { listen } from "@tauri-apps/api/event";
import { useTranslation } from "react-i18next";

import { IS_DESKTOP, clearClipboard, openExternal } from "./index";
import { coreRestart, coreStatus, onCoreStatus } from "./core";
import LoadingScreen from "../components/LoadingScreen";
import { clearSession, isAuth } from "../utils";

export default function DesktopGate({ children }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!IS_DESKTOP) return undefined;
    let disposed = false;
    let generation;
    const unlisten = [];
    const locked = () => {
      clearClipboard();
      clearSession();
      window.location.replace("/login");
    };
    const update = (next) => {
      if (disposed) return;
      if (
        isAuth() &&
        (next.state !== "ready" || (generation !== undefined && next.generation !== generation))
      )
        locked();
      generation = next.generation;
      setStatus(next);
    };
    Promise.all([onCoreStatus(update), listen("vault-locked", locked)]).then((stops) => {
      if (disposed) stops.forEach((stop) => stop());
      else unlisten.push(...stops);
    });
    coreStatus().then(update);
    const click = (event) => {
      const link = event.target.closest?.("a[href]");
      if (link && /^https?:|^mailto:/i.test(link.href)) {
        event.preventDefault();
        openExternal(link.href).catch(() => {});
      }
    };
    const keydown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "l") {
        event.preventDefault();
        import("../api/session").then(({ endSession }) => endSession());
      }
    };
    document.addEventListener("click", click, true);
    document.addEventListener("keydown", keydown);
    return () => {
      disposed = true;
      unlisten.forEach((stop) => stop());
      document.removeEventListener("click", click, true);
      document.removeEventListener("keydown", keydown);
    };
  }, []);

  if (!IS_DESKTOP || status?.state === "ready") return children;
  if (status?.state === "failed")
    return (
      <main>
        <Text as="h1" variant="header-1">
          {t("desktopGate.openFailedTitle")}
        </Text>
        <Text as="p" color="secondary" wordBreak="break-word">
          {t("desktopGate.openFailedDescription")}
        </Text>
        <Button type="button" view="action" size="l" onClick={() => coreRestart()}>
          {t("common.actions.retry")}
        </Button>
      </main>
    );
  return <LoadingScreen label={t("desktopGate.opening")} />;
}

import { useEffect, useState } from "react";
import { Alert, Button, Dialog, Loader, Progress } from "@gravity-ui/uikit";
import { useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import { openExternal } from "../platform";

export default function DesktopUpdateDialog({ open, onClose }) {
  const { t } = useTranslation();
  const { current, latest, notes, canInstall, releaseUrl } = useStoreState(
    (state) => state.ciphermothModels.updates
  );
  const [busy, setBusy] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let disposed = false;
    const listeners = Promise.all([
      listen("update-progress", ({ payload }) => {
        if (!disposed)
          setProgress(
            payload.total ? Math.min(100, (payload.downloaded / payload.total) * 100) : null
          );
      }),
      listen("update-installing", () => {
        if (!disposed) setInstalling(true);
      }),
    ]);
    return () => {
      disposed = true;
      listeners.then((stops) => stops.forEach((stop) => stop()));
    };
  }, []);

  const install = async () => {
    setBusy(true);
    setError(null);
    setProgress(null);
    try {
      await invoke("update_install");
    } catch (requestError) {
      setError(String(requestError));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    try {
      await invoke("update_cancel");
    } catch (requestError) {
      setError(String(requestError));
    }
  };

  return (
    <Dialog
      aria-label={t("updateDialog.title")}
      className="cm-secondary-dialog cm-update-dialog"
      contentOverflow="auto"
      fullWidth
      hasCloseButton={!busy}
      maxWidth="s"
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !busy) onClose();
      }}
    >
      <Dialog.Header caption={t("updateDialog.title")} />
      <Dialog.Body>
        <div className="cm-update-dialog__content">
          <p className="cm-update-dialog__version-copy">
            v{current} → v{latest}
          </p>
          {notes && <p className="cm-update-dialog__notes">{notes}</p>}
          <p className="cm-secondary-copy">
            {canInstall
              ? t("desktopUpdate.installDescription")
              : t("desktopUpdate.debianDescription")}
          </p>
          {busy && (
            <div className="cm-update-dialog__progress" role="status">
              {progress === null ? <Loader size="m" /> : <Progress value={progress} />}
              <span>
                {t(installing ? "desktopUpdate.installing" : "desktopUpdate.downloading")}
              </span>
            </div>
          )}
          {error && <Alert theme="info" view="outlined" message={error} />}
          {releaseUrl && (
            <Button type="button" view="flat" onClick={() => openExternal(releaseUrl)}>
              {t("desktopUpdate.releaseNotes")}
            </Button>
          )}
        </div>
      </Dialog.Body>
      <div className="cm-secondary-dialog__footer">
        {busy ? (
          <Button type="button" view="outlined" onClick={cancel} disabled={installing}>
            {t("desktopUpdate.cancelDownload")}
          </Button>
        ) : (
          <Button type="button" view="flat" onClick={onClose}>
            {t("common.actions.later")}
          </Button>
        )}
        {canInstall && (
          <Button type="button" view="action" onClick={install} disabled={busy} loading={busy}>
            {t("desktopUpdate.downloadInstall")}
          </Button>
        )}
      </div>
    </Dialog>
  );
}

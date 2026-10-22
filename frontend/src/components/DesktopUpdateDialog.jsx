import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { openExternal } from "../platform";

export default function DesktopUpdateDialog({ open, onClose }) {
  const { t } = useTranslation();
  const { current, latest, notes, canInstall, releaseUrl } = useStoreState(
    (s) => s.ciphermothModels.updates
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
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    try {
      await invoke("update_cancel");
    } catch (err) {
      setError(String(err));
    }
  };
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t("updateDialog.title")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography>
            v{current} → v{latest}
          </Typography>
          {notes && (
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
              {notes}
            </Typography>
          )}
          <Typography variant="body2" color="text.secondary">
            {canInstall
              ? t("desktopUpdate.installDescription")
              : t("desktopUpdate.debianDescription")}
          </Typography>
          {busy && (
            <>
              <LinearProgress
                variant={progress === null ? "indeterminate" : "determinate"}
                value={progress ?? 0}
              />
              <Typography variant="body2">
                {t(installing ? "desktopUpdate.installing" : "desktopUpdate.downloading")}
              </Typography>
            </>
          )}
          {error && <Alert severity="info">{error}</Alert>}
          <Button onClick={() => openExternal(releaseUrl)}>
            {t("desktopUpdate.releaseNotes")}
          </Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        {busy ? (
          <Button onClick={cancel} disabled={installing}>
            {t("desktopUpdate.cancelDownload")}
          </Button>
        ) : (
          <Button onClick={onClose}>{t("common.actions.later")}</Button>
        )}
        {canInstall && (
          <Button variant="contained" onClick={install} disabled={busy}>
            {t("desktopUpdate.downloadInstall")}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

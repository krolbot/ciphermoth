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
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { openExternal } from "../platform";

export default function DesktopUpdateDialog({ open, onClose }) {
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
      <DialogTitle>A new moult is ready</DialogTitle>
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
              ? "Download from GitHub and verify its signature, then lock your vault and restart CipherMoth. Your local vault stays in place."
              : "This Debian installation updates through your package manager. Download the new .deb from GitHub and install it over this version. Your local vault stays in place."}
          </Typography>
          {busy && (
            <>
              <LinearProgress
                variant={progress === null ? "indeterminate" : "determinate"}
                value={progress ?? 0}
              />
              <Typography variant="body2">
                {installing ? "Installing…" : "Downloading and verifying…"}
              </Typography>
            </>
          )}
          {error && <Alert severity="info">{error}</Alert>}
          <Button onClick={() => openExternal(releaseUrl)}>Release notes and downloads</Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        {busy ? (
          <Button onClick={cancel} disabled={installing}>
            Cancel download
          </Button>
        ) : (
          <Button onClick={onClose}>Later</Button>
        )}
        {canInstall && (
          <Button variant="contained" onClick={install} disabled={busy}>
            Download and install
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

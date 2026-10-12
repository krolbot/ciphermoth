import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  Stack,
  Typography,
} from "@mui/material";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";

import { GLOW } from "../lib/brand";
import {
  DONE_STATES,
  MANUAL_UPDATE_COMMAND,
  RECREATE_UPDATER_COMMAND,
  START_UPDATER_COMMAND,
  STATE_COPY,
  failureMessage,
  progressOutcome,
  updaterMode,
} from "../lib/updateProgress";

const POLL_MS = 3000;
const TIMEOUT_MS = 10 * 60 * 1000;

const stripV = (v) => String(v ?? "").replace(/^v/, "");

const Command = ({ children }) => (
  <Box
    component="pre"
    sx={{
      m: 0,
      p: 1.5,
      borderRadius: 1,
      border: "1px solid",
      borderColor: "divider",
      bgcolor: (t) => (t.palette.mode === "dark" ? "rgba(255,255,255,0.06)" : "#141416"),
      color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#f4f4f2"),
      fontSize: 12,
      overflowX: "auto",
      whiteSpace: "pre-wrap",
    }}
  >
    {children}
  </Box>
);

const UpdateDialog = ({ open, onClose }) => {
  const { enqueueSnackbar } = useSnackbar();

  const { current, latest, releaseUrl } = useStoreState((s) => s.ciphermothModels.updates);
  const apply = useStoreState((s) => s.ciphermothModels.updates.apply);
  const { applyUpdate, fetchApplyStatus, fetchLiveVersion, checkForUpdates } = useStoreActions(
    (a) => a.ciphermothModels.updates
  );

  const [busy, setBusy] = useState(false);
  const bootVersion = useRef(null);
  const requestId = useRef(null);
  const protocol = useRef(null);

  const mode = updaterMode(apply);
  const updaterPresent = mode === "ready";

  useEffect(() => {
    if (open) fetchApplyStatus();
  }, [open, fetchApplyStatus]);

  useEffect(() => {
    if (!busy) return undefined;

    const deadline = Date.now() + TIMEOUT_MS;
    let done = false;
    const finish = (fn) => {
      if (done) return;
      done = true;
      clearInterval(id);
      fn();
    };

    const reloadDone = () =>
      finish(() => {
        enqueueSnackbar("Update complete. Reloading…", { variant: "success" });
        setTimeout(() => window.location.reload(), 1500);
      });

    const tick = async () => {
      const live = await fetchLiveVersion();
      const status = await fetchApplyStatus();
      const outcome = progressOutcome({
        status,
        requestId: requestId.current,
        live,
        boot: bootVersion.current,
        target: latest,
        protocol: protocol.current,
      });
      if (outcome === "success") {
        reloadDone();
      } else if (outcome === "failed") {
        finish(() => {
          setBusy(false);
          enqueueSnackbar(failureMessage(status), { variant: "error" });
        });
      } else if (Date.now() > deadline) {
        finish(() => {
          setBusy(false);
          checkForUpdates();
          enqueueSnackbar("Still updating in the background, refresh in a moment.", {
            variant: "info",
          });
        });
      }
    };

    const id = setInterval(tick, POLL_MS);
    tick();
    return () => {
      done = true;
      clearInterval(id);
    };
  }, [busy, fetchApplyStatus, fetchLiveVersion, latest, enqueueSnackbar, checkForUpdates]);

  const handleApply = async () => {
    bootVersion.current = stripV(current);
    protocol.current = apply?.updater_protocol ?? null;
    setBusy(true);
    try {
      const accepted = await applyUpdate(latest);
      requestId.current = accepted?.request_id ?? null;
    } catch (err) {
      setBusy(false);
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  const inProgress =
    busy || (apply?.state && !DONE_STATES.has(apply.state) && apply.state !== "idle");

  return (
    <Dialog open={open} onClose={inProgress ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>A new moult is ready</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip label={current ? `v${String(current).replace(/^v/, "")}` : "-"} size="small" />
            <Typography sx={{ color: "text.disabled" }}>→</Typography>
            <Chip
              label={latest ?? "-"}
              size="small"
              sx={{ bgcolor: GLOW, color: "#0b0b0c", fontWeight: 700 }}
            />
          </Stack>

          {releaseUrl && (
            <Link href={releaseUrl} target="_blank" rel="noopener noreferrer" variant="body2">
              Read the release notes on GitHub
            </Link>
          )}

          {inProgress ? (
            <Alert severity="info">{STATE_COPY[apply?.state] ?? "Working…"}</Alert>
          ) : apply?.state === "intervention" ? (
            <Alert severity="warning">{apply.detail ?? STATE_COPY.intervention}</Alert>
          ) : mode === "ready" ? (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              CipherMoth will verify the new images are signed by the official release, take a
              verified backup of your database, restart, and restore everything automatically if
              anything looks wrong. Your master password is never needed and your vault stays
              encrypted throughout.
            </Typography>
          ) : mode === "upgrade" ? (
            <Box>
              <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
                One-click updates need a newer updater first: the one installed here can&apos;t
                restore your database if an update goes wrong. Run this once in your CipherMoth
                folder, then come back:
              </Typography>
              <Command>{RECREATE_UPDATER_COMMAND}</Command>
            </Box>
          ) : mode === "stopped" ? (
            <Box>
              <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
                The updater isn&apos;t running. Start it from your CipherMoth folder:
              </Typography>
              <Command>{START_UPDATER_COMMAND}</Command>
            </Box>
          ) : (
            <Box>
              <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
                One-click updates aren&apos;t enabled on this instance. Update from a terminal in
                your CipherMoth folder:
              </Typography>
              <Command>{MANUAL_UPDATE_COMMAND}</Command>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={inProgress}>
          {updaterPresent ? "Later" : "Close"}
        </Button>
        {updaterPresent && (
          <Button variant="contained" onClick={handleApply} loading={inProgress}>
            Update now
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default UpdateDialog;

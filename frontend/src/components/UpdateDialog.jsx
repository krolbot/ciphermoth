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
import { useTranslation } from "react-i18next";

import { GLOW } from "../lib/brand";

const DONE = new Set(["success", "failed", "rolled_back"]);
const POLL_MS = 3000;
const TIMEOUT_MS = 6 * 60 * 1000;

const stripV = (v) => String(v ?? "").replace(/^v/, "");

const STATE_MESSAGE_KEYS = {
  requested: "updateDialog.states.requested",
  verifying: "updateDialog.states.verifying",
  applying: "updateDialog.states.applying",
  success: "updateDialog.states.success",
  failed: "updateDialog.states.failed",
  rolled_back: "updateDialog.states.rolledBack",
};

const UpdateDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();

  const { current, latest, releaseUrl } = useStoreState((s) => s.ciphermothModels.updates);
  const apply = useStoreState((s) => s.ciphermothModels.updates.apply);
  const { applyUpdate, fetchApplyStatus, fetchLiveVersion, checkForUpdates } = useStoreActions(
    (a) => a.ciphermothModels.updates
  );

  const [busy, setBusy] = useState(false);
  const bootVersion = useRef(null);

  const updaterPresent = apply?.updater_present;

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
        enqueueSnackbar(t("updateDialog.complete"), { variant: "success" });
        setTimeout(() => window.location.reload(), 1500);
      });

    const tick = async () => {
      const live = stripV(await fetchLiveVersion());
      const boot = bootVersion.current;
      const target = stripV(latest);
      if (live && ((boot && live !== boot) || (target && live === target))) {
        reloadDone();
        return;
      }

      const status = await fetchApplyStatus();
      const state = status?.state;
      if (state && DONE.has(state)) {
        if (state === "success") {
          reloadDone();
        } else {
          finish(() => {
            setBusy(false);
            enqueueSnackbar(t(STATE_MESSAGE_KEYS[state]), { variant: "error" });
          });
        }
      } else if (Date.now() > deadline) {
        finish(() => {
          setBusy(false);
          checkForUpdates();
          enqueueSnackbar(t("updateDialog.background"), {
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
  }, [busy, fetchApplyStatus, fetchLiveVersion, latest, enqueueSnackbar, checkForUpdates, t]);

  const handleApply = async () => {
    bootVersion.current = stripV(current);
    setBusy(true);
    try {
      await applyUpdate(latest);
    } catch (err) {
      setBusy(false);
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  const inProgress = busy || (apply?.state && !DONE.has(apply.state) && apply.state !== "idle");

  const manualCommand =
    "docker compose -f docker-compose.prod.yml pull && \\\n" +
    "docker compose -f docker-compose.prod.yml up -d";

  return (
    <Dialog open={open} onClose={inProgress ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t("updateDialog.title")}</DialogTitle>
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
              {t("updateDialog.releaseNotes")}
            </Link>
          )}

          {inProgress ? (
            <Alert severity="info">
              {STATE_MESSAGE_KEYS[apply?.state]
                ? t(STATE_MESSAGE_KEYS[apply.state])
                : t("common.labels.working")}
            </Alert>
          ) : updaterPresent ? (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {t("updateDialog.automaticDescription")}
            </Typography>
          ) : (
            <Box>
              <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
                {t("updateDialog.manualDescription")}
              </Typography>
              <Box
                component="pre"
                sx={{
                  m: 0,
                  p: 1.5,
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "divider",
                  bgcolor: (t) =>
                    t.palette.mode === "dark" ? "rgba(255,255,255,0.06)" : "#141416",
                  color: (t) => (t.palette.mode === "dark" ? t.palette.text.primary : "#f4f4f2"),
                  fontSize: 12,
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                }}
              >
                {manualCommand}
              </Box>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={inProgress}>
          {t(updaterPresent ? "common.actions.later" : "common.actions.close")}
        </Button>
        {updaterPresent && (
          <Button variant="contained" onClick={handleApply} loading={inProgress}>
            {t("updateDialog.updateNow")}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default UpdateDialog;

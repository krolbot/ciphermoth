import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

const toUtc = (value) => (value ? new Date(value).toISOString() : null);
const toLocalInput = (value) => {
  if (!value) return "";
  const parsed = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const ShareDialog = ({ entry, open, onClose }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const { listShares, setShare, revokeShare } = useStoreActions(
    (actions) => actions.ciphermothModels.passwords
  );
  const shareTargets = useStoreActions((actions) => actions.ciphermothModels.users.shareTargets);
  const [shares, setShares] = useState([]);
  const [targets, setTargets] = useState([]);
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState("read");
  const [expiresAt, setExpiresAt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!entry) return;
    const [nextShares, nextTargets] = await Promise.all([listShares(entry.id), shareTargets()]);
    setShares(nextShares);
    setTargets(nextTargets);
  }, [entry, listShares, shareTargets]);

  useEffect(() => {
    if (!open) return;
    setTargetId("");
    setPermission("read");
    setExpiresAt("");
    setError("");
    load().catch((err) => setError(err.message));
  }, [open, load]);

  const run = async (operation) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      await load();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!targetId) return;
    if (
      await run(() =>
        setShare({
          entryId: entry.id,
          userId: targetId,
          permission,
          expiresAt: toUtc(expiresAt),
        })
      )
    ) {
      setTargetId("");
      setExpiresAt("");
    }
  };

  const available = targets.filter(
    (target) => !shares.some((share) => share.user_id === target.id)
  );

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      fullScreen={fullScreen}
      slotProps={{
        paper: {
          sx: {
            "& .MuiButton-root": { minHeight: { xs: 44, sm: 36 } },
            "& .MuiInputBase-root": { minHeight: { xs: 44, sm: "initial" } },
          },
        },
      }}
    >
      <DialogTitle component="div">
        <Typography component="h2" variant="h6">
          {t("sharing.manage")}
        </Typography>
        <Typography component="p" variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {entry?.password_name}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={3}>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack spacing={1}>
            <Typography variant="subtitle2">{t("sharing.currentAccess")}</Typography>
            {shares.length === 0 ? (
              <Typography color="text.secondary">{t("sharing.ownerOnly")}</Typography>
            ) : (
              shares.map((share) => (
                <Paper
                  key={share.user_id}
                  variant="outlined"
                  sx={{
                    p: 1.5,
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", sm: "minmax(0, 1fr) 150px auto" },
                    gap: 1.25,
                    alignItems: "center",
                  }}
                >
                  <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                    <Typography sx={{ fontWeight: 650, overflowWrap: "anywhere" }}>
                      {share.username}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t(`users.roles.${share.role}`)}
                    </Typography>
                  </Stack>
                  <Select
                    size="small"
                    value={share.permission}
                    disabled={busy}
                    inputProps={{ "aria-label": t("sharing.permission") }}
                    onChange={(event) =>
                      run(() =>
                        setShare({
                          entryId: entry.id,
                          userId: share.user_id,
                          permission: event.target.value,
                          expiresAt: toUtc(toLocalInput(share.expires_at)),
                        })
                      )
                    }
                  >
                    <MenuItem value="read">{t("sharing.read")}</MenuItem>
                    <MenuItem value="write">{t("sharing.readWrite")}</MenuItem>
                  </Select>
                  <Button
                    color="error"
                    variant="outlined"
                    disabled={busy}
                    onClick={() =>
                      run(() => revokeShare({ entryId: entry.id, userId: share.user_id }))
                    }
                  >
                    {t("sharing.revoke")}
                  </Button>
                </Paper>
              ))
            )}
          </Stack>

          <Stack spacing={1}>
            <Typography variant="subtitle2">{t("sharing.grantAccess")}</Typography>
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                display: "grid",
                gridTemplateColumns: {
                  xs: "1fr",
                  sm: "minmax(0, 1fr) 150px 190px auto",
                },
                gap: 1.25,
              }}
            >
              <Select
                size="small"
                displayEmpty
                value={targetId}
                disabled={busy || available.length === 0}
                inputProps={{ "aria-label": t("sharing.user") }}
                onChange={(event) => setTargetId(event.target.value)}
              >
                <MenuItem value="" disabled>
                  {t("sharing.selectTarget")}
                </MenuItem>
                {available.map((target) => (
                  <MenuItem key={target.id} value={target.id}>
                    {target.username} · {t(`users.roles.${target.role}`)}
                  </MenuItem>
                ))}
              </Select>
              <Select
                size="small"
                value={permission}
                disabled={busy}
                inputProps={{ "aria-label": t("sharing.permission") }}
                onChange={(event) => setPermission(event.target.value)}
              >
                <MenuItem value="read">{t("sharing.read")}</MenuItem>
                <MenuItem value="write">{t("sharing.readWrite")}</MenuItem>
              </Select>
              <TextField
                size="small"
                type="datetime-local"
                label={t("folderAccess.expiresAt")}
                helperText={t("folderAccess.expiresHint")}
                value={expiresAt}
                disabled={busy}
                onChange={(event) => setExpiresAt(event.target.value)}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { min: toLocalInput(new Date().toISOString()) },
                }}
              />
              <Button variant="contained" disabled={busy || !targetId} onClick={add}>
                {t("sharing.grant")}
              </Button>
            </Paper>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          {t("common.actions.close")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ShareDialog;

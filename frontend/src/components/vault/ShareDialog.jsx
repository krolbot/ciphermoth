import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

const ShareDialog = ({ entry, open, onClose }) => {
  const { t } = useTranslation();
  const { listShares, setShare, revokeShare } = useStoreActions(
    (a) => a.ciphermothModels.passwords
  );
  const shareTargets = useStoreActions((a) => a.ciphermothModels.users.shareTargets);
  const [shares, setShares] = useState([]);
  const [targets, setTargets] = useState([]);
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState("read");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!entry) return;
    try {
      const [nextShares, nextTargets] = await Promise.all([listShares(entry.id), shareTargets()]);
      setShares(nextShares);
      setTargets(nextTargets);
    } catch (err) {
      setError(err.message);
    }
  }, [entry, listShares, shareTargets]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const save = async () => {
    if (!targetId) return;
    try {
      await setShare({ passwordId: entry.id, userId: targetId, permission });
      setTargetId("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const revoke = async (userId) => {
    try {
      await revokeShare({ passwordId: entry.id, userId });
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const changePermission = async (userId, nextPermission) => {
    try {
      await setShare({ passwordId: entry.id, userId, permission: nextPermission });
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const available = targets.filter(
    (target) => !shares.some((share) => share.user_id === target.id)
  );

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t("sharing.title", { name: entry?.password_name })}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.5}>
          {shares.length === 0 ? (
            <Typography color="text.secondary">{t("sharing.empty")}</Typography>
          ) : (
            shares.map((share) => (
              <Stack key={share.user_id} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <Typography sx={{ flex: 1 }}>{share.username}</Typography>
                <TextField
                  select
                  size="small"
                  value={share.permission}
                  onChange={(e) => changePermission(share.user_id, e.target.value)}
                  sx={{ width: 130 }}
                >
                  <MenuItem value="read">{t("sharing.read")}</MenuItem>
                  <MenuItem value="write">{t("sharing.write")}</MenuItem>
                </TextField>
                <Button size="small" color="error" onClick={() => revoke(share.user_id)}>
                  {t("sharing.revoke")}
                </Button>
              </Stack>
            ))
          )}
          <Stack direction="row" spacing={1}>
            <TextField
              select
              size="small"
              label={t("sharing.user")}
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              sx={{ flex: 1 }}
            >
              {available.map((target) => (
                <MenuItem key={target.id} value={target.id}>
                  {target.username} · {t(`users.roles.${target.role}`)}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label={t("sharing.permission")}
              value={permission}
              onChange={(e) => setPermission(e.target.value)}
              sx={{ width: 130 }}
            >
              <MenuItem value="read">{t("sharing.read")}</MenuItem>
              <MenuItem value="write">{t("sharing.write")}</MenuItem>
            </TextField>
            <Button variant="contained" disabled={!targetId} onClick={save}>
              {t("common.actions.save")}
            </Button>
          </Stack>
          {error && <Typography color="error">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("common.actions.close")}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default ShareDialog;

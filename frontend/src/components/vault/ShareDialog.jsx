import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

const ShareDialog = ({ entry, open, onClose }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
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
      setError("");
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
      setError("");
      await setShare({ passwordId: entry.id, userId: targetId, permission });
      setTargetId("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const revoke = async (userId) => {
    try {
      setError("");
      await revokeShare({ passwordId: entry.id, userId });
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const changePermission = async (userId, nextPermission) => {
    try {
      setError("");
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
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth fullScreen={fullScreen}>
      <DialogTitle sx={{ pb: 1.5 }}>
        <Typography component="span" variant="h6" sx={{ display: "block" }}>
          {t("sharing.manage")}
        </Typography>
        <Typography
          component="span"
          variant="body2"
          sx={{
            display: "block",
            color: "text.secondary",
            mt: 0.5,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {entry?.password_name}
        </Typography>
      </DialogTitle>
      <DialogContent dividers sx={{ px: { xs: 2, sm: 3 }, py: 2 }}>
        <Stack spacing={2.5}>
          <Stack spacing={1}>
            <Typography variant="subtitle2">{t("sharing.currentAccess")}</Typography>
            {shares.length === 0 ? (
              <Typography color="text.secondary">{t("sharing.empty")}</Typography>
            ) : (
              shares.map((share) => (
                <Paper key={share.user_id} variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    sx={{ alignItems: { xs: "stretch", sm: "center" } }}
                  >
                    <Typography sx={{ flex: 1, minWidth: 0 }} noWrap>
                      {share.username} · {t(`users.roles.${share.role}`)}
                    </Typography>
                    <TextField
                      select
                      size="small"
                      label={t("sharing.permission")}
                      value={share.permission}
                      onChange={(event) => changePermission(share.user_id, event.target.value)}
                      sx={{ width: { xs: "100%", sm: 150 }, flexShrink: 0 }}
                    >
                      <MenuItem value="read">{t("sharing.read")}</MenuItem>
                      <MenuItem value="write">{t("sharing.write")}</MenuItem>
                    </TextField>
                    <Button
                      size="small"
                      color="error"
                      onClick={() => revoke(share.user_id)}
                      sx={{ minHeight: 40 }}
                    >
                      {t("sharing.revoke")}
                    </Button>
                  </Stack>
                </Paper>
              ))
            )}
          </Stack>

          <Stack spacing={1.25}>
            <Typography variant="subtitle2">{t("sharing.addAccess")}</Typography>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={1}
              sx={{ alignItems: "stretch" }}
            >
              <TextField
                select
                fullWidth
                size="small"
                label={t("sharing.user")}
                value={targetId}
                onChange={(event) => setTargetId(event.target.value)}
                disabled={available.length === 0}
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
                onChange={(event) => setPermission(event.target.value)}
                sx={{ width: { xs: "100%", sm: 150 }, flexShrink: 0 }}
              >
                <MenuItem value="read">{t("sharing.read")}</MenuItem>
                <MenuItem value="write">{t("sharing.write")}</MenuItem>
              </TextField>
              <Button
                variant="contained"
                disabled={!targetId}
                onClick={save}
                sx={{ minHeight: 40, width: { xs: "100%", sm: "auto" } }}
              >
                {t("common.actions.save")}
              </Button>
            </Stack>
            {available.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                {t("sharing.noAvailableTargets")}
              </Typography>
            )}
          </Stack>

          {error && <Typography color="error">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: { xs: 2, sm: 3 }, py: 1.5 }}>
        <Button onClick={onClose} sx={{ minHeight: 40 }}>
          {t("common.actions.close")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ShareDialog;

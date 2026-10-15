import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

const ACCESS_GRID_COLUMNS = {
  xs: "minmax(0, 1fr)",
  sm: "minmax(0, 1fr) 160px 128px",
};
const SELECT_SX = { minHeight: { xs: 44, sm: 40 } };

export const ShareAccessPanel = ({ entry, active = true, draft = false, onChange }) => {
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
  const lifecycleRef = useRef(0);

  const load = useCallback(
    async (isCurrent = () => true) => {
      if (!isCurrent()) return;
      try {
        setError("");
        const [nextShares, nextTargets] = await Promise.all([
          entry ? listShares(entry.id) : Promise.resolve([]),
          shareTargets(),
        ]);
        if (!isCurrent()) return;
        const sharesWithKeys = nextShares.map((share) => ({
          ...share,
          public_key:
            share.public_key ??
            nextTargets.find((target) => target.id === share.user_id)?.public_key,
        }));
        setShares(sharesWithKeys);
        setTargets(nextTargets);
        if (draft) onChange?.(sharesWithKeys, false);
      } catch (err) {
        if (isCurrent()) setError(err.message);
      }
    },
    [draft, entry, listShares, onChange, shareTargets]
  );

  useEffect(() => {
    const lifecycle = ++lifecycleRef.current;
    if (!active) return;
    let current = true;
    setTargetId("");
    load(() => current && lifecycleRef.current === lifecycle);
    return () => {
      current = false;
      if (lifecycleRef.current === lifecycle) lifecycleRef.current += 1;
    };
  }, [active, entry, load]);

  const setDraftShares = (next) => {
    setShares(next);
    onChange?.(next, true);
  };

  const save = async () => {
    if (!targetId) return;
    if (draft) {
      const target = targets.find((candidate) => candidate.id === targetId);
      if (!target) return;
      setDraftShares([
        ...shares,
        {
          user_id: target.id,
          username: target.username,
          role: target.role,
          public_key: target.public_key,
          permission,
        },
      ]);
      setTargetId("");
      return;
    }
    const lifecycle = lifecycleRef.current;
    try {
      setError("");
      await setShare({ passwordId: entry.id, userId: targetId, permission });
      setTargetId("");
      await load(() => lifecycleRef.current === lifecycle);
    } catch (err) {
      if (lifecycleRef.current === lifecycle) setError(err.message);
    }
  };

  const revoke = async (userId) => {
    if (draft) {
      setDraftShares(shares.filter((share) => share.user_id !== userId));
      return;
    }
    const lifecycle = lifecycleRef.current;
    try {
      setError("");
      await revokeShare({ passwordId: entry.id, userId });
      await load(() => lifecycleRef.current === lifecycle);
    } catch (err) {
      if (lifecycleRef.current === lifecycle) setError(err.message);
    }
  };

  const changePermission = async (userId, nextPermission) => {
    if (draft) {
      setDraftShares(
        shares.map((share) =>
          share.user_id === userId ? { ...share, permission: nextPermission } : share
        )
      );
      return;
    }
    const lifecycle = lifecycleRef.current;
    try {
      setError("");
      await setShare({ passwordId: entry.id, userId, permission: nextPermission });
      await load(() => lifecycleRef.current === lifecycle);
    } catch (err) {
      if (lifecycleRef.current === lifecycle) setError(err.message);
    }
  };

  const available = targets.filter(
    (target) => !shares.some((share) => share.user_id === target.id)
  );

  return (
    <Stack spacing={3}>
      {draft && (
        <Typography variant="body2" color="text.secondary">
          {t("sharing.savedWithEntry")}
        </Typography>
      )}
      <Stack spacing={1}>
        <Typography variant="subtitle2">{t("sharing.currentAccess")}</Typography>
        {shares.length === 0 ? (
          <Typography color="text.secondary">{t("sharing.empty")}</Typography>
        ) : (
          shares.map((share) => (
            <Paper
              key={share.user_id}
              variant="outlined"
              sx={{
                display: "grid",
                gridTemplateColumns: ACCESS_GRID_COLUMNS,
                gap: 1.25,
                alignItems: "end",
                p: 1.5,
                borderRadius: 2,
              }}
            >
              <Stack spacing={0.25} sx={{ minWidth: 0, gridColumn: { xs: "1 / -1", sm: "1" } }}>
                <Typography variant="caption" color="text.secondary">
                  {t("sharing.user")}
                </Typography>
                <Typography sx={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                  {share.username}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t("users.columns.role")}: {t(`users.roles.${share.role}`)}
                </Typography>
              </Stack>
              <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                <Typography variant="caption" color="text.secondary">
                  {t("sharing.permission")}
                </Typography>
                <Select
                  size="small"
                  value={share.permission}
                  onChange={(event) => changePermission(share.user_id, event.target.value)}
                  inputProps={{ "aria-label": t("sharing.permission") }}
                  sx={SELECT_SX}
                  fullWidth
                >
                  <MenuItem value="read">{t("sharing.read")}</MenuItem>
                  <MenuItem value="write">{t("sharing.write")}</MenuItem>
                </Select>
              </Stack>
              <Button
                type="button"
                size="small"
                color="error"
                variant="outlined"
                onClick={() => revoke(share.user_id)}
                sx={{
                  width: { xs: "auto", sm: "100%" },
                  minWidth: 96,
                  justifySelf: "end",
                  minHeight: 40,
                  color: "error.main",
                  borderColor: "error.main",
                  "&:hover": { borderColor: "error.main" },
                }}
              >
                {t("sharing.revoke")}
              </Button>
            </Paper>
          ))
        )}
      </Stack>

      <Stack spacing={1}>
        <Typography variant="subtitle2">{t("sharing.addAccess")}</Typography>
        <Paper
          variant="outlined"
          sx={{
            display: "grid",
            gridTemplateColumns: ACCESS_GRID_COLUMNS,
            gap: 1.25,
            alignItems: "end",
            p: 1.5,
            borderRadius: 2,
          }}
        >
          <Stack spacing={0.5} sx={{ minWidth: 0, gridColumn: { xs: "1 / -1", sm: "1" } }}>
            <Typography variant="caption" color="text.secondary">
              {t("sharing.user")}
            </Typography>
            <Select
              fullWidth
              size="small"
              displayEmpty
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
              disabled={available.length === 0}
              inputProps={{ "aria-label": t("sharing.user") }}
              sx={SELECT_SX}
            >
              <MenuItem value="" disabled>
                {t("sharing.selectUser")}
              </MenuItem>
              {available.map((target) => (
                <MenuItem key={target.id} value={target.id}>
                  {target.username} · {t(`users.roles.${target.role}`)}
                </MenuItem>
              ))}
            </Select>
          </Stack>
          <Stack spacing={0.5} sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">
              {t("sharing.permission")}
            </Typography>
            <Select
              size="small"
              value={permission}
              onChange={(event) => setPermission(event.target.value)}
              inputProps={{ "aria-label": t("sharing.permission") }}
              sx={SELECT_SX}
              fullWidth
            >
              <MenuItem value="read">{t("sharing.read")}</MenuItem>
              <MenuItem value="write">{t("sharing.write")}</MenuItem>
            </Select>
          </Stack>
          <Button
            type="button"
            variant="contained"
            disabled={!targetId}
            onClick={save}
            sx={{
              width: { xs: "auto", sm: "100%" },
              minWidth: 96,
              justifySelf: "end",
              minHeight: 40,
              "&.Mui-disabled": {
                color: "text.secondary",
                backgroundColor: "action.disabledBackground",
              },
            }}
          >
            {t("common.actions.add")}
          </Button>
        </Paper>
        {available.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            {t("sharing.noAvailableTargets")}
          </Typography>
        )}
      </Stack>

      {error && <Typography color="error">{error}</Typography>}
    </Stack>
  );
};

const ShareDialog = ({ entry, open, onClose }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      fullScreen={fullScreen}
      slotProps={{ paper: { sx: { borderRadius: { xs: 0, sm: "14px" } } } }}
    >
      <DialogTitle sx={{ px: { xs: 2, sm: 3 }, pt: { xs: 2, sm: 2.5 }, pb: 1.5 }}>
        <Typography component="span" variant="h6" sx={{ display: "block" }}>
          {t("sharing.manage")}
        </Typography>
        <Typography
          component="span"
          variant="body2"
          sx={{
            display: "block",
            color: "text.primary",
            opacity: 0.72,
            mt: 0.5,
            overflowWrap: "anywhere",
          }}
        >
          {entry?.password_name}
        </Typography>
      </DialogTitle>
      <DialogContent dividers sx={{ px: { xs: 2, sm: 3 }, py: 2.5 }}>
        <ShareAccessPanel entry={entry} active={open} />
      </DialogContent>
      <DialogActions sx={{ px: { xs: 2, sm: 3 }, py: 1.25 }}>
        <Button onClick={onClose} sx={{ minHeight: 40, color: "text.primary" }}>
          {t("common.actions.close")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ShareDialog;

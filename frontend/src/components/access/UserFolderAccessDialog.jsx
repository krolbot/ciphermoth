import { useCallback, useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
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
  useTheme,
} from "@mui/material";
import { useStoreActions } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

const asUtc = (value) => (value ? new Date(value).toISOString() : null);
const asLocalInput = (value) => {
  if (!value) return "";
  const parsed = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const AccessRow = ({ item, busy, onSave, onRevoke }) => {
  const { t } = useTranslation();
  const [permission, setPermission] = useState(item.direct_permission ?? "read");
  const [expiresAt, setExpiresAt] = useState(asLocalInput(item.direct_expires_at));
  const owned = item.folder.owner_id === item.userId;

  useEffect(() => {
    setPermission(item.direct_permission ?? "read");
    setExpiresAt(asLocalInput(item.direct_expires_at));
  }, [item.direct_expires_at, item.direct_permission]);

  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
      <Stack spacing={1.25}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontWeight: 650, overflowWrap: "anywhere" }}>
              {item.folder.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t("folderAccess.ownerLabel", { owner: item.folder.owner_username })}
            </Typography>
          </Box>
          <Chip
            size="small"
            label={t(
              item.effective_permission
                ? `folderAccess.permissions.${item.effective_permission}`
                : "folderAccess.permissions.none"
            )}
            color={item.effective_permission ? "primary" : "default"}
            variant="outlined"
          />
        </Stack>

        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
          {item.sources.map((source, index) => (
            <Chip
              key={`${source.source}-${source.source_id}-${index}`}
              size="small"
              variant="outlined"
              color={source.expired ? "default" : "success"}
              label={t("folderAccess.source", {
                source: t(`folderAccess.sources.${source.source}`),
                name: source.name || "",
                permission: t(`folderAccess.permissions.${source.permission}`),
              })}
            />
          ))}
        </Stack>

        {owned ? (
          <Typography variant="body2" color="text.secondary">
            {t("folderAccess.ownerCannotChange")}
          </Typography>
        ) : (
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", sm: "140px minmax(180px, 1fr) auto auto" },
              gap: 1,
              alignItems: "center",
            }}
          >
            <TextField
              select
              size="small"
              label={t("sharing.permission")}
              value={permission}
              disabled={busy}
              onChange={(event) => setPermission(event.target.value)}
            >
              <MenuItem value="read">{t("sharing.read")}</MenuItem>
              <MenuItem value="write">{t("sharing.readWrite")}</MenuItem>
            </TextField>
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
                htmlInput: { min: asLocalInput(new Date().toISOString()) },
              }}
            />
            <Button
              variant="contained"
              disabled={busy}
              onClick={() => onSave(item.folder.id, permission, asUtc(expiresAt))}
            >
              {t("common.actions.save")}
            </Button>
            <Button
              color="error"
              variant="outlined"
              disabled={busy || !item.direct_permission}
              onClick={() => onRevoke(item.folder.id)}
            >
              {t("sharing.revoke")}
            </Button>
          </Box>
        )}
      </Stack>
    </Paper>
  );
};

const UserFolderAccessDialog = ({ open, user, onClose }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const { enqueueSnackbar } = useSnackbar();
  const { userFolderAccess, setFolderGrant, revokeFolderGrant } = useStoreActions(
    (actions) => actions.ciphermothModels.access
  );
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    setItems(await userFolderAccess(user.id));
  }, [user, userFolderAccess]);

  useEffect(() => {
    if (!open) return;
    load().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, load, enqueueSnackbar]);

  const run = async (operation, message) => {
    setBusy(true);
    try {
      await operation();
      await load();
      enqueueSnackbar(message, { variant: "success" });
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth="md"
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
      <DialogTitle>{t("folderAccess.userTitle", { username: user?.username })}</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t("folderAccess.userDescription")}
        </Typography>
        <Stack spacing={1.25}>
          {items.length === 0 ? (
            <Typography color="text.secondary">{t("folderAccess.empty")}</Typography>
          ) : (
            items.map((item) => (
              <AccessRow
                key={item.folder.id}
                item={{ ...item, userId: user?.id }}
                busy={busy}
                onSave={(folderId, permission, expiresAt) =>
                  run(
                    () =>
                      setFolderGrant({
                        folderId,
                        targetType: "user",
                        targetId: user.id,
                        permission,
                        expiresAt,
                      }),
                    t("folderAccess.saved")
                  )
                }
                onRevoke={(folderId) =>
                  run(
                    () =>
                      revokeFolderGrant({
                        folderId,
                        targetType: "user",
                        targetId: user.id,
                      }),
                    t("folderAccess.revoked")
                  )
                }
              />
            ))
          )}
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

export default UserFolderAccessDialog;

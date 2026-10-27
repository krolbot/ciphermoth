import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

import { getCurrentUser } from "../../utils";

const toUtc = (value) => (value ? new Date(value).toISOString() : null);
const eventDate = (value, language) => {
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(iso).toLocaleString(language);
};
const toLocalInput = (value) => {
  if (!value) return "";
  const parsed = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const GrantRow = ({ grant, busy, onSave, onRevoke }) => {
  const { t } = useTranslation();
  const [permission, setPermission] = useState(grant.permission);
  const [expiresAt, setExpiresAt] = useState(toLocalInput(grant.expires_at));

  useEffect(() => {
    setPermission(grant.permission);
    setExpiresAt(toLocalInput(grant.expires_at));
  }, [grant.expires_at, grant.permission]);

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.25,
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "minmax(140px, 1fr) 130px 190px auto auto" },
        gap: 1,
        alignItems: "center",
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ fontWeight: 650, overflowWrap: "anywhere" }}>
          {grant.target_name}
        </Typography>
        <Stack direction="row" spacing={0.75} sx={{ mt: 0.5 }}>
          <Chip size="small" label={t(`folderAccess.targetTypes.${grant.target_type}`)} />
          {grant.expired && <Chip size="small" color="warning" label={t("folderAccess.expired")} />}
        </Stack>
      </Box>
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
          htmlInput: { min: toLocalInput(new Date().toISOString()) },
        }}
      />
      <Button
        variant="outlined"
        disabled={busy}
        onClick={() => onSave(permission, toUtc(expiresAt))}
      >
        {t("common.actions.save")}
      </Button>
      <Button color="error" disabled={busy} onClick={onRevoke}>
        {t("sharing.revoke")}
      </Button>
    </Paper>
  );
};

const FolderAccessDialog = ({ open, onClose }) => {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const { enqueueSnackbar } = useSnackbar();
  const folders = useStoreState((state) => state.ciphermothModels.access.folders);
  const groups = useStoreState((state) => state.ciphermothModels.access.groups);
  const {
    getFolders,
    createFolder,
    renameFolder,
    deleteFolder,
    folderGrants,
    setFolderGrant,
    revokeFolderGrant,
    folderAudit,
    getGroups,
  } = useStoreActions((actions) => actions.ciphermothModels.access);
  const shareTargets = useStoreActions((actions) => actions.ciphermothModels.users.shareTargets);

  const [folderId, setFolderId] = useState("");
  const [newFolderName, setNewFolderName] = useState("");
  const [renameName, setRenameName] = useState("");
  const [grants, setGrants] = useState([]);
  const [audit, setAudit] = useState([]);
  const [targets, setTargets] = useState([]);
  const [targetType, setTargetType] = useState("user");
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState("read");
  const [expiresAt, setExpiresAt] = useState("");
  const [busy, setBusy] = useState(false);
  const currentUserId = getCurrentUser()?.id;
  const selected = folders.find((folder) => folder.id === Number(folderId)) ?? null;
  const ownsSelected = selected?.owner_id === currentUserId;

  const loadBase = useCallback(async () => {
    const [nextFolders, nextGroups, nextTargets] = await Promise.all([
      getFolders(),
      getGroups(),
      shareTargets(),
    ]);
    setTargets(nextTargets);
    setFolderId((current) => {
      if (nextFolders.some((folder) => folder.id === Number(current))) return current;
      return nextFolders[0]?.id ?? "";
    });
    return { nextFolders, nextGroups };
  }, [getFolders, getGroups, shareTargets]);

  const loadDetails = useCallback(async () => {
    if (!selected?.can_manage) {
      setGrants([]);
      setAudit([]);
      return;
    }
    const [nextGrants, nextAudit] = await Promise.all([
      folderGrants(selected.id),
      folderAudit(selected.id),
    ]);
    setGrants(nextGrants);
    setAudit(nextAudit);
  }, [selected?.can_manage, selected?.id, folderGrants, folderAudit]);

  useEffect(() => {
    if (!open) return;
    loadBase().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, loadBase, enqueueSnackbar]);

  useEffect(() => {
    if (!open || !selected) return;
    setRenameName(selected.name);
    loadDetails().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, selected, loadDetails, enqueueSnackbar]);

  const run = async (operation, message, { refreshBase = false } = {}) => {
    setBusy(true);
    try {
      await operation();
      if (refreshBase) await loadBase();
      else await loadDetails();
      enqueueSnackbar(message, { variant: "success" });
      return true;
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const grantTargets = useMemo(() => {
    const source = targetType === "user" ? targets : groups;
    return source.filter(
      (target) =>
        target.id !== selected?.owner_id &&
        !grants.some((grant) => grant.target_type === targetType && grant.target_id === target.id)
    );
  }, [targetType, targets, groups, grants, selected?.owner_id]);

  const saveGrant = (grant, nextPermission, nextExpiry) =>
    run(
      () =>
        setFolderGrant({
          folderId: selected.id,
          targetType: grant.target_type,
          targetId: grant.target_id,
          permission: nextPermission,
          expiresAt: nextExpiry,
        }),
      t("folderAccess.saved")
    );

  const addGrant = async () => {
    if (!targetId) return;
    const saved = await run(
      () =>
        setFolderGrant({
          folderId: selected.id,
          targetType,
          targetId,
          permission,
          expiresAt: toUtc(expiresAt),
        }),
      t("folderAccess.saved")
    );
    if (saved) {
      setTargetId("");
      setExpiresAt("");
    }
  };

  const addFolder = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) return;
    const created = await run(() => createFolder(trimmed), t("folderAccess.folderCreated"), {
      refreshBase: true,
    });
    if (created) setNewFolderName("");
  };

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth="lg"
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
      <DialogTitle>{t("folderAccess.title")}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2.5}>
          <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t("folderAccess.createFolder")}
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                size="small"
                label={t("common.fields.name")}
                value={newFolderName}
                onChange={(event) => setNewFolderName(event.target.value)}
                sx={{ flex: 1 }}
              />
              <Button
                variant="contained"
                disabled={busy || !newFolderName.trim()}
                onClick={addFolder}
              >
                {t("common.actions.create")}
              </Button>
            </Stack>
          </Paper>

          {folders.length === 0 ? (
            <Typography color="text.secondary">{t("folderAccess.empty")}</Typography>
          ) : (
            <>
              <TextField
                select
                label={t("common.fields.folder")}
                value={folderId}
                onChange={(event) => setFolderId(event.target.value)}
              >
                {folders.map((folder) => (
                  <MenuItem key={folder.id} value={folder.id}>
                    {folder.name} · {folder.owner_username}
                  </MenuItem>
                ))}
              </TextField>

              <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                <Stack spacing={1.25}>
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
                  >
                    <Box>
                      <Typography variant="h6">{selected?.name}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {t("folderAccess.ownerLabel", { owner: selected?.owner_username })}
                      </Typography>
                    </Box>
                    <Chip
                      label={t(
                        selected?.access
                          ? `folderAccess.permissions.${selected.access}`
                          : "folderAccess.managementOnly"
                      )}
                      variant="outlined"
                    />
                  </Stack>
                  {ownsSelected && (
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                      <TextField
                        size="small"
                        label={t("folderAccess.rename")}
                        value={renameName}
                        onChange={(event) => setRenameName(event.target.value)}
                        sx={{ flex: 1 }}
                      />
                      <Button
                        variant="outlined"
                        disabled={busy || !renameName.trim() || renameName.trim() === selected.name}
                        onClick={() =>
                          run(
                            () =>
                              renameFolder({
                                folderId: selected.id,
                                name: renameName.trim(),
                              }),
                            t("folderAccess.folderRenamed"),
                            { refreshBase: true }
                          )
                        }
                      >
                        {t("common.actions.save")}
                      </Button>
                      <Button
                        color="error"
                        disabled={busy}
                        onClick={() =>
                          window.confirm(
                            t("folderAccess.deleteConfirm", { name: selected.name })
                          ) &&
                          run(() => deleteFolder(selected.id), t("folderAccess.folderDeleted"), {
                            refreshBase: true,
                          })
                        }
                      >
                        {t("common.actions.delete")}
                      </Button>
                    </Stack>
                  )}
                </Stack>
              </Paper>

              {selected?.can_manage && (
                <>
                  <Box>
                    <Typography variant="h6" sx={{ mb: 1 }}>
                      {t("folderAccess.grants")}
                    </Typography>
                    <Stack spacing={1}>
                      {grants.length === 0 && (
                        <Typography color="text.secondary">{t("folderAccess.noGrants")}</Typography>
                      )}
                      {grants.map((grant) => (
                        <GrantRow
                          key={`${grant.target_type}-${grant.target_id}`}
                          grant={grant}
                          busy={busy}
                          onSave={(nextPermission, nextExpiry) =>
                            saveGrant(grant, nextPermission, nextExpiry)
                          }
                          onRevoke={() =>
                            run(
                              () =>
                                revokeFolderGrant({
                                  folderId: selected.id,
                                  targetType: grant.target_type,
                                  targetId: grant.target_id,
                                }),
                              t("folderAccess.revoked")
                            )
                          }
                        />
                      ))}
                    </Stack>
                  </Box>

                  <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      {t("sharing.grantAccess")}
                    </Typography>
                    <Box
                      sx={{
                        display: "grid",
                        gridTemplateColumns: {
                          xs: "1fr",
                          md: "130px minmax(160px, 1fr) 130px 190px auto",
                        },
                        gap: 1,
                      }}
                    >
                      <TextField
                        select
                        size="small"
                        label={t("folderAccess.targetType")}
                        value={targetType}
                        disabled={busy}
                        onChange={(event) => {
                          setTargetType(event.target.value);
                          setTargetId("");
                        }}
                      >
                        <MenuItem value="user">{t("folderAccess.targetTypes.user")}</MenuItem>
                        <MenuItem value="group">{t("folderAccess.targetTypes.group")}</MenuItem>
                      </TextField>
                      <TextField
                        select
                        size="small"
                        label={t("folderAccess.target")}
                        value={targetId}
                        disabled={busy || grantTargets.length === 0}
                        onChange={(event) => setTargetId(event.target.value)}
                      >
                        {grantTargets.map((target) => (
                          <MenuItem key={target.id} value={target.id}>
                            {target.name ?? target.username}
                          </MenuItem>
                        ))}
                      </TextField>
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
                          htmlInput: { min: toLocalInput(new Date().toISOString()) },
                        }}
                      />
                      <Button variant="contained" disabled={busy || !targetId} onClick={addGrant}>
                        {t("sharing.grant")}
                      </Button>
                    </Box>
                  </Paper>

                  <Divider />
                  <Box>
                    <Typography variant="h6" sx={{ mb: 1 }}>
                      {t("folderAccess.audit")}
                    </Typography>
                    <Stack spacing={0.75}>
                      {audit.length === 0 ? (
                        <Typography color="text.secondary">{t("folderAccess.noAudit")}</Typography>
                      ) : (
                        audit.slice(0, 20).map((event) => (
                          <Paper key={event.id} variant="outlined" sx={{ p: 1.25 }}>
                            <Typography variant="body2">
                              {t(`folderAccess.actions.${event.action}`, {
                                defaultValue: event.action,
                                actor: event.actor_username || t("folderAccess.systemActor"),
                                target: event.target_username || event.target_group_name || "",
                              })}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {eventDate(event.created, i18n.resolvedLanguage)}
                            </Typography>
                          </Paper>
                        ))
                      )}
                    </Stack>
                  </Box>
                </>
              )}
            </>
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

export default FolderAccessDialog;

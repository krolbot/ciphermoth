import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Box,
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
  useTheme,
} from "@mui/material";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

const GroupManagementDialog = ({ open, onClose }) => {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const { enqueueSnackbar } = useSnackbar();
  const groups = useStoreState((state) => state.ciphermothModels.access.groups);
  const users = useStoreState((state) => state.ciphermothModels.users.users);
  const {
    getGroups,
    createGroup,
    renameGroup,
    deleteGroup,
    groupMembers,
    addGroupMember,
    removeGroupMember,
    groupAudit,
  } = useStoreActions((actions) => actions.ciphermothModels.access);
  const [groupId, setGroupId] = useState("");
  const [newName, setNewName] = useState("");
  const [renameName, setRenameName] = useState("");
  const [members, setMembers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [userId, setUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const selected = groups.find((group) => group.id === Number(groupId)) ?? null;

  const loadGroups = useCallback(async () => {
    const next = await getGroups();
    setGroupId((current) =>
      next.some((group) => group.id === Number(current)) ? current : (next[0]?.id ?? "")
    );
  }, [getGroups]);

  const loadDetails = useCallback(async () => {
    if (!selected) {
      setMembers([]);
      setAudit([]);
      return;
    }
    const [nextMembers, nextAudit] = await Promise.all([
      groupMembers(selected.id),
      groupAudit(selected.id),
    ]);
    setMembers(nextMembers);
    setAudit(nextAudit);
  }, [selected, groupMembers, groupAudit]);

  useEffect(() => {
    if (!open) return;
    loadGroups().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, loadGroups, enqueueSnackbar]);

  useEffect(() => {
    if (!open || !selected) return;
    setRenameName(selected.name);
    loadDetails().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, selected, loadDetails, enqueueSnackbar]);

  const run = async (operation, message, refreshGroups = false) => {
    setBusy(true);
    try {
      await operation();
      if (refreshGroups) await loadGroups();
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

  const availableUsers = useMemo(
    () =>
      users.filter((user) => user.active && !members.some((member) => member.user_id === user.id)),
    [users, members]
  );

  const addGroup = async () => {
    const name = newName.trim();
    if (!name) return;
    const created = await run(() => createGroup(name), t("groups.created"), true);
    if (created) setNewName("");
  };

  const addMember = async () => {
    if (!selected || !userId) return;
    const added = await run(
      () => addGroupMember({ groupId: selected.id, userId }),
      t("groups.memberAdded")
    );
    if (added) setUserId("");
  };

  const eventDate = (value) => {
    const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
    return new Date(iso).toLocaleString(i18n.resolvedLanguage);
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
      <DialogTitle>{t("groups.title")}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2.5}>
          <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              {t("groups.create")}
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                size="small"
                label={t("groups.name")}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                sx={{ flex: 1 }}
              />
              <Button variant="contained" disabled={busy || !newName.trim()} onClick={addGroup}>
                {t("common.actions.create")}
              </Button>
            </Stack>
          </Paper>

          {groups.length === 0 ? (
            <Typography color="text.secondary">{t("groups.empty")}</Typography>
          ) : (
            <>
              <TextField
                select
                label={t("groups.group")}
                value={groupId}
                onChange={(event) => setGroupId(event.target.value)}
              >
                {groups.map((group) => (
                  <MenuItem key={group.id} value={group.id}>
                    {group.name} · {t("groups.memberCount", { count: group.member_count })}
                  </MenuItem>
                ))}
              </TextField>

              <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <TextField
                    size="small"
                    label={t("groups.rename")}
                    value={renameName}
                    onChange={(event) => setRenameName(event.target.value)}
                    sx={{ flex: 1 }}
                  />
                  <Button
                    variant="outlined"
                    disabled={busy || !renameName.trim() || renameName.trim() === selected?.name}
                    onClick={() =>
                      run(
                        () => renameGroup({ groupId: selected.id, name: renameName.trim() }),
                        t("groups.renamed"),
                        true
                      )
                    }
                  >
                    {t("common.actions.save")}
                  </Button>
                  <Button
                    color="error"
                    disabled={busy}
                    onClick={() =>
                      window.confirm(t("groups.deleteConfirm", { name: selected.name })) &&
                      run(() => deleteGroup(selected.id), t("groups.deleted"), true)
                    }
                  >
                    {t("common.actions.delete")}
                  </Button>
                </Stack>
              </Paper>

              <Box>
                <Typography variant="h6" sx={{ mb: 1 }}>
                  {t("groups.members")}
                </Typography>
                <Stack spacing={1}>
                  {members.length === 0 && (
                    <Typography color="text.secondary">{t("groups.noMembers")}</Typography>
                  )}
                  {members.map((member) => (
                    <Paper
                      key={member.user_id}
                      variant="outlined"
                      sx={{
                        p: 1.25,
                        display: "flex",
                        gap: 1,
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <Box sx={{ minWidth: 0 }}>
                        <Typography sx={{ fontWeight: 650, overflowWrap: "anywhere" }}>
                          {member.username}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {t(`users.roles.${member.role}`)}
                        </Typography>
                      </Box>
                      <Button
                        color="error"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () =>
                              removeGroupMember({
                                groupId: selected.id,
                                userId: member.user_id,
                              }),
                            t("groups.memberRemoved")
                          )
                        }
                      >
                        {t("common.actions.remove")}
                      </Button>
                    </Paper>
                  ))}
                </Stack>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1 }}>
                  <TextField
                    select
                    size="small"
                    label={t("groups.addMember")}
                    value={userId}
                    disabled={busy || availableUsers.length === 0}
                    onChange={(event) => setUserId(event.target.value)}
                    sx={{ flex: 1 }}
                  >
                    {availableUsers.map((user) => (
                      <MenuItem key={user.id} value={user.id}>
                        {user.username} · {t(`users.roles.${user.role}`)}
                      </MenuItem>
                    ))}
                  </TextField>
                  <Button variant="contained" disabled={busy || !userId} onClick={addMember}>
                    {t("common.actions.add")}
                  </Button>
                </Stack>
              </Box>

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
                            target: event.target_username || "",
                          })}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {eventDate(event.created)}
                        </Typography>
                      </Paper>
                    ))
                  )}
                </Stack>
              </Box>
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

export default GroupManagementDialog;

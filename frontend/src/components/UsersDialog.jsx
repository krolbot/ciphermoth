import { useEffect, useState } from "react";
import {
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
  Switch,
  TextField,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

import useClipboard from "../hooks/useClipboard";
import { generateUserKeyMaterial } from "../lib/crypto";
import { userAdminActions } from "../lib/userAdmin";
import { getCurrentUser } from "../utils";
import ConfirmDialog from "./ConfirmDialog";
import PasswordField from "./PasswordField";

const UsersDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const { enqueueSnackbar } = useSnackbar();
  const copy = useClipboard();
  const { get, create, update, revokeSessions, requirePasswordChange, remove } = useStoreActions(
    (a) => a.ciphermothModels.users
  );
  const users = useStoreState((s) => s.ciphermothModels.users.users);
  const currentUserId = getCurrentUser()?.id;
  const [form, setForm] = useState({ username: "", temporary_password: "", role: "member" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [serviceToken, setServiceToken] = useState("");
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    if (open) get().catch((err) => setError(err.message));
  }, [open, get]);

  const add = async () => {
    setSaving(true);
    setError("");
    try {
      const keyMaterial =
        form.role === "service" ? null : await generateUserKeyMaterial(form.temporary_password);
      const payload =
        form.role === "service"
          ? { username: form.username, role: form.role }
          : {
              username: form.username,
              role: form.role,
              salt: keyMaterial.salt,
              public_key: keyMaterial.publicKey,
              encrypted_private_key: keyMaterial.encryptedPrivateKey,
              auth_public_key: keyMaterial.authPublicKey,
              encrypted_auth_private_key: keyMaterial.encryptedAuthPrivateKey,
            };
      const created = await create(payload);
      setServiceToken(created.service_token || "");
      setForm({ username: "", temporary_password: "", role: "member" });
      enqueueSnackbar(t("users.messages.created"), { variant: "success" });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const close = () => {
    setServiceToken("");
    setConfirmation(null);
    onClose();
  };

  const change = async (userId, patch) => {
    setError("");
    try {
      await update({ userId, ...patch });
    } catch (err) {
      setError(err.message);
    }
  };

  const confirmAction = async () => {
    if (!confirmation) return;
    setSaving(true);
    setError("");
    try {
      const { type, user } = confirmation;
      if (type === "sessions") await revokeSessions(user.id);
      if (type === "password") await requirePasswordChange(user.id);
      if (type === "delete") await remove(user.id);
      enqueueSnackbar(t(`users.messages.${type}`), { variant: "success" });
      setConfirmation(null);
    } catch (err) {
      setError(err.message);
      setConfirmation(null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onClose={close} maxWidth="md" fullWidth fullScreen={fullScreen}>
        <DialogTitle>{t("users.title")}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2.5}>
            <Stack spacing={1}>
              {users.map((user) => {
                const actions = userAdminActions(user, currentUserId);
                return (
                  <Paper key={user.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                    <Stack spacing={1.25}>
                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        spacing={1}
                        sx={{ alignItems: { xs: "flex-start", sm: "center" } }}
                      >
                        <Typography sx={{ flex: 1, minWidth: 0, fontWeight: 600 }} noWrap>
                          {user.username}
                        </Typography>
                        <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }}>
                          <Chip size="small" label={t(`users.roles.${user.role}`)} />
                          <Chip
                            size="small"
                            color={user.active ? "success" : "default"}
                            label={t(user.active ? "users.active" : "users.inactive")}
                          />
                          {user.must_change_password && user.role !== "service" && (
                            <Chip
                              size="small"
                              color="warning"
                              label={t("users.passwordChangePending")}
                            />
                          )}
                        </Stack>
                      </Stack>

                      <Stack
                        direction={{ xs: "column", md: "row" }}
                        spacing={1}
                        sx={{ alignItems: { xs: "stretch", md: "center" } }}
                      >
                        <TextField
                          select
                          size="small"
                          label={t("users.role")}
                          value={user.role}
                          onChange={(event) => change(user.id, { role: event.target.value })}
                          disabled={saving || user.role === "service" || user.id === currentUserId}
                          sx={{ width: { xs: "100%", md: 180 }, flexShrink: 0 }}
                        >
                          {(user.role === "service" ? ["service"] : ["admin", "member"]).map(
                            (role) => (
                              <MenuItem key={role} value={role}>
                                {t(`users.roles.${role}`)}
                              </MenuItem>
                            )
                          )}
                        </TextField>
                        <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
                          <Switch
                            checked={user.active}
                            onChange={(event) => change(user.id, { active: event.target.checked })}
                            disabled={saving || user.id === currentUserId}
                            slotProps={{ input: { "aria-label": t("users.active") } }}
                          />
                          <Typography variant="body2">
                            {t(user.active ? "users.active" : "users.inactive")}
                          </Typography>
                        </Stack>
                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          spacing={1}
                          sx={{ ml: { md: "auto" } }}
                        >
                          {actions.canRevokeSessions && (
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={saving}
                              onClick={() => setConfirmation({ type: "sessions", user })}
                            >
                              {t("users.revokeSessions")}
                            </Button>
                          )}
                          {actions.canRequirePasswordChange && (
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={saving || user.must_change_password}
                              onClick={() => setConfirmation({ type: "password", user })}
                            >
                              {t("users.requirePasswordChange")}
                            </Button>
                          )}
                          {actions.canDelete && (
                            <Button
                              size="small"
                              color="error"
                              variant="outlined"
                              disabled={saving}
                              onClick={() => setConfirmation({ type: "delete", user })}
                            >
                              {t("common.actions.delete")}
                            </Button>
                          )}
                        </Stack>
                      </Stack>
                    </Stack>
                  </Paper>
                );
              })}
            </Stack>

            <Divider />

            <Stack spacing={1.5}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {t("users.create")}
              </Typography>
              <TextField
                label={t("auth.username")}
                value={form.username}
                onChange={(event) =>
                  setForm((current) => ({ ...current, username: event.target.value }))
                }
                autoComplete="username"
              />
              {form.role !== "service" && (
                <PasswordField
                  label={t("users.temporaryPassword")}
                  value={form.temporary_password}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, temporary_password: event.target.value }))
                  }
                  autoComplete="new-password"
                />
              )}
              <TextField
                select
                label={t("users.role")}
                value={form.role}
                onChange={(event) =>
                  setForm((current) => ({ ...current, role: event.target.value }))
                }
              >
                {["admin", "member", "service"].map((role) => (
                  <MenuItem key={role} value={role}>
                    {t(`users.roles.${role}`)}
                  </MenuItem>
                ))}
              </TextField>
              <Button
                variant="contained"
                loading={saving}
                onClick={add}
                disabled={
                  !form.username.trim() || (form.role !== "service" && !form.temporary_password)
                }
              >
                {t("common.actions.create")}
              </Button>
            </Stack>

            {serviceToken && (
              <Paper variant="outlined" sx={{ p: 1.5, borderColor: "warning.main" }}>
                <Stack spacing={1}>
                  <Typography color="warning.main">{t("users.serviceTokenOnce")}</Typography>
                  <TextField
                    label={t("users.serviceToken")}
                    value={serviceToken}
                    slotProps={{ input: { readOnly: true } }}
                  />
                  <Button onClick={() => copy(serviceToken)}>{t("users.copyToken")}</Button>
                </Stack>
              </Paper>
            )}

            {error && <Typography color="error">{error}</Typography>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>{t("common.actions.close")}</Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={Boolean(confirmation)}
        title={confirmation ? t(`users.confirm.${confirmation.type}.title`) : ""}
        onClose={() => setConfirmation(null)}
        onConfirm={confirmAction}
        confirmColor={confirmation?.type === "delete" ? "error" : "primary"}
      >
        {confirmation
          ? t(`users.confirm.${confirmation.type}.message`, {
              username: confirmation.user.username,
            })
          : ""}
      </ConfirmDialog>
    </>
  );
};

export default UsersDialog;

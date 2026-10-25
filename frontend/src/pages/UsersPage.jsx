import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useStoreActions, useStoreState } from "easy-peasy";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import PasswordField from "../components/PasswordField";
import useClipboard from "../hooks/useClipboard";
import { getCurrentUser } from "../utils";

const EMPTY_FORM = { username: "", temporary_password: "", role: "member" };

const UsersPage = () => {
  const { t } = useTranslation();
  const copy = useClipboard();
  const users = useStoreState((state) => state.ciphermothModels.users.users);
  const { get, create, update, revokeSessions, resetPassword, rotateServiceToken, remove } =
    useStoreActions((actions) => actions.ciphermothModels.users);
  const currentUserId = getCurrentUser()?.id;
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [serviceToken, setServiceToken] = useState("");
  const [resetTarget, setResetTarget] = useState(null);
  const [temporaryPassword, setTemporaryPassword] = useState("");

  useEffect(() => {
    get().catch((err) => setError(err.message));
  }, [get]);

  const run = async (operation, message = "") => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await operation();
      if (message) setNotice(message);
      return result ?? true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async (event) => {
    event.preventDefault();
    const payload = form.role === "service" ? { username: form.username, role: form.role } : form;
    const created = await run(() => create(payload), t("users.messages.created"));
    if (!created) return;
    setServiceToken(created.service_token || "");
    setForm(EMPTY_FORM);
  };

  const saveReset = async () => {
    const ok = await run(
      () => resetPassword({ userId: resetTarget.id, temporaryPassword }),
      t("users.messages.passwordReset")
    );
    if (!ok) return;
    setResetTarget(null);
    setTemporaryPassword("");
  };

  const rotateToken = async (user) => {
    const token = await run(() => rotateServiceToken(user.id), t("users.messages.tokenRotated"));
    if (token) setServiceToken(token);
  };

  return (
    <Stack spacing={3} sx={{ minWidth: 0 }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }}
      >
        <Box>
          <Typography component="h1" variant="h4" sx={{ fontWeight: 700 }}>
            {t("users.title")}
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {t("users.subtitle")}
          </Typography>
        </Box>
        <Button component={Link} to="/passwords" variant="outlined" startIcon={<ArrowBackIcon />}>
          {t("users.backToVault")}
        </Button>
      </Stack>

      {notice && (
        <Alert severity="success" onClose={() => setNotice("")}>
          {notice}
        </Alert>
      )}
      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {serviceToken && (
        <Alert severity="warning">
          <Stack spacing={1}>
            <Typography>{t("users.serviceTokenOnce")}</Typography>
            <TextField value={serviceToken} slotProps={{ input: { readOnly: true } }} fullWidth />
            <Stack direction="row" spacing={1}>
              <Button onClick={() => copy(serviceToken)}>{t("users.copyToken")}</Button>
              <Button color="inherit" onClick={() => setServiceToken("")}>
                {t("common.actions.dismiss")}
              </Button>
            </Stack>
          </Stack>
        </Alert>
      )}

      <Paper variant="outlined" sx={{ borderRadius: 2.5, overflow: "hidden" }}>
        {users.map((user) => {
          const isCurrent = user.id === currentUserId;
          return (
            <Box
              key={user.id}
              sx={{
                display: "grid",
                gridTemplateColumns: {
                  xs: "minmax(0, 1fr)",
                  md: "minmax(180px, 1fr) 170px 150px minmax(280px, auto)",
                },
                gap: 1.25,
                alignItems: "center",
                p: 2,
                borderBottom: "1px solid",
                borderColor: "divider",
                "&:last-child": { borderBottom: 0 },
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontWeight: 650, overflowWrap: "anywhere" }}>
                  {user.username}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {user.must_change_password && user.role !== "service"
                    ? t("users.passwordChangeRequested")
                    : user.role === "service"
                      ? t("users.serviceAccount")
                      : t("users.interactiveAccount")}
                </Typography>
              </Box>
              <TextField
                select
                size="small"
                label={t("users.role")}
                value={user.role}
                disabled={busy || isCurrent || user.role === "service"}
                onChange={(event) =>
                  run(
                    () => update({ userId: user.id, role: event.target.value }),
                    t("users.messages.roleUpdated")
                  )
                }
              >
                {(user.role === "service" ? ["service"] : ["admin", "member"]).map((role) => (
                  <MenuItem key={role} value={role}>
                    {t(`users.roles.${role}`)}
                  </MenuItem>
                ))}
              </TextField>
              <FormControlLabel
                control={
                  <Switch
                    checked={user.active}
                    disabled={busy || isCurrent}
                    onChange={(event) =>
                      run(
                        () => update({ userId: user.id, active: event.target.checked }),
                        t("users.messages.statusUpdated")
                      )
                    }
                  />
                }
                label={t(user.active ? "users.active" : "users.inactive")}
              />
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                {user.role === "service" ? (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={busy}
                    onClick={() => rotateToken(user)}
                  >
                    {t("users.rotateToken")}
                  </Button>
                ) : (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={busy || isCurrent}
                    onClick={() => setResetTarget(user)}
                  >
                    {t("users.resetPassword")}
                  </Button>
                )}
                <Button
                  size="small"
                  variant="outlined"
                  disabled={busy}
                  onClick={() =>
                    run(() => revokeSessions(user.id), t("users.messages.sessionsRevoked"))
                  }
                >
                  {t("users.revokeSessions")}
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={busy || isCurrent}
                  onClick={() => {
                    if (window.confirm(t("users.deleteConfirm", { username: user.username }))) {
                      run(() => remove(user.id), t("users.messages.deleted"));
                    }
                  }}
                >
                  {t("common.actions.delete")}
                </Button>
              </Stack>
            </Box>
          );
        })}
      </Paper>

      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 2.5 }, borderRadius: 2.5 }}>
        <Typography variant="h6">{t("users.createAccount")}</Typography>
        <Box
          component="form"
          onSubmit={add}
          sx={{
            mt: 2,
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) minmax(0, 1fr) 180px auto" },
            gap: 1.25,
          }}
        >
          <TextField
            label={t("auth.username")}
            required
            value={form.username}
            onChange={(event) =>
              setForm((current) => ({ ...current, username: event.target.value }))
            }
            autoComplete="off"
          />
          {form.role === "service" ? (
            <Box />
          ) : (
            <PasswordField
              label={t("users.temporaryPassword")}
              required
              value={form.temporary_password}
              onGenerate={(password) =>
                setForm((current) => ({ ...current, temporary_password: password }))
              }
              disabled={busy}
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
              setForm((current) => ({
                ...current,
                role: event.target.value,
                temporary_password:
                  event.target.value === "service" ? "" : current.temporary_password,
              }))
            }
          >
            {["admin", "member", "service"].map((role) => (
              <MenuItem key={role} value={role}>
                {t(`users.roles.${role}`)}
              </MenuItem>
            ))}
          </TextField>
          <Button type="submit" variant="contained" disabled={busy || !form.username.trim()}>
            {t("common.actions.create")}
          </Button>
        </Box>
      </Paper>

      <Dialog
        open={Boolean(resetTarget)}
        onClose={() => setResetTarget(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          {t("users.resetPasswordFor", { username: resetTarget?.username })}
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t("users.resetPasswordDescription")}
          </Typography>
          <PasswordField
            label={t("users.temporaryPassword")}
            value={temporaryPassword}
            onGenerate={setTemporaryPassword}
            disabled={busy}
            onChange={(event) => setTemporaryPassword(event.target.value)}
            autoComplete="new-password"
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetTarget(null)}>{t("common.actions.cancel")}</Button>
          <Button variant="contained" disabled={busy || !temporaryPassword} onClick={saveReset}>
            {t("users.resetPassword")}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
};

export default UsersPage;

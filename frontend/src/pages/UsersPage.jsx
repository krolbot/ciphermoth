import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  IconButton,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";
import LogoutOutlinedIcon from "@mui/icons-material/LogoutOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import { alpha, useTheme } from "@mui/material/styles";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import ConfirmDialog from "../components/ConfirmDialog";
import PasswordField from "../components/PasswordField";
import useClipboard from "../hooks/useClipboard";
import { generateUserKeyMaterial } from "../lib/crypto";
import { userAdminActions } from "../lib/userAdmin";
import { getCurrentUser } from "../utils";

const UsersPage = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { enqueueSnackbar } = useSnackbar();
  const copy = useClipboard();
  const { get, create, update, revokeSessions, requirePasswordChange, remove } = useStoreActions(
    (actions) => actions.ciphermothModels.users
  );
  const users = useStoreState((state) => state.ciphermothModels.users.users);
  const currentUserId = getCurrentUser()?.id;
  const [form, setForm] = useState({ username: "", temporary_password: "", role: "member" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [serviceToken, setServiceToken] = useState("");
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    get().catch((err) => setError(err.message));
  }, [get]);

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
    <Stack spacing={{ xs: 2.5, sm: 3 }} sx={{ minWidth: 0, maxWidth: "100%" }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ alignItems: { xs: "flex-start", sm: "center" }, justifyContent: "space-between" }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h1"
            variant="h4"
            sx={{ fontWeight: 700, lineHeight: 1.1, fontSize: { xs: 32, sm: 38 } }}
          >
            {t("users.title")}
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.75, maxWidth: 680 }}>
            {t("users.subtitle")}
          </Typography>
        </Box>
        <Button component={Link} to="/passwords" variant="outlined" startIcon={<ArrowBackIcon />}>
          {t("users.backToVault")}
        </Button>
      </Stack>

      <Paper variant="outlined" sx={{ overflow: "hidden", borderRadius: 2.5 }}>
        <Box
          sx={{
            display: { xs: "none", md: "grid" },
            gridTemplateColumns: "minmax(180px, 1fr) 180px 150px 140px",
            gap: 1.5,
            px: 2,
            py: 1.25,
            bgcolor: alpha(theme.palette.primary.main, 0.07),
            borderBottom: "1px solid",
            borderColor: "divider",
          }}
        >
          {["account", "role", "status", "actions"].map((key) => (
            <Typography
              key={key}
              variant="overline"
              sx={{ color: "text.secondary", fontWeight: 700, letterSpacing: "0.08em" }}
            >
              {t(`users.columns.${key}`)}
            </Typography>
          ))}
        </Box>

        {users.map((user) => {
          const actions = userAdminActions(user, currentUserId);
          const roleColor = theme.palette.primary.main;
          const RoleIcon = user.role === "service" ? SmartToyOutlinedIcon : PersonOutlineIcon;

          return (
            <Box
              key={user.id}
              sx={{
                display: "grid",
                gridTemplateColumns: {
                  xs: "minmax(0, 1fr) auto",
                  md: "minmax(180px, 1fr) 180px 150px 140px",
                },
                gap: { xs: 1, sm: 1.5 },
                alignItems: "center",
                px: { xs: 1.5, sm: 2 },
                py: 1.5,
                bgcolor: user.active ? "transparent" : alpha(theme.palette.text.disabled, 0.06),
                borderBottom: "1px solid",
                borderColor: "divider",
                "&:last-child": { borderBottom: 0 },
              }}
            >
              <Stack direction="row" spacing={1.25} sx={{ minWidth: 0, alignItems: "center" }}>
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    display: "grid",
                    placeItems: "center",
                    flexShrink: 0,
                    color: roleColor,
                    bgcolor: alpha(roleColor, 0.14),
                  }}
                >
                  <RoleIcon fontSize="small" />
                </Box>
                <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                  <Typography sx={{ minWidth: 0, fontWeight: 650, overflowWrap: "anywhere" }}>
                    {user.username}
                  </Typography>
                  {user.must_change_password && user.role !== "service" && (
                    <Typography
                      variant="caption"
                      sx={{ color: "text.secondary", lineHeight: 1.25 }}
                    >
                      {t("users.passwordChangePending")}
                    </Typography>
                  )}
                </Stack>
              </Stack>

              <Select
                size="small"
                value={user.role}
                onChange={(event) => change(user.id, { role: event.target.value })}
                disabled={saving || user.role === "service" || user.id === currentUserId}
                inputProps={{ "aria-label": t("users.role") }}
                sx={{
                  width: "100%",
                  minHeight: { xs: 44, md: 40 },
                  gridColumn: { xs: "1", md: "2" },
                  gridRow: { xs: "2", md: "1" },
                  bgcolor: alpha(roleColor, 0.09),
                  "& .MuiOutlinedInput-notchedOutline": { borderColor: alpha(roleColor, 0.45) },
                  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: roleColor },
                  "&.Mui-disabled .MuiSelect-select": {
                    color: "text.secondary",
                    WebkitTextFillColor: theme.palette.text.secondary,
                  },
                }}
              >
                {(user.role === "service" ? ["service"] : ["admin", "member"]).map((role) => (
                  <MenuItem key={role} value={role}>
                    {t(`users.roles.${role}`)}
                  </MenuItem>
                ))}
              </Select>

              <FormControlLabel
                control={
                  <Switch
                    checked={user.active}
                    onChange={(event) => change(user.id, { active: event.target.checked })}
                    disabled={saving || user.id === currentUserId}
                    slotProps={{ input: { "aria-label": t("users.active") } }}
                  />
                }
                label={t(user.active ? "users.active" : "users.inactive")}
                sx={{
                  m: 0,
                  minHeight: 44,
                  gridColumn: { xs: "2", md: "3" },
                  gridRow: { xs: "2", md: "1" },
                  "& .MuiFormControlLabel-label": {
                    color: user.active ? "text.primary" : "text.secondary",
                    fontSize: theme.typography.body2.fontSize,
                    fontWeight: 600,
                  },
                }}
              />

              <Stack
                direction="row"
                spacing={0.5}
                sx={{
                  justifyContent: "flex-end",
                  gridColumn: { xs: "2", md: "4" },
                  gridRow: "1",
                }}
              >
                {actions.canRevokeSessions && (
                  <Tooltip title={t("users.revokeSessions")}>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t("users.revokeSessions")}
                        disabled={saving}
                        onClick={() => setConfirmation({ type: "sessions", user })}
                        sx={{
                          minWidth: 44,
                          minHeight: 44,
                          color: "text.secondary",
                          bgcolor: "action.hover",
                        }}
                      >
                        <LogoutOutlinedIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
                {actions.canRequirePasswordChange && (
                  <Tooltip title={t("users.requirePasswordChange")}>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t("users.requirePasswordChange")}
                        disabled={saving || user.must_change_password}
                        onClick={() => setConfirmation({ type: "password", user })}
                        sx={{
                          minWidth: 44,
                          minHeight: 44,
                          color: "text.secondary",
                          bgcolor: "action.hover",
                        }}
                      >
                        <KeyOutlinedIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
                {actions.canDelete && (
                  <Tooltip title={t("common.actions.delete")}>
                    <span>
                      <IconButton
                        size="small"
                        aria-label={t("common.actions.delete")}
                        disabled={saving}
                        onClick={() => setConfirmation({ type: "delete", user })}
                        sx={{
                          minWidth: 44,
                          minHeight: 44,
                          color: "error.main",
                          bgcolor: alpha(theme.palette.error.main, 0.09),
                        }}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
              </Stack>
            </Box>
          );
        })}
      </Paper>

      <Paper
        variant="outlined"
        sx={{
          p: { xs: 1.5, sm: 2.5 },
          borderRadius: 2.5,
          borderColor: alpha(theme.palette.primary.main, 0.4),
          bgcolor: alpha(theme.palette.primary.main, 0.035),
        }}
      >
        <Stack spacing={1.75}>
          <Box>
            <Typography variant="h6">{t("users.create")}</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.25 }}>
              {t("users.createDescription")}
            </Typography>
          </Box>
          <Box
            component="form"
            onSubmit={(event) => {
              event.preventDefault();
              add();
            }}
            sx={{
              display: "grid",
              gridTemplateColumns: {
                xs: "minmax(0, 1fr)",
                sm: "minmax(0, 1fr) minmax(0, 1fr)",
                md: "minmax(0, 1fr) minmax(0, 1fr) 180px auto",
              },
              gap: 1.25,
              alignItems: "stretch",
            }}
          >
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
              onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))}
            >
              {["admin", "member", "service"].map((role) => (
                <MenuItem key={role} value={role}>
                  {t(`users.roles.${role}`)}
                </MenuItem>
              ))}
            </TextField>
            <Button
              type="submit"
              variant="contained"
              loading={saving}
              disabled={
                !form.username.trim() || (form.role !== "service" && !form.temporary_password)
              }
              sx={{ px: 2.5 }}
            >
              {t("common.actions.create")}
            </Button>
          </Box>
        </Stack>
      </Paper>

      {serviceToken && (
        <Alert
          severity="warning"
          action={<Button onClick={() => copy(serviceToken)}>{t("users.copyToken")}</Button>}
          sx={{ alignItems: "center" }}
        >
          <Stack spacing={1}>
            <Typography variant="body2">{t("users.serviceTokenOnce")}</Typography>
            <TextField
              size="small"
              label={t("users.serviceToken")}
              value={serviceToken}
              slotProps={{ input: { readOnly: true } }}
              fullWidth
            />
          </Stack>
        </Alert>
      )}

      {error && <Alert severity="error">{error}</Alert>}

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
    </Stack>
  );
};

export default UsersPage;

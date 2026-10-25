import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";

import apiClient from "../api/client";
import { errorDetail } from "../lib/http";
import { getMasterPasswordStrength } from "../lib/passwordStrength";
import { setCurrentUser, setSessionToken } from "../utils";
import PasswordField from "./PasswordField";

const PasswordChangeDialog = ({ open, onClose, required = false, onChanged }) => {
  const { t } = useTranslation();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const strength = getMasterPasswordStrength(newPassword);

  useEffect(() => {
    if (!open) return;
    setCurrentPassword("");
    setNewPassword("");
    setConfirm("");
    setError("");
  }, [open]);

  const save = async () => {
    if (newPassword !== confirm) {
      setError(t("auth.validation.passwordsDoNotMatch"));
      return;
    }
    if (!strength || strength.value < 70) {
      setError(t("auth.validation.passwordChangeWeak"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const { data } = await apiClient.put("/auth/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      if (!data.session_token || !data.user) throw new Error(t("auth.passwordChangeNoSession"));
      setSessionToken(data.session_token);
      setCurrentUser(data.user);
      onChanged?.(data.user);
      onClose();
    } catch (err) {
      setError(await errorDetail(err, err.message || t("errors.changePassword")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={required ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        {t(required ? "auth.changeTemporaryPassword" : "auth.changePassword")}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {required && (
            <Typography variant="body2" color="text.secondary">
              {t("auth.passwordChangeRequired")}
            </Typography>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          <PasswordField
            label={t("auth.currentPassword")}
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            autoFocus
          />
          <PasswordField
            label={t("auth.newPassword")}
            value={newPassword}
            onGenerate={setNewPassword}
            disabled={busy}
            onChange={(event) => setNewPassword(event.target.value)}
            autoComplete="new-password"
          />
          {newPassword && strength && (
            <LinearProgress variant="determinate" value={strength.value} color={strength.color} />
          )}
          <PasswordField
            label={t("auth.confirmNewPassword")}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        {!required && <Button onClick={onClose}>{t("common.actions.cancel")}</Button>}
        <Button
          variant="contained"
          loading={busy}
          disabled={!currentPassword || !newPassword || !confirm}
          onClick={save}
        >
          {t("auth.changePassword")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PasswordChangeDialog;

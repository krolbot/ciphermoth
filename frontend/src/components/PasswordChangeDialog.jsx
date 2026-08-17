import { useState } from "react";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import apiClient from "../api/client";
import PasswordField from "./PasswordField";
import { setAuthSession } from "../utils";
import { errorDetail } from "../lib/http";

const PasswordChangeDialog = ({ open, onClose, required = false }) => {
  const { t } = useTranslation();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setError("");
    if (!currentPassword || !newPassword) {
      setError(t("auth.validation.enterPasswordChange"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setError(t("auth.validation.passwordsDoNotMatch"));
      return;
    }
    setSaving(true);
    try {
      const { data } = await apiClient.put("/auth/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setAuthSession(data);
      window.location.replace("/passwords");
    } catch (err) {
      setError(await errorDetail(err, t("errors.changePassword")));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={(event, reason) => {
        if (!required) onClose?.(event, reason);
      }}
      maxWidth="xs"
      fullWidth
    >
      <DialogTitle>{t("auth.changePasswordTitle")}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          {required && (
            <Typography variant="body2" color="text.secondary">
              {t("auth.changePasswordRequired")}
            </Typography>
          )}
          <PasswordField
            label={t("auth.currentPassword")}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
          />
          <PasswordField
            label={t("auth.newPassword")}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
          />
          <PasswordField
            label={t("auth.confirmMasterPassword")}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
          />
          {error && <Typography color="error">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        {!required && <Button onClick={onClose}>{t("common.actions.cancel")}</Button>}
        <Button variant="contained" loading={saving} onClick={save}>
          {t("auth.changePassword")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PasswordChangeDialog;

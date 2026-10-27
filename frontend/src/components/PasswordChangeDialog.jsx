import { useEffect, useId, useState } from "react";
import { Alert, Dialog, Progress } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import apiClient from "../api/client";
import { errorDetail } from "../lib/http";
import { getMasterPasswordStrength } from "../lib/passwordStrength";
import { setCurrentUser, setSessionToken } from "../utils";
import PasswordField from "./PasswordField";

const STRENGTH_THEME = { error: "danger", warning: "warning", success: "success" };

const PasswordChangeDialog = ({ open, onClose, required = false, onChanged }) => {
  const { t } = useTranslation();
  const titleId = useId();
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
    <Dialog
      aria-labelledby={titleId}
      className="cm-secondary-dialog cm-secondary-dialog--password-change"
      contentOverflow="auto"
      disableEscapeKeyDown={required || busy}
      disableOutsideClick={required || busy}
      fullWidth
      hasCloseButton={false}
      maxWidth="s"
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !required && !busy) onClose();
      }}
      open={open}
    >
      <Dialog.Header
        caption={t(required ? "auth.changeTemporaryPassword" : "auth.changePassword")}
        id={titleId}
      />
      <Dialog.Body>
        <div className="cm-secondary-form">
          {required && <p className="cm-secondary-copy">{t("auth.passwordChangeRequired")}</p>}
          {error && (
            <div role="alert">
              <Alert message={error} size="s" theme="danger" />
            </div>
          )}
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
            <div
              aria-label={t(strength.labelKey)}
              aria-live="polite"
              className="cm-secondary-strength"
              role="status"
            >
              <Progress size="s" theme={STRENGTH_THEME[strength.color]} value={strength.value} />
            </div>
          )}
          <PasswordField
            label={t("auth.confirmNewPassword")}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
          />
        </div>
      </Dialog.Body>
      <Dialog.Footer
        loading={busy}
        onClickButtonApply={save}
        onClickButtonCancel={onClose}
        propsButtonApply={{ disabled: !currentPassword || !newPassword || !confirm }}
        textButtonApply={t("auth.changePassword")}
        textButtonCancel={required ? undefined : t("common.actions.cancel")}
      />
    </Dialog>
  );
};

export default PasswordChangeDialog;

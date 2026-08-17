import { useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import useClipboard from "../hooks/useClipboard";
import { generateUserKeyMaterial } from "../lib/crypto";
import PasswordField from "./PasswordField";

const UsersDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const copy = useClipboard();
  const { get, create, update } = useStoreActions((a) => a.ciphermothModels.users);
  const users = useStoreState((s) => s.ciphermothModels.users.users);
  const [form, setForm] = useState({ username: "", temporary_password: "", role: "member" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [serviceToken, setServiceToken] = useState("");

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
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const close = () => {
    setServiceToken("");
    onClose();
  };

  const change = async (userId, patch) => {
    try {
      await update({ userId, ...patch });
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
      <DialogTitle>{t("users.title")}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.5}>
          {users.map((user) => (
            <Stack key={user.id} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Typography sx={{ flex: 1 }}>{user.username}</Typography>
              <TextField
                select
                size="small"
                value={user.role}
                onChange={(e) => change(user.id, { role: e.target.value })}
                disabled={user.role === "service"}
                sx={{ width: 170, flexShrink: 0 }}
              >
                {(user.role === "service" ? ["service"] : ["admin", "member"]).map((role) => (
                  <MenuItem key={role} value={role}>
                    {t(`users.roles.${role}`)}
                  </MenuItem>
                ))}
              </TextField>
              <Switch
                checked={user.active}
                onChange={(e) => change(user.id, { active: e.target.checked })}
                slotProps={{ input: { "aria-label": t("users.active") } }}
              />
            </Stack>
          ))}
          <Typography variant="subtitle2" sx={{ pt: 1 }}>
            {t("users.create")}
          </Typography>
          <TextField
            label={t("auth.username")}
            value={form.username}
            onChange={(e) => setForm((current) => ({ ...current, username: e.target.value }))}
            autoComplete="username"
          />
          {form.role !== "service" && (
            <PasswordField
              label={t("users.temporaryPassword")}
              value={form.temporary_password}
              onChange={(e) =>
                setForm((current) => ({ ...current, temporary_password: e.target.value }))
              }
              autoComplete="new-password"
            />
          )}
          <TextField
            select
            label={t("users.role")}
            value={form.role}
            onChange={(e) => setForm((current) => ({ ...current, role: e.target.value }))}
          >
            {["admin", "member", "service"].map((role) => (
              <MenuItem key={role} value={role}>
                {t(`users.roles.${role}`)}
              </MenuItem>
            ))}
          </TextField>
          {serviceToken && (
            <Stack spacing={1}>
              <Typography color="warning.main">{t("users.serviceTokenOnce")}</Typography>
              <TextField
                label={t("users.serviceToken")}
                value={serviceToken}
                slotProps={{ input: { readOnly: true } }}
              />
              <Button onClick={() => copy(serviceToken)}>{t("users.copyToken")}</Button>
            </Stack>
          )}
          {error && <Typography color="error">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t("common.actions.close")}</Button>
        <Button
          variant="contained"
          loading={saving}
          onClick={add}
          disabled={!form.username.trim() || (form.role !== "service" && !form.temporary_password)}
        >
          {t("common.actions.create")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default UsersDialog;

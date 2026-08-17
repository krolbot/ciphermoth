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

import PasswordField from "./PasswordField";

const UsersDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const { get, create, update } = useStoreActions((a) => a.ciphermothModels.users);
  const users = useStoreState((s) => s.ciphermothModels.users.users);
  const [form, setForm] = useState({ username: "", temporary_password: "", role: "member" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) get().catch((err) => setError(err.message));
  }, [open, get]);

  const add = async () => {
    setSaving(true);
    setError("");
    try {
      await create(form);
      setForm({ username: "", temporary_password: "", role: "member" });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const change = async (userId, patch) => {
    try {
      await update({ userId, ...patch });
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
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
                sx={{ width: 120 }}
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
          <PasswordField
            label={t("users.temporaryPassword")}
            value={form.temporary_password}
            onChange={(e) => setForm((current) => ({ ...current, temporary_password: e.target.value }))}
            autoComplete="new-password"
          />
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
          {error && <Typography color="error">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("common.actions.close")}</Button>
        <Button
          variant="contained"
          loading={saving}
          onClick={add}
          disabled={!form.username.trim() || !form.temporary_password}
        >
          {t("common.actions.create")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default UsersDialog;

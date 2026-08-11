import { useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";

import PasswordField from "../PasswordField";

const BackupDialog = ({ open, onClose, onBackup }) => {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setPassword("");
      setError("");
    }
  }, [open]);

  const handleBackup = async () => {
    if (!password.trim()) {
      setError(t("backup.passwordRequired"));
      return;
    }
    setLoading(true);
    try {
      await onBackup(password);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={loading ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t("backup.title")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            {t("backup.description")}
          </Typography>
          <PasswordField
            label={t("auth.masterPassword")}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError("");
            }}
            error={!!error}
            helperText={error}
            required
            autoFocus
            autoComplete="current-password"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleBackup();
            }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading}>
          {t("common.actions.cancel")}
        </Button>
        <Button variant="contained" onClick={handleBackup} loading={loading}>
          {t("backup.title")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default BackupDialog;

import { useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  InputAdornment,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlined";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

import PasswordChangeDialog from "./PasswordChangeDialog";

const FIELDS = [
  {
    key: "inactivity_ms",
    labelKey: "settings.fields.inactivity",
    tooltipKey: "settings.fields.inactivityHelp",
    min: 30,
    max: 3600,
  },
  {
    key: "warn_before_ms",
    labelKey: "settings.fields.warning",
    tooltipKey: "settings.fields.warningHelp",
    min: 5,
    max: 600,
  },
  {
    key: "hidden_ms",
    labelKey: "settings.fields.hidden",
    tooltipKey: "settings.fields.hiddenHelp",
    min: 10,
    max: 3600,
  },
  {
    key: "debounce_ms",
    labelKey: "settings.fields.debounce",
    tooltipKey: "settings.fields.debounceHelp",
    min: 1,
    max: 10,
  },
  {
    key: "clipboard_clear_ms",
    labelKey: "settings.fields.clipboard",
    tooltipKey: "settings.fields.clipboardHelp",
    min: 5,
    max: 600,
  },
];

const toSec = (ms) => Math.round(ms / 1000);
const toMs = (sec) => Math.round(Number(sec)) * 1000;

const toForm = (settings) => ({
  ...Object.fromEntries(FIELDS.map(({ key }) => [key, toSec(settings[key])])),
  update_check_enabled: settings.update_check_enabled ?? true,
});

const isDirty = (form, settings) =>
  FIELDS.some(({ key }) => Number(form[key]) !== toSec(settings[key])) ||
  form.update_check_enabled !== (settings.update_check_enabled ?? true);

const SettingsModal = ({ open, onClose }) => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();

  const { update } = useStoreActions((a) => a.ciphermothModels.settings);
  const settings = useStoreState((s) => s.ciphermothModels.settings.settings);

  const [form, setForm] = useState(() => toForm(settings));
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(toForm(settings));
      setFormError("");
    }
  }, [open, settings]);

  const handleChange = (key) => (e) => {
    setForm((prev) => ({ ...prev, [key]: e.target.value }));
    setFormError("");
  };

  const handleSave = async () => {
    if (Number(form.warn_before_ms) >= Number(form.inactivity_ms)) {
      setFormError(t("settings.warningValidation"));
      return;
    }
    setSaving(true);
    try {
      await update({
        ...Object.fromEntries(FIELDS.map(({ key }) => [key, toMs(form[key])])),
        update_check_enabled: form.update_check_enabled,
      });
      enqueueSnackbar(t("settings.saved"), { variant: "success" });
      onClose();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const dirty = isDirty(form, settings);

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t("settings.title")}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          {FIELDS.map(({ key, labelKey, tooltipKey, min, max }) => (
            <TextField
              key={key}
              label={t(labelKey)}
              type="number"
              size="small"
              value={form[key]}
              onChange={handleChange(key)}
              fullWidth
              slotProps={{
                htmlInput: { min, max, step: 1 },
                input: {
                  endAdornment: (
                    <InputAdornment position="end">
                      <Typography variant="caption" sx={{ color: "text.disabled", mr: 0.5 }}>
                        {t("common.labels.secondsShort")}
                      </Typography>
                      <Tooltip title={t(tooltipKey)} arrow placement="top">
                        <HelpOutlineIcon
                          fontSize="small"
                          sx={{ color: "text.disabled", cursor: "help" }}
                        />
                      </Tooltip>
                    </InputAdornment>
                  ),
                },
              }}
            />
          ))}
          <Divider sx={{ my: 0.5 }} />
          <Button variant="outlined" onClick={() => setPasswordOpen(true)}>
            {t("auth.changePassword")}
          </Button>
          <Divider sx={{ my: 0.5 }} />
          <FormControlLabel
            sx={{ ml: 0, justifyContent: "space-between" }}
            labelPlacement="start"
            control={
              <Switch
                checked={form.update_check_enabled}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    update_check_enabled: e.target.checked,
                  }))
                }
              />
            }
            label={
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Typography variant="body2">{t("settings.fields.updates")}</Typography>
                <Tooltip title={t("settings.fields.updatesHelp")} arrow placement="top">
                  <HelpOutlineIcon
                    fontSize="small"
                    sx={{ color: "text.disabled", cursor: "help" }}
                  />
                </Tooltip>
              </Stack>
            }
          />
          {formError && (
            <Typography variant="body2" color="error">
              {formError}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          {t("common.actions.cancel")}
        </Button>
        <Button variant="contained" onClick={handleSave} loading={saving} disabled={!dirty}>
          {t("common.actions.save")}
        </Button>
      </DialogActions>
      <PasswordChangeDialog
        open={passwordOpen}
        onClose={() => setPasswordOpen(false)}
      />
    </Dialog>
  );
};

export default SettingsModal;

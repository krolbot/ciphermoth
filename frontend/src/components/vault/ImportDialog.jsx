import { useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  Radio,
  RadioGroup,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { Trans, useTranslation } from "react-i18next";

import PasswordField from "../PasswordField";

const ImportResult = ({ result }) => {
  const { t } = useTranslation();
  if (result.total === 0) {
    return (
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        {t("importDialog.noPasswords")}
      </Typography>
    );
  }
  return (
    <>
      {result.imported > 0 && (
        <Typography variant="body2">
          <Trans
            i18nKey="importDialog.imported"
            count={result.imported}
            values={{ count: result.imported }}
            components={{ strong: <strong /> }}
          />
        </Typography>
      )}
      {result.overwritten > 0 && (
        <Typography variant="body2">
          <Trans
            i18nKey="importDialog.overwritten"
            count={result.overwritten}
            values={{ count: result.overwritten }}
            components={{ strong: <strong /> }}
          />
        </Typography>
      )}
      {result.skipped > 0 && (
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          <Trans
            i18nKey="importDialog.skipped"
            count={result.skipped}
            values={{ count: result.skipped }}
            components={{ strong: <strong /> }}
          />
        </Typography>
      )}
    </>
  );
};

const ImportDialog = ({ open, onClose, onImport, onImportCsv }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState("ciphermoth");
  const [file, setFile] = useState(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [onConflict, setOnConflict] = useState("skip");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (open) {
      setMode("ciphermoth");
      setFile(null);
      setPassword("");
      setError("");
      setOnConflict("skip");
      setResult(null);
    }
  }, [open]);

  const isCsv = mode === "csv";

  const changeMode = (_, next) => {
    if (!next) return;
    setMode(next);
    setFile(null);
    setError("");
  };

  const handleImport = async () => {
    if (!file) {
      setError(t(isCsv ? "importDialog.selectCsv" : "importDialog.selectBackup"));
      return;
    }
    if (!isCsv && !password.trim()) {
      setError(t("backup.passwordRequired"));
      return;
    }
    setLoading(true);
    try {
      const data = isCsv
        ? await onImportCsv({ file, onConflict })
        : await onImport({ file, masterPassword: password, onConflict });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={loading ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t(result ? "importDialog.completeTitle" : "importDialog.title")}</DialogTitle>
      <DialogContent>
        {result ? (
          <Stack spacing={1} sx={{ mt: 1 }}>
            <ImportResult result={result} />
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <ToggleButtonGroup value={mode} exclusive onChange={changeMode} size="small" fullWidth>
              <ToggleButton value="ciphermoth" sx={{ textTransform: "none" }}>
                {t("importDialog.backupMode")}
              </ToggleButton>
              <ToggleButton value="csv" sx={{ textTransform: "none" }}>
                {t("importDialog.csvMode")}
              </ToggleButton>
            </ToggleButtonGroup>

            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {t(isCsv ? "importDialog.csvDescription" : "importDialog.backupDescription")}
            </Typography>

            <Button
              component="label"
              variant="outlined"
              startIcon={<UploadFileIcon />}
              fullWidth
              sx={{ justifyContent: "flex-start", textTransform: "none" }}
            >
              {file ? file.name : t(isCsv ? "importDialog.chooseCsv" : "importDialog.chooseBackup")}
              <input
                type="file"
                hidden
                accept={isCsv ? ".csv" : ".zip"}
                onChange={(e) => {
                  setFile(e.target.files[0] ?? null);
                  setError("");
                }}
              />
            </Button>

            {!isCsv && (
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
                  if (e.key === "Enter") handleImport();
                }}
              />
            )}

            {isCsv && error && (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            )}

            <FormControl>
              <FormLabel sx={{ fontSize: "0.875rem" }}>{t("importDialog.existingLabel")}</FormLabel>
              <RadioGroup value={onConflict} onChange={(e) => setOnConflict(e.target.value)}>
                <FormControlLabel
                  value="skip"
                  control={<Radio size="small" />}
                  label={t("importDialog.keepExisting")}
                />
                <FormControlLabel
                  value="overwrite"
                  control={<Radio size="small" />}
                  label={t("importDialog.overwrite")}
                />
              </RadioGroup>
            </FormControl>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {result ? (
          <Button variant="contained" onClick={onClose}>
            {t("common.actions.done")}
          </Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={loading}>
              {t("common.actions.cancel")}
            </Button>
            <Button variant="contained" onClick={handleImport} loading={loading}>
              {t("common.actions.import")}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default ImportDialog;

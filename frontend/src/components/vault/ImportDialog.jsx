import { useEffect, useState } from "react";
import {
  Box,
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

import { IS_DESKTOP, chooseBackup } from "../../platform";
import PasswordField from "../PasswordField";

const ReportedRows = ({ rows = [], count, titleKey, color }) => {
  const { t } = useTranslation();
  const hidden = count - rows.length;
  return (
    <>
      <Typography variant="body2" sx={{ color, mt: 1 }}>
        <strong>{count}</strong> {t(titleKey, { count })}
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5, maxHeight: 160, overflowY: "auto" }}>
        {rows.map((row) => (
          <Typography component="li" variant="body2" key={row.where}>
            {row.where}
            {row.name ? ` (${row.name})` : ""}: {row.reason}
          </Typography>
        ))}
        {hidden > 0 && (
          <Typography component="li" variant="body2">
            {t("importDialog.andMore", { count: hidden })}
          </Typography>
        )}
      </Box>
    </>
  );
};

const restoredExtras = (result, t) =>
  [
    result.trashed > 0 && t("importDialog.restoredExtras.trash", { count: result.trashed }),
    result.attachments > 0 &&
      t("importDialog.restoredExtras.attachments", { count: result.attachments }),
    result.grants_restored > 0 &&
      t("importDialog.restoredExtras.grants", { count: result.grants_restored }),
    result.settings_restored && t("importDialog.restoredExtras.settings"),
  ].filter(Boolean);

const ImportResult = ({ result }) => {
  const { t } = useTranslation();
  const extras = restoredExtras(result, t);
  if (result.total === 0 && !result.ignored && extras.length === 0) {
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
      {extras.length > 0 && (
        <Typography variant="body2">
          {t("importDialog.alsoRestored", { items: extras.join(", ") })}
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
      {result.renamed > 0 && (
        <ReportedRows
          rows={result.renamed_rows}
          count={result.renamed}
          titleKey="importDialog.renamed"
          color="text.secondary"
        />
      )}
      {result.ignored > 0 && (
        <ReportedRows
          rows={result.ignored_rows}
          count={result.ignored}
          titleKey="importDialog.ignored"
          color="warning.main"
        />
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
      setError(t("importDialog.enterBackupPassword"));
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
      // Native selections are single-use grants; a retry needs a fresh picker.
      if (IS_DESKTOP && !isCsv) setFile(null);
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
              {isCsv ? t("importDialog.csvDescription") : t("importDialog.backupDescription")}
            </Typography>

            <Button
              component={IS_DESKTOP && !isCsv ? "button" : "label"}
              onClick={
                IS_DESKTOP && !isCsv
                  ? async () => {
                      try {
                        setFile(await chooseBackup());
                        setError("");
                      } catch {
                        setError(t("importDialog.filePickerError"));
                      }
                    }
                  : undefined
              }
              variant="outlined"
              startIcon={<UploadFileIcon />}
              fullWidth
              sx={{ justifyContent: "flex-start", textTransform: "none" }}
            >
              {file ? file.name : t(isCsv ? "importDialog.chooseCsv" : "importDialog.chooseBackup")}
              {(!IS_DESKTOP || isCsv) && (
                <input
                  type="file"
                  hidden
                  accept={isCsv ? ".csv" : ".cmbackup,.zip"}
                  onChange={(e) => {
                    setFile(e.target.files[0] ?? null);
                    setError("");
                  }}
                />
              )}
            </Button>

            {!isCsv && (
              <PasswordField
                label={t("importDialog.backupPassword")}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError("");
                }}
                error={!!error}
                helperText={error || t("importDialog.backupPasswordHelp")}
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

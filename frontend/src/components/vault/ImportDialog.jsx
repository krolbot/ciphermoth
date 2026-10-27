import { useEffect, useState } from "react";
import { FileArrowUp } from "@gravity-ui/icons";
import { Alert, Button, Dialog, Icon, RadioGroup, SegmentedRadioGroup } from "@gravity-ui/uikit";
import { Trans, useTranslation } from "react-i18next";

import { IS_DESKTOP, chooseBackup } from "../../platform";
import PasswordField from "../PasswordField";

const ReportedRows = ({ rows = [], count, titleKey, warning = false }) => {
  const { t } = useTranslation();
  const hidden = count - rows.length;
  return (
    <div
      className={warning ? "cm-import-result__reported is-warning" : "cm-import-result__reported"}
    >
      <p>
        <strong>{count}</strong> {t(titleKey, { count })}
      </p>
      <ul>
        {rows.map((row) => (
          <li key={row.where}>
            {row.where}
            {row.name ? ` (${row.name})` : ""}: {row.reason}
          </li>
        ))}
        {hidden > 0 && <li>{t("importDialog.andMore", { count: hidden })}</li>}
      </ul>
    </div>
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
    return <p className="cm-secondary-copy">{t("importDialog.noPasswords")}</p>;
  }
  return (
    <div className="cm-import-result">
      {result.imported > 0 && (
        <p>
          <Trans
            i18nKey="importDialog.imported"
            count={result.imported}
            values={{ count: result.imported }}
            components={{ strong: <strong /> }}
          />
        </p>
      )}
      {result.overwritten > 0 && (
        <p>
          <Trans
            i18nKey="importDialog.overwritten"
            count={result.overwritten}
            values={{ count: result.overwritten }}
            components={{ strong: <strong /> }}
          />
        </p>
      )}
      {extras.length > 0 && <p>{t("importDialog.alsoRestored", { items: extras.join(", ") })}</p>}
      {result.skipped > 0 && (
        <p className="cm-secondary-copy">
          <Trans
            i18nKey="importDialog.skipped"
            count={result.skipped}
            values={{ count: result.skipped }}
            components={{ strong: <strong /> }}
          />
        </p>
      )}
      {result.renamed > 0 && (
        <ReportedRows
          rows={result.renamed_rows}
          count={result.renamed}
          titleKey="importDialog.renamed"
        />
      )}
      {result.ignored > 0 && (
        <ReportedRows
          rows={result.ignored_rows}
          count={result.ignored}
          titleKey="importDialog.ignored"
          warning
        />
      )}
    </div>
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

  const changeMode = (next) => {
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
    setError("");
    try {
      const data = isCsv
        ? await onImportCsv({ file, onConflict })
        : await onImport({ file, masterPassword: password, onConflict });
      setResult(data);
    } catch (requestError) {
      setError(requestError.message);
      if (IS_DESKTOP && !isCsv) setFile(null);
    } finally {
      setLoading(false);
    }
  };

  const chooseFile = async () => {
    try {
      setFile(await chooseBackup());
      setError("");
    } catch {
      setError(t("importDialog.filePickerError"));
    }
  };

  return (
    <Dialog
      aria-label={t(result ? "importDialog.completeTitle" : "importDialog.title")}
      className="cm-secondary-dialog cm-import-dialog"
      contentOverflow="auto"
      fullWidth
      hasCloseButton={!loading}
      maxWidth="s"
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !loading) onClose();
      }}
    >
      <Dialog.Header caption={t(result ? "importDialog.completeTitle" : "importDialog.title")} />
      <Dialog.Body>
        {result ? (
          <ImportResult result={result} />
        ) : (
          <div className="cm-import-form">
            <SegmentedRadioGroup name="import-mode" width="max" value={mode} onUpdate={changeMode}>
              <SegmentedRadioGroup.Option value="ciphermoth">
                {t("importDialog.backupMode")}
              </SegmentedRadioGroup.Option>
              <SegmentedRadioGroup.Option value="csv">
                {t("importDialog.csvMode")}
              </SegmentedRadioGroup.Option>
            </SegmentedRadioGroup>

            <p className="cm-secondary-copy">
              {isCsv ? t("importDialog.csvDescription") : t("importDialog.backupDescription")}
            </p>

            <Button
              type="button"
              component={IS_DESKTOP && !isCsv ? "button" : "label"}
              view="outlined"
              size="l"
              width="max"
              onClick={IS_DESKTOP && !isCsv ? chooseFile : undefined}
            >
              <Icon data={FileArrowUp} />
              <span className="cm-import-form__filename">
                {file
                  ? file.name
                  : t(isCsv ? "importDialog.chooseCsv" : "importDialog.chooseBackup")}
              </span>
              {(!IS_DESKTOP || isCsv) && (
                <input
                  type="file"
                  hidden
                  accept={isCsv ? ".csv" : ".cmbackup,.zip"}
                  onChange={(event) => {
                    setFile(event.target.files[0] ?? null);
                    setError("");
                  }}
                />
              )}
            </Button>

            {!isCsv && (
              <PasswordField
                label={t("importDialog.backupPassword")}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setError("");
                }}
                error={Boolean(error)}
                helperText={error || t("importDialog.backupPasswordHelp")}
                required
                autoFocus
                autoComplete="current-password"
                onKeyDown={(event) => {
                  if (event.key === "Enter") handleImport();
                }}
              />
            )}

            {isCsv && error && <Alert theme="danger" view="outlined" message={error} />}

            <fieldset className="cm-import-form__conflict">
              <legend>{t("importDialog.existingLabel")}</legend>
              <RadioGroup
                direction="vertical"
                value={onConflict}
                onUpdate={setOnConflict}
                options={[
                  { value: "skip", content: t("importDialog.keepExisting") },
                  { value: "overwrite", content: t("importDialog.overwrite") },
                ]}
              />
            </fieldset>
          </div>
        )}
      </Dialog.Body>
      <Dialog.Footer
        onClickButtonApply={result ? onClose : handleImport}
        onClickButtonCancel={result ? undefined : onClose}
        textButtonApply={t(result ? "common.actions.done" : "common.actions.import")}
        textButtonCancel={result ? undefined : t("common.actions.cancel")}
        propsButtonApply={{ loading, disabled: loading, view: "action" }}
        propsButtonCancel={{ disabled: loading }}
      />
    </Dialog>
  );
};

export default ImportDialog;

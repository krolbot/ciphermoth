import { Dialog, Label } from "@gravity-ui/uikit";
import { useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { MANUAL_UPDATE_COMMAND } from "../lib/updateCommands";
import { IS_DESKTOP } from "../platform";
import DesktopUpdateDialog from "./DesktopUpdateDialog";

const stripV = (value) => String(value ?? "").replace(/^v/, "");

const UpdateDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const { current, latest, releaseUrl } = useStoreState((state) => state.ciphermothModels.updates);

  return (
    <Dialog
      aria-label={t("updateDialog.title")}
      className="cm-secondary-dialog cm-update-dialog"
      contentOverflow="auto"
      fullWidth
      maxWidth="s"
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <Dialog.Header caption={t("updateDialog.title")} />
      <Dialog.Body>
        <div className="cm-update-dialog__content">
          <div className="cm-update-dialog__versions" aria-label={t("updateDialog.title")}>
            <Label size="s">{current ? `v${stripV(current)}` : "-"}</Label>
            <span aria-hidden="true">→</span>
            <Label size="s" theme="success">
              {latest ?? "-"}
            </Label>
          </div>

          {releaseUrl && (
            <a
              className="cm-inline-link"
              href={releaseUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("updateDialog.releaseNotes")}
            </a>
          )}

          <div>
            <p className="cm-secondary-copy">{t("updateDialog.manualBackupDescription")}</p>
            <pre className="cm-command-block">{MANUAL_UPDATE_COMMAND}</pre>
          </div>
        </div>
      </Dialog.Body>
      <Dialog.Footer
        onClickButtonApply={onClose}
        textButtonApply={t("common.actions.close")}
        propsButtonApply={{ view: "action" }}
      />
    </Dialog>
  );
};

export default IS_DESKTOP ? DesktopUpdateDialog : UpdateDialog;

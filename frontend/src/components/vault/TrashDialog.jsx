import { useId, useState } from "react";
import { ArrowUturnCcwLeft, TrashBin } from "@gravity-ui/icons";
import { Button, Dialog, Icon, Tooltip } from "@gravity-ui/uikit";
import { Trans, useTranslation } from "react-i18next";

import ConfirmDialog from "../ConfirmDialog";

const formatDeleted = (iso, language) => {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(language);
};

const TrashDialog = ({ open, trash, onClose, onRestore, onPurge }) => {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const [purgeTarget, setPurgeTarget] = useState(null);
  const [purgeError, setPurgeError] = useState("");
  const [pendingId, setPendingId] = useState(null);

  const handleRestore = async (entry) => {
    setPendingId(entry.id);
    try {
      await onRestore({ passwordName: entry.password_name, entryId: entry.id });
    } catch {
      // The parent reports the request error; keep this dialog open for retry.
    } finally {
      setPendingId(null);
    }
  };

  const handlePurge = async () => {
    setPurgeError("");
    setPendingId(purgeTarget.id);
    try {
      await onPurge({ passwordName: purgeTarget.password_name, entryId: purgeTarget.id });
      setPurgeTarget(null);
    } catch {
      setPurgeError(t("trashDialog.purgeFailed"));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <Dialog
      aria-labelledby={titleId}
      className="cm-secondary-dialog cm-secondary-dialog--trash"
      contentOverflow="auto"
      fullWidth
      hasCloseButton={false}
      maxWidth="m"
      modalClassName="cm-secondary-dialog-modal"
      onOpenChange={(nextOpen) => {
        if (!nextOpen && pendingId === null) onClose();
      }}
      open={open}
    >
      <Dialog.Header caption={t("vault.trash")} id={titleId} />
      <Dialog.Body hasBorders>
        {trash.length === 0 ? (
          <p className="cm-trash__empty">{t("trashDialog.empty")}</p>
        ) : (
          <ul aria-label={t("vault.trash")} className="cm-trash__list">
            {trash.map((entry) => (
              <li className="cm-trash__row" key={entry.id}>
                <div className="cm-trash__details">
                  <span className="cm-trash__name">{entry.password_name}</span>
                  {entry.username && <span className="cm-trash__username">{entry.username}</span>}
                  <span className="cm-trash__deleted">
                    {t("trashDialog.deleted")}:{" "}
                    {formatDeleted(entry.deleted, i18n.resolvedLanguage)}
                  </span>
                </div>
                <div className="cm-trash__actions">
                  <Tooltip content={t("trashDialog.restore")} role="label">
                    <Button
                      aria-label={`${t("trashDialog.restore")}: ${entry.password_name}`}
                      className="cm-trash__action"
                      disabled={pendingId !== null}
                      loading={pendingId === entry.id && !purgeTarget}
                      onClick={() => handleRestore(entry)}
                      size="l"
                      type="button"
                      view="flat"
                    >
                      <Icon data={ArrowUturnCcwLeft} />
                    </Button>
                  </Tooltip>
                  <Tooltip content={t("trashDialog.deleteForever")} role="label">
                    <Button
                      aria-label={`${t("trashDialog.deleteForever")}: ${entry.password_name}`}
                      className="cm-trash__action"
                      disabled={pendingId !== null}
                      onClick={() => {
                        setPurgeError("");
                        setPurgeTarget(entry);
                      }}
                      size="l"
                      type="button"
                      view="flat-danger"
                    >
                      <Icon data={TrashBin} />
                    </Button>
                  </Tooltip>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Dialog.Body>
      <Dialog.Footer
        onClickButtonCancel={onClose}
        propsButtonCancel={{ disabled: pendingId !== null }}
        textButtonCancel={t("common.actions.close")}
      />
      <ConfirmDialog
        confirmColor="error"
        confirmText={t(purgeError ? "common.actions.retry" : "trashDialog.deleteForever")}
        error={purgeError}
        onClose={() => {
          setPurgeError("");
          setPurgeTarget(null);
        }}
        onConfirm={handlePurge}
        open={Boolean(purgeTarget)}
        pending={pendingId !== null}
        title={t("trashDialog.deleteForeverTitle")}
      >
        <Trans
          components={{ strong: <strong /> }}
          i18nKey="trashDialog.deleteForeverMessage"
          values={{ name: purgeTarget?.password_name }}
        />
      </ConfirmDialog>
    </Dialog>
  );
};

export default TrashDialog;

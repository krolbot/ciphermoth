import { useCallback, useEffect, useRef, useState } from "react";
import { FileArrowDown, Paperclip, TrashBin } from "@gravity-ui/icons";
import { Button, Icon, Tooltip } from "@gravity-ui/uikit";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { useSnackbar } from "../../hooks/useNotify";
import ConfirmDialog from "../ConfirmDialog";

const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;

const formatBytes = (bytes, language) => {
  const formatter = new Intl.NumberFormat(language, { maximumFractionDigits: 1 });
  if (bytes < 1024) return `${formatter.format(bytes)} B`;
  if (bytes < 1024 * 1024) return `${formatter.format(bytes / 1024)} KB`;
  return `${formatter.format(bytes / (1024 * 1024))} MB`;
};

const AttachmentsSection = ({ passwordName, onChanged, readOnly = false }) => {
  const { t, i18n } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const fetchAttachments = useStoreActions((a) => a.ciphermothModels.passwords.fetchAttachments);
  const uploadAttachment = useStoreActions((a) => a.ciphermothModels.passwords.uploadAttachment);
  const downloadAttachment = useStoreActions(
    (a) => a.ciphermothModels.passwords.downloadAttachment
  );
  const deleteAttachment = useStoreActions((a) => a.ciphermothModels.passwords.deleteAttachment);

  const [attachments, setAttachments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const inputRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      setAttachments(await fetchAttachments(passwordName));
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
    }
  }, [fetchAttachments, passwordName, enqueueSnackbar]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleFiles = async (files) => {
    setBusy(true);
    try {
      for (const file of files) {
        if (file.size > MAX_ATTACHMENT_BYTES) {
          enqueueSnackbar(t("attachments.tooLarge", { filename: file.name }), {
            variant: "warning",
          });
          continue;
        }
        await uploadAttachment({ passwordName, file });
        enqueueSnackbar(t("attachments.attached", { filename: file.name }), {
          variant: "success",
        });
        onChanged?.();
      }
      await refresh();
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  const onPick = (event) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length) handleFiles(files);
  };

  const onDownload = async (attachment) => {
    try {
      await downloadAttachment({
        passwordName,
        attachmentId: attachment.id,
        filename: attachment.filename,
      });
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
    }
  };

  const confirmDelete = async () => {
    const attachment = pendingDelete;
    try {
      await deleteAttachment({ passwordName, attachmentId: attachment.id });
      setPendingDelete(null);
      enqueueSnackbar(t("attachments.removed", { filename: attachment.filename }), {
        variant: "success",
      });
      onChanged?.();
      await refresh();
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
    }
  };

  return (
    <div className="cm-attachments">
      {attachments.length === 0 ? (
        <p className="cm-attachments__empty">{t("attachments.empty")}</p>
      ) : (
        <ul className="cm-attachments__list">
          {attachments.map((attachment) => (
            <li className="cm-attachments__row" key={attachment.id}>
              <Icon data={Paperclip} size={16} className="cm-attachments__file-icon" />
              <span className="cm-attachments__filename">{attachment.filename}</span>
              <span className="cm-attachments__size">
                {formatBytes(attachment.size_bytes, i18n.resolvedLanguage)}
              </span>
              <Tooltip content={t("common.actions.download")}>
                <Button
                  type="button"
                  size="s"
                  view="flat-secondary"
                  onClick={() => onDownload(attachment)}
                  aria-label={t("common.actions.download")}
                >
                  <Icon data={FileArrowDown} />
                </Button>
              </Tooltip>
              {!readOnly && (
                <Tooltip content={t("attachments.removeFile")}>
                  <Button
                    type="button"
                    size="s"
                    view="flat-danger"
                    onClick={() => setPendingDelete(attachment)}
                    aria-label={t("attachments.removeFile")}
                  >
                    <Icon data={TrashBin} />
                  </Button>
                </Tooltip>
              )}
            </li>
          ))}
        </ul>
      )}

      {!readOnly && (
        <div className="cm-attachments__upload">
          <input ref={inputRef} type="file" multiple hidden onChange={onPick} />
          <Button
            type="button"
            size="m"
            view="outlined"
            onClick={() => inputRef.current?.click()}
            loading={busy}
          >
            <Icon data={Paperclip} />
            {t("attachments.attachFile")}
          </Button>
          <span>{t("attachments.limits")}</span>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={t("attachments.removeTitle")}
        onClose={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
        confirmText={t("common.actions.remove")}
        confirmColor="error"
      >
        {t("attachments.removeMessage", { filename: pendingDelete?.filename })}
      </ConfirmDialog>
    </div>
  );
};

export default AttachmentsSection;

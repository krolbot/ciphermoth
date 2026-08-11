import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import { useSnackbar } from "notistack";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

import ConfirmDialog from "../ConfirmDialog";

const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;

const formatBytes = (bytes, language) => {
  const formatter = new Intl.NumberFormat(language, { maximumFractionDigits: 1 });
  if (bytes < 1024) return `${formatter.format(bytes)} B`;
  if (bytes < 1024 * 1024) return `${formatter.format(bytes / 1024)} KB`;
  return `${formatter.format(bytes / (1024 * 1024))} MB`;
};

const AttachmentsSection = ({ passwordName, onChanged }) => {
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
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
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
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  const onPick = (e) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length) handleFiles(files);
  };

  const onDownload = async (att) => {
    try {
      await downloadAttachment({
        passwordName,
        attachmentId: att.id,
        filename: att.filename,
      });
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  const confirmDelete = async () => {
    const att = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteAttachment({ passwordName, attachmentId: att.id });
      enqueueSnackbar(t("attachments.removed", { filename: att.filename }), {
        variant: "success",
      });
      onChanged?.();
      await refresh();
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  return (
    <Stack spacing={1}>
      {attachments.length === 0 ? (
        <Typography variant="body2" sx={{ color: "text.disabled" }}>
          {t("attachments.empty")}
        </Typography>
      ) : (
        attachments.map((att) => (
          <Stack key={att.id} direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <AttachFileIcon fontSize="small" sx={{ color: "text.disabled" }} />
            <Typography
              variant="body2"
              sx={{
                flex: 1,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {att.filename}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.disabled", flexShrink: 0 }}>
              {formatBytes(att.size_bytes, i18n.resolvedLanguage)}
            </Typography>
            <Tooltip title={t("common.actions.download")}>
              <IconButton size="small" onClick={() => onDownload(att)}>
                <FileDownloadOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title={t("attachments.removeFile")}>
              <IconButton size="small" color="error" onClick={() => setPendingDelete(att)}>
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        ))
      )}

      <Box>
        <input ref={inputRef} type="file" multiple hidden onChange={onPick} />
        <Button
          size="small"
          startIcon={<AttachFileIcon />}
          onClick={() => inputRef.current?.click()}
          loading={busy}
        >
          {t("attachments.attachFile")}
        </Button>
        <Typography variant="caption" sx={{ color: "text.disabled", ml: 1 }}>
          {t("attachments.limits")}
        </Typography>
      </Box>

      <ConfirmDialog
        open={!!pendingDelete}
        title={t("attachments.removeTitle")}
        onClose={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
        confirmText={t("common.actions.remove")}
        confirmColor="error"
      >
        {t("attachments.removeMessage", { filename: pendingDelete?.filename })}
      </ConfirmDialog>
    </Stack>
  );
};

export default AttachmentsSection;

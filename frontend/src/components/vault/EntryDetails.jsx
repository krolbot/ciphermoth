import { useState } from "react";
import { Box, Button, Chip, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import ShareOutlinedIcon from "@mui/icons-material/ShareOutlined";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { useTranslation } from "react-i18next";

import AttachmentsSection from "./AttachmentsSection";
import StrengthBar from "./StrengthBar";
import TotpCell from "./TotpCell";
import { IS_DESKTOP, openExternal } from "../../platform";

const EntryValue = ({
  label,
  value,
  hidden = false,
  mono = false,
  onCopy,
  copyLabel,
  revealLabel,
  hideLabel,
  children,
}) => {
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(false);
  const visibilityLabel = revealed
    ? hideLabel || `${t("passwordField.hide")}: ${label}`
    : revealLabel || `${t("passwordField.show")}: ${label}`;
  return (
    <Box sx={{ py: 1.5, borderBottom: "1px solid", borderColor: "divider", minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Stack direction="row" spacing={0.5} sx={{ alignItems: "flex-start", minWidth: 0 }}>
        <Typography
          sx={{
            flex: 1,
            minWidth: 0,
            py: 1,
            overflowWrap: "anywhere",
            whiteSpace: "pre-wrap",
            fontFamily: mono ? "fontFamilyMonospace" : undefined,
          }}
        >
          {hidden && !revealed ? "••••••••••••" : value}
        </Typography>
        {hidden && (
          <Tooltip title={visibilityLabel}>
            <IconButton
              aria-label={visibilityLabel}
              onClick={() => setRevealed((v) => !v)}
              sx={{ width: 44, height: 44 }}
            >
              {revealed ? (
                <VisibilityOffIcon fontSize="small" />
              ) : (
                <VisibilityIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title={copyLabel || t("vault.browser.copyValue", { label })}>
          <IconButton
            aria-label={copyLabel || t("vault.browser.copyValue", { label })}
            onClick={() => onCopy(value)}
            sx={{ width: 44, height: 44 }}
          >
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
      {children}
    </Box>
  );
};

const EntryDetails = ({ entry, onClose, onCopy, onEdit, onDelete, onShare, onToggleFavorite }) => {
  const { t, i18n } = useTranslation();
  const isNote = entry.kind === "note";
  const writable = entry.access === "owner" || entry.access === "write";
  const history = entry.password_history ?? [];
  const openWebsite = () => {
    const url = /^https?:\/\//i.test(entry.url) ? entry.url : `https://${entry.url}`;
    if (IS_DESKTOP) openExternal(url).catch(() => {});
    else window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <Box
      sx={{
        minWidth: 0,
        p: { xs: 2, sm: 3 },
        "& summary": { cursor: "pointer", py: 1.5, fontWeight: 600, overflowWrap: "anywhere" },
        "& summary:focus-visible": {
          outline: "2px solid",
          outlineColor: "primary.main",
          outlineOffset: 2,
        },
      }}
    >
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 2 }}>
        {onClose ? (
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={onClose}
            sx={{ minHeight: 44, textTransform: "none" }}
          >
            {t("vault.browser.back")}
          </Button>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t(isNote ? "entry.kind.note" : "entry.kind.login")}
          </Typography>
        )}
        {writable && (
          <Tooltip
            title={t(
              entry.favorite ? "vault.columns.removeFavorite" : "vault.columns.markFavorite"
            )}
          >
            <IconButton
              aria-label={t(
                entry.favorite ? "vault.columns.removeFavorite" : "vault.columns.markFavorite"
              )}
              onClick={() => onToggleFavorite(entry)}
              sx={{ width: 44, height: 44 }}
            >
              {entry.favorite ? <StarIcon color="secondary" /> : <StarBorderIcon />}
            </IconButton>
          </Tooltip>
        )}
      </Stack>
      <Typography
        id="entry-detail-title"
        component="h2"
        variant="h5"
        sx={{ overflowWrap: "anywhere", lineHeight: 1.3 }}
      >
        {entry.password_name}
      </Typography>
      {(entry.folder || entry.access !== "owner") && (
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", mt: 1 }}>
          {entry.folder && (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ overflowWrap: "anywhere", minWidth: 0 }}
            >
              {entry.folder}
            </Typography>
          )}
          {entry.access !== "owner" && (
            <Chip
              size="small"
              variant="outlined"
              label={t(entry.access === "read" ? "sharing.readOnlyAccess" : "sharing.readWrite")}
            />
          )}
        </Stack>
      )}
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", mt: 2, mb: 1 }}>
        {writable && (
          <Button
            variant="outlined"
            startIcon={<EditOutlinedIcon />}
            onClick={() => onEdit(entry)}
            sx={{ minHeight: 44, textTransform: "none" }}
          >
            {t("common.actions.edit")}
          </Button>
        )}
        {entry.access === "owner" && (
          <Button
            startIcon={<ShareOutlinedIcon />}
            onClick={() => onShare(entry)}
            sx={{ minHeight: 44, textTransform: "none" }}
          >
            {t("sharing.manage")}
          </Button>
        )}
      </Stack>

      {!isNote && entry.username && (
        <EntryValue
          label={t("common.fields.usernameEmail")}
          value={entry.username}
          copyLabel={t("vault.columns.copyUsername")}
          onCopy={onCopy}
        />
      )}
      <EntryValue
        label={t(isNote ? "entry.labels.note" : "common.fields.password")}
        value={entry.password_value}
        hidden
        revealLabel={!isNote ? t("vault.columns.revealPassword") : undefined}
        hideLabel={!isNote ? t("vault.columns.hidePassword") : undefined}
        mono={!isNote}
        copyLabel={t(isNote ? "vault.browser.copyNote" : "vault.columns.copyPassword")}
        onCopy={onCopy}
      >
        {!isNote && <StrengthBar password={entry.password_value} />}
      </EntryValue>
      {!isNote && entry.totp_secret && (
        <Box sx={{ py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary">
            {t("entry.labels.twoFactor")}
          </Typography>
          <TotpCell secret={entry.totp_secret} onCopy={onCopy} />
        </Box>
      )}
      {entry.url && (
        <Box sx={{ py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary">
            {t("entry.labels.websiteOptional")}
          </Typography>
          <Button
            onClick={openWebsite}
            endIcon={<OpenInNewIcon fontSize="small" />}
            sx={{
              display: "flex",
              justifyContent: "flex-start",
              maxWidth: "100%",
              minHeight: 44,
              textTransform: "none",
              overflowWrap: "anywhere",
              textAlign: "left",
            }}
          >
            {entry.url}
          </Button>
        </Box>
      )}
      {entry.custom_fields?.map((field, index) => (
        <EntryValue
          key={index}
          label={field.label}
          value={field.value}
          hidden={field.hidden}
          onCopy={onCopy}
        />
      ))}
      {entry.description && (
        <Box sx={{ py: 2 }}>
          <Typography variant="caption" color="text.secondary">
            {t("entry.labels.notes")}
          </Typography>
          <Typography
            variant="body2"
            sx={{ mt: 0.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
          >
            {entry.description}
          </Typography>
        </Box>
      )}
      {entry.tags?.length > 0 && (
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", py: 2 }}>
          {entry.tags.map((tag) => (
            <Chip key={tag} size="small" variant="outlined" label={tag} sx={{ maxWidth: "100%" }} />
          ))}
        </Stack>
      )}
      {entry.attachment_count > 0 && (
        <Box component="details" sx={{ borderTop: "1px solid", borderColor: "divider" }}>
          <Box component="summary">
            {t("entry.labels.attachments")} ({entry.attachment_count})
          </Box>
          <AttachmentsSection passwordName={entry.password_name} readOnly />
        </Box>
      )}
      {!isNote && history.length > 0 && (
        <Box component="details" sx={{ borderTop: "1px solid", borderColor: "divider" }}>
          <Box component="summary">
            {t("entry.labels.passwordHistory")} ({history.length})
          </Box>
          {history.map((item, index) => (
            <EntryValue
              key={index}
              label={new Date(item.changed_at).toLocaleString(i18n.resolvedLanguage)}
              value={item.value}
              hidden
              mono
              onCopy={onCopy}
            />
          ))}
        </Box>
      )}
      {writable && (
        <Button
          color="error"
          startIcon={<DeleteOutlineIcon />}
          onClick={() => onDelete(entry.password_name)}
          sx={{ mt: 3, minHeight: 44, textTransform: "none" }}
        >
          {t("common.actions.delete")}
        </Button>
      )}
    </Box>
  );
};

export default EntryDetails;

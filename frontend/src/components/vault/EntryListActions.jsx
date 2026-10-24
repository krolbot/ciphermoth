import { useState } from "react";
import { Box, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PersonOutlinedIcon from "@mui/icons-material/PersonOutlined";
import ShareOutlinedIcon from "@mui/icons-material/ShareOutlined";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { useTranslation } from "react-i18next";

import TotpCell from "./TotpCell";
import { IS_DESKTOP, openExternal } from "../../platform";

const EntryListActions = ({ entry, onCopy, onEdit, onDelete, onShare, onToggleFavorite }) => {
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(false);
  const isNote = entry.kind === "note";
  const writable = entry.access === "owner" || entry.access === "write";
  const openWebsite = () => {
    const url = /^https?:\/\//i.test(entry.url) ? entry.url : `https://${entry.url}`;
    if (IS_DESKTOP) openExternal(url).catch(() => {});
    else window.open(url, "_blank", "noopener,noreferrer");
  };
  const buttons = [
    !isNote &&
      entry.username && [
        t("vault.columns.copyUsername"),
        PersonOutlinedIcon,
        () => onCopy(entry.username),
      ],
    [
      isNote
        ? `${t(revealed ? "passwordField.hide" : "passwordField.show")}: ${t("entry.labels.note")}`
        : t(revealed ? "vault.columns.hidePassword" : "vault.columns.revealPassword"),
      revealed ? VisibilityOffIcon : VisibilityIcon,
      () => setRevealed((value) => !value),
    ],
    [
      t(isNote ? "vault.browser.copyNote" : "vault.columns.copyPassword"),
      ContentCopyIcon,
      () => onCopy(entry.password_value),
    ],
    entry.url && [t("vault.columns.openWebsite"), OpenInNewIcon, openWebsite],
    writable && [
      t(entry.favorite ? "vault.columns.removeFavorite" : "vault.columns.markFavorite"),
      entry.favorite ? StarIcon : StarBorderIcon,
      () => onToggleFavorite(entry),
      entry.favorite ? "secondary" : "default",
    ],
    writable && [t("common.actions.edit"), EditOutlinedIcon, () => onEdit(entry)],
    entry.access === "owner" && [t("sharing.manage"), ShareOutlinedIcon, () => onShare(entry)],
    writable && [
      t("common.actions.delete"),
      DeleteOutlineIcon,
      () => onDelete(entry.password_name),
      "error",
    ],
  ].filter(Boolean);

  return (
    <Box sx={{ minWidth: 0, px: 1, pb: { xs: 1, md: 0 } }}>
      <Stack
        direction="row"
        useFlexGap
        sx={{ alignItems: "center", flexWrap: "wrap", justifyContent: { md: "flex-end" } }}
      >
        {!isNote && entry.totp_secret && <TotpCell secret={entry.totp_secret} onCopy={onCopy} />}
        {buttons.map(([label, Icon, onClick, color = "default"]) => (
          <Tooltip key={label} title={label}>
            <IconButton
              aria-label={`${label}: ${entry.password_name}`}
              color={color}
              onClick={onClick}
              sx={{ width: 44, height: 44 }}
            >
              <Icon fontSize="small" />
            </IconButton>
          </Tooltip>
        ))}
      </Stack>
      {revealed && (
        <Typography
          variant="body2"
          sx={{
            px: 1,
            py: 1,
            overflowWrap: "anywhere",
            whiteSpace: "pre-wrap",
            fontFamily: "fontFamilyMonospace",
          }}
        >
          {entry.password_value}
        </Typography>
      )}
    </Box>
  );
};

export default EntryListActions;

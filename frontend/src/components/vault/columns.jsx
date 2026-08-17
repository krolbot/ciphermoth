import { Box, Chip, Divider, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import GppBadIcon from "@mui/icons-material/GppBad";
import GppGoodIcon from "@mui/icons-material/GppGood";
import GppMaybeIcon from "@mui/icons-material/GppMaybe";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import HighlightOffIcon from "@mui/icons-material/HighlightOff";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import ShareIcon from "@mui/icons-material/Share";
import StickyNote2OutlinedIcon from "@mui/icons-material/StickyNote2Outlined";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { useTranslation } from "react-i18next";

import TotpCell from "./TotpCell";
import { getPasswordStrength } from "../../lib/passwordStrength";
import { GLOW } from "../../lib/brand";

const ValueCell = ({ text, mono = false, masked = false, color = "text.primary", actions }) => (
  <Box sx={{ display: "flex", alignItems: "center", width: "100%", minWidth: 0 }}>
    <Typography
      variant="body2"
      sx={{
        flex: 1,
        minWidth: 0,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        fontFamily: mono ? "'Space Mono', monospace" : undefined,
        letterSpacing: masked ? 2 : 0,
        color,
      }}
    >
      {text}
    </Typography>
    {actions && (
      <Box
        className="rowHoverActions"
        sx={{ display: "flex", alignItems: "center", flexShrink: 0, ml: 0.5 }}
      >
        {actions}
      </Box>
    )}
  </Box>
);

const CellActionButton = ({ title, onClick, children }) => (
  <Tooltip title={title}>
    <IconButton size="small" onClick={onClick} sx={{ p: 0.375 }}>
      {children}
    </IconButton>
  </Tooltip>
);

const openUrl = (url) => {
  const safe = /^https?:\/\//i.test(url) ? url : `https://${url}`;
  window.open(safe, "_blank", "noopener,noreferrer");
};

const strengthIconFor = (level) => {
  if (level <= 1) return GppBadIcon;
  if (level === 2) return GppMaybeIcon;
  return GppGoodIcon;
};

const StrengthIndicator = ({ password }) => {
  const { t } = useTranslation();
  const strength = getPasswordStrength(password);
  if (!strength) return null;
  const Icon = strengthIconFor(strength.level);
  return (
    <Tooltip
      title={
        <Box>
          <Typography variant="caption" sx={{ fontWeight: 700, color: strength.color }}>
            {t(strength.labelKey)}
          </Typography>
          <Typography variant="caption" sx={{ display: "block" }}>
            {strength.recommend
              ? t("vault.columns.updateRecommended")
              : t("vault.columns.looksGood")}
          </Typography>
        </Box>
      }
    >
      <Box sx={{ display: "flex", alignItems: "center" }}>
        <Icon fontSize="small" sx={{ color: strength.color }} />
      </Box>
    </Tooltip>
  );
};

export const createColumns = ({
  t,
  visibleRows,
  onToggleVisibility,
  onToggleFavorite,
  onCopy,
  onEdit,
  onDelete,
  onShare,
}) => [
  {
    field: "favorite",
    headerName: "",
    width: 48,
    sortable: false,
    align: "center",
    headerAlign: "center",
    renderCell: (params) => (
      <Tooltip
        title={t(params.value ? "vault.columns.removeFavorite" : "vault.columns.markFavorite")}
      >
        <span>
          <IconButton
            size="small"
            disabled={params.row.access === "read"}
            onClick={() => onToggleFavorite(params.row)}
          >
            {params.value ? (
              <StarIcon fontSize="small" sx={{ color: GLOW }} />
            ) : (
              <StarBorderIcon fontSize="small" sx={{ color: "text.disabled" }} />
            )}
          </IconButton>
        </span>
      </Tooltip>
    ),
  },
  {
    field: "password_name",
    headerName: t("common.fields.name"),
    flex: 1,
    minWidth: 130,
    renderCell: (params) => {
      const count = params.row.attachment_count ?? 0;
      const clip = count > 0 && (
        <Tooltip title={t("vault.columns.attachment", { count })}>
          <Stack direction="row" spacing={0.25} sx={{ alignItems: "center", flexShrink: 0 }}>
            <AttachFileIcon sx={{ fontSize: 15, color: "text.disabled" }} />
            <Typography variant="caption" sx={{ color: "text.disabled" }}>
              {count}
            </Typography>
          </Stack>
        </Tooltip>
      );
      return (
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", minWidth: 0 }}>
          {params.row.kind === "note" && (
            <Tooltip title={t("vault.columns.secureNote")}>
              <StickyNote2OutlinedIcon fontSize="small" sx={{ color: "text.disabled" }} />
            </Tooltip>
          )}
          <Typography
            variant="body2"
            sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {params.value}
          </Typography>
          {clip}
        </Stack>
      );
    },
  },
  {
    field: "folder",
    headerName: t("common.fields.folder"),
    flex: 0.7,
    minWidth: 110,
    renderCell: (params) =>
      params.value ? (
        <Typography
          variant="body2"
          sx={{
            color: "text.secondary",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {params.value}
        </Typography>
      ) : (
        <Typography variant="body2" sx={{ color: "text.disabled" }}>
          -
        </Typography>
      ),
  },
  {
    field: "username",
    headerName: t("common.fields.usernameEmail"),
    flex: 1,
    minWidth: 150,
    renderCell: (params) => {
      const value = params.value;
      return (
        <ValueCell
          text={value || "-"}
          color={value ? "text.primary" : "text.disabled"}
          actions={
            value ? (
              <CellActionButton
                title={t("vault.columns.copyUsername")}
                onClick={() => onCopy(value)}
              >
                <ContentCopyIcon fontSize="small" />
              </CellActionButton>
            ) : null
          }
        />
      );
    },
  },
  {
    field: "password_value",
    headerName: t("common.fields.password"),
    flex: 1,
    minWidth: 160,
    sortable: false,
    renderCell: (params) => {
      const id = params.row.id;
      const visible = visibleRows.has(id);
      return (
        <ValueCell
          mono
          masked={!visible}
          color="text.secondary"
          text={visible ? params.value : "••••••••"}
          actions={
            <>
              <CellActionButton
                title={t(visible ? "vault.columns.hidePassword" : "vault.columns.revealPassword")}
                onClick={() => onToggleVisibility(id)}
              >
                {visible ? (
                  <VisibilityOffIcon fontSize="small" />
                ) : (
                  <VisibilityIcon fontSize="small" />
                )}
              </CellActionButton>
              <CellActionButton
                title={t("vault.columns.copyPassword")}
                onClick={() => onCopy(params.value)}
              >
                <ContentCopyIcon fontSize="small" />
              </CellActionButton>
            </>
          }
        />
      );
    },
  },
  {
    field: "tags",
    headerName: t("common.fields.tags"),
    flex: 1,
    minWidth: 120,
    sortable: false,
    renderCell: (params) => {
      const tags = params.value ?? [];
      if (tags.length === 0) {
        return (
          <Typography variant="body2" sx={{ color: "text.disabled" }}>
            -
          </Typography>
        );
      }
      const shown = tags.slice(0, 2);
      const extra = tags.length - shown.length;
      return (
        <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", overflow: "hidden" }}>
          {shown.map((tag) => (
            <Chip key={tag} label={tag} size="small" variant="outlined" />
          ))}
          {extra > 0 && (
            <Tooltip title={tags.join(", ")}>
              <Chip label={`+${extra}`} size="small" />
            </Tooltip>
          )}
        </Stack>
      );
    },
  },
  {
    field: "totp_secret",
    headerName: t("vault.columns.twoFactor"),
    width: 118,
    sortable: false,
    renderCell: (params) =>
      params.value ? (
        <TotpCell secret={params.value} onCopy={onCopy} />
      ) : (
        <Typography variant="body2" sx={{ color: "text.disabled" }}>
          -
        </Typography>
      ),
  },
  {
    field: "owner_username",
    headerName: t("sharing.access"),
    width: 140,
    renderCell: (params) => (
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        {params.value} · {t(`sharing.${params.row.access}`)}
      </Typography>
    ),
  },
  {
    field: "actions",
    headerName: t("common.fields.actions"),
    width: 180,
    sortable: false,
    align: "center",
    headerAlign: "center",
    renderCell: (params) => {
      const { password_value, url, backed_up, kind, access } = params.row;
      const canWrite = access !== "read";
      const owner = access === "owner";
      return (
        <Stack direction="row" spacing={0} sx={{ alignItems: "center", height: "100%" }}>
          <Box sx={{ visibility: url ? "visible" : "hidden" }}>
            <Tooltip title={t("vault.columns.openWebsite")}>
              <IconButton size="small" onClick={() => url && openUrl(url)}>
                <OpenInNewIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          {canWrite && (
            <Tooltip title={t("common.actions.edit")}>
              <IconButton size="small" onClick={() => onEdit(params.row)}>
                <EditIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {owner && (
            <Tooltip title={t("sharing.manage")}>
              <IconButton size="small" onClick={() => onShare(params.row)}>
                <ShareIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {owner && (
            <Tooltip title={t("common.actions.delete")}>
              <IconButton size="small" color="error" onClick={() => onDelete(params.row)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5, my: 1 }} />
          {kind !== "note" && <StrengthIndicator password={password_value} />}
          <Tooltip
            title={t(
              backed_up ? "vault.columns.passwordBackedUp" : "vault.columns.passwordNotBackedUp"
            )}
          >
            <Box sx={{ display: "flex", alignItems: "center" }}>
              {backed_up ? (
                <CheckCircleOutlineIcon fontSize="small" sx={{ color: "success.main" }} />
              ) : (
                <HighlightOffIcon fontSize="small" sx={{ color: "warning.main" }} />
              )}
            </Box>
          </Tooltip>
        </Stack>
      );
    },
  },
];

import { Box, Chip, IconButton, Paper, Stack, Tooltip, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import GppBadIcon from "@mui/icons-material/GppBad";
import GppGoodIcon from "@mui/icons-material/GppGood";
import GppMaybeIcon from "@mui/icons-material/GppMaybe";
import HighlightOffIcon from "@mui/icons-material/HighlightOff";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import ShareIcon from "@mui/icons-material/Share";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import StickyNote2OutlinedIcon from "@mui/icons-material/StickyNote2Outlined";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { useTranslation } from "react-i18next";

import TotpCell from "./TotpCell";
import { GLOW } from "../../lib/brand";
import { getPasswordStrength } from "../../lib/passwordStrength";

const ActionButton = ({ label, color = "default", disabled = false, onClick, children }) => (
  <Tooltip title={label}>
    <span>
      <IconButton
        aria-label={label}
        color={color}
        disabled={disabled}
        size="small"
        onClick={onClick}
        sx={{ width: 40, height: 40 }}
      >
        {children}
      </IconButton>
    </span>
  </Tooltip>
);

const EmptyActionSlot = () => <Box aria-hidden sx={{ width: 40, height: 40, flexShrink: 0 }} />;
const EmptyIndicatorSlot = () => <Box aria-hidden sx={{ width: 20, height: 20, flexShrink: 0 }} />;

const ValueBlock = ({ label, value, monospace = false, actions }) => (
  <Box sx={{ minWidth: 0 }}>
    <Typography
      variant="caption"
      sx={{ color: "text.disabled", display: "block", lineHeight: 1.2, mb: 0.35 }}
    >
      {label}
    </Typography>
    <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", minWidth: 0 }}>
      <Typography
        variant="body2"
        sx={{
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          color: value ? "text.primary" : "text.disabled",
          fontFamily: monospace ? "'Space Mono', monospace" : undefined,
        }}
      >
        {value || "—"}
      </Typography>
      {actions}
    </Stack>
  </Box>
);

const openUrl = (value) => {
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    window.open(url.href, "_blank", "noopener,noreferrer");
  } catch {
    // The entry editor accepts free-form URLs; malformed values simply stay inert.
  }
};

const strengthIcon = (password) => {
  const strength = getPasswordStrength(password);
  if (!strength) return null;
  const Icon = strength.level <= 1 ? GppBadIcon : strength.level === 2 ? GppMaybeIcon : GppGoodIcon;
  return { Icon, strength };
};

const VaultEntryCard = ({
  entry,
  visible,
  onToggleVisibility,
  onToggleFavorite,
  onCopy,
  onEdit,
  onDelete,
  onShare,
}) => {
  const { t } = useTranslation();
  const canWrite = entry.access !== "read";
  const owner = entry.access === "owner";
  const strength = entry.kind === "note" ? null : strengthIcon(entry.password_value);
  const StrengthIcon = strength?.Icon;
  const tags = entry.tags ?? [];

  return (
    <Paper
      component="article"
      variant="outlined"
      sx={{
        p: { xs: 1.5, md: 1.75 },
        borderRadius: 2.5,
        bgcolor: "background.paper",
        display: { xs: "grid", lg: "flex" },
        gridTemplateColumns: {
          xs: "minmax(0, 1fr) minmax(0, 1fr)",
        },
        "@media (max-width:350px)": { gridTemplateColumns: "minmax(0, 1fr)" },
        gap: { xs: 1.4, lg: 2 },
        alignItems: "center",
        "& > :nth-of-type(1)": {
          flex: { lg: "1 1 auto" },
          minWidth: { lg: 240 },
        },
        "& > :nth-of-type(2)": { flex: { lg: "0 0 220px" } },
        "& > :nth-of-type(3)": { flex: { lg: "0 0 190px" } },
        "& > :nth-of-type(4)": { flex: { lg: "0 0 auto" } },
        transition: "border-color 150ms ease, background-color 150ms ease",
        "&:hover": { borderColor: "text.disabled" },
      }}
    >
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: "flex-start", minWidth: 0, gridColumn: { xs: "1 / -1", lg: "auto" } }}
      >
        <ActionButton
          label={t(entry.favorite ? "vault.columns.removeFavorite" : "vault.columns.markFavorite")}
          disabled={!canWrite}
          onClick={() => onToggleFavorite(entry)}
        >
          {entry.favorite ? (
            <StarIcon fontSize="small" sx={{ color: GLOW }} />
          ) : (
            <StarBorderIcon fontSize="small" sx={{ color: "text.disabled" }} />
          )}
        </ActionButton>
        <Box sx={{ minWidth: 0, flex: 1, pt: 0.4 }}>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", minWidth: 0 }}>
            {entry.kind === "note" && (
              <StickyNote2OutlinedIcon fontSize="small" sx={{ color: "text.disabled" }} />
            )}
            <Typography
              sx={{
                fontWeight: 700,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {entry.password_name}
            </Typography>
            {(entry.attachment_count ?? 0) > 0 && (
              <Stack direction="row" spacing={0.25} sx={{ color: "text.disabled" }}>
                <AttachFileIcon sx={{ fontSize: 16 }} />
                <Typography variant="caption">{entry.attachment_count}</Typography>
              </Stack>
            )}
          </Stack>
          <Stack
            direction="row"
            spacing={0.75}
            useFlexGap
            sx={{
              flexWrap: { xs: "wrap", lg: "nowrap" },
              height: { lg: 24 },
              overflow: "hidden",
              mt: 0.75,
              alignItems: "center",
              "& .MuiChip-root": { flexShrink: 0 },
            }}
          >
            {entry.folder && <Chip label={entry.folder} size="small" variant="outlined" />}
            {tags.slice(0, 2).map((tag) => (
              <Chip key={tag} label={tag} size="small" />
            ))}
            {tags.length > 2 && <Chip label={`+${tags.length - 2}`} size="small" />}
          </Stack>
          <Typography
            variant="caption"
            noWrap
            sx={{ color: "text.secondary", display: "block", mt: 0.5 }}
          >
            {entry.owner_username} · {t(`sharing.${entry.access}`)}
          </Typography>
        </Box>
      </Stack>

      <ValueBlock
        label={t("common.fields.usernameEmail")}
        value={entry.username}
        actions={
          entry.username ? (
            <ActionButton
              label={t("vault.columns.copyUsername")}
              onClick={() => onCopy(entry.username)}
            >
              <ContentCopyIcon fontSize="small" />
            </ActionButton>
          ) : null
        }
      />

      <Stack spacing={1} sx={{ minWidth: 0 }}>
        <ValueBlock
          label={entry.kind === "note" ? t("entry.labels.note") : t("common.fields.password")}
          value={visible ? entry.password_value : "••••••••"}
          monospace
          actions={
            <>
              <ActionButton
                label={t(visible ? "vault.columns.hidePassword" : "vault.columns.revealPassword")}
                onClick={() => onToggleVisibility(entry.id)}
              >
                {visible ? (
                  <VisibilityOffIcon fontSize="small" />
                ) : (
                  <VisibilityIcon fontSize="small" />
                )}
              </ActionButton>
              <ActionButton
                label={t("vault.columns.copyPassword")}
                onClick={() => onCopy(entry.password_value)}
              >
                <ContentCopyIcon fontSize="small" />
              </ActionButton>
            </>
          }
        />
        {entry.totp_secret && <TotpCell secret={entry.totp_secret} onCopy={onCopy} />}
      </Stack>

      <Stack
        direction="row"
        spacing={0.25}
        sx={{
          alignItems: "center",
          justifyContent: { xs: "space-between", lg: "flex-start" },
          borderTop: { xs: "1px solid", lg: "none" },
          borderColor: "divider",
          pt: { xs: 1, lg: 0 },
          gridColumn: { xs: "1 / -1", lg: "auto" },
        }}
      >
        <Stack direction="row" spacing={0.25}>
          {entry.url ? (
            <ActionButton label={t("vault.columns.openWebsite")} onClick={() => openUrl(entry.url)}>
              <OpenInNewIcon fontSize="small" />
            </ActionButton>
          ) : (
            <EmptyActionSlot />
          )}
          {canWrite ? (
            <ActionButton label={t("common.actions.edit")} onClick={() => onEdit(entry)}>
              <EditIcon fontSize="small" />
            </ActionButton>
          ) : (
            <EmptyActionSlot />
          )}
          {owner ? (
            <ActionButton label={t("sharing.manage")} onClick={() => onShare(entry)}>
              <ShareIcon fontSize="small" />
            </ActionButton>
          ) : (
            <EmptyActionSlot />
          )}
          {owner ? (
            <ActionButton
              label={t("common.actions.delete")}
              color="error"
              onClick={() => onDelete(entry)}
            >
              <DeleteIcon fontSize="small" />
            </ActionButton>
          ) : (
            <EmptyActionSlot />
          )}
        </Stack>
        <Stack
          direction="row"
          spacing={0.75}
          sx={{
            alignItems: "center",
          }}
        >
          {strength && StrengthIcon ? (
            <Tooltip title={t(strength.strength.labelKey)}>
              <StrengthIcon fontSize="small" sx={{ color: strength.strength.color }} />
            </Tooltip>
          ) : (
            <EmptyIndicatorSlot />
          )}
          <Tooltip
            title={t(
              entry.backed_up
                ? "vault.columns.passwordBackedUp"
                : "vault.columns.passwordNotBackedUp"
            )}
          >
            {entry.backed_up ? (
              <CheckCircleOutlineIcon fontSize="small" sx={{ color: "success.main" }} />
            ) : (
              <HighlightOffIcon fontSize="small" sx={{ color: "warning.main" }} />
            )}
          </Tooltip>
        </Stack>
      </Stack>
    </Paper>
  );
};

export default VaultEntryCard;

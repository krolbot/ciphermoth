import { useState } from "react";
import {
  Box,
  ButtonBase,
  Dialog,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import StarIcon from "@mui/icons-material/Star";
import StickyNote2OutlinedIcon from "@mui/icons-material/StickyNote2Outlined";
import { useTranslation } from "react-i18next";

import EntryDetails from "./EntryDetails";

const EntryBrowser = ({ entries, emptyMessage, onCopy, ...actions }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const desktop = useMediaQuery(theme.breakpoints.up("md"));
  const [selectedId, setSelectedId] = useState(null);
  const selected = entries.find((entry) => entry.id === selectedId);
  const details = selected && (
    <EntryDetails
      key={selected.id}
      entry={selected}
      onCopy={onCopy}
      {...actions}
      onClose={desktop ? undefined : () => setSelectedId(null)}
    />
  );

  return (
    <Paper
      variant="outlined"
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 0.9fr) minmax(0, 1.1fr)" },
        borderRadius: 2.5,
        overflow: "hidden",
        minWidth: 0,
      }}
    >
      <Box sx={{ minWidth: 0, borderRight: { md: "1px solid" }, borderColor: { md: "divider" } }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {t("vault.browser.entries")}{" "}
            <Box
              component="span"
              sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums", ml: 0.5 }}
            >
              {entries.length}
            </Box>
          </Typography>
        </Box>
        {entries.length === 0 ? (
          <Typography role="status" variant="body2" color="text.secondary" sx={{ p: 3 }}>
            {emptyMessage}
          </Typography>
        ) : (
          <Box
            component="ul"
            aria-label={t("vault.browser.entries")}
            sx={{
              listStyle: "none",
              m: 0,
              p: 0,
              maxHeight: { md: "min(72vh, 760px)" },
              overflowY: { md: "auto" },
            }}
          >
            {entries.map((entry) => {
              const isNote = entry.kind === "note";
              const Icon = isNote ? StickyNote2OutlinedIcon : KeyOutlinedIcon;
              const copyLabel = t(isNote ? "vault.browser.copyNote" : "vault.columns.copyPassword");
              return (
                <Box
                  component="li"
                  key={entry.id}
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    minWidth: 0,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    "&:last-child": { borderBottom: 0 },
                    bgcolor: entry.id === selected?.id ? "action.selected" : "transparent",
                  }}
                >
                  <ButtonBase
                    aria-label={t("vault.browser.open", { name: entry.password_name })}
                    aria-current={entry.id === selected?.id ? "true" : undefined}
                    onClick={() => setSelectedId(entry.id)}
                    sx={{
                      flex: 1,
                      minWidth: 0,
                      alignSelf: "stretch",
                      justifyContent: "flex-start",
                      textAlign: "left",
                      gap: 1.5,
                      p: 2,
                      minHeight: 88,
                      "&:hover": { bgcolor: "action.hover" },
                      "&.Mui-focusVisible": {
                        outline: "2px solid",
                        outlineColor: "primary.main",
                        outlineOffset: -2,
                      },
                    }}
                  >
                    <Box
                      sx={{
                        width: 40,
                        height: 40,
                        flexShrink: 0,
                        display: "grid",
                        placeItems: "center",
                        bgcolor: "action.hover",
                        borderRadius: 1.5,
                        color: "text.secondary",
                      }}
                    >
                      <Icon fontSize="small" />
                    </Box>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Stack
                        direction="row"
                        spacing={0.5}
                        sx={{ alignItems: "center", minWidth: 0 }}
                      >
                        <Typography noWrap variant="body2" sx={{ fontWeight: 650, minWidth: 0 }}>
                          {entry.password_name}
                        </Typography>
                        {entry.favorite && (
                          <StarIcon
                            color="secondary"
                            sx={{ fontSize: 14, flexShrink: 0 }}
                            aria-label={t("vault.browser.favorite")}
                          />
                        )}
                        {entry.access === "read" && (
                          <LockOutlinedIcon
                            sx={{ fontSize: 14, color: "text.secondary", flexShrink: 0 }}
                            aria-label={t("sharing.readOnlyAccess")}
                          />
                        )}
                      </Stack>
                      <Typography noWrap variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                        {isNote
                          ? t("entry.kind.note")
                          : entry.username || entry.url || t("entry.kind.login")}
                      </Typography>
                      {(entry.folder || entry.attachment_count > 0) && (
                        <Stack
                          direction="row"
                          spacing={1}
                          sx={{ alignItems: "center", mt: 0.25, minWidth: 0 }}
                        >
                          <Typography
                            noWrap
                            variant="caption"
                            color="text.secondary"
                            sx={{ minWidth: 0 }}
                          >
                            {entry.folder}
                          </Typography>
                          {entry.attachment_count > 0 && (
                            <AttachFileIcon
                              sx={{ fontSize: 14, flexShrink: 0, color: "text.secondary" }}
                              aria-label={t("vault.columns.attachment", {
                                count: entry.attachment_count,
                              })}
                            />
                          )}
                        </Stack>
                      )}
                    </Box>
                  </ButtonBase>
                  <Tooltip title={copyLabel}>
                    <IconButton
                      aria-label={`${copyLabel}: ${entry.password_name}`}
                      onClick={() => onCopy(entry.password_value)}
                      sx={{ width: 44, height: 44, mr: 1, flexShrink: 0 }}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <ChevronRightIcon
                    sx={{
                      color: "text.secondary",
                      fontSize: 18,
                      mr: 1,
                      display: { xs: "none", sm: "block" },
                    }}
                  />
                </Box>
              );
            })}
          </Box>
        )}
      </Box>
      {desktop && (
        <Box
          component="section"
          aria-label={t("vault.browser.details")}
          sx={{ minWidth: 0, maxHeight: "min(80vh, 840px)", overflowY: "auto" }}
        >
          {details || (
            <Stack
              spacing={1.5}
              sx={{
                alignItems: "center",
                justifyContent: "center",
                minHeight: 400,
                p: 4,
                textAlign: "center",
              }}
            >
              <KeyOutlinedIcon sx={{ color: "text.secondary", fontSize: 40 }} />
              <Typography variant="h6">{t("vault.browser.selectTitle")}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 280 }}>
                {t("vault.browser.selectHint")}
              </Typography>
            </Stack>
          )}
        </Box>
      )}
      {!desktop && (
        <Dialog
          fullScreen
          open={Boolean(selected)}
          onClose={() => setSelectedId(null)}
          aria-labelledby="entry-detail-title"
          slotProps={{ paper: { sx: { borderRadius: 0 } } }}
        >
          {details}
        </Dialog>
      )}
    </Paper>
  );
};

export default EntryBrowser;

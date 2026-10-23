import { useState } from "react";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import RestoreFromTrashIcon from "@mui/icons-material/RestoreFromTrash";
import { Trans, useTranslation } from "react-i18next";

import ConfirmDialog from "../ConfirmDialog";

const formatDeleted = (iso, language) => {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(language);
};

const TrashDialog = ({ open, trash, onClose, onRestore, onPurge }) => {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const [purgeTarget, setPurgeTarget] = useState(null);

  const handlePurge = async () => {
    await onPurge({ passwordName: purgeTarget.password_name, entryId: purgeTarget.id });
    setPurgeTarget(null);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      fullScreen={fullScreen}
      aria-labelledby="trash-title"
    >
      <DialogTitle id="trash-title">{t("vault.trash")}</DialogTitle>
      <DialogContent dividers>
        {trash.length === 0 ? (
          <Typography variant="body2" sx={{ color: "text.secondary", py: 4, textAlign: "center" }}>
            {t("trashDialog.empty")}
          </Typography>
        ) : (
          <Box component="ul" aria-label={t("vault.trash")} sx={{ listStyle: "none", p: 0, m: 0 }}>
            {trash.map((entry) => (
              <Stack
                component="li"
                key={entry.id}
                direction="row"
                spacing={1}
                sx={{
                  py: 1.5,
                  alignItems: "center",
                  borderBottom: "1px solid",
                  borderColor: "divider",
                  "&:last-child": { borderBottom: 0 },
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                    {entry.password_name}
                  </Typography>
                  {entry.username && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ overflowWrap: "anywhere" }}
                    >
                      {entry.username}
                    </Typography>
                  )}
                  <Typography variant="caption" color="text.secondary">
                    {t("trashDialog.deleted")}:{" "}
                    {formatDeleted(entry.deleted, i18n.resolvedLanguage)}
                  </Typography>
                </Box>
                <Tooltip title={t("trashDialog.restore")}>
                  <IconButton
                    aria-label={`${t("trashDialog.restore")}: ${entry.password_name}`}
                    color="primary"
                    onClick={() =>
                      onRestore({ passwordName: entry.password_name, entryId: entry.id })
                    }
                    sx={{ width: 44, height: 44 }}
                  >
                    <RestoreFromTrashIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t("trashDialog.deleteForever")}>
                  <IconButton
                    aria-label={`${t("trashDialog.deleteForever")}: ${entry.password_name}`}
                    color="error"
                    onClick={() => setPurgeTarget(entry)}
                    sx={{ width: 44, height: 44 }}
                  >
                    <DeleteForeverIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            ))}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{ minHeight: 44 }}>
          {t("common.actions.close")}
        </Button>
      </DialogActions>
      <ConfirmDialog
        open={!!purgeTarget}
        title={t("trashDialog.deleteForeverTitle")}
        confirmText={t("trashDialog.deleteForever")}
        confirmColor="error"
        onClose={() => setPurgeTarget(null)}
        onConfirm={handlePurge}
      >
        <Trans
          i18nKey="trashDialog.deleteForeverMessage"
          values={{ name: purgeTarget?.password_name }}
          components={{ strong: <strong /> }}
        />
      </ConfirmDialog>
    </Dialog>
  );
};

export default TrashDialog;

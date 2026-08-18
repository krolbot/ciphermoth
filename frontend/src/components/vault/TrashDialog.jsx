import { useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import RestoreFromTrashIcon from "@mui/icons-material/RestoreFromTrash";
import { Trans, useTranslation } from "react-i18next";

import ConfirmDialog from "../ConfirmDialog";

const formatDeleted = (iso, language) => {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(language);
};

const TrashDialog = ({ open, trash, onClose, onRestore, onPurge, onPurgeAll }) => {
  const { t, i18n } = useTranslation();
  const [purgeTarget, setPurgeTarget] = useState(null);
  const [purgeAllOpen, setPurgeAllOpen] = useState(false);
  const ownedCount = trash.filter((entry) => entry.access === "owner").length;

  const handlePurge = async () => {
    await onPurge(purgeTarget.id);
    setPurgeTarget(null);
  };

  const handlePurgeAll = async () => {
    await onPurgeAll();
    setPurgeAllOpen(false);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t("vault.trash")}</DialogTitle>
      <DialogContent dividers sx={{ px: { xs: 1.5, sm: 3 } }}>
        {trash.length === 0 ? (
          <Typography variant="body2" sx={{ color: "text.secondary", py: 4, textAlign: "center" }}>
            {t("trashDialog.empty")}
          </Typography>
        ) : (
          <Stack spacing={1}>
            {trash.map((entry) => (
              <Paper
                key={entry.id}
                variant="outlined"
                sx={{
                  p: 1.5,
                  borderRadius: 2,
                  display: "grid",
                  gridTemplateColumns: { xs: "minmax(0, 1fr) auto", sm: "minmax(0, 1fr) auto" },
                  gap: 1,
                  alignItems: "center",
                }}
              >
                <Stack spacing={0.35} sx={{ minWidth: 0 }}>
                  <Typography
                    sx={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" }}
                    noWrap
                  >
                    {entry.password_name}
                  </Typography>
                  <Typography variant="body2" sx={{ color: "text.secondary" }} noWrap>
                    {entry.username || "—"} · {formatDeleted(entry.deleted, i18n.resolvedLanguage)}
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={0.25}>
                  <Tooltip title={t("trashDialog.restore")}>
                    <IconButton
                      aria-label={t("trashDialog.restore")}
                      size="small"
                      color="primary"
                      onClick={() => onRestore(entry.id)}
                    >
                      <RestoreFromTrashIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  {entry.access === "owner" && (
                    <Tooltip title={t("trashDialog.deleteForever")}>
                      <IconButton
                        aria-label={t("trashDialog.deleteForever")}
                        size="small"
                        color="error"
                        onClick={() => setPurgeTarget(entry)}
                      >
                        <DeleteForeverIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Stack>
              </Paper>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ justifyContent: "space-between", px: { xs: 1.5, sm: 3 } }}>
        <Button
          color="error"
          startIcon={<DeleteSweepIcon />}
          disabled={ownedCount === 0}
          onClick={() => setPurgeAllOpen(true)}
        >
          {t("trashDialog.deleteAll")}
        </Button>
        <Button onClick={onClose}>{t("common.actions.close")}</Button>
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

      <ConfirmDialog
        open={purgeAllOpen}
        title={t("trashDialog.deleteAllTitle")}
        confirmText={t("trashDialog.deleteAll")}
        confirmColor="error"
        onClose={() => setPurgeAllOpen(false)}
        onConfirm={handlePurgeAll}
      >
        {t("trashDialog.deleteAllMessage", { count: ownedCount })}
      </ConfirmDialog>
    </Dialog>
  );
};

export default TrashDialog;

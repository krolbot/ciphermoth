import { useState } from "react";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Tooltip,
  Typography,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import RestoreFromTrashIcon from "@mui/icons-material/RestoreFromTrash";
import { Trans, useTranslation } from "react-i18next";

import ConfirmDialog from "../ConfirmDialog";
import { gridBaseSx } from "./gridStyles";

const formatDeleted = (iso, language) => {
  if (!iso) return "-";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString(language);
};

const buildColumns = ({ t, language, onRestore, onPurge }) => [
  { field: "password_name", headerName: t("common.fields.name"), flex: 1, minWidth: 140 },
  {
    field: "username",
    headerName: t("common.fields.usernameEmail"),
    flex: 1,
    minWidth: 150,
    renderCell: (params) => (
      <Typography variant="body2" sx={{ color: params.value ? "text.primary" : "text.disabled" }}>
        {params.value || "-"}
      </Typography>
    ),
  },
  {
    field: "deleted",
    headerName: t("trashDialog.deleted"),
    flex: 1,
    minWidth: 170,
    renderCell: (params) => (
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        {formatDeleted(params.value, language)}
      </Typography>
    ),
  },
  {
    field: "actions",
    headerName: t("common.fields.actions"),
    width: 110,
    sortable: false,
    align: "center",
    headerAlign: "center",
    renderCell: (params) => (
      <Box sx={{ display: "flex", alignItems: "center", height: "100%" }}>
        <Tooltip title={t("trashDialog.restore")}>
          <IconButton
            size="small"
            color="primary"
            onClick={() => onRestore(params.row.password_name)}
          >
            <RestoreFromTrashIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title={t("trashDialog.deleteForever")}>
          <IconButton size="small" color="error" onClick={() => onPurge(params.row.password_name)}>
            <DeleteForeverIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    ),
  },
];

const TrashDialog = ({ open, trash, onClose, onRestore, onPurge }) => {
  const { t, i18n } = useTranslation();
  const [purgeTarget, setPurgeTarget] = useState(null);

  const columns = buildColumns({
    t,
    language: i18n.resolvedLanguage,
    onRestore,
    onPurge: setPurgeTarget,
  });

  const handlePurge = async () => {
    await onPurge(purgeTarget);
    setPurgeTarget(null);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{t("vault.trash")}</DialogTitle>
      <DialogContent>
        {trash.length === 0 ? (
          <Typography variant="body2" sx={{ color: "text.secondary", py: 4, textAlign: "center" }}>
            {t("trashDialog.empty")}
          </Typography>
        ) : (
          <DataGrid
            rows={trash}
            columns={columns}
            getRowId={(row) => row.password_name}
            disableRowSelectionOnClick
            density="compact"
            rowHeight={44}
            columnHeaderHeight={42}
            autoHeight
            pageSizeOptions={[10, 25]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            sx={gridBaseSx}
          />
        )}
      </DialogContent>
      <DialogActions>
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
          values={{ name: purgeTarget }}
          components={{ strong: <strong /> }}
        />
      </ConfirmDialog>
    </Dialog>
  );
};

export default TrashDialog;

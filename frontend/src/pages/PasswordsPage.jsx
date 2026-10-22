import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import DownloadIcon from "@mui/icons-material/Download";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";
import SearchIcon from "@mui/icons-material/Search";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { Trans, useTranslation } from "react-i18next";

import BackupDialog from "../components/vault/BackupDialog";
import ConfirmDialog from "../components/ConfirmDialog";
import EmptyVault from "../components/vault/EmptyVault";
import HealthDialog from "../components/vault/HealthDialog";
import ImportDialog from "../components/vault/ImportDialog";
import PasswordFormDialog from "../components/vault/PasswordFormDialog";
import ShareDialog from "../components/vault/ShareDialog";
import TrashDialog from "../components/vault/TrashDialog";
import { createColumns } from "../components/vault/columns";
import { gridBaseSx } from "../components/vault/gridStyles";
import useClipboard from "../hooks/useClipboard";

const buildSubtitle = (loading, passwords, t) => {
  if (loading) return t("common.labels.loading");
  const n = passwords.length;
  if (n === 0) return t("vault.subtitle.empty");
  return `${t("vault.subtitle.secretCount", { count: n })}.`;
};

const PasswordsPage = () => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const copy = useClipboard();

  const {
    get,
    create,
    update,
    remove,
    backup,
    importPasswords,
    importCsv,
    toggleFavorite,
    getTrash,
    restore,
    purge,
    getDamaged,
    removeDamaged,
  } = useStoreActions((actions) => actions.ciphermothModels.passwords);
  const { error, loading, passwords, trash, damaged, damageCheckError } = useStoreState(
    (state) => state.ciphermothModels.passwords
  );

  const [visibleRows, setVisibleRows] = useState(new Set());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [shareTarget, setShareTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [backupOpen, setBackupOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [healthOpen, setHealthOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);
  const [removeDamagedOpen, setRemoveDamagedOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [folderFilter, setFolderFilter] = useState("");

  useEffect(() => {
    get();
    getTrash();
    getDamaged();
  }, [get, getTrash, getDamaged]);

  const damagedCount = damaged.entries.length + damaged.attachments.length;

  useEffect(() => {
    if (error) enqueueSnackbar(error, { variant: "error" });
  }, [error, enqueueSnackbar]);

  const toggleVisibility = useCallback((name) => {
    setVisibleRows((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const openAdd = () => {
    setEditTarget(null);
    setDialogOpen(true);
  };

  const openEdit = useCallback((row) => {
    if (row.access === "read") return;
    setEditTarget(row);
    setDialogOpen(true);
  }, []);

  const handleToggleFavorite = useCallback(
    async (row) => {
      try {
        await toggleFavorite({ passwordName: row.password_name, favorite: !row.favorite });
      } catch (err) {
        enqueueSnackbar(err.message, { variant: "error" });
      }
    },
    [toggleFavorite, enqueueSnackbar]
  );

  const handleSubmit = async (entry) => {
    if (editTarget) {
      await update({
        password: {
          password_name: editTarget.password_name,
          username: editTarget.username ?? null,
          password_value: editTarget.password_value,
          description: editTarget.description ?? null,
        },
        new_password: entry,
      });
      enqueueSnackbar(
        t(entry.kind === "note" ? "vault.messages.noteUpdated" : "vault.messages.passwordUpdated"),
        {
          variant: "success",
        }
      );
    } else {
      await create(entry);
      enqueueSnackbar(
        t(entry.kind === "note" ? "vault.messages.noteCreated" : "vault.messages.passwordCreated"),
        {
          variant: "success",
        }
      );
    }
    setDialogOpen(false);
  };

  const handleDelete = async () => {
    try {
      await remove(deleteTarget);
      enqueueSnackbar(t("vault.messages.movedToTrash"), { variant: "success" });
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleRestore = async (name) => {
    try {
      await restore(name);
      enqueueSnackbar(t("vault.messages.restored"), { variant: "success" });
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  const handleRemoveDamaged = async () => {
    setRemoveDamagedOpen(false);
    try {
      await removeDamaged(damaged);
      enqueueSnackbar(t("vault.damage.removed"), { variant: "success" });
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  const handlePurge = async (name) => {
    try {
      await purge(name);
      enqueueSnackbar(t("vault.messages.permanentlyDeleted"), { variant: "success" });
    } catch (err) {
      enqueueSnackbar(err.message, { variant: "error" });
    }
  };

  const handleBackup = async (masterPassword) => {
    await backup(masterPassword);
    enqueueSnackbar(t("vault.messages.backupRequested"), {
      variant: "info",
    });
  };

  const columns = useMemo(
    () =>
      createColumns({
        visibleRows,
        onToggleVisibility: toggleVisibility,
        onToggleFavorite: handleToggleFavorite,
        onCopy: copy,
        onEdit: openEdit,
        onDelete: setDeleteTarget,
        onShare: setShareTarget,
        t,
      }),
    [visibleRows, toggleVisibility, handleToggleFavorite, copy, openEdit, t]
  );

  const folderOptions = useMemo(
    () =>
      [...new Set(passwords.map((p) => p.folder).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b)
      ),
    [passwords]
  );
  const activeFolder = folderOptions.includes(folderFilter) ? folderFilter : "";

  const filteredPasswords = useMemo(() => {
    const query = search.trim().toLowerCase();
    const byFolder = activeFolder ? passwords.filter((p) => p.folder === activeFolder) : passwords;
    const matches = !query
      ? byFolder
      : byFolder.filter(
          (p) =>
            p.password_name.toLowerCase().includes(query) ||
            p.username?.toLowerCase().includes(query) ||
            p.description?.toLowerCase().includes(query) ||
            p.url?.toLowerCase().includes(query) ||
            p.folder?.toLowerCase().includes(query) ||
            p.tags?.some((tag) => tag.toLowerCase().includes(query)) ||
            p.custom_fields?.some(
              (f) =>
                f.label.toLowerCase().includes(query) ||
                (!f.hidden && f.value.toLowerCase().includes(query))
            )
        );

    return [...matches].sort(
      (a, b) =>
        Number(b.favorite) - Number(a.favorite) || a.password_name.localeCompare(b.password_name)
    );
  }, [passwords, search, activeFolder]);

  const subtitle = useMemo(() => buildSubtitle(loading, passwords, t), [loading, passwords, t]);
  const isEmpty = !loading && passwords.length === 0;

  return (
    <Box>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        sx={{
          justifyContent: "space-between",
          alignItems: { xs: "stretch", md: "flex-start" },
          mb: 2.5,
        }}
      >
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
            {t("vault.title")}
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
            {subtitle}
          </Typography>
        </Box>
        <Stack
          direction="row"
          spacing={1}
          useFlexGap
          sx={{ flexWrap: "wrap", justifyContent: { xs: "flex-start", md: "flex-end" } }}
        >
          <Button
            variant="outlined"
            startIcon={<HealthAndSafetyIcon />}
            onClick={() => setHealthOpen(true)}
            disabled={passwords.length === 0}
          >
            {t("vault.health")}
          </Button>
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={() => setBackupOpen(true)}
            disabled={passwords.length === 0}
          >
            {t("vault.backup")}
          </Button>
          <Button
            variant="outlined"
            startIcon={<UploadFileIcon />}
            onClick={() => setImportOpen(true)}
          >
            {t("vault.import")}
          </Button>
          <Button
            variant="outlined"
            startIcon={<DeleteOutlineIcon />}
            onClick={() => setTrashOpen(true)}
          >
            {trash.length ? t("vault.trashCount", { count: trash.length }) : t("vault.trash")}
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={openAdd}>
            {t("common.actions.add")}
          </Button>
        </Stack>
      </Stack>

      {!isEmpty && (
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1.5}
          sx={{ mb: 2, alignItems: { xs: "stretch", sm: "center" } }}
        >
          <TextField
            size="small"
            placeholder={t("vault.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ width: { xs: "100%", sm: 320 } }}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
                  </InputAdornment>
                ),
              },
            }}
          />
          {folderOptions.length > 0 && (
            <TextField
              select
              size="small"
              label={t("common.fields.folder")}
              value={activeFolder}
              onChange={(e) => setFolderFilter(e.target.value)}
              sx={{ width: { xs: "100%", sm: 200 } }}
            >
              <MenuItem value="">{t("vault.allFolders")}</MenuItem>
              {folderOptions.map((f) => (
                <MenuItem key={f} value={f}>
                  {f}
                </MenuItem>
              ))}
            </TextField>
          )}
        </Stack>
      )}

      {damageCheckError && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => getDamaged()}>
              {t("common.actions.retry")}
            </Button>
          }
        >
          {damageCheckError}
        </Alert>
      )}

      {damagedCount > 0 && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => setRemoveDamagedOpen(true)}>
              {t("common.actions.remove")}
            </Button>
          }
        >
          {t("vault.damage.message", { count: damagedCount })}
        </Alert>
      )}

      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
          <CircularProgress />
        </Box>
      )}

      {isEmpty && <EmptyVault onAdd={openAdd} />}

      {!loading && !isEmpty && (
        <DataGrid
          rows={filteredPasswords}
          columns={columns}
          getRowId={(row) => row.password_name}
          disableRowSelectionOnClick
          density="compact"
          rowHeight={44}
          columnHeaderHeight={42}
          pageSizeOptions={[10, 25, 50]}
          initialState={{
            pagination: { paginationModel: { pageSize: 10 } },
          }}
          slots={{
            noRowsOverlay: () => (
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  height: "100%",
                }}
              >
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {t("vault.noSearchResults", { search: search.trim() })}
                </Typography>
              </Box>
            ),
          }}
          sx={{
            ...gridBaseSx,
            bgcolor: "background.paper",
            borderRadius: 2.5,
            "& .MuiDataGrid-columnHeaders": { borderColor: "divider" },
            "& .MuiDataGrid-columnHeader": { bgcolor: "background.paper" },
            "& .MuiDataGrid-columnHeaderTitle": {
              fontWeight: 600,
              color: "text.secondary",
            },
            "& .MuiDataGrid-row:hover": { bgcolor: "action.hover" },
            "& .rowHoverActions": {
              opacity: 0,
              pointerEvents: "none",
              transition: "opacity 120ms ease",
            },
            "& .MuiDataGrid-row:hover .rowHoverActions, & .MuiDataGrid-row:has(:focus-visible) .rowHoverActions":
              {
                opacity: 1,
                pointerEvents: "auto",
              },
          }}
        />
      )}

      <PasswordFormDialog
        open={dialogOpen}
        editTarget={editTarget}
        folderOptions={folderOptions}
        onClose={() => setDialogOpen(false)}
        onSubmit={handleSubmit}
        onCopy={copy}
      />
      <ShareDialog
        open={Boolean(shareTarget)}
        entry={shareTarget}
        onClose={() => setShareTarget(null)}
      />
      <BackupDialog
        open={backupOpen}
        onClose={() => setBackupOpen(false)}
        onBackup={handleBackup}
      />
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={importPasswords}
        onImportCsv={importCsv}
      />
      <HealthDialog
        open={healthOpen}
        passwords={passwords}
        onClose={() => setHealthOpen(false)}
        onSelect={(row) => {
          setHealthOpen(false);
          openEdit(row);
        }}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title={t("vault.moveToTrash.title")}
        confirmText={t("vault.moveToTrash.title")}
        confirmColor="error"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      >
        <Trans
          i18nKey="vault.moveToTrash.message"
          values={{ name: deleteTarget }}
          components={{ strong: <strong /> }}
        />
      </ConfirmDialog>
      <ConfirmDialog
        open={removeDamagedOpen}
        title={t("vault.damage.removeTitle")}
        confirmText={t("common.actions.remove")}
        confirmColor="error"
        onClose={() => setRemoveDamagedOpen(false)}
        onConfirm={handleRemoveDamaged}
      >
        {t("vault.damage.removeMessage", { count: damagedCount })}
      </ConfirmDialog>
      <TrashDialog
        open={trashOpen}
        trash={trash}
        onClose={() => setTrashOpen(false)}
        onRestore={handleRestore}
        onPurge={handlePurge}
      />
    </Box>
  );
};

export default PasswordsPage;

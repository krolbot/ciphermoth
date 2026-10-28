import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Ellipsis,
  FolderOpen,
  HeartPulse,
  Magnifier,
  Plus,
  TrashBin,
} from "@gravity-ui/icons";
import {
  Flex,
  Row,
  Col,
  Text,
  Alert,
  Button,
  Icon,
  Loader,
  Menu,
  MenuItem,
  Select,
  TextInput,
  useLayoutContext,
} from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";

import { Trans, useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import BackupDialog from "../components/vault/BackupDialog";
import ConfirmDialog from "../components/ConfirmDialog";
import EmptyVault from "../components/vault/EmptyVault";
import HealthDialog from "../components/vault/HealthDialog";
import ImportDialog from "../components/vault/ImportDialog";
import PasswordFormDialog from "../components/vault/PasswordFormDialog";
import FolderAccessDialog from "../components/access/FolderAccessDialog";
import ShareDialog from "../components/vault/ShareDialog";
import TrashDialog from "../components/vault/TrashDialog";
import EntryBrowser from "../components/vault/EntryBrowser";
import useClipboard from "../hooks/useClipboard";
import { useSnackbar } from "../hooks/useNotify";
import apiClient from "../api/client";
import { createEntryDraftStore } from "../lib/entryDraft";
import { getCurrentUser } from "../utils";

const buildSubtitle = (loading, passwords, t) => {
  if (loading) return t("common.labels.loading");
  const count = passwords.length;
  if (count === 0) return t("vault.subtitle.empty");
  return t("vault.subtitle.secretCount", { count });
};

const PasswordsPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isMediaActive } = useLayoutContext();
  const mobile = !isMediaActive("s");
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
  const getFolders = useStoreActions((actions) => actions.ciphermothModels.access.getFolders);
  const { error, loading, passwords, trash, damaged, damageCheckError } = useStoreState(
    (state) => state.ciphermothModels.passwords
  );
  const folders = useStoreState((state) => state.ciphermothModels.access.folders);

  const [sortOrder, setSortOrder] = useState("created-desc");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [shareTarget, setShareTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [backupOpen, setBackupOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [healthOpen, setHealthOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);
  const [foldersOpen, setFoldersOpen] = useState(false);
  const [removeDamagedOpen, setRemoveDamagedOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [folderFilter, setFolderFilter] = useState("");
  const [draftStore, setDraftStore] = useState(null);
  const [initialDraft, setInitialDraft] = useState(null);
  const [draftError, setDraftError] = useState(false);
  const [draftReady, setDraftReady] = useState(false);
  const [draftAttempt, setDraftAttempt] = useState(0);
  const [requestedEntryId, setRequestedEntryId] = useState(null);

  const clearToolRoute = useCallback(() => {
    if (!searchParams.has("tool")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("tool");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const tool = searchParams.get("tool");
    if (tool === "backup") setBackupOpen(true);
    if (tool === "health") setHealthOpen(true);
    if (tool === "trash") setTrashOpen(true);
    if (tool === "folders") setFoldersOpen(true);
    if (tool === "import") setImportOpen(true);
  }, [searchParams]);

  useEffect(() => {
    let active = true;
    setDraftError(false);
    setDraftStore(null);
    const restoreDraft = async () => {
      try {
        const { data } = await apiClient.get("/auth/entry-draft-key");
        if (!active) return;
        if (data.user_id !== getCurrentUser()?.id) throw new Error("Draft owner changed");
        const store = createEntryDraftStore(data);
        setDraftStore(store);
        const draft = store.read();
        setDraftReady(true);
        if (draft) {
          setInitialDraft(draft);
          setEditTarget(null);
          setDialogOpen(true);
        }
      } catch {
        if (active) setDraftError(true);
      }
    };
    restoreDraft();
    return () => {
      active = false;
    };
  }, [draftAttempt]);

  const saveDraft = useCallback(
    (form) => {
      if (!draftStore) return;
      try {
        if (form) draftStore.write(form);
        else draftStore.clear();
        setDraftError(false);
      } catch {
        setDraftError(true);
      }
    },
    [draftStore]
  );

  const closeEntryForm = () => {
    if (!editTarget) {
      draftStore?.clear();
      setInitialDraft(null);
      setDraftError(false);
    }
    setDialogOpen(false);
  };

  useEffect(() => {
    get();
    getTrash();
    getDamaged();
    getFolders().catch((requestError) =>
      enqueueSnackbar(requestError.message, { variant: "error" })
    );
  }, [get, getTrash, getDamaged, getFolders, enqueueSnackbar]);

  const damagedCount = damaged.entries.length + damaged.attachments.length;

  const folderOptions = useMemo(
    () => folders.filter((folder) => ["owner", "write", "read"].includes(folder.access)),
    [folders]
  );
  const writableFolderOptions = useMemo(
    () => folders.filter((folder) => ["owner", "write"].includes(folder.access)),
    [folders]
  );
  const formFolderOptions = useMemo(
    () =>
      editTarget
        ? writableFolderOptions.filter((folder) => folder.owner_id === editTarget.owner_id)
        : writableFolderOptions,
    [editTarget, writableFolderOptions]
  );
  const activeFolder = folderOptions.some((folder) => folder.id === Number(folderFilter))
    ? folderFilter
    : "";

  const openAdd = () => {
    const folder = writableFolderOptions.find((item) => item.id === Number(folderFilter));
    if (mobile) {
      navigate("/entries/new", { state: { folderId: folder?.id ?? null } });
      return;
    }
    if (!draftReady) {
      enqueueSnackbar(t("entry.draft.unavailable"), { variant: "error" });
      return;
    }
    setEditTarget(null);
    setInitialDraft(folder ? { folder: folder.name, folder_id: folder.id } : null);
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
      } catch (requestError) {
        enqueueSnackbar(requestError.message, { variant: "error" });
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
        { variant: "success" }
      );
    } else {
      await create(entry);
      enqueueSnackbar(
        t(entry.kind === "note" ? "vault.messages.noteCreated" : "vault.messages.passwordCreated"),
        { variant: "success" }
      );
    }
    closeEntryForm();
    await getFolders().catch((requestError) =>
      enqueueSnackbar(requestError.message, { variant: "error" })
    );
  };

  const handleDelete = async () => {
    try {
      await remove(deleteTarget);
      setDeleteTarget(null);
      enqueueSnackbar(t("vault.messages.movedToTrash"), { variant: "success" });
    } catch (requestError) {
      enqueueSnackbar(requestError.message, { variant: "error" });
    }
  };

  const handleRestore = async (name) => {
    try {
      await restore(name);
      enqueueSnackbar(t("vault.messages.restored"), { variant: "success" });
    } catch (requestError) {
      enqueueSnackbar(requestError.message, { variant: "error" });
      throw requestError;
    }
  };

  const handleRemoveDamaged = async () => {
    try {
      await removeDamaged(damaged);
      setRemoveDamagedOpen(false);
      enqueueSnackbar(t("vault.damage.removed"), { variant: "success" });
    } catch (requestError) {
      enqueueSnackbar(requestError.message, { variant: "error" });
    }
  };

  const handlePurge = async (name) => {
    try {
      await purge(name);
      enqueueSnackbar(t("vault.messages.permanentlyDeleted"), { variant: "success" });
    } catch (requestError) {
      enqueueSnackbar(requestError.message, { variant: "error" });
      throw requestError;
    }
  };

  const handleBackup = async (masterPassword) => {
    await backup(masterPassword);
    enqueueSnackbar(t("vault.messages.backupRequested"), { variant: "info" });
  };

  const filteredPasswords = useMemo(() => {
    const query = search.trim().toLowerCase();
    const byFolder = activeFolder
      ? passwords.filter((password) => password.folder_id === Number(activeFolder))
      : passwords;
    const matches = !query
      ? byFolder
      : byFolder.filter(
          (password) =>
            password.password_name.toLowerCase().includes(query) ||
            password.username?.toLowerCase().includes(query) ||
            password.description?.toLowerCase().includes(query) ||
            password.url?.toLowerCase().includes(query) ||
            password.folder?.toLowerCase().includes(query) ||
            password.tags?.some((tag) => tag.toLowerCase().includes(query)) ||
            password.custom_fields?.some(
              (field) =>
                field.label.toLowerCase().includes(query) ||
                (!field.hidden && field.value.toLowerCase().includes(query))
            )
        );

    return [...matches].sort(
      (first, second) =>
        (sortOrder === "created-desc"
          ? Date.parse(second.created) - Date.parse(first.created)
          : 0) ||
        (sortOrder === "favorites" ? Number(second.favorite) - Number(first.favorite) : 0) ||
        first.password_name.localeCompare(second.password_name) *
          (sortOrder === "name-desc" ? -1 : 1)
    );
  }, [passwords, search, activeFolder, sortOrder]);

  const subtitle = useMemo(() => buildSubtitle(loading, passwords, t), [loading, passwords, t]);
  const isEmpty = !loading && passwords.length === 0;
  const backupUnavailable = passwords.length === 0 && trash.length === 0 && damagedCount === 0;
  const tools = [
    {
      icon: HeartPulse,
      label: t("vault.health"),
      action: () => setHealthOpen(true),
      disabled: passwords.length === 0,
    },
    {
      icon: FolderOpen,
      label: t("folderAccess.manageShort"),
      action: () => setFoldersOpen(true),
      disabled: false,
    },
    {
      icon: ArrowDownToLine,
      label: t("vault.backup"),
      action: () => setBackupOpen(true),
      disabled: backupUnavailable,
    },
    {
      icon: ArrowUpFromLine,
      label: t("vault.import"),
      action: () => setImportOpen(true),
      disabled: false,
    },
    {
      icon: TrashBin,
      label: trash.length ? t("vault.trashCount", { count: trash.length }) : t("vault.trash"),
      action: () => setTrashOpen(true),
      disabled: false,
    },
  ];

  return (
    <Flex direction="column" gap="spacing-5" minWidth="0" as="section">
      <Flex
        direction={{ xs: "column", m: "row" }}
        gap="spacing-3"
        minWidth="0"
        as="header"
        alignItems={{ m: "center" }}
        justifyContent="space-between"
      >
        <Flex alignItems="baseline" gap="spacing-3" wrap="wrap" minWidth="0">
          <Text as="h1" variant="header-1" style={{ margin: 0 }}>
            {t("vault.title")}
          </Text>
          <Text color="secondary" wordBreak="break-word" role="status">
            {subtitle}
          </Text>
        </Flex>
        <Flex direction="row" gap="spacing-3" minWidth="0" wrap="wrap" alignItems="center">
          <Button type="button" view="action" size="xl" disabled={!draftReady} onClick={openAdd}>
            <Icon data={Plus} />
            {t("common.actions.add")}
          </Button>
          <Menu
            placement="bottom-end"
            trigger={
              <Button type="button" view="outlined" size="xl" aria-label={t("vault.browser.tools")}>
                <Icon data={Ellipsis} />
                {t("vault.browser.tools")}
              </Button>
            }
          >
            {tools.map(({ icon, label, action, disabled }) => (
              <MenuItem
                key={label}
                icon={<Icon data={icon} />}
                disabled={disabled}
                onClick={action}
              >
                {label}
              </MenuItem>
            ))}
          </Menu>
        </Flex>
      </Flex>

      {(error || (draftError && !draftReady) || damageCheckError || damagedCount > 0) && (
        <Flex direction="column" gap="spacing-3" minWidth="0">
          {error && <Alert theme="danger" view="outlined" message={error} />}
          {draftError && !draftReady && (
            <Alert
              theme="danger"
              view="outlined"
              message={t("entry.draft.unavailable")}
              actions={
                <>
                  <Button
                    type="button"
                    view="flat-danger"
                    onClick={() => setDraftAttempt((n) => n + 1)}
                  >
                    {t("common.actions.retry")}
                  </Button>
                  {draftStore && (
                    <Button
                      type="button"
                      view="flat-danger"
                      onClick={() => {
                        draftStore.clear();
                        setDraftError(false);
                        setDraftReady(true);
                      }}
                    >
                      {t("entry.draft.discard")}
                    </Button>
                  )}
                </>
              }
              actionsLayout="horizontal"
            />
          )}
          {damageCheckError && (
            <Alert
              theme="warning"
              view="outlined"
              message={damageCheckError}
              actions={
                <Button type="button" view="flat-warning" onClick={() => getDamaged()}>
                  {t("common.actions.retry")}
                </Button>
              }
            />
          )}
          {damagedCount > 0 && (
            <Alert
              theme="warning"
              view="outlined"
              message={t("vault.damage.message", { count: damagedCount })}
              actions={
                <Button
                  type="button"
                  view="flat-warning"
                  onClick={() => setRemoveDamagedOpen(true)}
                >
                  {t("common.actions.remove")}
                </Button>
              }
            />
          )}
        </Flex>
      )}

      {!isEmpty && (
        <Row gap="spacing-3">
          <Col
            size={{ xs: 12, m: folderOptions.length ? 12 : 8, xl: folderOptions.length ? 6 : 8 }}
          >
            <TextInput
              size="xl"
              type="search"
              placeholder={t("vault.searchPlaceholder")}
              value={search}
              onUpdate={setSearch}
              hasClear
              startContent={<Icon data={Magnifier} />}
              controlProps={{ "aria-label": t("vault.searchPlaceholder") }}
            />
          </Col>
          {folderOptions.length > 0 && (
            <Col size={{ xs: 12, m: 6, xl: 3 }}>
              <Select
                size="xl"
                width="max"
                aria-label={t("common.fields.folder")}
                label={`${t("common.fields.folder")}:`}
                value={[activeFolder]}
                onUpdate={([value = ""]) => setFolderFilter(value)}
                options={[
                  { value: "", content: t("vault.allFolders") },
                  ...folderOptions.map((folder) => ({
                    value: String(folder.id),
                    content: `${folder.name} · ${folder.owner_username ?? folder.owner_id}`,
                  })),
                ]}
              />
            </Col>
          )}
          <Col size={{ xs: 12, m: folderOptions.length ? 6 : 4, xl: folderOptions.length ? 3 : 4 }}>
            <Select
              size="xl"
              width="max"
              aria-label={t("vault.browser.sort")}
              label={`${t("vault.browser.sort")}:`}
              value={[sortOrder]}
              onUpdate={([value = "created-desc"]) => setSortOrder(value)}
              options={[
                { value: "favorites", content: t("vault.browser.favoritesFirst") },
                { value: "name", content: t("vault.browser.nameAscending") },
                { value: "name-desc", content: t("vault.browser.nameDescending") },
                { value: "created-desc", content: t("vault.browser.dateAdded") },
              ]}
            />
          </Col>
        </Row>
      )}

      {loading && (
        <Flex
          direction="column"
          gap="spacing-3"
          minWidth="0"
          alignItems="center"
          justifyContent="center"
          paddingBlock="spacing-10"
        >
          <Loader size="l" />
        </Flex>
      )}

      {isEmpty && <EmptyVault onAdd={openAdd} />}

      {passwords.length > 0 && (
        <EntryBrowser
          entries={filteredPasswords}
          totalCount={passwords.length}
          emptyMessage={t("vault.noSearchResults", { search: search.trim() })}
          requestedEntryId={requestedEntryId}
          onRequestedEntryOpen={() => setRequestedEntryId(null)}
          onCopy={copy}
          onEdit={openEdit}
          onDelete={setDeleteTarget}
          onShare={setShareTarget}
          onToggleFavorite={handleToggleFavorite}
        />
      )}

      {dialogOpen && (
        <PasswordFormDialog
          key={editTarget?.id ?? "new"}
          open
          editTarget={editTarget}
          initialDraft={initialDraft}
          onDraftChange={saveDraft}
          draftError={draftError}
          folderOptions={formFolderOptions}
          onClose={closeEntryForm}
          onSubmit={handleSubmit}
          onCopy={copy}
        />
      )}
      <ShareDialog
        open={Boolean(shareTarget)}
        entry={shareTarget}
        onClose={() => setShareTarget(null)}
      />
      <FolderAccessDialog
        open={foldersOpen}
        onClose={() => {
          setFoldersOpen(false);
          clearToolRoute();
        }}
      />
      <BackupDialog
        open={backupOpen}
        onClose={() => {
          setBackupOpen(false);
          clearToolRoute();
        }}
        onBackup={handleBackup}
      />
      <ImportDialog
        open={importOpen}
        onClose={() => {
          setImportOpen(false);
          clearToolRoute();
        }}
        onImport={importPasswords}
        onImportCsv={importCsv}
      />
      <HealthDialog
        open={healthOpen}
        passwords={passwords}
        onClose={() => {
          setHealthOpen(false);
          clearToolRoute();
        }}
        onSelect={(row) => {
          setHealthOpen(false);
          clearToolRoute();
          if (row.access === "read") {
            setFolderFilter("");
            setSearch(row.password_name);
            setRequestedEntryId(row.id);
          } else {
            openEdit(row);
          }
        }}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("vault.moveToTrash.title")}
        confirmText={t("vault.moveToTrash.title")}
        confirmColor="error"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      >
        <Trans
          i18nKey="vault.moveToTrash.message"
          values={{ name: deleteTarget }}
          components={{ strong: <Text as="strong" /> }}
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
        onClose={() => {
          setTrashOpen(false);
          clearToolRoute();
        }}
        onRestore={handleRestore}
        onPurge={handlePurge}
      />
    </Flex>
  );
};

export default PasswordsPage;

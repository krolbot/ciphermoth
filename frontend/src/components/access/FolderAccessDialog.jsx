import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Dialog, Label, Select, TextInput } from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { useSnackbar } from "../../hooks/useNotify";
import { isInvalidExpiry, toLocalExpiry, toUtcExpiry } from "../../lib/accessExpiry";
import { getCurrentUser } from "../../utils";
import ConfirmDialog from "../ConfirmDialog";

const eventDate = (value, language) => {
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(iso).toLocaleString(language);
};

const permissionOptions = (t) => [
  { value: "read", content: t("sharing.read") },
  { value: "write", content: t("sharing.readWrite") },
];

const GrantRow = ({ grant, busy, onSave, onRevoke }) => {
  const { t } = useTranslation();
  const [permission, setPermission] = useState(grant.permission);
  const [expiresAt, setExpiresAt] = useState(toLocalExpiry(grant.expires_at));
  const expiryInvalid = isInvalidExpiry(expiresAt);

  useEffect(() => {
    setPermission(grant.permission);
    setExpiresAt(toLocalExpiry(grant.expires_at));
  }, [grant.expires_at, grant.permission]);

  return (
    <article className="cm-grant-row">
      <div className="cm-grant-row__target">
        <strong>{grant.target_name}</strong>
        <span>
          <Label size="s">{t(`folderAccess.targetTypes.${grant.target_type}`)}</Label>
          {grant.expired && (
            <Label size="s" theme="warning">
              {t("folderAccess.expired")}
            </Label>
          )}
        </span>
      </div>
      <Select
        size="m"
        aria-label={t("sharing.permission")}
        value={[permission]}
        disabled={busy}
        options={permissionOptions(t)}
        onUpdate={([value = "read"]) => setPermission(value)}
      />
      <TextInput
        size="m"
        type="datetime-local"
        label={t("folderAccess.expiresAt")}
        note={t("folderAccess.expiresHint")}
        value={expiresAt}
        disabled={busy}
        onUpdate={setExpiresAt}
        validationState={expiryInvalid ? "invalid" : undefined}
        errorMessage={expiryInvalid ? t("folderAccess.expiresValidation") : undefined}
        controlProps={{ min: toLocalExpiry(new Date().toISOString()) }}
      />
      <Button
        type="button"
        view="outlined"
        disabled={busy || expiryInvalid}
        onClick={() => onSave(permission, toUtcExpiry(expiresAt))}
      >
        {t("common.actions.save")}
      </Button>
      <Button type="button" view="flat-danger" disabled={busy} onClick={onRevoke}>
        {t("sharing.revoke")}
      </Button>
    </article>
  );
};

const FolderAccessDialog = ({ open, onClose }) => {
  const { t, i18n } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const folders = useStoreState((state) => state.ciphermothModels.access.folders);
  const groups = useStoreState((state) => state.ciphermothModels.access.groups);
  const {
    getFolders,
    createFolder,
    renameFolder,
    deleteFolder,
    folderGrants,
    setFolderGrant,
    revokeFolderGrant,
    folderAudit,
    getGroups,
  } = useStoreActions((actions) => actions.ciphermothModels.access);
  const shareTargets = useStoreActions((actions) => actions.ciphermothModels.users.shareTargets);

  const [folderId, setFolderId] = useState("");
  const [newFolderName, setNewFolderName] = useState("");
  const [renameName, setRenameName] = useState("");
  const [grants, setGrants] = useState([]);
  const [audit, setAudit] = useState([]);
  const [targets, setTargets] = useState([]);
  const [targetType, setTargetType] = useState("user");
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState("read");
  const [expiresAt, setExpiresAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const expiryInvalid = isInvalidExpiry(expiresAt);
  const currentUserId = getCurrentUser()?.id;
  const selected = folders.find((folder) => folder.id === Number(folderId)) ?? null;
  const ownsSelected = selected?.owner_id === currentUserId;

  const loadBase = useCallback(async () => {
    const [nextFolders, nextGroups, nextTargets] = await Promise.all([
      getFolders(),
      getGroups(),
      shareTargets(),
    ]);
    setTargets(nextTargets);
    setFolderId((current) => {
      if (nextFolders.some((folder) => folder.id === Number(current))) return current;
      return String(nextFolders[0]?.id ?? "");
    });
    return { nextFolders, nextGroups };
  }, [getFolders, getGroups, shareTargets]);

  const loadDetails = useCallback(async () => {
    if (!selected?.can_manage) {
      setGrants([]);
      setAudit([]);
      return;
    }
    const [nextGrants, nextAudit] = await Promise.all([
      folderGrants(selected.id),
      folderAudit(selected.id),
    ]);
    setGrants(nextGrants);
    setAudit(nextAudit);
  }, [selected?.can_manage, selected?.id, folderGrants, folderAudit]);

  useEffect(() => {
    if (!open) return;
    loadBase().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, loadBase, enqueueSnackbar]);

  useEffect(() => {
    if (!open || !selected) return;
    setRenameName(selected.name);
    loadDetails().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, selected, loadDetails, enqueueSnackbar]);

  const run = async (operation, message, { refreshBase = false } = {}) => {
    setBusy(true);
    try {
      await operation();
      if (refreshBase) await loadBase();
      else await loadDetails();
      enqueueSnackbar(message, { variant: "success" });
      return true;
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const grantTargets = useMemo(() => {
    const source = targetType === "user" ? targets : groups;
    return source.filter(
      (target) =>
        !(targetType === "user" && target.id === selected?.owner_id) &&
        !grants.some((grant) => grant.target_type === targetType && grant.target_id === target.id)
    );
  }, [targetType, targets, groups, grants, selected?.owner_id]);

  const saveGrant = (grant, nextPermission, nextExpiry) =>
    run(
      () =>
        setFolderGrant({
          folderId: selected.id,
          targetType: grant.target_type,
          targetId: grant.target_id,
          permission: nextPermission,
          expiresAt: nextExpiry,
        }),
      t("folderAccess.saved")
    );

  const addGrant = async () => {
    if (!targetId) return;
    const saved = await run(
      () =>
        setFolderGrant({
          folderId: selected.id,
          targetType,
          targetId: Number(targetId),
          permission,
          expiresAt: toUtcExpiry(expiresAt),
        }),
      t("folderAccess.saved")
    );
    if (saved) {
      setTargetId("");
      setExpiresAt("");
    }
  };

  const addFolder = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) return;
    const created = await run(() => createFolder(trimmed), t("folderAccess.folderCreated"), {
      refreshBase: true,
    });
    if (created) setNewFolderName("");
  };

  const removeSelectedFolder = async () => {
    const removed = await run(
      () => deleteFolder(deleteTarget.id),
      t("folderAccess.folderDeleted"),
      { refreshBase: true }
    );
    if (removed) setDeleteTarget(null);
  };

  return (
    <>
      <Dialog
        aria-label={t("folderAccess.title")}
        className="cm-secondary-dialog cm-access-dialog cm-access-dialog--wide"
        contentOverflow="auto"
        fullWidth
        hasCloseButton={!busy}
        maxWidth="l"
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !busy) onClose();
        }}
      >
        <Dialog.Header caption={t("folderAccess.title")} />
        <Dialog.Body>
          <div className="cm-access-dialog__content">
            <section className="cm-access-panel">
              <h3>{t("folderAccess.createFolder")}</h3>
              <div className="cm-access-inline-form">
                <TextInput
                  size="m"
                  label={t("common.fields.name")}
                  value={newFolderName}
                  onUpdate={setNewFolderName}
                />
                <Button
                  type="button"
                  view="action"
                  disabled={busy || !newFolderName.trim()}
                  onClick={addFolder}
                >
                  {t("common.actions.create")}
                </Button>
              </div>
            </section>

            {folders.length === 0 ? (
              <p className="cm-secondary-copy">{t("folderAccess.empty")}</p>
            ) : (
              <>
                <Select
                  size="l"
                  aria-label={t("common.fields.folder")}
                  value={folderId ? [folderId] : []}
                  options={folders.map((folder) => ({
                    value: String(folder.id),
                    content: `${folder.name} · ${folder.owner_username}`,
                  }))}
                  onUpdate={([value = ""]) => setFolderId(value)}
                />

                <section className="cm-access-panel">
                  <header className="cm-access-panel__header">
                    <div>
                      <h3>{selected?.name}</h3>
                      <p>{t("folderAccess.ownerLabel", { owner: selected?.owner_username })}</p>
                    </div>
                    <Label size="s">
                      {t(
                        selected?.access
                          ? `folderAccess.permissions.${selected.access}`
                          : "folderAccess.managementOnly"
                      )}
                    </Label>
                  </header>
                  {ownsSelected && (
                    <div className="cm-access-inline-form cm-access-inline-form--danger">
                      <TextInput
                        size="m"
                        label={t("folderAccess.rename")}
                        value={renameName}
                        onUpdate={setRenameName}
                      />
                      <Button
                        type="button"
                        view="outlined"
                        disabled={busy || !renameName.trim() || renameName.trim() === selected.name}
                        onClick={() =>
                          run(
                            () =>
                              renameFolder({
                                folderId: selected.id,
                                name: renameName.trim(),
                              }),
                            t("folderAccess.folderRenamed"),
                            { refreshBase: true }
                          )
                        }
                      >
                        {t("common.actions.save")}
                      </Button>
                      <Button
                        type="button"
                        view="outlined-danger"
                        disabled={busy}
                        onClick={() => setDeleteTarget(selected)}
                      >
                        {t("common.actions.delete")}
                      </Button>
                    </div>
                  )}
                </section>

                {selected?.can_manage && (
                  <>
                    <section className="cm-access-section">
                      <h3>{t("folderAccess.grants")}</h3>
                      {grants.length === 0 ? (
                        <p className="cm-secondary-copy">{t("folderAccess.noGrants")}</p>
                      ) : (
                        <div className="cm-grant-list">
                          {grants.map((grant) => (
                            <GrantRow
                              key={`${grant.target_type}-${grant.target_id}`}
                              grant={grant}
                              busy={busy}
                              onSave={(nextPermission, nextExpiry) =>
                                saveGrant(grant, nextPermission, nextExpiry)
                              }
                              onRevoke={() =>
                                run(
                                  () =>
                                    revokeFolderGrant({
                                      folderId: selected.id,
                                      targetType: grant.target_type,
                                      targetId: grant.target_id,
                                    }),
                                  t("folderAccess.revoked")
                                )
                              }
                            />
                          ))}
                        </div>
                      )}
                    </section>

                    <section className="cm-access-panel">
                      <h3>{t("sharing.grantAccess")}</h3>
                      <div className="cm-grant-form">
                        <Select
                          size="m"
                          aria-label={t("folderAccess.targetType")}
                          value={[targetType]}
                          disabled={busy}
                          options={[
                            { value: "user", content: t("folderAccess.targetTypes.user") },
                            { value: "group", content: t("folderAccess.targetTypes.group") },
                          ]}
                          onUpdate={([value = "user"]) => {
                            setTargetType(value);
                            setTargetId("");
                          }}
                        />
                        <Select
                          size="m"
                          aria-label={t("folderAccess.target")}
                          placeholder={t("folderAccess.target")}
                          value={targetId ? [targetId] : []}
                          disabled={busy || grantTargets.length === 0}
                          options={grantTargets.map((target) => ({
                            value: String(target.id),
                            content: target.name ?? target.username,
                          }))}
                          onUpdate={([value = ""]) => setTargetId(value)}
                        />
                        <Select
                          size="m"
                          aria-label={t("sharing.permission")}
                          value={[permission]}
                          disabled={busy}
                          options={permissionOptions(t)}
                          onUpdate={([value = "read"]) => setPermission(value)}
                        />
                        <TextInput
                          size="m"
                          type="datetime-local"
                          label={t("folderAccess.expiresAt")}
                          note={t("folderAccess.expiresHint")}
                          value={expiresAt}
                          disabled={busy}
                          onUpdate={setExpiresAt}
                          validationState={expiryInvalid ? "invalid" : undefined}
                          errorMessage={
                            expiryInvalid ? t("folderAccess.expiresValidation") : undefined
                          }
                          controlProps={{ min: toLocalExpiry(new Date().toISOString()) }}
                        />
                        <Button
                          type="button"
                          view="action"
                          disabled={busy || !targetId || expiryInvalid}
                          onClick={addGrant}
                        >
                          {t("sharing.grant")}
                        </Button>
                      </div>
                    </section>

                    <section className="cm-access-section">
                      <h3>{t("folderAccess.audit")}</h3>
                      {audit.length === 0 ? (
                        <p className="cm-secondary-copy">{t("folderAccess.noAudit")}</p>
                      ) : (
                        <ol className="cm-audit-list">
                          {audit.slice(0, 20).map((event) => (
                            <li key={event.id}>
                              <span>
                                {t(`folderAccess.actions.${event.action}`, {
                                  defaultValue: event.action,
                                  actor: event.actor_username || t("folderAccess.systemActor"),
                                  target: event.target_username || event.target_group_name || "",
                                })}
                              </span>
                              <time dateTime={event.created}>
                                {eventDate(event.created, i18n.resolvedLanguage)}
                              </time>
                            </li>
                          ))}
                        </ol>
                      )}
                    </section>
                  </>
                )}
              </>
            )}
          </div>
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonApply={onClose}
          textButtonApply={t("common.actions.close")}
          propsButtonApply={{ disabled: busy, view: "action" }}
        />
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("common.actions.delete")}
        confirmText={t("common.actions.delete")}
        confirmColor="error"
        onClose={() => setDeleteTarget(null)}
        onConfirm={removeSelectedFolder}
      >
        {t("folderAccess.deleteConfirm", { name: deleteTarget?.name })}
      </ConfirmDialog>
    </>
  );
};

export default FolderAccessDialog;

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Dialog, Select, TextInput } from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { useSnackbar } from "../../hooks/useNotify";
import ConfirmDialog from "../ConfirmDialog";

const GroupManagementDialog = ({ open, onClose }) => {
  const { t, i18n } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const groups = useStoreState((state) => state.ciphermothModels.access.groups);
  const users = useStoreState((state) => state.ciphermothModels.users.users);
  const {
    getGroups,
    createGroup,
    renameGroup,
    deleteGroup,
    groupMembers,
    addGroupMember,
    removeGroupMember,
    groupAudit,
  } = useStoreActions((actions) => actions.ciphermothModels.access);
  const [groupId, setGroupId] = useState("");
  const [newName, setNewName] = useState("");
  const [renameName, setRenameName] = useState("");
  const [members, setMembers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [userId, setUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const selected = groups.find((group) => group.id === Number(groupId)) ?? null;

  const loadGroups = useCallback(async () => {
    const next = await getGroups();
    setGroupId((current) =>
      next.some((group) => group.id === Number(current)) ? current : String(next[0]?.id ?? "")
    );
  }, [getGroups]);

  const loadDetails = useCallback(async () => {
    if (!selected) {
      setMembers([]);
      setAudit([]);
      return;
    }
    const [nextMembers, nextAudit] = await Promise.all([
      groupMembers(selected.id),
      groupAudit(selected.id),
    ]);
    setMembers(nextMembers);
    setAudit(nextAudit);
  }, [selected, groupMembers, groupAudit]);

  useEffect(() => {
    if (!open) return;
    loadGroups().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, loadGroups, enqueueSnackbar]);

  useEffect(() => {
    if (!open || !selected) return;
    setRenameName(selected.name);
    loadDetails().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, selected, loadDetails, enqueueSnackbar]);

  const run = async (operation, message, refreshGroups = false) => {
    setBusy(true);
    try {
      await operation();
      if (refreshGroups) await loadGroups();
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

  const availableUsers = useMemo(
    () =>
      users.filter((user) => user.active && !members.some((member) => member.user_id === user.id)),
    [users, members]
  );

  const addGroup = async () => {
    const name = newName.trim();
    if (!name) return;
    const created = await run(() => createGroup(name), t("groups.created"), true);
    if (created) setNewName("");
  };

  const addMember = async () => {
    if (!selected || !userId) return;
    const added = await run(
      () => addGroupMember({ groupId: selected.id, userId: Number(userId) }),
      t("groups.memberAdded")
    );
    if (added) setUserId("");
  };

  const removeSelectedGroup = async () => {
    const removed = await run(() => deleteGroup(deleteTarget.id), t("groups.deleted"), true);
    if (removed) setDeleteTarget(null);
  };

  const eventDate = (value) => {
    const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
    return new Date(iso).toLocaleString(i18n.resolvedLanguage);
  };

  return (
    <>
      <Dialog
        aria-label={t("groups.title")}
        className="cm-secondary-dialog cm-access-dialog"
        contentOverflow="auto"
        fullWidth
        hasCloseButton={!busy}
        maxWidth="m"
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !busy) onClose();
        }}
      >
        <Dialog.Header caption={t("groups.title")} />
        <Dialog.Body>
          <div className="cm-access-dialog__content">
            <section className="cm-access-panel">
              <h3>{t("groups.create")}</h3>
              <div className="cm-access-inline-form">
                <TextInput
                  size="m"
                  label={t("groups.name")}
                  value={newName}
                  onUpdate={setNewName}
                />
                <Button
                  type="button"
                  view="action"
                  disabled={busy || !newName.trim()}
                  onClick={addGroup}
                >
                  {t("common.actions.create")}
                </Button>
              </div>
            </section>

            {groups.length === 0 ? (
              <p className="cm-secondary-copy">{t("groups.empty")}</p>
            ) : (
              <>
                <Select
                  size="l"
                  aria-label={t("groups.group")}
                  value={groupId ? [groupId] : []}
                  options={groups.map((group) => ({
                    value: String(group.id),
                    content: `${group.name} · ${t("groups.memberCount", { count: group.member_count })}`,
                  }))}
                  onUpdate={([value = ""]) => setGroupId(value)}
                />

                <section className="cm-access-panel">
                  <div className="cm-access-inline-form cm-access-inline-form--danger">
                    <TextInput
                      size="m"
                      label={t("groups.rename")}
                      value={renameName}
                      onUpdate={setRenameName}
                    />
                    <Button
                      type="button"
                      view="outlined"
                      disabled={busy || !renameName.trim() || renameName.trim() === selected?.name}
                      onClick={() =>
                        run(
                          () => renameGroup({ groupId: selected.id, name: renameName.trim() }),
                          t("groups.renamed"),
                          true
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
                </section>

                <section className="cm-access-section">
                  <h3>{t("groups.members")}</h3>
                  {members.length === 0 ? (
                    <p className="cm-secondary-copy">{t("groups.noMembers")}</p>
                  ) : (
                    <ul className="cm-access-list">
                      {members.map((member) => (
                        <li key={member.user_id}>
                          <span>
                            <strong>{member.username}</strong>
                            <small>{t(`users.roles.${member.role}`)}</small>
                          </span>
                          <Button
                            type="button"
                            view="flat-danger"
                            disabled={busy}
                            onClick={() =>
                              run(
                                () =>
                                  removeGroupMember({
                                    groupId: selected.id,
                                    userId: member.user_id,
                                  }),
                                t("groups.memberRemoved")
                              )
                            }
                          >
                            {t("common.actions.remove")}
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="cm-access-inline-form">
                    <Select
                      size="m"
                      aria-label={t("groups.addMember")}
                      placeholder={t("groups.addMember")}
                      value={userId ? [userId] : []}
                      disabled={busy || availableUsers.length === 0}
                      options={availableUsers.map((user) => ({
                        value: String(user.id),
                        content: `${user.username} · ${t(`users.roles.${user.role}`)}`,
                      }))}
                      onUpdate={([value = ""]) => setUserId(value)}
                    />
                    <Button
                      type="button"
                      view="action"
                      disabled={busy || !userId}
                      onClick={addMember}
                    >
                      {t("common.actions.add")}
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
                              target: event.target_username || "",
                            })}
                          </span>
                          <time dateTime={event.created}>{eventDate(event.created)}</time>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
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
        onConfirm={removeSelectedGroup}
      >
        {t("groups.deleteConfirm", { name: deleteTarget?.name })}
      </ConfirmDialog>
    </>
  );
};

export default GroupManagementDialog;

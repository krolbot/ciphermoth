import { useEffect, useState } from "react";
import { ArrowLeft, EllipsisVertical, Persons } from "@gravity-ui/icons";
import {
  Alert,
  Button,
  Dialog,
  Icon,
  Menu,
  MenuDivider,
  MenuItem,
  Select,
  Switch,
  TextInput,
} from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import GroupManagementDialog from "../components/access/GroupManagementDialog";
import UserFolderAccessDialog from "../components/access/UserFolderAccessDialog";
import ConfirmDialog from "../components/ConfirmDialog";
import PasswordField from "../components/PasswordField";
import useClipboard from "../hooks/useClipboard";
import { useSnackbar } from "../hooks/useNotify";
import { getCurrentUser } from "../utils";

const EMPTY_FORM = { username: "", temporary_password: "", role: "member" };

const UsersPage = () => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const copy = useClipboard();
  const users = useStoreState((state) => state.ciphermothModels.users.users);
  const { get, create, update, revokeSessions, resetPassword, rotateServiceToken, remove } =
    useStoreActions((actions) => actions.ciphermothModels.users);
  const currentUserId = getCurrentUser()?.id;
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [serviceToken, setServiceToken] = useState("");
  const [resetTarget, setResetTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [folderAccessTarget, setFolderAccessTarget] = useState(null);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [temporaryPassword, setTemporaryPassword] = useState("");

  const closeUserAction = (setter, target) => {
    const userId = target?.id;
    setter(null);
    if (userId) {
      window.requestAnimationFrame(() =>
        document.querySelector(`[data-user-menu="${userId}"]`)?.focus()
      );
    }
  };

  useEffect(() => {
    get().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [get, enqueueSnackbar]);

  const run = async (operation, message = "") => {
    setBusy(true);
    try {
      const result = await operation();
      if (message) enqueueSnackbar(message, { variant: "success" });
      return result ?? true;
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async (event) => {
    event.preventDefault();
    const payload = form.role === "service" ? { username: form.username, role: form.role } : form;
    const created = await run(() => create(payload), t("users.messages.created"));
    if (!created) return;
    setServiceToken(created.service_token || "");
    setForm(EMPTY_FORM);
  };

  const saveReset = async () => {
    const ok = await run(
      () => resetPassword({ userId: resetTarget.id, temporaryPassword }),
      t("users.messages.passwordReset")
    );
    if (!ok) return;
    closeUserAction(setResetTarget, resetTarget);
    setTemporaryPassword("");
  };

  const rotateToken = async (user) => {
    const token = await run(() => rotateServiceToken(user.id), t("users.messages.tokenRotated"));
    if (token) setServiceToken(token);
  };

  const deleteUser = async () => {
    const removed = await run(() => remove(deleteTarget.id), t("users.messages.deleted"));
    if (removed) setDeleteTarget(null);
  };

  return (
    <section className="cm-users-page">
      <header className="cm-page-header cm-users-page__header">
        <div>
          <h1>{t("users.title")}</h1>
          <p>{t("users.subtitle")}</p>
        </div>
        <div className="cm-page-header__actions">
          <Button type="button" view="outlined" onClick={() => setGroupsOpen(true)}>
            <Icon data={Persons} />
            {t("groups.title")}
          </Button>
          <Button component={Link} to="/passwords" view="flat-secondary">
            <Icon data={ArrowLeft} />
            {t("users.backToVault")}
          </Button>
        </div>
      </header>

      {serviceToken && (
        <Alert
          theme="warning"
          view="outlined"
          title={t("users.serviceTokenOnce")}
          message={
            <div className="cm-users-token">
              <TextInput value={serviceToken} controlProps={{ readOnly: true }} />
              <div>
                <Button type="button" view="outlined" onClick={() => copy(serviceToken)}>
                  {t("users.copyToken")}
                </Button>
                <Button type="button" view="flat" onClick={() => setServiceToken("")}>
                  {t("common.actions.dismiss")}
                </Button>
              </div>
            </div>
          }
        />
      )}

      <div className="cm-users-list">
        {users.map((user) => {
          const isCurrent = user.id === currentUserId;
          return (
            <article className="cm-user-row" key={user.id}>
              <div className="cm-user-row__identity">
                <strong>{user.username}</strong>
                <small>
                  {user.must_change_password && user.role !== "service"
                    ? t("users.passwordChangeRequested")
                    : user.role === "service"
                      ? t("users.serviceAccount")
                      : t("users.interactiveAccount")}
                </small>
              </div>
              <Select
                size="m"
                aria-label={t("users.role")}
                value={[user.role]}
                disabled={busy || isCurrent || user.role === "service"}
                options={(user.role === "service" ? ["service"] : ["admin", "member"]).map(
                  (role) => ({ value: role, content: t(`users.roles.${role}`) })
                )}
                onUpdate={([role = user.role]) =>
                  run(() => update({ userId: user.id, role }), t("users.messages.roleUpdated"))
                }
              />
              <Switch
                size="m"
                checked={user.active}
                disabled={busy || isCurrent}
                onUpdate={(active) =>
                  run(() => update({ userId: user.id, active }), t("users.messages.statusUpdated"))
                }
              >
                {t(user.active ? "users.active" : "users.inactive")}
              </Switch>
              <div className="cm-user-row__actions">
                <Menu
                  placement="bottom-end"
                  trigger={
                    <Button
                      type="button"
                      size="l"
                      view="flat-secondary"
                      aria-label={`${t("navigation.more")}: ${user.username}`}
                      data-user-menu={user.id}
                    >
                      <Icon data={EllipsisVertical} />
                      {t("navigation.more")}
                    </Button>
                  }
                >
                  <MenuItem disabled={busy} onClick={() => setFolderAccessTarget(user)}>
                    {t("folderAccess.manage")}
                  </MenuItem>
                  {user.role === "service" ? (
                    <MenuItem disabled={busy} onClick={() => rotateToken(user)}>
                      {t("users.rotateToken")}
                    </MenuItem>
                  ) : (
                    <MenuItem disabled={busy || isCurrent} onClick={() => setResetTarget(user)}>
                      {t("users.resetPassword")}
                    </MenuItem>
                  )}
                  <MenuItem
                    disabled={busy}
                    onClick={() =>
                      run(() => revokeSessions(user.id), t("users.messages.sessionsRevoked"))
                    }
                  >
                    {t("users.revokeSessions")}
                  </MenuItem>
                  <MenuDivider />
                  <MenuItem
                    theme="danger"
                    disabled={busy || isCurrent}
                    onClick={() => setDeleteTarget(user)}
                  >
                    {t("common.actions.delete")}
                  </MenuItem>
                </Menu>
              </div>
            </article>
          );
        })}
      </div>

      <section className="cm-users-create">
        <h2>{t("users.createAccount")}</h2>
        <form className="cm-users-create__form" onSubmit={add}>
          <TextInput
            size="l"
            label={t("auth.username")}
            required
            value={form.username}
            onUpdate={(username) => setForm((current) => ({ ...current, username }))}
            autoComplete="off"
            note={t("auth.usernameRules")}
            controlProps={{ autoCapitalize: "none", spellCheck: false }}
          />
          {form.role === "service" ? (
            <div />
          ) : (
            <PasswordField
              label={t("users.temporaryPassword")}
              size="l"
              required
              value={form.temporary_password}
              onGenerate={(temporary_password) =>
                setForm((current) => ({ ...current, temporary_password }))
              }
              disabled={busy}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  temporary_password: event.target.value,
                }))
              }
              autoComplete="new-password"
            />
          )}
          <Select
            size="l"
            aria-label={t("users.role")}
            value={[form.role]}
            options={["admin", "member", "service"].map((role) => ({
              value: role,
              content: t(`users.roles.${role}`),
            }))}
            onUpdate={([role = "member"]) =>
              setForm((current) => ({
                ...current,
                role,
                temporary_password: role === "service" ? "" : current.temporary_password,
              }))
            }
          />
          <Button
            type="submit"
            view="action"
            size="l"
            disabled={busy || !form.username.trim()}
            loading={busy}
          >
            {t("common.actions.create")}
          </Button>
        </form>
      </section>

      <Dialog
        aria-label={t("users.resetPasswordFor", { username: resetTarget?.username })}
        className="cm-secondary-dialog"
        fullWidth
        maxWidth="s"
        open={Boolean(resetTarget)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !busy) closeUserAction(setResetTarget, resetTarget);
        }}
      >
        <Dialog.Header caption={t("users.resetPasswordFor", { username: resetTarget?.username })} />
        <Dialog.Body>
          <div className="cm-secondary-form">
            <p className="cm-secondary-copy">{t("users.resetPasswordDescription")}</p>
            <PasswordField
              label={t("users.temporaryPassword")}
              value={temporaryPassword}
              onGenerate={setTemporaryPassword}
              disabled={busy}
              onChange={(event) => setTemporaryPassword(event.target.value)}
              autoComplete="new-password"
              autoFocus
            />
          </div>
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonApply={saveReset}
          onClickButtonCancel={() => closeUserAction(setResetTarget, resetTarget)}
          textButtonApply={t("users.resetPassword")}
          textButtonCancel={t("common.actions.cancel")}
          propsButtonApply={{ disabled: busy || !temporaryPassword, loading: busy, view: "action" }}
          propsButtonCancel={{ disabled: busy }}
        />
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("common.actions.delete")}
        confirmText={t("common.actions.delete")}
        confirmColor="error"
        onClose={() => closeUserAction(setDeleteTarget, deleteTarget)}
        onConfirm={deleteUser}
      >
        {t("users.deleteConfirm", { username: deleteTarget?.username })}
      </ConfirmDialog>

      <UserFolderAccessDialog
        open={Boolean(folderAccessTarget)}
        user={folderAccessTarget}
        onClose={() => closeUserAction(setFolderAccessTarget, folderAccessTarget)}
      />
      <GroupManagementDialog open={groupsOpen} onClose={() => setGroupsOpen(false)} />
    </section>
  );
};

export default UsersPage;

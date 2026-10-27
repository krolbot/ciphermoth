import { useCallback, useEffect, useState } from "react";
import { Button, Dialog, Label, Select, TextInput } from "@gravity-ui/uikit";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { useSnackbar } from "../../hooks/useNotify";
import { isInvalidExpiry, toLocalExpiry, toUtcExpiry } from "../../lib/accessExpiry";

const AccessRow = ({ item, busy, onSave, onRevoke }) => {
  const { t } = useTranslation();
  const [permission, setPermission] = useState(item.direct_permission ?? "read");
  const [expiresAt, setExpiresAt] = useState(toLocalExpiry(item.direct_expires_at));
  const owned = item.folder.owner_id === item.userId;
  const expiryInvalid = isInvalidExpiry(expiresAt);

  useEffect(() => {
    setPermission(item.direct_permission ?? "read");
    setExpiresAt(toLocalExpiry(item.direct_expires_at));
  }, [item.direct_expires_at, item.direct_permission]);

  return (
    <article className="cm-access-card">
      <header className="cm-access-card__header">
        <div>
          <h3>{item.folder.name}</h3>
          <p>{t("folderAccess.ownerLabel", { owner: item.folder.owner_username })}</p>
        </div>
        <Label size="s" theme={item.effective_permission ? "success" : "unknown"}>
          {t(
            item.effective_permission
              ? `folderAccess.permissions.${item.effective_permission}`
              : "folderAccess.permissions.none"
          )}
        </Label>
      </header>

      <div className="cm-access-card__sources">
        {item.sources.map((source, index) => (
          <Label
            key={`${source.source}-${source.source_id}-${index}`}
            size="s"
            theme={source.expired ? "unknown" : "success"}
          >
            {t("folderAccess.source", {
              source: t(`folderAccess.sources.${source.source}`),
              name: source.name || "",
              permission: t(`folderAccess.permissions.${source.permission}`),
            })}
          </Label>
        ))}
      </div>

      {owned ? (
        <p className="cm-secondary-copy">{t("folderAccess.ownerCannotChange")}</p>
      ) : (
        <div className="cm-access-card__controls">
          <Select
            size="m"
            aria-label={t("sharing.permission")}
            value={[permission]}
            disabled={busy}
            options={[
              { value: "read", content: t("sharing.read") },
              { value: "write", content: t("sharing.readWrite") },
            ]}
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
            view="action"
            disabled={busy || expiryInvalid}
            onClick={() => onSave(item.folder.id, permission, toUtcExpiry(expiresAt))}
          >
            {t("common.actions.save")}
          </Button>
          <Button
            type="button"
            view="outlined-danger"
            disabled={busy || !item.direct_permission}
            onClick={() => onRevoke(item.folder.id)}
          >
            {t("sharing.revoke")}
          </Button>
        </div>
      )}
    </article>
  );
};

const UserFolderAccessDialog = ({ open, user, onClose }) => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const { userFolderAccess, setFolderGrant, revokeFolderGrant } = useStoreActions(
    (actions) => actions.ciphermothModels.access
  );
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    setItems(await userFolderAccess(user.id));
  }, [user, userFolderAccess]);

  useEffect(() => {
    if (!open) return;
    load().catch((error) => enqueueSnackbar(error.message, { variant: "error" }));
  }, [open, load, enqueueSnackbar]);

  const run = async (operation, message) => {
    setBusy(true);
    try {
      await operation();
      await load();
      enqueueSnackbar(message, { variant: "success" });
    } catch (error) {
      enqueueSnackbar(error.message, { variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      aria-label={t("folderAccess.userTitle", { username: user?.username })}
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
      <Dialog.Header caption={t("folderAccess.userTitle", { username: user?.username })} />
      <Dialog.Body>
        <div className="cm-access-dialog__content">
          <p className="cm-secondary-copy">{t("folderAccess.userDescription")}</p>
          {items.length === 0 ? (
            <p className="cm-secondary-copy">{t("folderAccess.empty")}</p>
          ) : (
            items.map((item) => (
              <AccessRow
                key={item.folder.id}
                item={{ ...item, userId: user?.id }}
                busy={busy}
                onSave={(folderId, permission, expiresAt) =>
                  run(
                    () =>
                      setFolderGrant({
                        folderId,
                        targetType: "user",
                        targetId: user.id,
                        permission,
                        expiresAt,
                      }),
                    t("folderAccess.saved")
                  )
                }
                onRevoke={(folderId) =>
                  run(
                    () =>
                      revokeFolderGrant({
                        folderId,
                        targetType: "user",
                        targetId: user.id,
                      }),
                    t("folderAccess.revoked")
                  )
                }
              />
            ))
          )}
        </div>
      </Dialog.Body>
      <Dialog.Footer
        onClickButtonApply={onClose}
        textButtonApply={t("common.actions.close")}
        propsButtonApply={{ disabled: busy, view: "action" }}
      />
    </Dialog>
  );
};

export default UserFolderAccessDialog;

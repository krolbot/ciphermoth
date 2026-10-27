import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Dialog, Select, TextInput } from "@gravity-ui/uikit";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { isInvalidExpiry, toLocalExpiry, toUtcExpiry } from "../../lib/accessExpiry";

const ShareDialog = ({ entry, open, onClose }) => {
  const { t } = useTranslation();
  const { listShares, setShare, revokeShare } = useStoreActions(
    (actions) => actions.ciphermothModels.passwords
  );
  const shareTargets = useStoreActions((actions) => actions.ciphermothModels.users.shareTargets);
  const [shares, setShares] = useState([]);
  const [targets, setTargets] = useState([]);
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState("read");
  const [expiresAt, setExpiresAt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const expiryInvalid = isInvalidExpiry(expiresAt);

  const load = useCallback(async () => {
    if (!entry) return;
    const [nextShares, nextTargets] = await Promise.all([listShares(entry.id), shareTargets()]);
    setShares(nextShares);
    setTargets(nextTargets);
  }, [entry, listShares, shareTargets]);

  useEffect(() => {
    if (!open) return;
    setTargetId("");
    setPermission("read");
    setExpiresAt("");
    setError("");
    load().catch((requestError) => setError(requestError.message));
  }, [open, load]);

  const run = async (operation) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      await load();
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!targetId) return;
    if (
      await run(() =>
        setShare({
          entryId: entry.id,
          userId: Number(targetId),
          permission,
          expiresAt: toUtcExpiry(expiresAt),
        })
      )
    ) {
      setTargetId("");
      setExpiresAt("");
    }
  };

  const available = targets.filter(
    (target) => !shares.some((share) => share.user_id === target.id)
  );
  const permissionOptions = [
    { value: "read", content: t("sharing.read") },
    { value: "write", content: t("sharing.readWrite") },
  ];

  return (
    <Dialog
      aria-label={t("sharing.manage")}
      className="cm-secondary-dialog cm-share-dialog"
      contentOverflow="auto"
      fullWidth
      hasCloseButton={!busy}
      maxWidth="m"
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !busy) onClose();
      }}
    >
      <Dialog.Header caption={t("sharing.manage")} />
      <Dialog.Body>
        <div className="cm-share-dialog__content">
          <p className="cm-share-dialog__entry">{entry?.password_name}</p>
          {error && <Alert theme="danger" view="outlined" message={error} />}

          <section className="cm-share-dialog__section">
            <h3>{t("sharing.currentAccess")}</h3>
            {shares.length === 0 ? (
              <p className="cm-secondary-copy">{t("sharing.ownerOnly")}</p>
            ) : (
              <ul className="cm-share-dialog__list">
                {shares.map((share) => (
                  <li className="cm-share-dialog__row" key={share.user_id}>
                    <span className="cm-share-dialog__identity">
                      <strong>{share.username}</strong>
                      <small>{t(`users.roles.${share.role}`)}</small>
                    </span>
                    <Select
                      size="m"
                      aria-label={t("sharing.permission")}
                      value={[share.permission]}
                      disabled={busy}
                      options={permissionOptions}
                      onUpdate={([nextPermission = "read"]) =>
                        run(() =>
                          setShare({
                            entryId: entry.id,
                            userId: share.user_id,
                            permission: nextPermission,
                            expiresAt: toUtcExpiry(toLocalExpiry(share.expires_at)),
                          })
                        )
                      }
                    />
                    <Button
                      type="button"
                      view="outlined-danger"
                      disabled={busy}
                      onClick={() =>
                        run(() => revokeShare({ entryId: entry.id, userId: share.user_id }))
                      }
                    >
                      {t("sharing.revoke")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="cm-share-dialog__section">
            <h3>{t("sharing.grantAccess")}</h3>
            <div className="cm-share-dialog__grant">
              <Select
                size="m"
                aria-label={t("sharing.user")}
                placeholder={t("sharing.selectTarget")}
                value={targetId ? [targetId] : []}
                disabled={busy || available.length === 0}
                options={available.map((target) => ({
                  value: String(target.id),
                  content: `${target.username} · ${t(`users.roles.${target.role}`)}`,
                }))}
                onUpdate={([value = ""]) => setTargetId(value)}
              />
              <Select
                size="m"
                aria-label={t("sharing.permission")}
                value={[permission]}
                disabled={busy}
                options={permissionOptions}
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
                disabled={busy || !targetId || expiryInvalid}
                loading={busy}
                onClick={add}
              >
                {t("sharing.grant")}
              </Button>
            </div>
          </section>
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

export default ShareDialog;

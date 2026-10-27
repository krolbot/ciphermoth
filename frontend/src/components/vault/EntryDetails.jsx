import { useState } from "react";
import {
  ArrowLeft,
  ArrowUpRightFromSquare,
  Copy,
  Eye,
  EyeSlash,
  Pencil,
  PersonPlus,
  Star,
  StarFill,
  TrashBin,
  Xmark,
} from "@gravity-ui/icons";
import { Button, Icon, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import AttachmentsSection from "./AttachmentsSection";
import StrengthBar from "./StrengthBar";
import TotpCell from "./TotpCell";
import { IS_DESKTOP, openExternal } from "../../platform";

const IconAction = ({ label, icon, onClick, selected = false }) => (
  <Tooltip content={label} role="label">
    <Button
      type="button"
      view="flat-secondary"
      size="l"
      aria-label={label}
      onClick={onClick}
      selected={selected}
    >
      <Icon data={icon} />
    </Button>
  </Tooltip>
);

const EntryValue = ({
  label,
  value,
  hidden = false,
  mono = false,
  onCopy,
  copyLabel,
  revealLabel,
  hideLabel,
  children,
}) => {
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(false);
  const visibilityLabel = revealed
    ? hideLabel || `${t("passwordField.hide")}: ${label}`
    : revealLabel || `${t("passwordField.show")}: ${label}`;

  return (
    <div className="cm-entry-value">
      <span className="cm-entry-value__label">{label}</span>
      <div className="cm-entry-value__body">
        <span className={`cm-entry-value__text${mono ? " cm-entry-value__text--mono" : ""}`}>
          {hidden && !revealed ? "••••••••••••" : value}
        </span>
        {hidden && (
          <IconAction
            label={visibilityLabel}
            icon={revealed ? EyeSlash : Eye}
            selected={revealed}
            onClick={() => setRevealed((current) => !current)}
          />
        )}
        <IconAction
          label={copyLabel || t("vault.browser.copyValue", { label })}
          icon={Copy}
          onClick={() => onCopy(value)}
        />
      </div>
      {children}
    </div>
  );
};

const EntryDetails = ({ entry, onClose, onCopy, onEdit, onDelete, onShare, onToggleFavorite }) => {
  const { t, i18n } = useTranslation();
  const isNote = entry.kind === "note";
  const writable = entry.access === "owner" || entry.access === "write";
  const history = entry.password_history ?? [];
  const favoriteLabel = t(
    entry.favorite ? "vault.columns.removeFavorite" : "vault.columns.markFavorite"
  );

  const openWebsite = () => {
    const url = /^https?:\/\//i.test(entry.url) ? entry.url : `https://${entry.url}`;
    if (IS_DESKTOP) openExternal(url).catch(() => {});
    else window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="cm-entry-detail">
      <div className="cm-entry-detail__topbar">
        {onClose && (
          <Button
            type="button"
            view="flat-secondary"
            size="l"
            onClick={onClose}
            className="cm-entry-detail__back"
          >
            <Icon data={ArrowLeft} />
            {t("vault.browser.back")}
          </Button>
        )}
        <span className="cm-entry-detail__kind">
          {t(isNote ? "entry.kind.note" : "entry.kind.login")}
        </span>
        <div className="cm-entry-detail__title-line">
          {writable && (
            <IconAction
              label={favoriteLabel}
              icon={entry.favorite ? StarFill : Star}
              selected={entry.favorite}
              onClick={() => onToggleFavorite(entry)}
            />
          )}
          {onClose && (
            <span className="cm-entry-detail__close">
              <IconAction label={t("common.actions.close")} icon={Xmark} onClick={onClose} />
            </span>
          )}
        </div>
      </div>

      <h2 id="entry-detail-title" className="cm-entry-detail__title">
        {entry.password_name}
      </h2>
      {(entry.folder || entry.access !== "owner") && (
        <div className="cm-entry-detail__badges">
          {entry.folder && <span>{entry.folder}</span>}
          {entry.access !== "owner" && (
            <span className="cm-entry-detail__badge">
              {t(entry.access === "read" ? "sharing.readOnlyAccess" : "sharing.readWrite")}
            </span>
          )}
        </div>
      )}

      <div className="cm-entry-detail__actions">
        {writable && (
          <Button type="button" view="outlined" size="l" onClick={() => onEdit(entry)}>
            <Icon data={Pencil} />
            {t("common.actions.edit")}
          </Button>
        )}
        {entry.access === "owner" && (
          <Button type="button" view="outlined" size="l" onClick={() => onShare(entry)}>
            <Icon data={PersonPlus} />
            {t("sharing.manage")}
          </Button>
        )}
      </div>

      {!isNote && entry.username && (
        <EntryValue
          label={t("common.fields.usernameEmail")}
          value={entry.username}
          copyLabel={t("vault.columns.copyUsername")}
          onCopy={onCopy}
        />
      )}
      <EntryValue
        label={t(isNote ? "entry.labels.note" : "common.fields.password")}
        value={entry.password_value}
        hidden
        revealLabel={!isNote ? t("vault.columns.revealPassword") : undefined}
        hideLabel={!isNote ? t("vault.columns.hidePassword") : undefined}
        mono={!isNote}
        copyLabel={t(isNote ? "vault.browser.copyNote" : "vault.columns.copyPassword")}
        onCopy={onCopy}
      >
        {!isNote && <StrengthBar password={entry.password_value} />}
      </EntryValue>
      {!isNote && entry.totp_secret && (
        <div className="cm-entry-section">
          <span className="cm-entry-section__label">{t("entry.labels.twoFactor")}</span>
          <TotpCell secret={entry.totp_secret} onCopy={onCopy} />
        </div>
      )}
      {entry.url && (
        <div className="cm-entry-section">
          <span className="cm-entry-section__label">{t("entry.labels.websiteOptional")}</span>
          <Button
            type="button"
            view="flat-action"
            size="l"
            onClick={openWebsite}
            className="cm-entry-section__website"
          >
            {entry.url}
            <Icon data={ArrowUpRightFromSquare} />
          </Button>
        </div>
      )}
      {entry.custom_fields?.map((field, index) => (
        <EntryValue
          key={`${field.label}-${index}`}
          label={field.label}
          value={field.value}
          hidden={field.hidden}
          onCopy={onCopy}
        />
      ))}
      {entry.description && (
        <div className="cm-entry-section">
          <span className="cm-entry-section__label">{t("entry.labels.notes")}</span>
          <p className="cm-entry-section__text">{entry.description}</p>
        </div>
      )}
      {entry.tags?.length > 0 && (
        <div className="cm-entry-detail__tags">
          {entry.tags.map((tag) => (
            <span key={tag} className="cm-entry-detail__tag">
              {tag}
            </span>
          ))}
        </div>
      )}
      {entry.attachment_count > 0 && (
        <details>
          <summary>
            {t("entry.labels.attachments")} ({entry.attachment_count})
          </summary>
          <AttachmentsSection passwordName={entry.password_name} readOnly />
        </details>
      )}
      {!isNote && history.length > 0 && (
        <details>
          <summary>
            {t("entry.labels.passwordHistory")} ({history.length})
          </summary>
          {history.map((item, index) => (
            <EntryValue
              key={`${item.changed_at}-${index}`}
              label={new Date(item.changed_at).toLocaleString(i18n.resolvedLanguage)}
              value={item.value}
              hidden
              mono
              onCopy={onCopy}
            />
          ))}
        </details>
      )}
      {writable && (
        <Button
          type="button"
          view="outlined-danger"
          size="l"
          onClick={() => onDelete(entry.password_name)}
          className="cm-entry-detail__danger"
        >
          <Icon data={TrashBin} />
          {t("common.actions.delete")}
        </Button>
      )}
    </div>
  );
};

export default EntryDetails;

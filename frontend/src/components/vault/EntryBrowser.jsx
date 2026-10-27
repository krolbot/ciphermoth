import { useEffect, useRef, useState } from "react";
import { ChevronRight, Copy, FileText, Key, Paperclip, StarFill } from "@gravity-ui/icons";
import { Button, Dialog, Icon, Label, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import EntryDetails from "./EntryDetails";
import EntryListActions from "./EntryListActions";
import "../../styles/vault.css";

const DESKTOP_QUERY = "(min-width: 1200px)";

const EntryBrowser = ({
  entries,
  emptyMessage,
  onCopy,
  requestedEntryId,
  onRequestedEntryOpen,
  ...actions
}) => {
  const { t } = useTranslation();
  const [desktop, setDesktop] = useState(() => window.matchMedia?.(DESKTOP_QUERY).matches ?? false);
  const [selectedId, setSelectedId] = useState(null);
  const browserRef = useRef(null);
  const focusRequested = useRef(false);
  const selectedTrigger = useRef(null);
  const selected = entries.find((entry) => entry.id === selectedId);

  useEffect(() => {
    const query = window.matchMedia?.(DESKTOP_QUERY);
    if (!query) return undefined;
    const update = ({ matches }) => setDesktop(matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (selectedId !== null && !selected) setSelectedId(null);
  }, [selected, selectedId]);

  useEffect(() => {
    if (requestedEntryId == null || !entries.some((entry) => entry.id === requestedEntryId)) return;
    selectedTrigger.current = browserRef.current?.querySelector(
      `[data-entry-id="${requestedEntryId}"]`
    );
    focusRequested.current = true;
    setSelectedId(requestedEntryId);
    onRequestedEntryOpen?.();
  }, [entries, requestedEntryId, onRequestedEntryOpen]);

  useEffect(() => {
    if (!focusRequested.current || selectedId === null) return;
    focusRequested.current = false;
    [
      ...(browserRef.current?.querySelectorAll(
        ".cm-entry-detail__back, .cm-entry-detail__close .g-button"
      ) ?? []),
    ]
      .find((element) => element.offsetParent !== null)
      ?.focus();
  }, [selectedId]);

  const closeDetails = () => {
    setSelectedId(null);
    window.requestAnimationFrame(() => selectedTrigger.current?.focus());
  };

  const details = selected && (
    <EntryDetails
      key={selected.id}
      entry={selected}
      onCopy={onCopy}
      {...actions}
      onClose={closeDetails}
    />
  );

  return (
    <div
      ref={browserRef}
      className={`cm-entry-browser${desktop && selected ? " cm-entry-browser--split" : ""}`}
      onKeyDown={(event) => {
        if (desktop && selected && event.key === "Escape" && !event.defaultPrevented) {
          event.stopPropagation();
          closeDetails();
        }
      }}
    >
      <section className="cm-entry-list-pane" aria-label={t("vault.browser.entries")}>
        <header className="cm-entry-list-header">
          <span>{t("vault.browser.entries")}</span>
          <span className="cm-entry-list-count">{entries.length}</span>
        </header>
        {entries.length === 0 ? (
          <p className="cm-entry-list-empty" role="status">
            {emptyMessage}
          </p>
        ) : (
          <ul className="cm-entry-list">
            {entries.map((entry) => {
              const isNote = entry.kind === "note";
              const copyLabel = t(isNote ? "vault.browser.copyNote" : "vault.columns.copyPassword");
              const current = entry.id === selected?.id;
              return (
                <li
                  key={entry.id}
                  className={`cm-entry-row${current ? " cm-entry-row--selected" : ""}`}
                >
                  <button
                    type="button"
                    className="cm-entry-row__open"
                    data-entry-id={entry.id}
                    aria-current={current ? "true" : undefined}
                    onClick={(event) => {
                      selectedTrigger.current = event.currentTarget;
                      setSelectedId(entry.id);
                    }}
                  >
                    <span className="cm-entry-row__type" aria-hidden="true">
                      <Icon data={isNote ? FileText : Key} size={18} />
                    </span>
                    <span className="cm-entry-row__content">
                      <span className="cm-entry-row__title-line">
                        <span className="cm-entry-row__title">{entry.password_name}</span>
                        {entry.favorite && (
                          <Tooltip content={t("vault.columns.favorite")}>
                            <span className="cm-entry-row__status-icon" aria-hidden="true">
                              <Icon data={StarFill} size={14} />
                            </span>
                          </Tooltip>
                        )}
                      </span>
                      <span className="cm-entry-row__summary">
                        {isNote
                          ? t("entry.kind.note")
                          : entry.username || entry.url || t("entry.kind.login")}
                      </span>
                      {(entry.access === "read" || entry.folder || entry.attachment_count > 0) && (
                        <span className="cm-entry-row__meta-line">
                          {entry.access === "read" && (
                            <Label size="s" theme="normal">
                              {t("sharing.readOnlyAccess")}
                            </Label>
                          )}
                          {entry.folder && (
                            <span className="cm-entry-row__meta">{entry.folder}</span>
                          )}
                          {entry.attachment_count > 0 && (
                            <>
                              <Icon data={Paperclip} size={13} />
                              <span>{entry.attachment_count}</span>
                            </>
                          )}
                        </span>
                      )}
                    </span>
                    <Icon className="cm-entry-row__chevron" data={ChevronRight} size={16} />
                  </button>

                  {desktop && selected ? (
                    <div className="cm-entry-row__actions">
                      <Tooltip content={copyLabel} role="label">
                        <Button
                          type="button"
                          view="flat-secondary"
                          size="l"
                          aria-label={`${copyLabel}: ${entry.password_name}`}
                          onClick={() => onCopy(entry.password_value)}
                        >
                          <Icon data={Copy} />
                        </Button>
                      </Tooltip>
                    </div>
                  ) : (
                    <EntryListActions entry={entry} onCopy={onCopy} {...actions} />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {desktop && selected && (
        <section className="cm-entry-detail-pane" aria-label={t("vault.browser.details")}>
          {details}
        </section>
      )}

      {!desktop && (
        <Dialog
          open={Boolean(selected)}
          onOpenChange={(open) => {
            if (!open) closeDetails();
          }}
          aria-labelledby="entry-detail-title"
          hasCloseButton={false}
          fullWidth
          maxWidth="l"
          contentOverflow="auto"
          className="cm-entry-mobile-dialog"
        >
          <Dialog.Body>{details}</Dialog.Body>
        </Dialog>
      )}
    </div>
  );
};

export default EntryBrowser;

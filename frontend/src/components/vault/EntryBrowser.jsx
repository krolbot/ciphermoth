import { useEffect, useRef, useState } from "react";
import { FileText, Key, Paperclip, StarFill } from "@gravity-ui/icons";
import {
  Box,
  Button,
  Dialog,
  Flex,
  Icon,
  Label,
  List,
  PlaceholderContainer,
  Text,
  useLayoutContext,
} from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import EntryDetails from "./EntryDetails";
import EntryListActions from "./EntryListActions";

const EntryBrowser = ({
  entries,
  emptyMessage,
  onCopy,
  requestedEntryId,
  onRequestedEntryOpen,
  ...actions
}) => {
  const { t } = useTranslation();
  const { isMediaActive } = useLayoutContext();
  const desktop = isMediaActive("xl");
  const [selectedId, setSelectedId] = useState(null);
  const listRef = useRef(null);
  const closeRef = useRef(null);
  const selectedTrigger = useRef(null);
  const selected = entries.find((entry) => entry.id === selectedId);

  useEffect(() => {
    if (selectedId !== null && !selected) setSelectedId(null);
  }, [selected, selectedId]);

  useEffect(() => {
    if (requestedEntryId == null || !entries.some((entry) => entry.id === requestedEntryId)) return;
    selectedTrigger.current = listRef.current?.querySelector(
      `[data-entry-id="${requestedEntryId}"]`
    );
    setSelectedId(requestedEntryId);
    onRequestedEntryOpen?.();
  }, [entries, requestedEntryId, onRequestedEntryOpen]);

  useEffect(() => {
    if (desktop && selectedId !== null) closeRef.current?.focus();
  }, [selectedId, desktop]);

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
      onEdit={(entry) => {
        if (desktop) actions.onEdit(entry);
        else {
          setSelectedId(null);
          window.requestAnimationFrame(() => actions.onEdit(entry));
        }
      }}
      onDelete={(entry) => {
        if (desktop) actions.onDelete(entry);
        else {
          setSelectedId(null);
          window.requestAnimationFrame(() => actions.onDelete(entry));
        }
      }}
      onShare={(entry) => {
        if (desktop) actions.onShare(entry);
        else {
          setSelectedId(null);
          window.requestAnimationFrame(() => actions.onShare(entry));
        }
      }}
    />
  );

  return (
    <Flex
      gap="spacing-6"
      alignItems="flex-start"
      onKeyDown={(event) => {
        if (desktop && selected && event.key === "Escape" && !event.defaultPrevented) {
          event.stopPropagation();
          closeDetails();
        }
      }}
    >
      <Box
        minWidth="0"
        flexGrow={1}
        flexBasis="0"
        as="section"
        aria-label={t("vault.browser.entries")}
      >
        <Flex alignItems="center" gap="spacing-2" paddingBlockEnd="spacing-3">
          <Text variant="subheader-1">{t("vault.browser.entries")}</Text>
          <Label>{entries.length}</Label>
        </Flex>
        {entries.length === 0 ? (
          <PlaceholderContainer size="s" title={emptyMessage} />
        ) : (
          <List
            ref={listRef}
            qa="entry-list"
            aria-label={t("vault.browser.entries")}
            role="grid"
            size="xl"
            items={entries}
            getItemId={(entry) => String(entry.id)}
            getItemTextValue={(entry) => entry.password_name}
            selectionMode="single"
            selectedIds={selected ? [String(selected.id)] : []}
            onItemAction={(_id, entry, event) => {
              selectedTrigger.current = event.currentTarget;
              setSelectedId(entry.id);
            }}
            renderItem={(ctx, { getItemProps, getItemViewProps, getCellProps }) => (
              <List.ItemView
                {...getItemProps({ "data-entry-id": ctx.item.id })}
                {...getItemViewProps()}
                startContent={<Icon data={ctx.item.kind === "note" ? FileText : Key} />}
                description={
                  <Flex gap="spacing-2" wrap="wrap" alignItems="center">
                    <Text ellipsis>
                      {ctx.item.kind === "note"
                        ? t("entry.kind.note")
                        : ctx.item.username || ctx.item.url || t("entry.kind.login")}
                    </Text>
                    {ctx.item.access === "read" && (
                      <Label size="s">{t("sharing.readOnlyAccess")}</Label>
                    )}
                    {ctx.item.folder && (
                      <Text ellipsis color="secondary">
                        {ctx.item.folder}
                      </Text>
                    )}
                    {ctx.item.attachment_count > 0 && (
                      <Text>
                        <Icon data={Paperclip} size={12} /> {ctx.item.attachment_count}
                      </Text>
                    )}
                  </Flex>
                }
                endContent={
                  desktop && !selected ? (
                    <Box {...getCellProps()} onClick={(event) => event.stopPropagation()}>
                      <EntryListActions entry={ctx.item} onCopy={onCopy} {...actions} />
                    </Box>
                  ) : undefined
                }
              >
                <span {...getCellProps()}>
                  <Text ellipsis>{ctx.item.password_name}</Text>
                  {ctx.item.favorite && <Icon data={StarFill} size={12} />}
                </span>
              </List.ItemView>
            )}
          />
        )}
      </Box>
      {desktop && selected && (
        <Flex
          as="section"
          aria-label={t("vault.browser.details")}
          direction="column"
          gap="spacing-4"
          flexBasis="50%"
          minWidth="0"
        >
          <Button ref={closeRef} view="flat-secondary" onClick={closeDetails}>
            {t("vault.browser.back")}
          </Button>
          <Text as="h2" variant="header-1" wordBreak="break-word">
            {selected.password_name}
          </Text>
          {details}
        </Flex>
      )}
      {!desktop && (
        <Dialog
          open={Boolean(selected)}
          onOpenChange={(open) => {
            if (!open) closeDetails();
          }}
          aria-label={selected?.password_name}
          fullWidth
          maxWidth="m"
          contentOverflow="auto"
          returnFocus={selectedTrigger}
        >
          <Dialog.Header caption={selected?.password_name} />
          <Dialog.Body>{details}</Dialog.Body>
          <Dialog.Footer
            onClickButtonCancel={closeDetails}
            textButtonCancel={t("vault.browser.back")}
          />
        </Dialog>
      )}
    </Flex>
  );
};
export default EntryBrowser;

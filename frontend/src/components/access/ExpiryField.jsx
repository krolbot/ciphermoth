import { useId, useRef } from "react";
import { Calendar } from "@gravity-ui/icons";
import { Button, Flex, Icon, Text, TextInput } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { toLocalExpiry } from "../../lib/accessExpiry";

const ExpiryField = ({ value, onUpdate, disabled, invalid }) => {
  const { t } = useTranslation();
  const inputId = useId();
  const inputRef = useRef(null);

  const openPicker = () => {
    if (inputRef.current?.showPicker) inputRef.current.showPicker();
    else inputRef.current?.focus();
  };

  return (
    <Flex direction="column" gap="spacing-2" minWidth="0" width="100%">
      <Text as="label" htmlFor={inputId}>
        {t("folderAccess.expiresAt")}
      </Text>
      <TextInput
        id={inputId}
        controlRef={inputRef}
        size="xl"
        type="datetime-local"
        note={t("folderAccess.expiresHint")}
        value={value}
        disabled={disabled}
        onUpdate={onUpdate}
        validationState={invalid ? "invalid" : undefined}
        errorMessage={invalid ? t("folderAccess.expiresValidation") : undefined}
        endContent={
          <Button
            type="button"
            size="xl"
            view="flat-secondary"
            disabled={disabled}
            aria-label={t("folderAccess.chooseExpiry")}
            onClick={openPicker}
          >
            <Icon data={Calendar} />
          </Button>
        }
        controlProps={{
          "aria-label": t("folderAccess.expiresAt"),
          min: toLocalExpiry(new Date().toISOString()),
        }}
      />
    </Flex>
  );
};

export default ExpiryField;

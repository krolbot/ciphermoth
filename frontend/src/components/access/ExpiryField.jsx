import { useId } from "react";
import { Flex, Text, TextInput } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { toLocalExpiry } from "../../lib/accessExpiry";

const ExpiryField = ({ value, onUpdate, disabled, invalid }) => {
  const { t } = useTranslation();
  const inputId = useId();

  return (
    <Flex direction="column" gap="spacing-2" minWidth="0" width="100%">
      <Text as="label" htmlFor={inputId}>
        {t("folderAccess.expiresAt")}
      </Text>
      <TextInput
        id={inputId}
        size="xl"
        type="datetime-local"
        note={t("folderAccess.expiresHint")}
        value={value}
        disabled={disabled}
        onUpdate={onUpdate}
        validationState={invalid ? "invalid" : undefined}
        errorMessage={invalid ? t("folderAccess.expiresValidation") : undefined}

        controlProps={{
          "aria-label": t("folderAccess.expiresAt"),
          min: toLocalExpiry(new Date().toISOString()),
        }}
      />
    </Flex>
  );
};

export default ExpiryField;

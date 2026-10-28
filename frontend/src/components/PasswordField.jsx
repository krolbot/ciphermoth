import { useId, useState } from "react";
import { Eye, EyeSlash, MagicWand } from "@gravity-ui/icons";
import { Button, Flex, Icon, PasswordInput, Text, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { IS_DESKTOP } from "../platform";
import { generatePassword } from "../lib/passwordGenerator";

const SIZE_MAP = { small: "m", medium: "l", large: "xl" };

const PasswordField = ({
  show: showProp,
  onToggleShow,
  onGenerate,
  adornment = null,
  slotProps,
  label,
  helperText,
  required = false,
  size = "xl",
  id: idProp,
  inputRef,
  error,
  fullWidth: _fullWidth,
  sx: _sx,
  ...props
}) => {
  // Legacy layout props are intentionally consumed here while callers migrate from MUI.
  void _fullWidth;
  void _sx;
  const { t } = useTranslation();
  const generatedId = useId();
  const id = idProp ?? `cm-password-${generatedId}`;
  const controlSize = SIZE_MAP[size] ?? size;

  const [showInternal, setShowInternal] = useState(false);
  const controlled = showProp !== undefined;
  const show = controlled ? showProp : showInternal;
  const readOnly = props.readOnly || slotProps?.input?.readOnly || slotProps?.htmlInput?.readOnly;

  const updateReveal = (visible) => {
    if (controlled) onToggleShow?.(visible);
    else setShowInternal(visible);
  };

  const generateAction = onGenerate && !readOnly && (
    <Tooltip content={t("entry.actions.generatePassword")} role="label">
      <Button
        type="button"
        view="flat-secondary"
        size={controlSize}
        aria-label={t("entry.actions.generatePassword")}
        onClick={() => onGenerate(generatePassword())}
        disabled={props.disabled}
      >
        <Icon data={MagicWand} />
      </Button>
    </Tooltip>
  );

  const input = (
    <PasswordInput
      {...props}
      required={required}
      controlRef={inputRef ?? props.controlRef}
      validationState={error ? "invalid" : props.validationState}
      errorMessage={error || props.validationState === "invalid" ? helperText : undefined}
      note={!error && props.validationState !== "invalid" ? helperText : undefined}

      id={id}
      size={controlSize}
      hideCopyButton
      hideRevealButton
      revealValue={show}
      onRevealValueUpdate={updateReveal}
      endContent={
        <Flex alignItems="center" gap="spacing-1">
          {adornment}
          {generateAction}
          <Tooltip content={t(show ? "passwordField.hide" : "passwordField.show")} role="label">
            <Button
              type="button"
              view="flat-secondary"
              size={controlSize}
              qa="reveal-button"
              aria-label={t(show ? "passwordField.hide" : "passwordField.show")}
              disabled={props.disabled}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => updateReveal(!show)}
            >
              <Icon data={show ? EyeSlash : Eye} />
            </Button>
          </Tooltip>
        </Flex>
      }
      autoComplete={IS_DESKTOP ? "off" : props.autoComplete}
      controlProps={{
        spellCheck: false,
        autoCorrect: "off",
        autoCapitalize: "none",
        required,
        ...props.controlProps,
        ...slotProps?.htmlInput,
      }}
    />
  );

  return label ? (
    <Flex direction="column" gap="spacing-2" minWidth="0">
      <Text as="label" htmlFor={id}>
        {label}
      </Text>
      {input}
    </Flex>
  ) : (
    input
  );
};

export default PasswordField;

import { useId, useState } from "react";
import { MagicWand } from "@gravity-ui/icons";
import { Button, Icon, PasswordInput, Tooltip } from "@gravity-ui/uikit";
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
  size = "l",
  id: idProp,
  className,
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
  const labelId = `${id}-label`;
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
        size="m"
        aria-label={t("entry.actions.generatePassword")}
        onClick={() => onGenerate(generatePassword())}
        disabled={props.disabled}
      >
        <Icon data={MagicWand} />
      </Button>
    </Tooltip>
  );

  return (
    <div className={`cm-password-field${className ? ` ${className}` : ""}`}>
      {label && (
        <span id={labelId} className="cm-field__label">
          {label}
          {required && (
            <span className="cm-field__required" aria-hidden="true">
              *
            </span>
          )}
        </span>
      )}
      <PasswordInput
        {...props}
        id={id}
        size={SIZE_MAP[size] ?? size}
        hideCopyButton
        showRevealTooltip
        revealValue={show}
        onRevealValueUpdate={updateReveal}
        endContent={
          adornment || generateAction ? (
            <span className="cm-password-field__actions">
              {adornment}
              {generateAction}
            </span>
          ) : undefined
        }
        autoComplete={IS_DESKTOP ? "off" : props.autoComplete}
        controlProps={{
          spellCheck: false,
          autoCorrect: "off",
          autoCapitalize: "none",
          required,
          ...(label ? { "aria-labelledby": labelId } : {}),
          ...slotProps?.htmlInput,
        }}
      />
      {helperText && <span className="cm-password-field__note">{helperText}</span>}
    </div>
  );
};

export default PasswordField;

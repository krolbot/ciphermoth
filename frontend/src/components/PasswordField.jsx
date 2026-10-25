import { IS_DESKTOP } from "../platform";
import { useState } from "react";
import { IconButton, InputAdornment, TextField, Tooltip } from "@mui/material";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { useTranslation } from "react-i18next";
import { generatePassword } from "../lib/passwordGenerator";

const PasswordField = ({
  show: showProp,
  onToggleShow,
  onGenerate,
  adornment = null,
  slotProps,
  ...props
}) => {
  const { t } = useTranslation();
  const [showInternal, setShowInternal] = useState(false);
  const controlled = showProp !== undefined;
  const show = controlled ? showProp : showInternal;
  const toggle = controlled ? onToggleShow : () => setShowInternal((v) => !v);

  return (
    <TextField
      fullWidth
      type={show ? "text" : "password"}
      {...props}
      autoComplete={IS_DESKTOP ? "off" : props.autoComplete}
      slotProps={{
        ...slotProps,
        htmlInput: {
          spellCheck: false,
          autoCorrect: "off",
          autoCapitalize: "none",
          ...slotProps?.htmlInput,
        },
        input: {
          ...slotProps?.input,
          endAdornment: (
            <InputAdornment position="end">
              {adornment}
              {onGenerate && !slotProps?.input?.readOnly && !slotProps?.htmlInput?.readOnly && (
                <Tooltip title={t("entry.actions.generatePassword")}>
                  <span>
                    <IconButton
                      type="button"
                      aria-label={t("entry.actions.generatePassword")}
                      onClick={() => onGenerate(generatePassword())}
                      disabled={props.disabled}
                      size="small"
                      sx={{ width: 44, height: 44 }}
                    >
                      <AutoFixHighIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              )}
              <Tooltip title={t(show ? "passwordField.hide" : "passwordField.show")}>
                <IconButton
                  type="button"
                  aria-label={t(show ? "passwordField.hide" : "passwordField.show")}
                  onClick={toggle}
                  disabled={props.disabled}
                  edge="end"
                  size="small"
                  sx={{ width: 44, height: 44 }}
                >
                  {show ? (
                    <VisibilityOffIcon fontSize="small" />
                  ) : (
                    <VisibilityIcon fontSize="small" />
                  )}
                </IconButton>
              </Tooltip>
            </InputAdornment>
          ),
        },
      }}
    />
  );
};

export default PasswordField;

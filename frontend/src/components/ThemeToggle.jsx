import { Moon, Sun } from "@gravity-ui/icons";
import { Button, Icon, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { useColorMode } from "../hooks/useColorMode";

const ThemeToggle = ({ placement = "inline", showLabel = false }) => {
  const { t } = useTranslation();
  const { mode, toggle } = useColorMode();
  const dark = mode === "dark";
  const label = t(dark ? "theme.switchToLight" : "theme.switchToDark");

  return (
    <Tooltip content={label} role={showLabel ? "tooltip" : "label"}>
      <Button
        type="button"
        view="flat-secondary"
        size="l"
        aria-label={label}
        onClick={toggle}
        className={placement === "floating" ? "cm-theme-toggle--floating" : undefined}
      >
        <Icon data={dark ? Sun : Moon} />
        {showLabel && t(dark ? "theme.toLight" : "theme.toDark")}
      </Button>
    </Tooltip>
  );
};

export default ThemeToggle;

import { useState } from "react";
import { IconButton, ListItemText, Menu, MenuItem, Tooltip } from "@mui/material";
import LanguageIcon from "@mui/icons-material/Language";
import { useTranslation } from "react-i18next";

const OPTIONS = [
  { language: "en", labelKey: "language.english" },
  { language: "ru", labelKey: "language.russian" },
];

const placementStyles = {
  floating: {
    position: "fixed",
    top: 20,
    right: 20,
    zIndex: 1301,
    bgcolor: "background.paper",
    border: "1px solid",
    borderColor: "divider",
  },
  toolbar: undefined,
};

const LanguageSwitcher = ({ placement = "toolbar" }) => {
  const { t, i18n } = useTranslation();
  const [anchor, setAnchor] = useState(null);
  const current = i18n.resolvedLanguage ?? i18n.language;

  const selectLanguage = async (language) => {
    setAnchor(null);
    await i18n.changeLanguage(language);
  };

  return (
    <>
      <Tooltip title={t("language.label")}>
        <IconButton
          color={placement === "toolbar" ? "inherit" : "default"}
          aria-label={t("language.label")}
          onClick={(event) => setAnchor(event.currentTarget)}
          sx={placementStyles[placement]}
        >
          <LanguageIcon />
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {OPTIONS.map(({ language, labelKey }) => (
          <MenuItem
            key={language}
            selected={current === language}
            onClick={() => selectLanguage(language)}
          >
            <ListItemText>{t(labelKey)}</ListItemText>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
};

export default LanguageSwitcher;

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "@mui/material/styles";
import { useTranslation } from "react-i18next";

import { createAppTheme } from "../lib/theme";

const STORAGE_KEY = "ciphermoth-theme";
const ColorModeContext = createContext({ mode: "dark", toggle: () => {} });

const readStoredMode = () => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    return "dark";
  }
  return "dark";
};

export const ColorModeProvider = ({ children }) => {
  const { i18n } = useTranslation();
  const [mode, setMode] = useState(readStoredMode);

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      return;
    }
  }, [mode]);

  const value = useMemo(
    () => ({
      mode,
      toggle: () => {
        const root = document.documentElement;
        root.classList.add("cm-theming");
        window.setTimeout(() => root.classList.remove("cm-theming"), 520);
        setMode((prev) => (prev === "dark" ? "light" : "dark"));
      },
    }),
    [mode]
  );

  const language = i18n.resolvedLanguage ?? i18n.language;
  const theme = useMemo(() => createAppTheme(mode, language), [mode, language]);

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </ColorModeContext.Provider>
  );
};

export const useColorMode = () => useContext(ColorModeContext);

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Provider as GravityProvider } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

const STORAGE_KEY = "ciphermoth-theme";
const MOBILE_QUERY = "(max-width: 899px)";
const ModeContext = createContext(null);

const initialMode = () => {
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === "light" || saved === "dark" ? saved : "dark";
};

const initialMobile = () => window.matchMedia?.(MOBILE_QUERY).matches ?? false;

export const ColorModeProvider = ({ children }) => {
  const { i18n } = useTranslation();
  const [mode, setMode] = useState(initialMode);
  const [mobile, setMobile] = useState(initialMobile);
  const language = (i18n.resolvedLanguage ?? i18n.language)?.startsWith("ru") ? "ru" : "en";

  useEffect(() => {
    const query = window.matchMedia?.(MOBILE_QUERY);
    if (!query) return undefined;
    const update = ({ matches }) => setMobile(matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode);
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
  }, [mode]);

  const value = useMemo(
    () => ({
      mode,
      setMode,
      toggle: () => {
        document.documentElement.classList.add("cm-theming");
        window.setTimeout(() => document.documentElement.classList.remove("cm-theming"), 460);
        setMode((current) => (current === "dark" ? "light" : "dark"));
      },
    }),
    [mode]
  );

  return (
    <ModeContext.Provider value={value}>
      <GravityProvider
        theme={mode}
        lang={language}
        mobile={mobile}
        defaultProps={{ TooltipDelayGroup: { skipDelay: 300 } }}
      >
        {children}
      </GravityProvider>
    </ModeContext.Provider>
  );
};

export const useColorMode = () => {
  const context = useContext(ModeContext);
  if (!context) throw new Error("useColorMode must be used inside ColorModeProvider");
  return context;
};

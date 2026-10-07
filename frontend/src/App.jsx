import { useEffect, useState } from "react";
import { BrowserRouter as Router, Navigate, Route, Routes } from "react-router-dom";
import { Alert, Box, Button, Container, CssBaseline, GlobalStyles, Toolbar } from "@mui/material";
import { useStoreActions } from "easy-peasy";
import { useTranslation } from "react-i18next";

import apiClient from "./api/client";
import PasswordChangeDialog from "./components/PasswordChangeDialog";
import ThemeToggle from "./components/ThemeToggle";
import TopMenu from "./components/TopMenu";
import { ColorModeProvider } from "./hooks/useColorMode";
import useAutoLogout from "./hooks/useAutoLogout";
import routes from "./routes";
import { getCurrentUser, isAuth, setCurrentUser } from "./utils";
import { GLOW, INFO, PAPER_DARK, TEXT_ON_DARK, WARN, WEAK } from "./lib/brand";

const SANS = "'Space Grotesk Variable', system-ui, sans-serif";

const AppContent = () => {
  useAutoLogout();

  const { t } = useTranslation();
  const authed = isAuth();
  const [currentUser, setUser] = useState(getCurrentUser);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwordReminderOpen, setPasswordReminderOpen] = useState(true);
  const mustChangePassword = currentUser?.must_change_password;
  const getSettings = useStoreActions((a) => a.ciphermothModels.settings.get);
  useEffect(() => {
    if (!authed) return;
    getSettings();
    apiClient
      .get("/auth/me")
      .then(({ data }) => {
        setCurrentUser(data);
        setUser(data);
      })
      .catch(() => {});
  }, [authed, getSettings]);

  const appRoutes = (
    <Routes>
      {routes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element} />
      ))}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );

  if (!authed) {
    return (
      <>
        <CssBaseline />
        {appRoutes}
      </>
    );
  }

  return (
    <Box sx={{ display: "flex", width: "100%", maxWidth: "100vw", overflowX: "hidden" }}>
      <CssBaseline />
      <TopMenu />
      <Box
        component="main"
        sx={{
          bgcolor: "background.default",
          flexGrow: 1,
          minWidth: 0,
          width: "100%",
          maxWidth: "100%",
          minHeight: "100vh",
          overflowX: "hidden",
          overflowY: "auto",
        }}
      >
        <Toolbar />
        <Container
          maxWidth="lg"
          sx={{ mt: { xs: 2.5, sm: 4 }, mb: 4, px: { xs: 2, sm: 3 }, pb: { xs: 7, sm: 3 } }}
        >
          {mustChangePassword && passwordReminderOpen && (
            <Alert
              severity="warning"
              onClose={() => setPasswordReminderOpen(false)}
              sx={{ mb: 2, alignItems: "flex-start", "& .MuiAlert-message": { width: "100%" } }}
            >
              <Box
                sx={{
                  display: "flex",
                  flexDirection: { xs: "column", sm: "row" },
                  alignItems: { xs: "flex-start", sm: "center" },
                  gap: 1,
                }}
              >
                <Box sx={{ flexGrow: 1 }}>{t("auth.passwordChangeReminder")}</Box>
                <Button color="inherit" size="small" onClick={() => setPasswordOpen(true)}>
                  {t("auth.changePassword")}
                </Button>
              </Box>
            </Alert>
          )}
          {appRoutes}
        </Container>
      </Box>
      <PasswordChangeDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />
      <ThemeToggle />
    </Box>
  );
};

const snackbarStyles = (
  <GlobalStyles
    styles={{
      // Toasts share a single dark surface with a coloured accent stripe so the
      // outcome reads at a glance without breaking the black-and-glow palette.
      ".notistack-MuiContent": {
        backgroundColor: `${PAPER_DARK} !important`,
        color: `${TEXT_ON_DARK} !important`,
        fontFamily: `${SANS} !important`,
        borderRadius: "10px !important",
        border: "1px solid rgba(255,255,255,0.12)",
      },
      ".notistack-MuiContent-success": { borderLeft: `3px solid ${GLOW} !important` },
      ".notistack-MuiContent-error": { borderLeft: `3px solid ${WEAK} !important` },
      ".notistack-MuiContent-warning": { borderLeft: `3px solid ${WARN} !important` },
      ".notistack-MuiContent-info": { borderLeft: `3px solid ${INFO} !important` },
    }}
  />
);

const themeTransitionStyles = (
  <GlobalStyles
    styles={{
      "html.cm-theming, html.cm-theming *, html.cm-theming *::before, html.cm-theming *::after": {
        transition:
          "background-color 420ms ease, border-color 420ms ease, color 300ms ease, fill 300ms ease !important",
      },
    }}
  />
);

const App = () => (
  <Router>
    <ColorModeProvider>
      {snackbarStyles}
      {themeTransitionStyles}
      <AppContent />
    </ColorModeProvider>
  </Router>
);

export default App;

import { useEffect, useState } from "react";
import { BrowserRouter as Router, Navigate, Route, Routes } from "react-router-dom";
import { useStoreActions } from "easy-peasy";
import { Box, Container, Flex, ToasterComponent } from "@gravity-ui/uikit";

import DesktopGate from "./platform/DesktopGate";
import apiClient from "./api/client";
import PasswordChangeDialog from "./components/PasswordChangeDialog";
import TopMenu from "./components/TopMenu";
import { ColorModeProvider } from "./hooks/useColorMode";
import useAutoLogout from "./hooks/useAutoLogout";
import routes from "./routes";
import { getCurrentUser, isAuth, setCurrentUser } from "./utils";

const AppContent = () => {
  useAutoLogout();

  const authed = isAuth();
  const [currentUser, setUser] = useState(getCurrentUser);
  const passwordChangeRequired = Boolean(currentUser?.must_change_password);
  const getSettings = useStoreActions((actions) => actions.ciphermothModels.settings.get);

  useEffect(() => {
    if (!authed || passwordChangeRequired) return;
    getSettings();
    apiClient
      .get("/auth/me")
      .then(({ data }) => {
        setCurrentUser(data);
        setUser(data);
      })
      .catch(() => {});
  }, [authed, passwordChangeRequired, getSettings]);

  const appRoutes = (
    <Routes>
      {routes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element} />
      ))}
      <Route path="*" element={<Navigate to="/passwords" replace />} />
    </Routes>
  );

  if (!authed) return appRoutes;

  return (
    <Flex minHeight="100dvh" direction={{ xs: "column", l: "row" }}>
      <TopMenu />
      <Box as="main" flexGrow={1} minWidth="0">
        <Container paddingBlock="spacing-6" gutters={{ xs: "spacing-3", m: "spacing-6" }}>
          {!passwordChangeRequired && appRoutes}
        </Container>
      </Box>
      <PasswordChangeDialog
        open={passwordChangeRequired}
        required
        onClose={() => {}}
        onChanged={setUser}
      />
    </Flex>
  );
};

const App = () => (
  <Router>
    <ColorModeProvider>
      <DesktopGate>
        <AppContent />
      </DesktopGate>
      <ToasterComponent />
    </ColorModeProvider>
  </Router>
);

export default App;

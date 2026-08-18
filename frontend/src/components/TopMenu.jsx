import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  AppBar,
  Box,
  Button,
  Chip,
  Container,
  IconButton,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import PeopleIcon from "@mui/icons-material/People";
import LogoutIcon from "@mui/icons-material/Logout";
import SettingsIcon from "@mui/icons-material/Settings";
import UpgradeIcon from "@mui/icons-material/Upgrade";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import apiClient from "../api/client";
import { getCurrentUser, isAuth, removeKeyDerivation } from "../utils";
import { DEV_ACCENT, IS_DEV } from "../lib/appEnv";
import { GLOW } from "../lib/brand";
import { VAULT_HEALTH_ACTION_ID } from "../lib/domSlots";
import EnvBadge from "./EnvBadge";
import LanguageSwitcher from "./LanguageSwitcher";
import MothIcon from "./MothIcon";
import SettingsModal from "./SettingsModal";
import UpdateDialog from "./UpdateDialog";
import UsersDialog from "./UsersDialog";

const TopMenu = () => {
  const { t } = useTranslation();
  const userIsAuth = isAuth();
  const { pathname } = useLocation();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [usersOpen, setUsersOpen] = useState(false);
  const user = getCurrentUser();
  const [updateOpen, setUpdateOpen] = useState(false);

  const updateCheckEnabled = useStoreState(
    (s) => s.ciphermothModels.settings.settings.update_check_enabled
  );
  const updateAvailable = useStoreState((s) => s.ciphermothModels.updates.updateAvailable);
  const version = useStoreState((s) => s.ciphermothModels.updates.current);
  const checkForUpdates = useStoreActions((a) => a.ciphermothModels.updates.checkForUpdates);
  const fetchVersion = useStoreActions((a) => a.ciphermothModels.updates.fetchVersion);

  useEffect(() => {
    if (userIsAuth) fetchVersion();
  }, [userIsAuth, fetchVersion]);

  useEffect(() => {
    if (userIsAuth && user?.role === "admin" && updateCheckEnabled) checkForUpdates();
  }, [userIsAuth, user?.role, updateCheckEnabled, checkForUpdates]);

  const handleLogout = async () => {
    try {
      await apiClient.post("/auth/logout");
    } finally {
      removeKeyDerivation();
      window.location.replace("/login");
    }
  };

  return (
    <AppBar
      position="absolute"
      sx={IS_DEV ? { borderBottom: `3px solid ${DEV_ACCENT}` } : undefined}
    >
      <Container maxWidth="lg" sx={{ px: { xs: 1.5, sm: 3 } }}>
        <Toolbar disableGutters sx={{ minHeight: { xs: 64, sm: 72 }, gap: 0.25 }}>
          <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 22, height: 22, display: "flex", flexShrink: 0, color: "inherit" }}>
              <MothIcon
                width="100%"
                height="100%"
                style={{ display: "block", overflow: "visible" }}
              />
            </Box>
            <Typography
              component="h1"
              variant="h6"
              noWrap
              sx={{ color: "inherit", fontWeight: 600, fontSize: { xs: 18, sm: 20 } }}
            >
              Cipher
              <Box component="span" sx={{ color: GLOW }}>
                Moth
              </Box>
            </Typography>
            <Box sx={{ display: { xs: "none", sm: "block" } }}>
              <EnvBadge />
            </Box>
            {version && (
              <Tooltip arrow title={t("topMenu.runningVersion")}>
                <Typography
                  component="span"
                  sx={{
                    display: { xs: "none", md: "inline" },
                    fontFamily: "'Space Mono', monospace",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    color: "rgba(255,255,255,0.4)",
                    cursor: "default",
                  }}
                >
                  v{String(version).replace(/^v/, "")}
                </Typography>
              </Tooltip>
            )}
          </Box>

          {userIsAuth ? (
            <>
              {user?.role === "admin" && updateAvailable && (
                <Tooltip title={t("topMenu.updateAvailable")}>
                  <Chip
                    icon={<UpgradeIcon sx={{ fontSize: 18 }} />}
                    label={t("common.actions.update")}
                    size="small"
                    onClick={() => setUpdateOpen(true)}
                    sx={{
                      display: { xs: "none", sm: "inline-flex" },
                      mr: 1,
                      bgcolor: GLOW,
                      color: "#0b0b0c",
                      fontWeight: 700,
                      cursor: "pointer",
                      "& .MuiChip-icon": { color: "#0b0b0c" },
                      "&:hover": { bgcolor: GLOW, filter: "brightness(0.92)" },
                    }}
                  />
                </Tooltip>
              )}
              <Box id={VAULT_HEALTH_ACTION_ID} sx={{ display: "flex", alignItems: "center" }} />
              <LanguageSwitcher />
              {user?.role === "admin" && (
                <Tooltip title={t("users.title")}>
                  <IconButton color="inherit" onClick={() => setUsersOpen(true)} sx={{ p: 1 }}>
                    <PeopleIcon />
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title={t("topMenu.settings")}>
                <IconButton color="inherit" onClick={() => setSettingsOpen(true)} sx={{ p: 1 }}>
                  <SettingsIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title={t("auth.logOut")}>
                <IconButton
                  color="inherit"
                  aria-label={t("auth.logOut")}
                  onClick={handleLogout}
                  sx={{ p: 1 }}
                >
                  <LogoutIcon />
                </IconButton>
              </Tooltip>
              <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
              <UsersDialog open={usersOpen} onClose={() => setUsersOpen(false)} />
              <UpdateDialog open={updateOpen} onClose={() => setUpdateOpen(false)} />
            </>
          ) : (
            pathname !== "/login" && (
              <Button href="/login" color="inherit">
                {t("auth.logIn")}
              </Button>
            )
          )}
        </Toolbar>
      </Container>
    </AppBar>
  );
};

export default TopMenu;

import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
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
import SettingsIcon from "@mui/icons-material/Settings";
import GroupOutlinedIcon from "@mui/icons-material/GroupOutlined";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";
import UpgradeIcon from "@mui/icons-material/Upgrade";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { endSession } from "../api/session";
import { getCurrentUser, isAuth } from "../utils";
import { DEV_ACCENT, IS_DEV } from "../lib/appEnv";
import { GLOW } from "../lib/brand";
import EnvBadge from "./EnvBadge";
import LanguageSwitcher from "./LanguageSwitcher";
import MothIcon from "./MothIcon";
import PasswordChangeDialog from "./PasswordChangeDialog";
import SettingsModal from "./SettingsModal";
import UpdateDialog from "./UpdateDialog";

const TopMenu = () => {
  const { t } = useTranslation();
  const userIsAuth = isAuth();
  const currentUser = getCurrentUser();
  const { pathname } = useLocation();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [updateOpen, setUpdateOpen] = useState(false);

  const updateCheckEnabled = useStoreState(
    (s) => s.ciphermothModels.settings.settings.update_check_enabled
  );
  const settingsLoaded = useStoreState((s) => s.ciphermothModels.settings.loaded);
  const updateAvailable = useStoreState((s) => s.ciphermothModels.updates.updateAvailable);
  const version = useStoreState((s) => s.ciphermothModels.updates.current);
  const checkForUpdates = useStoreActions((a) => a.ciphermothModels.updates.checkForUpdates);
  const fetchVersion = useStoreActions((a) => a.ciphermothModels.updates.fetchVersion);

  useEffect(() => {
    if (userIsAuth) fetchVersion();
  }, [userIsAuth, fetchVersion]);

  useEffect(() => {
    if (userIsAuth && settingsLoaded && updateCheckEnabled) checkForUpdates();
  }, [userIsAuth, settingsLoaded, updateCheckEnabled, checkForUpdates]);

  const handleLogout = () => endSession();

  return (
    <AppBar
      position="absolute"
      sx={IS_DEV ? { borderBottom: `3px solid ${DEV_ACCENT}` } : undefined}
    >
      <Container maxWidth="lg">
        <Toolbar disableGutters>
          <Box sx={{ flexGrow: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 1 }}>
            <Box
              component={Link}
              to="/passwords"
              aria-label={`CipherMoth — ${t("users.backToVault")}`}
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 1,
                minWidth: 44,
                minHeight: 44,
                color: "inherit",
                textDecoration: "none",
                borderRadius: 1,
                "&:focus-visible": { outline: `2px solid ${GLOW}`, outlineOffset: 2 },
              }}
            >
              <Box sx={{ width: 24, height: 24, display: "flex", color: "inherit" }}>
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
                sx={{ color: "inherit", fontWeight: 600, display: { xs: "none", sm: "block" } }}
              >
                Cipher
                <Box component="span" sx={{ color: GLOW }}>
                  Moth
                </Box>
              </Typography>
            </Box>
            <EnvBadge />
            {version && (
              <Tooltip arrow title={t("topMenu.runningVersion")}>
                <Typography
                  component="span"
                  sx={{
                    fontFamily: "'Space Mono', monospace",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    color: "rgba(255,255,255,0.4)",
                    cursor: "default",
                    display: { xs: "none", sm: "inline" },
                  }}
                >
                  v{String(version).replace(/^v/, "")}
                </Typography>
              </Tooltip>
            )}
          </Box>

          {userIsAuth ? (
            <>
              <LanguageSwitcher />
              {updateAvailable && (
                <Tooltip title={t("topMenu.updateAvailable")}>
                  <Chip
                    icon={<UpgradeIcon sx={{ fontSize: 18 }} />}
                    label={t("common.actions.update")}
                    size="small"
                    onClick={() => setUpdateOpen(true)}
                    sx={{
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
              {currentUser?.role === "admin" && (
                <Tooltip title={t("users.title")}>
                  <IconButton component={Link} to="/users" color="inherit" sx={{ mr: 0.5 }}>
                    <GroupOutlinedIcon />
                  </IconButton>
                </Tooltip>
              )}
              {currentUser?.role === "admin" && (
                <Tooltip title={t("topMenu.settings")}>
                  <IconButton
                    color="inherit"
                    onClick={() => setSettingsOpen(true)}
                    sx={{ mr: 0.5 }}
                  >
                    <SettingsIcon />
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title={t("auth.changePassword")}>
                <IconButton color="inherit" onClick={() => setPasswordOpen(true)} sx={{ mr: 0.5 }}>
                  <KeyOutlinedIcon />
                </IconButton>
              </Tooltip>
              <Button color="inherit" onClick={handleLogout}>
                {t("auth.logOut")}
              </Button>
              {currentUser?.role === "admin" && (
                <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
              )}
              <PasswordChangeDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />
              <UpdateDialog open={updateOpen} onClose={() => setUpdateOpen(false)} />
            </>
          ) : (
            <>
              <LanguageSwitcher />
              {pathname !== "/login" && (
                <Button href="/login" color="inherit">
                  {t("auth.logIn")}
                </Button>
              )}
            </>
          )}
        </Toolbar>
      </Container>
    </AppBar>
  );
};

export default TopMenu;

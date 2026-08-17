import { useEffect, useState } from "react";
import { Box, Button, Checkbox, FormControlLabel, LinearProgress, TextField, Typography } from "@mui/material";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useSnackbar } from "notistack";
import { useTranslation } from "react-i18next";

import LanguageSwitcher from "../components/LanguageSwitcher";
import LoadingScreen from "../components/LoadingScreen";
import MothIcon from "../components/MothIcon";
import PasswordField from "../components/PasswordField";
import ThemeToggle from "../components/ThemeToggle";
import { getMasterPasswordStrength } from "../lib/passwordStrength";
import { GLOW, GLOW_SOFT, INK, WARN } from "../lib/brand";

const unlockButtonSx = {
  bgcolor: GLOW,
  color: INK,
  fontWeight: 700,
  letterSpacing: "0.06em",
  py: 1.6,
  "&:hover": { bgcolor: GLOW_SOFT },
  "&.Mui-disabled": { bgcolor: "rgba(125,211,192,0.3)", color: "rgba(11,11,12,0.55)" },
};

const LoginPage = () => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();

  const {
    fetchStatus,
    authenticate,
    setUsername,
    setValue,
    setConfirm,
    setMigrationToken,
    setError,
  } = useStoreActions((a) => a.ciphermothModels.masterPassword);
  const {
    initialized,
    legacyVault,
    error,
    username,
    value,
    confirm,
    migrationToken,
    loading,
  } = useStoreState((s) => s.ciphermothModels.masterPassword);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    const notice = sessionStorage.getItem("logout_notice");
    if (notice) {
      sessionStorage.removeItem("logout_notice");
      enqueueSnackbar(t(notice), { variant: "info" });
    }
  }, [enqueueSnackbar, t]);

  useEffect(() => {
    if (error) enqueueSnackbar(error, { variant: "error" });
  }, [error, enqueueSnackbar]);

  const [acknowledged, setAcknowledged] = useState(false);
  const creatingVault = initialized === false && !legacyVault;
  const strength = creatingVault ? getMasterPasswordStrength(value) : null;

  const validateUsername = () => {
    if (username.trim()) return true;
    setError(t("auth.validation.enterUsername"));
    return false;
  };

  const handleLogin = () => {
    if (!validateUsername()) return;
    if (!value.trim()) {
      enqueueSnackbar(t("auth.validation.enterMasterPassword"), { variant: "error" });
      return;
    }
    authenticate({ endpoint: "/auth/login", username, master_password: value });
  };

  const handleCreate = () => {
    if (!validateUsername()) return;
    if (!value) {
      setError(t(creatingVault ? "auth.validation.enterNewMasterPassword" : "auth.validation.enterMasterPassword"));
      return;
    }
    if (legacyVault && !migrationToken) {
      setError(t("auth.validation.enterMigrationToken"));
      return;
    }
    if (creatingVault && value !== confirm) {
      setError(t("auth.validation.passwordsDoNotMatch"));
      return;
    }
    if (creatingVault && strength && strength.value < 70) {
      setError(t("auth.validation.weakPassword"));
      return;
    }
    if (creatingVault && !acknowledged) {
      setError(t("auth.validation.confirmNoRecovery"));
      return;
    }
    authenticate({ endpoint: "/auth/bootstrap", username, master_password: value });
  };

  if (initialized === null) {
    return <LoadingScreen />;
  }

  return (
    <Box
      sx={{
        position: "fixed",
        inset: 0,
        bgcolor: "background.default",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        p: 3,
        overflow: "auto",
        zIndex: (t) => t.zIndex.modal,
      }}
    >
      <Box
        component="form"
        onSubmit={(e) => e.preventDefault()}
        sx={{
          width: "100%",
          maxWidth: initialized ? 400 : 440,
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          px: { xs: 3, sm: 4.25 },
          py: 5,
          textAlign: "center",
        }}
      >
        <Box
          sx={{
            width: 56,
            mx: "auto",
            mb: 2.25,
            color: "text.primary",
            filter: `drop-shadow(0 0 18px color-mix(in srgb, ${GLOW} 50%, transparent))`,
          }}
        >
          <MothIcon width="100%" height="100%" style={{ display: "block", overflow: "visible" }} />
        </Box>

        {initialized ? (
          <>
            <Typography sx={{ fontSize: 24, fontWeight: 700, color: "text.primary" }}>
              Cipher
              <Box component="span" sx={{ color: GLOW }}>
                Moth
              </Box>
            </Typography>
            <Typography
              sx={{
                mt: 1,
                mb: 3.25,
                fontFamily: "'Space Mono', monospace",
                fontSize: 12,
                color: "text.secondary",
              }}
            >
              {t("auth.tagline")}
            </Typography>
          </>
        ) : (
          <>
            <Typography sx={{ fontSize: 23, fontWeight: 700, color: "text.primary" }}>
              {t("auth.setupTitle")}
            </Typography>
            <Typography
              sx={{ mt: 1, mb: 3, fontSize: 13, color: "text.secondary", lineHeight: 1.5 }}
            >
              {t("auth.setupDescription")}
            </Typography>
          </>
        )}

        <TextField
          label={t("auth.username")}
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoFocus
          fullWidth
          sx={{ mb: 1.5 }}
          slotProps={{ htmlInput: { autoCapitalize: "none", spellCheck: false } }}
        />
        <PasswordField
          label={t("auth.masterPassword")}
          required
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") (initialized ? handleLogin : handleCreate)();
          }}
          autoFocus={false}
          autoComplete={creatingVault ? "new-password" : "current-password"}
        />

        {legacyVault && (
          <PasswordField
            label={t("auth.migrationToken")}
            required
            value={migrationToken}
            onChange={(e) => setMigrationToken(e.target.value)}
            autoComplete="off"
          />
        )}

        {creatingVault && value && strength && (
          <Box sx={{ mt: 2, textAlign: "left" }}>
            <LinearProgress
              variant="determinate"
              value={strength.value}
              color={strength.color}
              sx={{ borderRadius: 1, height: 6, bgcolor: "action.hover" }}
            />
            <Typography
              variant="caption"
              color={`${strength.color}.main`}
              sx={{ mt: 0.5, display: "block" }}
            >
              {t(strength.labelKey)}
            </Typography>
          </Box>
        )}

        {creatingVault && (
          <Box sx={{ mt: 2 }}>
            <PasswordField
              label={t("auth.confirmMasterPassword")}
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate();
              }}
              autoComplete="new-password"
            />
            <Box
              sx={{
                mt: 2,
                display: "flex",
                gap: 1.25,
                textAlign: "left",
                border: `1px solid ${WARN}`,
                bgcolor: "rgba(224,152,47,0.08)",
                borderRadius: 1.5,
                p: 1.6,
              }}
            >
              <Box component="span" sx={{ color: WARN, lineHeight: 1.4 }}>
                ⚠
              </Box>
              <Typography variant="caption" sx={{ color: WARN, lineHeight: 1.5 }}>
                {t("auth.noRecoveryWarning")}
              </Typography>
            </Box>
            <FormControlLabel
              sx={{ mt: 1, ml: 0, alignItems: "center" }}
              control={
                <Checkbox
                  size="small"
                  checked={acknowledged}
                  onChange={(e) => {
                    setAcknowledged(e.target.checked);
                    setError(null);
                  }}
                  sx={{ color: GLOW, "&.Mui-checked": { color: GLOW }, py: 0.25 }}
                />
              }
              label={
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {t("auth.noRecoveryAcknowledgement")}
                </Typography>
              }
            />
          </Box>
        )}

        <Button
          fullWidth
          size="large"
          variant="contained"
          loading={loading}
          disabled={creatingVault && !acknowledged}
          onClick={initialized ? handleLogin : handleCreate}
          sx={{ mt: 3, ...unlockButtonSx }}
        >
          {t(initialized ? "auth.unlock" : legacyVault ? "auth.migrate" : "auth.create")}
        </Button>

        <Typography sx={{ mt: 2.75, fontSize: 11, color: "text.disabled" }}>
          {t("auth.closeLocks")}
        </Typography>
      </Box>
      <LanguageSwitcher placement="floating" />
      <ThemeToggle zIndex={1301} />
    </Box>
  );
};

export default LoginPage;

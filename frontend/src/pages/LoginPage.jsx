import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Container,
  Flex,
  Progress,
  Text,
  TextInput,
} from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import LanguageSwitcher from "../components/LanguageSwitcher";
import LoadingScreen from "../components/LoadingScreen";
import BrandMark from "../components/BrandMark";
import PasswordField from "../components/PasswordField";
import ThemeToggle from "../components/ThemeToggle";
import { getMasterPasswordStrength } from "../lib/passwordStrength";
import { LOGOUT_NOTICE } from "../utils";

const STRENGTH_THEME = { error: "danger", warning: "warning", success: "success" };

const LoginPage = () => {
  const { t, i18n } = useTranslation();
  const { state } = useLocation();
  const [acknowledged, setAcknowledged] = useState(false);
  const [notice, setNotice] = useState("");

  const { fetchStatus, authenticate, setUsername, setValue, setConfirm, setError } =
    useStoreActions((actions) => actions.ciphermothModels.masterPassword);
  const { initialized, error, username, value, confirm, loading } = useStoreState(
    (storeState) => storeState.ciphermothModels.masterPassword
  );

  useEffect(() => {
    fetchStatus();
    const logoutNotice = sessionStorage.getItem(LOGOUT_NOTICE);
    if (logoutNotice) {
      sessionStorage.removeItem(LOGOUT_NOTICE);
      setNotice(t(logoutNotice));
    }
  }, [fetchStatus, t]);

  const strength = initialized === false ? getMasterPasswordStrength(value) : null;

  const handleLogin = () => {
    if (!username.trim()) {
      setError(t("auth.validation.enterUsername"));
      return;
    }
    if (!value.trim()) {
      setError(t("auth.validation.enterMasterPassword"));
      return;
    }
    authenticate({ endpoint: "/auth/login", username, password: value, returnTo: state?.returnTo });
  };

  const handleCreate = () => {
    if (!username.trim()) {
      setError(t("auth.validation.enterAdministratorUsername"));
      return;
    }
    if (!value) {
      setError(t("auth.validation.enterNewMasterPassword"));
      return;
    }
    if (value !== confirm) {
      setError(t("auth.validation.passwordsDoNotMatch"));
      return;
    }
    if (strength && strength.value < 70) {
      setError(t("auth.validation.weakPassword"));
      return;
    }
    if (!acknowledged) {
      setError(t("auth.validation.confirmNoRecovery"));
      return;
    }
    authenticate({
      endpoint: "/auth/bootstrap",
      username,
      password: value,
      returnTo: state?.returnTo,
    });
  };

  if (initialized === null) return <LoadingScreen />;

  return (
    <Container
      maxWidth="440px"
      gutters="spacing-3"
      paddingBlock={{ xs: "spacing-6", m: "spacing-10" }}
    >
      <Card view="outlined">
        <Flex
          as="form"
          direction="column"
          gap="spacing-5"
          padding="spacing-6"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!loading) (initialized ? handleLogin : handleCreate)();
          }}
        >
          <Flex alignItems="center" justifyContent="space-between" gap="spacing-3">
            <Flex alignItems="center" gap="spacing-2">
              <BrandMark />
              <Text variant="subheader-3">
                {i18n.resolvedLanguage?.startsWith("ru") ? "Недра" : "Nedra"}
              </Text>
            </Flex>
            <Flex gap="spacing-2">
              <ThemeToggle />
              <LanguageSwitcher />
            </Flex>
          </Flex>
          <Text as="h1" variant="header-1">
            {t(initialized ? "auth.unlock" : "auth.setupTitle")}
          </Text>
          <Text color="secondary">{t(initialized ? "auth.tagline" : "auth.setupDescription")}</Text>
          {notice && <Alert theme="info" message={notice} />}
          {error && <Alert theme="danger" message={error} />}
          <TextInput
            id="cm-auth-username"
            label={t(initialized ? "auth.username" : "auth.administratorUsername")}
            required
            size="l"
            value={username}
            disabled={loading}
            autoFocus
            autoComplete="username"
            onUpdate={(next) => {
              setUsername(next);
              setError(null);
            }}
            note={initialized ? undefined : t("auth.usernameRules")}
            controlProps={{ autoCapitalize: "none", spellCheck: false, required: true }}
          />
          <PasswordField
            label={t("auth.masterPassword")}
            required
            value={value}
            onGenerate={initialized ? undefined : setValue}
            disabled={loading}
            onUpdate={(next) => {
              setValue(next);
              setError(null);
            }}
            autoComplete={initialized ? "current-password" : "new-password"}
          />
          {!initialized && value && strength && (
            <Flex direction="column" gap="spacing-2" aria-live="polite">
              <Progress value={strength.value} theme={STRENGTH_THEME[strength.color]} size="s" />
              <Text color="secondary">{t(strength.labelKey)}</Text>
            </Flex>
          )}
          {!initialized && (
            <>
              <PasswordField
                label={t("auth.confirmMasterPassword")}
                required
                value={confirm}
                disabled={loading}
                onUpdate={(next) => {
                  setConfirm(next);
                  setError(null);
                }}
                autoComplete="new-password"
              />
              <Alert theme="warning" message={t("auth.noRecoveryWarning")} />
              <Checkbox
                checked={acknowledged}
                disabled={loading}
                size="l"
                onUpdate={(checked) => {
                  setAcknowledged(checked);
                  setError(null);
                }}
                content={t("auth.noRecoveryAcknowledgement")}
              />
            </>
          )}
          <Button
            type="submit"
            view="action"
            size="l"
            width="max"
            loading={loading}
            disabled={!initialized && !acknowledged}
          >
            {t(initialized ? "auth.unlock" : "auth.create")}
          </Button>
          <Text color="secondary" variant="caption-2">
            {t("auth.closeLocks")}
          </Text>
        </Flex>
      </Card>
    </Container>
  );
};

export default LoginPage;

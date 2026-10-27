import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button, Checkbox, Progress, TextInput } from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import LanguageSwitcher from "../components/LanguageSwitcher";
import LoadingScreen from "../components/LoadingScreen";
import MothIcon from "../components/MothIcon";
import PasswordField from "../components/PasswordField";
import ThemeToggle from "../components/ThemeToggle";
import { getMasterPasswordStrength } from "../lib/passwordStrength";
import { LOGOUT_NOTICE } from "../utils";

const STRENGTH_THEME = { error: "danger", warning: "warning", success: "success" };

const LoginPage = () => {
  const { t } = useTranslation();
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
    <div className="cm-auth-page">
      <section className="cm-auth-workspace">
        <form
          className="cm-auth-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!loading) (initialized ? handleLogin : handleCreate)();
          }}
        >
          <div className="cm-auth-form__brand">
            <div className="cm-auth-form__brand-identity">
              <span className="cm-auth-form__brand-mark" aria-hidden="true">
                <MothIcon />
              </span>
              <span className="cm-auth-form__brand-name">
                Cipher<span className="cm-brand__name-accent">Moth</span>
              </span>
            </div>
            <div className="cm-auth-form__utilities">
              <ThemeToggle />
              <LanguageSwitcher placement="auth" />
            </div>
          </div>
          <h2>{t(initialized ? "auth.unlock" : "auth.setupTitle")}</h2>
          <p className="cm-auth-form__description">
            {t(initialized ? "auth.tagline" : "auth.setupDescription")}
          </p>

          <div className="cm-auth-form__fields">
            {notice && (
              <div className="cm-auth-form__notice" role="status">
                {notice}
              </div>
            )}
            {error && (
              <div className="cm-auth-form__error" role="alert">
                {error}
              </div>
            )}

            <label className="cm-field" htmlFor="cm-auth-username">
              <span className="cm-field__label">
                {t(initialized ? "auth.username" : "auth.administratorUsername")}
                <span className="cm-field__required" aria-hidden="true">
                  *
                </span>
              </span>
              <TextInput
                id="cm-auth-username"
                size="xl"
                value={username}
                onUpdate={(nextUsername) => {
                  setUsername(nextUsername);
                  setError(null);
                }}
                autoComplete="username"
                autoFocus
                note={initialized ? undefined : t("auth.usernameRules")}
                controlProps={{ autoCapitalize: "none", spellCheck: false, required: true }}
              />
            </label>

            <PasswordField
              label={t("auth.masterPassword")}
              required
              size="xl"
              value={value}
              onGenerate={initialized ? undefined : setValue}
              disabled={loading}
              onUpdate={(nextPassword) => {
                setValue(nextPassword);
                setError(null);
              }}
              autoComplete={initialized ? "current-password" : "new-password"}
            />

            {!initialized && value && strength && (
              <div className="cm-auth-form__strength" aria-live="polite">
                <Progress value={strength.value} theme={STRENGTH_THEME[strength.color]} size="s" />
                <span className="cm-auth-form__strength-label">{t(strength.labelKey)}</span>
              </div>
            )}

            {!initialized && (
              <div className="cm-auth-form__bootstrap">
                <PasswordField
                  label={t("auth.confirmMasterPassword")}
                  required
                  size="xl"
                  value={confirm}
                  onUpdate={(nextConfirm) => {
                    setConfirm(nextConfirm);
                    setError(null);
                  }}
                  autoComplete="new-password"
                />
                <div className="cm-auth-form__warning" role="note">
                  {t("auth.noRecoveryWarning")}
                </div>
                <Checkbox
                  size="l"
                  checked={acknowledged}
                  onUpdate={(checked) => {
                    setAcknowledged(checked);
                    setError(null);
                  }}
                  content={
                    <span className="cm-auth-form__acknowledgement">
                      {t("auth.noRecoveryAcknowledgement")}
                    </span>
                  }
                />
              </div>
            )}
          </div>

          <Button
            className="cm-auth-form__submit"
            type="submit"
            view="action"
            size="xl"
            width="max"
            loading={loading}
            disabled={!initialized && !acknowledged}
          >
            {t(initialized ? "auth.unlock" : "auth.create")}
          </Button>

          <p className="cm-auth-form__lock-note">{t("auth.closeLocks")}</p>
        </form>
      </section>
    </div>
  );
};

export default LoginPage;

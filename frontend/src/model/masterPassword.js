import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import {
  enrollLegacyUserAuth,
  generateUserKeyMaterial,
  signAuthChallenge,
  unlockUserKeyMaterial,
} from "../lib/crypto";
import { errorDetail } from "../lib/http";
import i18n from "../i18n";
import { setAuthSession } from "../utils";

const MasterPassword = {
  initialized: null,
  legacyVault: false,
  legacySalt: null,
  error: null,
  loading: false,
  username: "",
  value: "",
  confirm: "",
  migrationToken: "",

  setInitialized: action((state, val) => {
    state.initialized = val;
  }),
  setLegacyVault: action((state, value) => {
    state.legacyVault = value;
  }),
  setLegacySalt: action((state, value) => {
    state.legacySalt = value;
  }),
  setUsername: action((state, value) => {
    state.username = value;
  }),
  setValue: action((state, value) => {
    state.value = value;
  }),
  setConfirm: action((state, value) => {
    state.confirm = value;
  }),
  setMigrationToken: action((state, value) => {
    state.migrationToken = value;
  }),
  setError: action((state, error) => {
    state.error = error;
  }),
  setLoading: action((state, loading) => {
    state.loading = loading;
  }),

  fetchStatus: thunk(async (actions) => {
    try {
      const { data } = await apiClient.get("/auth/status");
      actions.setInitialized(data.initialized);
      actions.setLegacyVault(data.legacy_vault);
      actions.setLegacySalt(data.legacy_salt ?? null);
    } catch {
      actions.setInitialized(true);
    }
  }),

  authenticate: thunk(async (actions, { endpoint, username, master_password }, { getState }) => {
    actions.setError(null);
    actions.setLoading(true);
    try {
      let session;
      let unlocked;
      if (endpoint === "/auth/bootstrap") {
        unlocked = await generateUserKeyMaterial(master_password, getState().legacySalt);
        ({ data: session } = await apiClient.post(endpoint, {
          username,
          salt: unlocked.salt,
          public_key: unlocked.publicKey,
          encrypted_private_key: unlocked.encryptedPrivateKey,
          auth_public_key: unlocked.authPublicKey,
          encrypted_auth_private_key: unlocked.encryptedAuthPrivateKey,
          legacy_migration_token: getState().legacyVault ? getState().migrationToken : undefined,
        }));
      } else {
        const { data: challenge } = await apiClient.post("/auth/challenge", { username });
        unlocked = challenge.legacy_user
          ? await enrollLegacyUserAuth(master_password, challenge)
          : await unlockUserKeyMaterial(master_password, challenge);
        ({ data: session } = await apiClient.post("/auth/login", {
          challenge: challenge.challenge,
          signature: challenge.legacy_user
            ? unlocked.proof
            : await signAuthChallenge(unlocked.authPrivateKey, challenge.nonce),
          auth_public_key: unlocked.authPublicKey,
          encrypted_auth_private_key: unlocked.encryptedAuthPrivateKey,
        }));
      }
      setAuthSession({
        token: session.token,
        user: session.user,
        vaultKey: unlocked.vaultKey,
        vaultSalt: session.salt,
        privateKey: unlocked.privateKey,
        authPrivateKey: unlocked.authPrivateKey,
        publicKey: session.public_key,
      });
      window.location.replace("/passwords");
    } catch (err) {
      const msg =
        err.response?.status === 429
          ? i18n.t("errors.tooManyAttempts")
          : await errorDetail(err, i18n.t("errors.generic"));
      actions.setError(msg);
    } finally {
      actions.setLoading(false);
    }
  }),
};

export default MasterPassword;

import { useEffect, useMemo, useState } from "react";
import { Box, CircularProgress } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useSnackbar } from "notistack";
import { useStoreActions, useStoreState } from "easy-peasy";

import apiClient from "../api/client";
import PasswordFormDialog from "../components/vault/PasswordFormDialog";
import { createEntryDraftStore } from "../lib/entryDraft";
import { getCurrentUser } from "../utils";

const EntryCreatePage = () => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const navigate = useNavigate();
  const location = useLocation();
  const create = useStoreActions((actions) => actions.ciphermothModels.passwords.create);
  const getFolders = useStoreActions((actions) => actions.ciphermothModels.access.getFolders);
  const folders = useStoreState((state) => state.ciphermothModels.access.folders);
  const [initialDraft, setInitialDraft] = useState(undefined);
  const [draftStore, setDraftStore] = useState(null);
  const [draftError, setDraftError] = useState(false);
  const entryType = location.state?.entryType === "note" ? "note" : "password";

  useEffect(() => {
    let active = true;
    const initialize = async () => {
      let availableFolders = [];
      try {
        availableFolders = await getFolders();
      } catch (err) {
        enqueueSnackbar(err.message, { variant: "error" });
      }

      const initialFolder = availableFolders.find(
        (item) =>
          item.id === Number(location.state?.folderId) && ["owner", "write"].includes(item.access)
      );

      try {
        const { data } = await apiClient.get("/auth/entry-draft-key");
        if (!active) return;
        if (data.user_id !== getCurrentUser()?.id) throw new Error("Draft owner changed");
        const store = createEntryDraftStore(data);
        setDraftStore(store);
        setInitialDraft(
          store.read() ??
            (initialFolder ? { folder: initialFolder.name, folder_id: initialFolder.id } : null)
        );
      } catch {
        if (!active) return;
        setDraftError(true);
        setInitialDraft(
          initialFolder ? { folder: initialFolder.name, folder_id: initialFolder.id } : null
        );
      }
    };
    initialize();
    return () => {
      active = false;
    };
  }, [enqueueSnackbar, getFolders, location.state?.folderId]);

  const folderOptions = useMemo(
    () => folders.filter((folder) => ["owner", "write"].includes(folder.access)),
    [folders]
  );

  const saveDraft = (value) => {
    if (!draftStore) {
      setDraftError(true);
      return;
    }
    try {
      if (value) draftStore.write(value);
      else draftStore.clear();
      setDraftError(false);
    } catch {
      setDraftError(true);
    }
  };

  const close = () => navigate("/passwords", { replace: true });
  const cancel = () => {
    draftStore?.clear();
    close();
  };

  const submit = async (payload) => {
    await create(payload);
    draftStore?.clear();
    enqueueSnackbar(
      t(payload.kind === "note" ? "vault.messages.noteCreated" : "vault.messages.passwordCreated"),
      { variant: "success" }
    );
    close();
  };

  if (initialDraft === undefined) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "50vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <PasswordFormDialog
      page
      open
      entryType={entryType}
      initialDraft={initialDraft}
      onDraftChange={saveDraft}
      draftError={draftError}
      folderOptions={folderOptions}
      onClose={cancel}
      onSubmit={submit}
    />
  );
};

export default EntryCreatePage;

import { useEffect, useState } from "react";
import {
  Autocomplete,
  Box,
  Button,
  ButtonBase,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlined";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";
import LockOpenOutlinedIcon from "@mui/icons-material/LockOpenOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import StickyNote2OutlinedIcon from "@mui/icons-material/StickyNote2Outlined";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { useTranslation } from "react-i18next";

import PasswordField from "../PasswordField";
import AttachmentsSection from "./AttachmentsSection";
import PasswordGenerator, { CHAR_KEYS } from "./PasswordGenerator";
import StrengthBar from "./StrengthBar";
import { generatePassword } from "../../lib/passwordGenerator";
import { GLOW } from "../../lib/brand";

const EMPTY_FORM = {
  password_name: "",
  kind: "login",
  username: "",
  password_value: "",
  url: "",
  totp_secret: "",
  description: "",
  tags: [],
  custom_fields: [],
  folder: "",
  favorite: false,
};
const GEN_DEFAULTS = { length: 16, uppercase: true, lowercase: true, numbers: true, symbols: true };

const normalizeCustomFields = (fields) =>
  (fields ?? [])
    .map((f) => ({ label: f.label.trim(), value: f.value, hidden: !!f.hidden }))
    .filter((f) => f.label);

const toForm = (target) =>
  target
    ? {
        password_name: target.password_name,
        kind: target.kind ?? "login",
        username: target.username ?? "",
        password_value: target.password_value,
        url: target.url ?? "",
        totp_secret: target.totp_secret ?? "",
        description: target.description ?? "",
        tags: target.tags ?? [],
        custom_fields: (target.custom_fields ?? []).map((f) => ({
          label: f.label ?? "",
          value: f.value ?? "",
          hidden: !!f.hidden,
        })),
        folder: target.folder ?? "",
        favorite: target.favorite ?? false,
      }
    : EMPTY_FORM;

const sectionsForTarget = (target) => ({
  totp: !!target?.totp_secret,
  tags: (target?.tags?.length ?? 0) > 0,
  custom: (target?.custom_fields?.length ?? 0) > 0,
  notes: !!target?.description,
  attachments: (target?.attachment_count ?? 0) > 0,
  history: false,
});

const FormSection = ({ label, count, preview, open, onToggle, children }) => (
  <Box sx={{ borderTop: "1px solid", borderColor: "divider" }}>
    <ButtonBase
      onClick={onToggle}
      sx={{
        width: "100%",
        justifyContent: "space-between",
        px: 0.5,
        py: 1,
        borderRadius: 1,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", minWidth: 0 }}>
        <ExpandMoreIcon
          fontSize="small"
          sx={{
            color: "text.secondary",
            transition: "transform 150ms ease",
            transform: open ? "none" : "rotate(-90deg)",
          }}
        />
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        {count > 0 && (
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            ({count})
          </Typography>
        )}
      </Stack>
      {!open && preview && (
        <Typography
          variant="caption"
          sx={{
            color: "text.disabled",
            ml: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: 190,
          }}
        >
          {preview}
        </Typography>
      )}
    </ButtonBase>
    <Collapse in={open}>
      <Box sx={{ px: 0.5, pt: 0.5, pb: 1.5 }}>{children}</Box>
    </Collapse>
  </Box>
);

const CustomFieldRow = ({ field, onChange, onToggleHidden, onRemove }) => {
  const { t } = useTranslation();

  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
      <TextField
        label={t("entry.labels.label")}
        size="small"
        value={field.label}
        onChange={(e) => onChange({ ...field, label: e.target.value })}
        sx={{ flex: "0 0 34%" }}
        placeholder={t("entry.placeholders.customLabel")}
      />
      <TextField
        label={t("entry.labels.value")}
        size="small"
        type={field.hidden ? "password" : "text"}
        value={field.value}
        onChange={(e) => onChange({ ...field, value: e.target.value })}
        sx={{ flex: 1 }}
        autoComplete="off"
        slotProps={{ htmlInput: { spellCheck: false, autoCorrect: "off", autoCapitalize: "none" } }}
      />
      <Tooltip title={t(field.hidden ? "entry.actions.valueHidden" : "entry.actions.hideValue")}>
        <IconButton size="small" onClick={onToggleHidden}>
          {field.hidden ? (
            <LockOutlinedIcon fontSize="small" />
          ) : (
            <LockOpenOutlinedIcon fontSize="small" />
          )}
        </IconButton>
      </Tooltip>
      <Tooltip title={t("entry.actions.removeField")}>
        <IconButton size="small" color="error" onClick={onRemove}>
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
};

const HistoryRow = ({ entry, onCopy }) => {
  const { t, i18n } = useTranslation();
  const [show, setShow] = useState(false);
  const when = new Date(entry.changed_at).toLocaleDateString(i18n.resolvedLanguage);
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
      <Typography
        variant="body2"
        sx={{ fontFamily: "'Space Mono', monospace", flex: 1, color: "text.secondary" }}
      >
        {show ? entry.value : "••••••••••••"}
      </Typography>
      <Typography variant="caption" sx={{ color: "text.disabled" }}>
        {when}
      </Typography>
      <Tooltip title={t(show ? "passwordField.hide" : "passwordField.show")}>
        <IconButton size="small" onClick={() => setShow((v) => !v)}>
          {show ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
      <Tooltip title={t("vault.columns.copyPassword")}>
        <IconButton size="small" onClick={() => onCopy?.(entry.value)}>
          <ContentCopyIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
};

const PasswordFormDialog = ({
  open,
  editTarget,
  onClose,
  onSubmit,
  onCopy,
  folderOptions = [],
  canWrite = true,
}) => {
  const { t } = useTranslation();
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [showValue, setShowValue] = useState(false);
  const [showTotp, setShowTotp] = useState(false);
  const [showGenerator, setShowGenerator] = useState(false);
  const [sections, setSections] = useState(() => sectionsForTarget(null));
  const [genOpts, setGenOpts] = useState(GEN_DEFAULTS);
  const [submitting, setSubmitting] = useState(false);
  const [attachmentsDirty, setAttachmentsDirty] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(toForm(editTarget));
    setSections(sectionsForTarget(editTarget));
    setFormError("");
    setShowValue(false);
    setShowTotp(false);
    setShowGenerator(false);
    setAttachmentsDirty(false);
  }, [open, editTarget]);

  const isNote = form.kind === "note";

  const toggleSection = (key) => () => setSections((prev) => ({ ...prev, [key]: !prev[key] }));

  const setField = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }));
    setFormError("");
  };

  const addCustomField = () => {
    setSections((prev) => ({ ...prev, custom: true }));
    setForm((prev) => ({
      ...prev,
      custom_fields: [...prev.custom_fields, { label: "", value: "", hidden: false }],
    }));
  };

  const updateCustomField = (index, next) => {
    setForm((prev) => ({
      ...prev,
      custom_fields: prev.custom_fields.map((f, i) => (i === index ? next : f)),
    }));
  };

  const removeCustomField = (index) => {
    setForm((prev) => ({
      ...prev,
      custom_fields: prev.custom_fields.filter((_, i) => i !== index),
    }));
  };

  const applyGenerated = (opts) => {
    setForm((prev) => ({ ...prev, password_value: generatePassword(opts) }));
    setShowValue(true);
  };

  const toggleGenerator = () => {
    if (!showGenerator) applyGenerated(genOpts);
    setShowGenerator((v) => !v);
  };

  const changeGenLength = (length) => {
    const next = { ...genOpts, length };
    setGenOpts(next);
    applyGenerated(next);
  };

  const toggleGenClass = (key) => {
    setGenOpts((prev) => {
      const wouldHaveNone = CHAR_KEYS.every((k) => (k === key ? prev[k] : !prev[k]));
      if (wouldHaveNone) return prev;
      const next = { ...prev, [key]: !prev[key] };
      applyGenerated(next);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!form.password_name.trim()) {
      setFormError(t("entry.validation.nameRequired"));
      return;
    }

    if (!form.password_value.trim()) {
      setFormError(
        t(isNote ? "entry.validation.noteRequired" : "entry.validation.passwordRequired")
      );
      return;
    }

    if (editTarget && unchanged) {
      onClose();
      return;
    }

    setSubmitting(true);

    try {
      await onSubmit({
        password_name: form.password_name.trim(),
        kind: form.kind,
        username: isNote ? null : form.username.trim() || null,
        password_value: form.password_value,
        url: isNote ? null : form.url.trim() || null,
        totp_secret: isNote ? null : form.totp_secret.trim() || null,
        description: isNote ? null : form.description.trim() || null,
        tags: form.tags,
        custom_fields: normalizeCustomFields(form.custom_fields),
        folder: form.folder.trim() || null,
        favorite: form.favorite,
      });
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const history = editTarget?.password_history ?? [];
  const customCount = normalizeCustomFields(form.custom_fields).length;

  const unchanged =
    !!editTarget &&
    form.username === (editTarget.username ?? "") &&
    form.password_value === editTarget.password_value &&
    form.url === (editTarget.url ?? "") &&
    form.totp_secret === (editTarget.totp_secret ?? "") &&
    form.description === (editTarget.description ?? "") &&
    form.favorite === (editTarget.favorite ?? false) &&
    (form.folder.trim() || "") === (editTarget.folder ?? "") &&
    form.tags.join(" ") === (editTarget.tags ?? []).join(" ") &&
    JSON.stringify(normalizeCustomFields(form.custom_fields)) ===
      JSON.stringify(normalizeCustomFields(editTarget.custom_fields));

  const titleKey = editTarget
    ? isNote
      ? "entry.title.editNote"
      : "entry.title.editPassword"
    : isNote
      ? "entry.title.addNote"
      : "entry.title.addPassword";

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        {t(titleKey)}
        <Tooltip
          title={t(form.favorite ? "vault.columns.removeFavorite" : "vault.columns.markFavorite")}
        >
          <IconButton onClick={() => setForm((p) => ({ ...p, favorite: !p.favorite }))}>
            {form.favorite ? <StarIcon sx={{ color: GLOW }} /> : <StarBorderIcon />}
          </IconButton>
        </Tooltip>
      </DialogTitle>
      <DialogContent dividers>
        {!editTarget && (
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            value={form.kind}
            onChange={(_, value) => value && setForm((prev) => ({ ...prev, kind: value }))}
            sx={{ mb: 2 }}
          >
            <ToggleButton value="login">
              <KeyOutlinedIcon fontSize="small" sx={{ mr: 0.75 }} />
              {t("entry.kind.login")}
            </ToggleButton>
            <ToggleButton value="note">
              <StickyNote2OutlinedIcon fontSize="small" sx={{ mr: 0.75 }} />
              {t("entry.kind.note")}
            </ToggleButton>
          </ToggleButtonGroup>
        )}

        <Stack spacing={1.5}>
          <TextField
            label={t("common.fields.name")}
            size="small"
            value={form.password_name}
            onChange={setField("password_name")}
            disabled={!!editTarget}
            required
            fullWidth
            autoFocus
            slotProps={{ htmlInput: { maxLength: 255 } }}
            helperText={
              editTarget
                ? t("entry.help.nameCannotChange")
                : isNote
                  ? t("entry.placeholders.noteName")
                  : t("entry.placeholders.passwordName")
            }
          />

          {isNote ? (
            <TextField
              label={t("entry.labels.note")}
              size="small"
              value={form.password_value}
              onChange={setField("password_value")}
              required
              fullWidth
              multiline
              minRows={6}
              maxRows={6}
              autoComplete="off"
              placeholder={t("entry.placeholders.note")}
              slotProps={{ htmlInput: { spellCheck: false, style: { overflow: "auto" } } }}
            />
          ) : (
            <>
              <TextField
                label={t("entry.labels.usernameOptional")}
                size="small"
                value={form.username}
                onChange={setField("username")}
                fullWidth
                placeholder={t("entry.placeholders.username")}
                slotProps={{
                  htmlInput: { spellCheck: false, autoCorrect: "off", autoCapitalize: "none" },
                }}
              />
              <TextField
                label={t("entry.labels.websiteOptional")}
                size="small"
                value={form.url}
                onChange={setField("url")}
                fullWidth
                placeholder={t("entry.placeholders.website")}
                slotProps={{
                  htmlInput: { spellCheck: false, autoCorrect: "off", autoCapitalize: "none" },
                }}
              />
              <PasswordField
                label={t("common.fields.password")}
                size="small"
                value={form.password_value}
                onChange={(e) => {
                  setField("password_value")(e);
                  if (showGenerator) setShowGenerator(false);
                }}
                required
                autoComplete="new-password"
                show={showValue}
                onToggleShow={() => setShowValue((v) => !v)}
                adornment={
                  <Tooltip
                    title={t(
                      showGenerator
                        ? "entry.actions.closeGenerator"
                        : "entry.actions.generatePassword"
                    )}
                  >
                    <IconButton
                      onClick={toggleGenerator}
                      size="small"
                      color={showGenerator ? "primary" : "default"}
                    >
                      <AutoFixHighIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                }
              />
              {showGenerator && (
                <PasswordGenerator
                  options={genOpts}
                  onChangeLength={changeGenLength}
                  onToggleClass={toggleGenClass}
                  onRegenerate={() => applyGenerated(genOpts)}
                />
              )}
              <StrengthBar password={form.password_value} />
            </>
          )}
        </Stack>

        <Autocomplete
          freeSolo
          size="small"
          options={folderOptions}
          inputValue={form.folder}
          onInputChange={(_, value) => {
            setForm((prev) => ({ ...prev, folder: value }));
            setFormError("");
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t("entry.labels.folderOptional")}
              placeholder={t("entry.placeholders.folder")}
            />
          )}
          sx={{ mt: 1.5 }}
        />

        <Box sx={{ mt: 1.5 }}>
          {!isNote && (
            <FormSection
              label={t("entry.labels.twoFactor")}
              preview={form.totp_secret ? t("common.labels.configured") : ""}
              open={sections.totp}
              onToggle={toggleSection("totp")}
            >
              <PasswordField
                label={t("entry.labels.twoFactorSecret")}
                size="small"
                value={form.totp_secret}
                onChange={setField("totp_secret")}
                autoComplete="off"
                show={showTotp}
                onToggleShow={() => setShowTotp((v) => !v)}
                helperText={t("entry.help.twoFactor")}
                adornment={
                  <Tooltip arrow placement="top" title={t("entry.help.twoFactorTooltip")}>
                    <HelpOutlineIcon
                      fontSize="small"
                      sx={{ color: "text.disabled", cursor: "help", mr: 0.5 }}
                    />
                  </Tooltip>
                }
              />
            </FormSection>
          )}

          <FormSection
            label={t("common.fields.tags")}
            count={form.tags.length}
            preview={form.tags.slice(0, 3).join(", ")}
            open={sections.tags}
            onToggle={toggleSection("tags")}
          >
            <Autocomplete
              multiple
              freeSolo
              size="small"
              options={[]}
              value={form.tags}
              onChange={(_, newValue) =>
                setForm((prev) => ({
                  ...prev,
                  tags: [...new Set(newValue.map((t) => t.trim()).filter(Boolean))],
                }))
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t("common.fields.tags")}
                  placeholder={t("entry.placeholders.tags")}
                />
              )}
            />
          </FormSection>

          <FormSection
            label={t("entry.labels.customFields")}
            count={customCount}
            preview={normalizeCustomFields(form.custom_fields)
              .map((f) => f.label)
              .join(", ")}
            open={sections.custom}
            onToggle={toggleSection("custom")}
          >
            <Stack spacing={1}>
              {form.custom_fields.map((field, index) => (
                <CustomFieldRow
                  key={index}
                  field={field}
                  onChange={(next) => updateCustomField(index, next)}
                  onToggleHidden={() =>
                    updateCustomField(index, { ...field, hidden: !field.hidden })
                  }
                  onRemove={() => removeCustomField(index)}
                />
              ))}
              <Box>
                <Button size="small" startIcon={<AddIcon />} onClick={addCustomField}>
                  {t("entry.actions.addField")}
                </Button>
              </Box>
            </Stack>
          </FormSection>

          {!isNote && (
            <FormSection
              label={t("entry.labels.notes")}
              preview={form.description}
              open={sections.notes}
              onToggle={toggleSection("notes")}
            >
              <TextField
                label={t("common.fields.description")}
                size="small"
                value={form.description}
                onChange={setField("description")}
                fullWidth
                multiline
                rows={2}
                placeholder={t("entry.placeholders.description")}
              />
            </FormSection>
          )}

          {editTarget && (
            <FormSection
              label={t("entry.labels.attachments")}
              count={editTarget.attachment_count ?? 0}
              open={sections.attachments}
              onToggle={toggleSection("attachments")}
            >
              <AttachmentsSection
                passwordId={editTarget.id}
                canWrite={canWrite}
                onChanged={() => setAttachmentsDirty(true)}
              />
            </FormSection>
          )}

          {!isNote && editTarget && history.length > 0 && (
            <FormSection
              label={t("entry.labels.passwordHistory")}
              count={history.length}
              open={sections.history}
              onToggle={toggleSection("history")}
            >
              <Stack spacing={1}>
                {history.map((entry, index) => (
                  <HistoryRow key={index} entry={entry} onCopy={onCopy} />
                ))}
              </Stack>
            </FormSection>
          )}
        </Box>

        {formError && (
          <Typography variant="body2" color="error" sx={{ mt: 1.5 }}>
            {formError}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          {t("common.actions.cancel")}
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          loading={submitting}
          disabled={unchanged && !attachmentsDirty}
        >
          {t(
            editTarget
              ? unchanged && attachmentsDirty
                ? "common.actions.done"
                : "common.actions.update"
              : "common.actions.create"
          )}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PasswordFormDialog;

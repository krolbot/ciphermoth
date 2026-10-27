import { useEffect, useId, useState } from "react";
import { CircleQuestion } from "@gravity-ui/icons";
import { Alert, Button, Dialog, Icon, Switch, TextInput, Tooltip } from "@gravity-ui/uikit";
import { toaster } from "@gravity-ui/uikit/toaster-singleton";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

const FIELDS = [
  {
    key: "inactivity_ms",
    labelKey: "settings.fields.inactivity",
    tooltipKey: "settings.fields.inactivityHelp",
    min: 30,
    max: 3600,
  },
  {
    key: "warn_before_ms",
    labelKey: "settings.fields.warning",
    tooltipKey: "settings.fields.warningHelp",
    min: 5,
    max: 600,
  },
  {
    key: "hidden_ms",
    labelKey: "settings.fields.hidden",
    tooltipKey: "settings.fields.hiddenHelp",
    min: 10,
    max: 3600,
  },
  {
    key: "debounce_ms",
    labelKey: "settings.fields.debounce",
    tooltipKey: "settings.fields.debounceHelp",
    min: 1,
    max: 10,
  },
  {
    key: "clipboard_clear_ms",
    labelKey: "settings.fields.clipboard",
    tooltipKey: "settings.fields.clipboardHelp",
    min: 5,
    max: 600,
  },
];

const toSec = (ms) => Math.round(ms / 1000);
const toMs = (sec) => Math.round(Number(sec)) * 1000;

const toForm = (settings) => ({
  ...Object.fromEntries(FIELDS.map(({ key }) => [key, toSec(settings[key])])),
  update_check_enabled: settings.update_check_enabled ?? true,
});

const isDirty = (form, settings) =>
  FIELDS.some(({ key }) => Number(form[key]) !== toSec(settings[key])) ||
  form.update_check_enabled !== (settings.update_check_enabled ?? true);

const SettingsModal = ({ open, onClose }) => {
  const { t } = useTranslation();
  const titleId = useId();
  const updatesLabelId = `${titleId}-updates`;

  const { update } = useStoreActions((a) => a.ciphermothModels.settings);
  const settings = useStoreState((s) => s.ciphermothModels.settings.settings);

  const [form, setForm] = useState(() => toForm(settings));
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(toForm(settings));
      setFormError("");
    }
  }, [open, settings]);

  const handleChange = (key) => (e) => {
    setForm((prev) => ({ ...prev, [key]: e.target.value }));
    setFormError("");
  };

  const handleSave = async () => {
    const invalidField = FIELDS.find(({ key, min, max }) => {
      const value = Number(form[key]);
      return !Number.isInteger(value) || value < min || value > max;
    });
    if (invalidField) {
      setFormError(
        t("settings.rangeValidation", {
          label: t(invalidField.labelKey),
          min: invalidField.min,
          max: invalidField.max,
        })
      );
      return;
    }
    if (Number(form.warn_before_ms) >= Number(form.inactivity_ms)) {
      setFormError(t("settings.warningValidation"));
      return;
    }
    setSaving(true);
    try {
      await update({
        ...Object.fromEntries(FIELDS.map(({ key }) => [key, toMs(form[key])])),
        update_check_enabled: form.update_check_enabled,
      });
      toaster.add({ name: "settings-saved", theme: "success", title: t("settings.saved") });
      onClose();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const dirty = isDirty(form, settings);

  return (
    <Dialog
      aria-labelledby={titleId}
      className="cm-secondary-dialog cm-secondary-dialog--settings"
      contentOverflow="auto"
      disableEscapeKeyDown={saving}
      disableOutsideClick={saving}
      fullWidth
      hasCloseButton={false}
      maxWidth="s"
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !saving) onClose();
      }}
      open={open}
    >
      <Dialog.Header caption={t("settings.title")} id={titleId} />
      <Dialog.Body>
        <div className="cm-secondary-form cm-settings-form">
          {FIELDS.map(({ key, labelKey, tooltipKey, min, max }) => {
            const inputId = `${titleId}-${key}`;
            return (
              <div className="cm-field cm-settings-form__field" key={key}>
                <label className="cm-field__label" htmlFor={inputId}>
                  {t(labelKey)}
                </label>
                <TextInput
                  controlProps={{ min, max, step: 1 }}
                  endContent={
                    <span className="cm-settings-form__input-actions">
                      <span className="cm-settings-form__unit">
                        {t("common.labels.secondsShort")}
                      </span>
                      <Tooltip content={t(tooltipKey)} placement="top" role="label">
                        <Button
                          aria-label={t(tooltipKey)}
                          className="cm-settings-form__help"
                          size="s"
                          type="button"
                          view="flat-secondary"
                        >
                          <Icon data={CircleQuestion} />
                        </Button>
                      </Tooltip>
                    </span>
                  }
                  id={inputId}
                  onChange={handleChange(key)}
                  size="m"
                  type="number"
                  value={form[key]}
                />
              </div>
            );
          })}
          <hr className="cm-settings-form__separator" />
          <div className="cm-settings-form__updates">
            <div className="cm-settings-form__updates-copy">
              <span className="cm-field__label" id={updatesLabelId}>
                {t("settings.fields.updates")}
              </span>
              <Tooltip content={t("settings.fields.updatesHelp")} placement="top" role="label">
                <Button
                  aria-label={t("settings.fields.updatesHelp")}
                  className="cm-settings-form__help"
                  size="s"
                  type="button"
                  view="flat-secondary"
                >
                  <Icon data={CircleQuestion} />
                </Button>
              </Tooltip>
            </div>
            <Switch
              checked={form.update_check_enabled}
              controlProps={{ "aria-labelledby": updatesLabelId }}
              onUpdate={(checked) =>
                setForm((prev) => ({ ...prev, update_check_enabled: checked }))
              }
              size="l"
            />
          </div>
          {formError && (
            <div role="alert">
              <Alert message={formError} size="s" theme="danger" />
            </div>
          )}
        </div>
      </Dialog.Body>
      <Dialog.Footer
        loading={saving}
        onClickButtonApply={handleSave}
        onClickButtonCancel={onClose}
        propsButtonApply={{ disabled: !dirty }}
        textButtonApply={t("common.actions.save")}
        textButtonCancel={t("common.actions.cancel")}
      />
    </Dialog>
  );
};

export default SettingsModal;

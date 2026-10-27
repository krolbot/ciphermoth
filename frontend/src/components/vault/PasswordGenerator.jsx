import { ArrowRotateRight } from "@gravity-ui/icons";
import { Button, Icon, Slider, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

const CHAR_OPTS = [
  { key: "uppercase", label: "A–Z" },
  { key: "lowercase", label: "a–z" },
  { key: "numbers", label: "0–9" },
  { key: "symbols", label: "!@#" },
];

const CHAR_KEYS = CHAR_OPTS.map((option) => option.key);

const PasswordGenerator = ({
  options,
  onChangeLength,
  onToggleClass,
  onRegenerate,
  canUndo = false,
  onUndo,
}) => {
  const { t } = useTranslation();

  return (
    <section className="cm-password-generator">
      <div className="cm-password-generator__length">
        <span>{t("generator.length")}</span>
        <output>{options.length}</output>
      </div>
      <Slider
        value={options.length}
        min={8}
        max={64}
        step={1}
        onUpdate={onChangeLength}
        aria-label={t("generator.length")}
      />
      <div className="cm-password-generator__classes">
        {CHAR_OPTS.map(({ key, label }) => (
          <Button
            key={key}
            type="button"
            size="s"
            selected={options[key]}
            view={options[key] ? "action" : "outlined"}
            onClick={() => onToggleClass(key)}
            aria-pressed={options[key]}
          >
            <span className="cm-password-generator__class-label">{label}</span>
          </Button>
        ))}
        {canUndo && (
          <Button type="button" size="s" view="flat-secondary" onClick={onUndo}>
            {t("generator.undoReplacement")}
          </Button>
        )}
        <Tooltip content={t("generator.regenerate")}>
          <Button
            type="button"
            size="s"
            view="flat-secondary"
            onClick={onRegenerate}
            aria-label={t("generator.regenerate")}
          >
            <Icon data={ArrowRotateRight} />
          </Button>
        </Tooltip>
      </div>
    </section>
  );
};

export { CHAR_KEYS };
export default PasswordGenerator;

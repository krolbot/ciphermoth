import { ArrowRotateRight } from "@gravity-ui/icons";
import { Flex, Text, Button, Icon, Slider, Tooltip } from "@gravity-ui/uikit";
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
    <Flex direction="column" gap="spacing-3" minWidth="0" as="section">
      <Flex
        direction={{ xs: "column", m: "row" }}
        gap="spacing-3"
        minWidth="0"
        wrap="wrap"
        alignItems={{ m: "center" }}
      >
        <span>{t("generator.length")}</span>
        <output>{options.length}</output>
      </Flex>
      <Slider
        value={options.length}
        min={8}
        max={64}
        step={1}
        onUpdate={onChangeLength}
        aria-label={t("generator.length")}
      />
      <Flex
        direction={{ xs: "column", m: "row" }}
        gap="spacing-3"
        minWidth="0"
        wrap="wrap"
        alignItems={{ m: "center" }}
      >
        {CHAR_OPTS.map(({ key, label }) => (
          <Button
            key={key}
            type="button"
            size="xl"
            selected={options[key]}
            view={options[key] ? "action" : "outlined"}
            onClick={() => onToggleClass(key)}
            aria-pressed={options[key]}
          >
            <Text wordBreak="break-word" variant="code-1">
              {label}
            </Text>
          </Button>
        ))}
        {canUndo && (
          <Button type="button" size="xl" view="flat-secondary" onClick={onUndo}>
            {t("generator.undoReplacement")}
          </Button>
        )}
        <Tooltip content={t("generator.regenerate")}>
          <Button
            type="button"
            size="xl"
            view="flat-secondary"
            onClick={onRegenerate}
            aria-label={t("generator.regenerate")}
          >
            <Icon data={ArrowRotateRight} />
          </Button>
        </Tooltip>
      </Flex>
    </Flex>
  );
};

export { CHAR_KEYS };
export default PasswordGenerator;

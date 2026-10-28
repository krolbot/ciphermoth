import { useId, useMemo } from "react";
import { Check, ChevronRight, Clock, Copy, ShieldExclamation } from "@gravity-ui/icons";
import { Flex, Text, Button, Dialog, Icon, Progress } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { analyzeVault } from "../../lib/vaultHealth";

const SCORE_THEME = { error: "danger", success: "success", warning: "warning" };

const scoreColor = (score) => {
  if (score >= 80) return "success";
  if (score >= 50) return "warning";
  return "error";
};

const scoreLabelKey = (score) => {
  if (score >= 80) return "health.healthy";
  if (score >= 50) return "health.needsAttention";
  return "health.atRisk";
};

const ScoreGauge = ({ score }) => {
  const { t } = useTranslation();
  const color = scoreColor(score);

  return (
    <Flex direction="column" gap="spacing-3" minWidth="0" as="section">
      <Flex direction="column" gap="spacing-3" minWidth="0">
        <output>{score}</output>
        <span>/ 100</span>
      </Flex>
      <Progress size="s" theme={SCORE_THEME[color]} value={score} />
      <Text as="strong">{t(scoreLabelKey(score))}</Text>
    </Flex>
  );
};

const StatTile = ({ icon, label, count, color }) => (
  <Flex direction="column" gap="spacing-3" minWidth="0">
    <Icon data={icon} />
    <Text as="strong" color={color === "error" ? "danger" : color}>
      {count}
    </Text>
    <span>{label}</span>
  </Flex>
);

const IssueGroup = ({ icon, title, hint, color, entries, onSelect }) => {
  if (entries.length === 0) return null;

  return (
    <Flex direction="column" gap="spacing-3" minWidth="0" as="section">
      <Flex direction="column" gap="spacing-3" minWidth="0">
        <Icon data={icon} />
        <Text as="strong" color={color === "error" ? "danger" : color}>
          {title}
        </Text>
        <span>({entries.length})</span>
      </Flex>
      <Text as="p" color="secondary" wordBreak="break-word">
        {hint}
      </Text>
      <Flex direction="column" gap="spacing-3" minWidth="0">
        {entries.map((entry) => (
          <Button
            key={entry.password_name}
            onClick={() => onSelect(entry)}
            type="button"
            view="flat-secondary"
            width="max"
          >
            <Text wordBreak="break-word">
              <span>
                <Text as="strong">{entry.password_name}</Text>
                {entry.username && (
                  <Text as="small" variant="caption-2" color="secondary">
                    {entry.username}
                  </Text>
                )}
              </span>
              <Icon data={ChevronRight} />
            </Text>
          </Button>
        ))}
      </Flex>
    </Flex>
  );
};

const HealthDialog = ({ open, onClose, passwords, onSelect }) => {
  const { t } = useTranslation();
  const titleId = useId();
  const report = useMemo(() => analyzeVault(passwords), [passwords]);
  const allClear =
    report.weak.length === 0 && report.reused.length === 0 && report.stale.length === 0;

  return (
    <Dialog
      aria-labelledby={titleId}

      contentOverflow="auto"
      fullWidth
      hasCloseButton={false}
      maxWidth="m"
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
      open={open}
    >
      <Dialog.Header caption={t("health.title")} id={titleId} />
      <Dialog.Body hasBorders>
        <Flex direction="column" gap="spacing-3" minWidth="0">
          <ScoreGauge score={report.score} />
          <Flex
            direction={{ xs: "column", m: "row" }}
            gap="spacing-3"
            minWidth="0"
            wrap="wrap"
            alignItems={{ m: "center" }}
          >
            <StatTile
              color="error"
              count={report.weak.length}
              icon={ShieldExclamation}
              label={t("health.weak")}
            />
            <StatTile
              color="warning"
              count={report.reused.length}
              icon={Copy}
              label={t("health.reused")}
            />
            <StatTile
              color="info"
              count={report.stale.length}
              icon={Clock}
              label={t("health.old")}
            />
          </Flex>
          <Text as="p" color="secondary" wordBreak="break-word">
            {t("health.localOnly")}
          </Text>
          {allClear ? (
            <Flex direction="column" gap="spacing-3" minWidth="0">
              <Icon data={Check} />
              <span>{t("health.allClear")}</span>
            </Flex>
          ) : (
            <Flex direction="column" gap="spacing-3" minWidth="0">
              <IssueGroup
                color="error"
                entries={report.weak}
                hint={t("health.weakHint")}
                icon={ShieldExclamation}
                onSelect={onSelect}
                title={t("health.weak")}
              />
              <IssueGroup
                color="warning"
                entries={report.reused}
                hint={t("health.reusedHint")}
                icon={Copy}
                onSelect={onSelect}
                title={t("health.reused")}
              />
              <IssueGroup
                color="info"
                entries={report.stale}
                hint={t("health.oldHint")}
                icon={Clock}
                onSelect={onSelect}
                title={t("health.old")}
              />
            </Flex>
          )}
        </Flex>
      </Dialog.Body>
      <Dialog.Footer onClickButtonApply={onClose} textButtonApply={t("common.actions.done")} />
    </Dialog>
  );
};

export default HealthDialog;

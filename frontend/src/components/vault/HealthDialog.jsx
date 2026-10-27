import { useId, useMemo } from "react";
import { Check, ChevronRight, Clock, Copy, ShieldExclamation } from "@gravity-ui/icons";
import { Button, Dialog, Icon, Progress } from "@gravity-ui/uikit";
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
    <section className={`cm-health__score cm-health__score--${color}`}>
      <div className="cm-health__score-value">
        <output>{score}</output>
        <span>/ 100</span>
      </div>
      <Progress size="s" theme={SCORE_THEME[color]} value={score} />
      <strong className="cm-health__score-label">{t(scoreLabelKey(score))}</strong>
    </section>
  );
};

const StatTile = ({ icon, label, count, color }) => (
  <div
    className={`cm-health__stat cm-health__stat--${color}${count ? "" : " cm-health__stat--empty"}`}
  >
    <Icon data={icon} />
    <strong>{count}</strong>
    <span>{label}</span>
  </div>
);

const IssueGroup = ({ icon, title, hint, color, entries, onSelect }) => {
  if (entries.length === 0) return null;

  return (
    <section className={`cm-health__issue cm-health__issue--${color}`}>
      <div className="cm-health__issue-heading">
        <Icon data={icon} />
        <strong>{title}</strong>
        <span>({entries.length})</span>
      </div>
      <p className="cm-health__issue-hint">{hint}</p>
      <div className="cm-health__issue-list">
        {entries.map((entry) => (
          <Button
            className="cm-health__issue-row"
            key={entry.password_name}
            onClick={() => onSelect(entry)}
            type="button"
            view="flat-secondary"
            width="max"
          >
            <span className="cm-health__issue-row-content">
              <span>
                <strong>{entry.password_name}</strong>
                {entry.username && <small>{entry.username}</small>}
              </span>
              <Icon data={ChevronRight} />
            </span>
          </Button>
        ))}
      </div>
    </section>
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
      className="cm-secondary-dialog cm-secondary-dialog--health"
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
        <div className="cm-health">
          <ScoreGauge score={report.score} />
          <div className="cm-health__stats">
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
          </div>
          <p className="cm-health__local-only">{t("health.localOnly")}</p>
          {allClear ? (
            <div className="cm-health__all-clear">
              <Icon data={Check} />
              <span>{t("health.allClear")}</span>
            </div>
          ) : (
            <div className="cm-health__issues">
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
            </div>
          )}
        </div>
      </Dialog.Body>
      <Dialog.Footer onClickButtonApply={onClose} textButtonApply={t("common.actions.done")} />
    </Dialog>
  );
};

export default HealthDialog;

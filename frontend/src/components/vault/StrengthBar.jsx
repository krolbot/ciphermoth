import { useTranslation } from "react-i18next";

import { getPasswordStrength } from "../../lib/passwordStrength";

const SEGMENTS = [0, 1, 2, 3, 4];

const StrengthBar = ({ password }) => {
  const { t } = useTranslation();
  const strength = getPasswordStrength(password);
  if (!strength) return null;

  const theme = strength.level < 2 ? "danger" : strength.level === 2 ? "warning" : "positive";

  return (
    <div className={`cm-strength cm-strength--${theme}`}>
      <div className="cm-strength__segments" aria-hidden="true">
        {SEGMENTS.map((index) => (
          <span
            key={index}
            className={`cm-strength__segment${index <= strength.level ? " cm-strength__segment--active" : ""}`}
          />
        ))}
      </div>
      <span className="cm-strength__label">
        {t(strength.labelKey)}
        {strength.recommend && ` — ${t("strength.recommendation")}`}
      </span>
    </div>
  );
};

export default StrengthBar;

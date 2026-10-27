import { Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { IS_DEV } from "../lib/appEnv";

const EnvBadge = () => {
  const { t } = useTranslation();
  const tooltip = t(IS_DEV ? "environment.developmentTooltip" : "environment.liveTooltip");
  const label = t(IS_DEV ? "environment.development" : "environment.live");

  return (
    <Tooltip content={tooltip}>
      <span
        className={`cm-env-badge${IS_DEV ? " cm-env-badge--development" : ""}`}
        aria-label={t(IS_DEV ? "environment.developmentAria" : "environment.liveAria")}
        tabIndex={0}
      >
        {!IS_DEV && <span className="cm-env-badge__dot" aria-hidden="true" />}
        {label}
      </span>
    </Tooltip>
  );
};

export default EnvBadge;

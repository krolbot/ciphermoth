import { Label, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { IS_DEV } from "../lib/appEnv";

const EnvBadge = () => {
  const { t } = useTranslation();
  const tooltip = t(IS_DEV ? "environment.developmentTooltip" : "environment.liveTooltip");
  const label = t(IS_DEV ? "environment.development" : "environment.live");

  return (
    <Tooltip content={tooltip}>
      <Label
        theme={IS_DEV ? "warning" : "normal"}
        aria-label={t(IS_DEV ? "environment.developmentAria" : "environment.liveAria")}
        tabIndex={0}
      >
        {label}
      </Label>
    </Tooltip>
  );
};

export default EnvBadge;

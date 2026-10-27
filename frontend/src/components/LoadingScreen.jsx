import { Loader } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import MothIcon from "./MothIcon";

const LoadingScreen = ({ label }) => {
  const { t } = useTranslation();

  return (
    <div className="cm-loading-screen" role="status" aria-live="polite">
      <div className="cm-loading-screen__content">
        <div className="cm-loading-screen__mark" aria-hidden="true">
          <MothIcon withAntennae={false} />
        </div>
        <Loader size="l" />
        <span>{label ?? t("auth.unlocking")}</span>
      </div>
    </div>
  );
};

export default LoadingScreen;

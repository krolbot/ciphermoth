import { Plus } from "@gravity-ui/icons";
import { Button, Icon } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import MothIcon from "../MothIcon";

const EmptyVault = ({ onAdd }) => {
  const { t } = useTranslation();

  return (
    <section className="cm-empty-vault" aria-labelledby="cm-empty-vault-title">
      <div className="cm-empty-vault__content">
        <div className="cm-empty-vault__mark" aria-hidden="true">
          <MothIcon />
        </div>
        <h2 id="cm-empty-vault-title">{t("vault.emptyTitle")}</h2>
        <p>{t("vault.emptyDescription")}</p>
        <Button type="button" view="action" size="l" onClick={onAdd}>
          <Icon data={Plus} />
          {t("vault.addFirstPassword")}
        </Button>
      </div>
    </section>
  );
};

export default EmptyVault;

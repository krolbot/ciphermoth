import { Plus } from "@gravity-ui/icons";
import { Button, Icon, PlaceholderContainer } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

const EmptyVault = ({ onAdd }) => {
  const { t } = useTranslation();

  return (
    <PlaceholderContainer
      size="s"
      direction="column"
      title={t("vault.emptyTitle")}
      description={t("vault.emptyDescription")}
      actions={
        <Button type="button" view="action" size="l" onClick={onAdd}>
          <Icon data={Plus} />
          {t("vault.addFirstPassword")}
        </Button>
      }
    />
  );
};

export default EmptyVault;

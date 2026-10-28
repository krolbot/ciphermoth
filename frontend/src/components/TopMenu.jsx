import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRightFromSquare,
  ArrowRotateRight,
  Bars,
  CloudArrowUpIn,
  Gear,
  HeartPulse,
  Key,
  Lock,
  Persons,
  TrashBin,
  Xmark,
} from "@gravity-ui/icons";
import {
  Box,
  Button,
  Divider,
  Drawer,
  Flex,
  Icon,
  List,
  Text,
  useLayoutContext,
} from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { endSession } from "../api/session";
import { getCurrentUser } from "../utils";

import EnvBadge from "./EnvBadge";
import LanguageSwitcher from "./LanguageSwitcher";
import BrandMark from "./BrandMark";
import PasswordChangeDialog from "./PasswordChangeDialog";
import SettingsModal from "./SettingsModal";
import ThemeToggle from "./ThemeToggle";
import UpdateDialog from "./UpdateDialog";

const Brand = ({ version, onClick }) => {
  const { i18n } = useTranslation();
  const name = i18n.resolvedLanguage?.startsWith("ru") ? "Недра" : "Nedra";
  return (
    <Button component={Link} to="/passwords" view="flat" size="xl" onClick={onClick}>
      <Flex alignItems="center" gap="spacing-2">
        <BrandMark />
        <Text variant="subheader-2">{name}</Text>
        {version && (
          <Text color="secondary" variant="caption-2">
            v{String(version).replace(/^v/, "")}
          </Text>
        )}
      </Flex>
    </Button>
  );
};

const TopMenu = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { isMediaActive } = useLayoutContext();
  const desktop = isMediaActive("l");
  const currentUser = getCurrentUser();
  const admin = currentUser?.role === "admin";
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [updateOpen, setUpdateOpen] = useState(false);
  const mobileMenuButton = useRef(null);
  const utilityReturnTarget = useRef(null);

  const updateCheckEnabled = useStoreState(
    (state) => state.ciphermothModels.settings.settings.update_check_enabled
  );
  const settingsLoaded = useStoreState((state) => state.ciphermothModels.settings.loaded);
  const updateAvailable = useStoreState((state) => state.ciphermothModels.updates.updateAvailable);
  const version = useStoreState((state) => state.ciphermothModels.updates.current);
  const checkForUpdates = useStoreActions(
    (actions) => actions.ciphermothModels.updates.checkForUpdates
  );
  const fetchVersion = useStoreActions((actions) => actions.ciphermothModels.updates.fetchVersion);

  useEffect(() => {
    fetchVersion();
  }, [fetchVersion]);

  useEffect(() => {
    if (settingsLoaded && updateCheckEnabled) checkForUpdates();
  }, [settingsLoaded, updateCheckEnabled, checkForUpdates]);

  const closeMobileNav = () => setMobileNavOpen(false);
  const rememberUtilityTrigger = (event) => {
    utilityReturnTarget.current = mobileNavOpen ? mobileMenuButton.current : event.currentTarget;
  };
  const closeUtility = (setter) => {
    setter(false);
    window.requestAnimationFrame(() => utilityReturnTarget.current?.focus());
  };
  const openSettings = (event) => {
    rememberUtilityTrigger(event);
    closeMobileNav();
    setSettingsOpen(true);
  };
  const openPassword = (event) => {
    rememberUtilityTrigger(event);
    closeMobileNav();
    setPasswordOpen(true);
  };
  const openUpdate = (event) => {
    rememberUtilityTrigger(event);
    closeMobileNav();
    setUpdateOpen(true);
  };
  const logOut = () => {
    closeMobileNav();
    endSession();
  };

  const navItems = [
    { id: "/passwords", label: t("vault.title"), icon: Lock },
    { id: "/passwords?tool=backup", label: t("vault.backup"), icon: CloudArrowUpIn },
    { id: "/passwords?tool=health", label: t("vault.health"), icon: HeartPulse },
    { id: "/passwords?tool=trash", label: t("vault.trash"), icon: TrashBin },
    ...(admin ? [{ id: "/users", label: t("users.title"), icon: Persons }] : []),
  ];
  const navigation = (
    <Box as="nav" aria-label={t("navigation.workspace")}>
      <List
        aria-label={t("navigation.workspace")}
        items={navItems}
        selectionMode="single"
        selectedIds={[`${location.pathname}${location.search}`]}
        getItemTextValue={(item) => item.label}
        onItemAction={(id, item, event) => {
          if ("key" in event) {
            event.preventDefault();
            navigate(id);
          }
          closeMobileNav();
        }}
        renderItem={(ctx, { getItemProps, getItemViewProps }) => (
          <List.ItemView
            component={Link}
            to={ctx.id}
            {...getItemProps()}
            {...getItemViewProps()}
            aria-current={`${location.pathname}${location.search}` === ctx.id ? "page" : undefined}
            startContent={<Icon data={ctx.item.icon} />}
          >
            {ctx.item.label}
          </List.ItemView>
        )}
      />
    </Box>
  );
  const utilities = (
    <Flex direction="column" gap="spacing-2">
      <Divider />
      {admin && (
        <Button view="flat" onClick={openSettings}>
          <Icon data={Gear} />
          {t("topMenu.settings")}
        </Button>
      )}
      <Button view="flat" onClick={openPassword}>
        <Icon data={Key} />
        {t("auth.changePassword")}
      </Button>
      {updateAvailable && (
        <Button view="flat-action" onClick={openUpdate}>
          <Icon data={ArrowRotateRight} />
          {t("common.actions.update")}
        </Button>
      )}
      <Divider />
      <Text ellipsis>{currentUser?.username}</Text>
      <Text color="secondary" variant="caption-2">
        {t(`users.roles.${currentUser?.role}`)}
      </Text>
      <Flex alignItems="center" gap="spacing-2" wrap="wrap">
        <EnvBadge />
        <LanguageSwitcher />
        <ThemeToggle />
      </Flex>
      <Button view="flat-danger" onClick={logOut}>
        <Icon data={ArrowRightFromSquare} />
        {t("auth.logOut")}
      </Button>
    </Flex>
  );

  return (
    <>
      {desktop ? (
        <Flex
          as="aside"
          direction="column"
          width="240px"
          flexShrink={0}
          padding="spacing-3"
          gap="spacing-5"
          backgroundColor="generic"
        >
          <Brand version={version} />
          {navigation}
          {utilities}
        </Flex>
      ) : (
        <Flex as="header" alignItems="center" gap="spacing-3" padding="spacing-3">
          <Button
            ref={mobileMenuButton}
            type="button"
            view="flat-secondary"
            size="xl"
            aria-label={t("navigation.more")}
            onClick={() => setMobileNavOpen(true)}
          >
            <Icon data={Bars} />
          </Button>
          <Brand />
        </Flex>
      )}

      <Drawer
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
        placement="left"
        size={304}
        maxSize={360}
        returnFocus={mobileMenuButton}
        disableLayer={false}
        aria-label={t("navigation.workspace")}

        contentOverflow="auto"
      >
        <Flex direction="column" gap="spacing-5" padding="spacing-3">
          <Flex alignItems="center" justifyContent="space-between">
            <Brand version={version} onClick={closeMobileNav} />
            <Button
              type="button"
              view="flat-secondary"
              size="xl"
              aria-label={t("common.actions.close")}
              onClick={closeMobileNav}
            >
              <Icon data={Xmark} />
            </Button>
          </Flex>
          {navigation}
          {utilities}
        </Flex>
      </Drawer>

      {admin && <SettingsModal open={settingsOpen} onClose={() => closeUtility(setSettingsOpen)} />}
      <PasswordChangeDialog open={passwordOpen} onClose={() => closeUtility(setPasswordOpen)} />
      <UpdateDialog open={updateOpen} onClose={() => closeUtility(setUpdateOpen)} />
    </>
  );
};

export default TopMenu;

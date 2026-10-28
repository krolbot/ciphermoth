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
    <Flex
      as={Link}
      to="/passwords"
      onClick={onClick}
      alignItems="center"
      gap="spacing-2"
      minHeight="44px"
      minWidth="0"
      style={{ color: "var(--g-color-text-primary)", textDecoration: "none" }}
    >
      <BrandMark data-qa="brand-mark" />
      <Text variant="subheader-2" qa="brand-title">
        {name}
      </Text>
      {version && (
        <Text color="secondary" variant="caption-2">
          v{String(version).replace(/^v/, "")}
        </Text>
      )}
    </Flex>
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
    ...(admin ? [{ id: "/users", label: t("navigation.accounts"), icon: Persons }] : []),
  ];
  const navigation = (
    <Box as="nav" aria-label={t("navigation.workspace")}>
      <List
        aria-label={t("navigation.workspace")}
        size="xl"
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
  const utilityItems = [
    ...(admin
      ? [{ id: "settings", label: t("topMenu.settings"), icon: Gear, action: openSettings }]
      : []),
    { id: "password", label: t("auth.changePassword"), icon: Key, action: openPassword },
    ...(updateAvailable
      ? [
          {
            id: "update",
            label: t("common.actions.update"),
            icon: ArrowRotateRight,
            action: openUpdate,
          },
        ]
      : []),
  ];
  const utilities = (
    <Flex direction="column" gap="spacing-1">
      {utilityItems.map((item) => (
        <List.ItemView
          key={item.id}
          component="button"
          type="button"
          size="xl"
          onClick={item.action}
          startContent={<Icon data={item.icon} />}
        >
          {item.label}
        </List.ItemView>
      ))}
    </Flex>
  );
  const profile = (
    <Flex
      as="footer"
      direction="column"
      gap="spacing-3"
      padding="spacing-4"
      flexShrink={0}
      qa="navigation-footer"
      style={{
        borderTop: "1px solid var(--g-color-line-generic)",
        paddingBottom: "max(var(--g-spacing-4), env(safe-area-inset-bottom))",
      }}
    >
      <Flex alignItems="center" justifyContent="space-between" gap="spacing-2" minWidth="0">
        <Flex direction="column" gap="spacing-1" minWidth="0">
          <Text variant="subheader-1" ellipsis>
            {currentUser?.username}
          </Text>
          <Text color="secondary" variant="caption-2" ellipsis>
            {t(`users.roles.${currentUser?.role}`)}
          </Text>
        </Flex>
        <EnvBadge />
      </Flex>
      <Flex gap="spacing-2" alignItems="center" qa="navigation-preferences">
        <Flex flexGrow={1} minWidth="0">
          <LanguageSwitcher width="max" />
        </Flex>
        <Flex flexGrow={1} minWidth="0">
          <ThemeToggle showLabel width="max" />
        </Flex>
      </Flex>
      <Button view="flat-secondary" size="xl" width="max" onClick={logOut}>
        <Icon data={ArrowRightFromSquare} />
        {t("auth.logOut")}
      </Button>
    </Flex>
  );
  const shell = (mobile) => (
    <Flex
      direction="column"
      height="100dvh"
      minHeight="0"
      width={mobile ? "100vw" : undefined}
      maxWidth={mobile ? "360px" : undefined}
      qa="navigation-shell"
    >
      <Flex
        alignItems="center"
        justifyContent="space-between"
        gap="spacing-2"
        padding="spacing-4"
        flexShrink={0}
        qa="navigation-header"
      >
        <Brand version={version} onClick={closeMobileNav} />
        {mobile && (
          <Button
            type="button"
            view="flat-secondary"
            size="xl"
            aria-label={t("common.actions.close")}
            onClick={closeMobileNav}
          >
            <Icon data={Xmark} />
          </Button>
        )}
      </Flex>
      <Flex
        direction="column"
        gap="spacing-4"
        paddingInline="spacing-3"
        paddingBlockEnd="spacing-4"
        flexGrow={1}
        minHeight="0"
        overflow="auto"
        qa="navigation-body"
      >
        {navigation}
        <Divider />
        {utilities}
      </Flex>
      {profile}
    </Flex>
  );

  return (
    <>
      {desktop ? (
        <Box
          as="aside"
          width="288px"
          flexShrink={0}
          position="sticky"
          top="0"
          height="100dvh"
          backgroundColor="generic"
          style={{ borderRight: "1px solid var(--g-color-line-generic)" }}
        >
          {shell(false)}
        </Box>
      ) : (
        <Flex
          as="header"
          alignItems="center"
          gap="spacing-3"
          paddingInline="spacing-3"
          paddingBlock="spacing-2"
          qa="mobile-header"
          style={{ borderBottom: "1px solid var(--g-color-line-generic)" }}
        >
          <Button
            ref={mobileMenuButton}
            qa="burger"
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
        size="auto"
        returnFocus={mobileMenuButton}
        disableLayer={false}
        aria-label={t("navigation.workspace")}

        contentOverflow="visible"
      >
        {shell(true)}
      </Drawer>

      {admin && <SettingsModal open={settingsOpen} onClose={() => closeUtility(setSettingsOpen)} />}
      <PasswordChangeDialog open={passwordOpen} onClose={() => closeUtility(setPasswordOpen)} />
      <UpdateDialog open={updateOpen} onClose={() => closeUtility(setUpdateOpen)} />
    </>
  );
};

export default TopMenu;

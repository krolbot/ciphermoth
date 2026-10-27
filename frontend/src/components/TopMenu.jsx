import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
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
  Plus,
  TrashBin,
  Xmark,
} from "@gravity-ui/icons";
import { Button, Drawer, Icon, Tooltip } from "@gravity-ui/uikit";
import { useStoreActions, useStoreState } from "easy-peasy";
import { useTranslation } from "react-i18next";

import { endSession } from "../api/session";
import { getCurrentUser } from "../utils";
import { IS_DEV } from "../lib/appEnv";
import EnvBadge from "./EnvBadge";
import LanguageSwitcher from "./LanguageSwitcher";
import MothIcon from "./MothIcon";
import PasswordChangeDialog from "./PasswordChangeDialog";
import SettingsModal from "./SettingsModal";
import ThemeToggle from "./ThemeToggle";
import UpdateDialog from "./UpdateDialog";

const NavigationItem = ({ to, icon, label, end = false, badge = false, onClick }) => {
  const location = useLocation();
  const [pathname, query] = to.split("?");
  const active =
    location.pathname === pathname &&
    (query ? location.search === `?${query}` : !location.search) &&
    (!end || location.pathname === pathname);

  return (
    <Link
      to={to}
      className={`cm-nav__item${active ? " cm-nav__item--active" : ""}`}
      aria-current={active ? "page" : undefined}
      onClick={onClick}
    >
      <Icon data={icon} size={18} />
      <span>{label}</span>
      {badge && <span className="cm-nav__badge" aria-hidden="true" />}
    </Link>
  );
};

const Brand = ({ version, compact = false, onClick }) => (
  <Link className="cm-brand" to="/passwords" onClick={onClick}>
    <span className="cm-brand__mark" aria-hidden="true">
      <MothIcon />
    </span>
    <span className="cm-brand__copy">
      <span className="cm-brand__name">
        Cipher<span className="cm-brand__name-accent">Moth</span>
      </span>
      {!compact && (
        <span className="cm-brand__meta">
          {version ? `v${String(version).replace(/^v/, "")}` : ""}
        </span>
      )}
    </span>
  </Link>
);

const TopMenu = () => {
  const { t } = useTranslation();
  const location = useLocation();
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

  const navigation = (mobile = false) => (
    <nav className="cm-nav" aria-label={t("navigation.workspace")}>
      <p className="cm-nav__section-label">{t("navigation.workspace")}</p>
      <NavigationItem
        to="/passwords"
        icon={Lock}
        label={t("vault.title")}
        end
        onClick={mobile ? closeMobileNav : undefined}
      />
      <NavigationItem
        to="/passwords?tool=backup"
        icon={CloudArrowUpIn}
        label={t("vault.backup")}
        onClick={mobile ? closeMobileNav : undefined}
      />
      <NavigationItem
        to="/passwords?tool=health"
        icon={HeartPulse}
        label={t("vault.health")}
        onClick={mobile ? closeMobileNav : undefined}
      />
      <NavigationItem
        to="/passwords?tool=trash"
        icon={TrashBin}
        label={t("vault.trash")}
        onClick={mobile ? closeMobileNav : undefined}
      />

      {admin && (
        <>
          <p className="cm-nav__section-label">{t("navigation.administration")}</p>
          <NavigationItem
            to="/users"
            icon={Persons}
            label={t("users.title")}
            onClick={mobile ? closeMobileNav : undefined}
          />
        </>
      )}

      <p className="cm-nav__section-label">{t("navigation.manage")}</p>
      {admin && (
        <button type="button" className="cm-nav__item" onClick={openSettings}>
          <Icon data={Gear} size={18} />
          <span>{t("topMenu.settings")}</span>
        </button>
      )}
      <button type="button" className="cm-nav__item" onClick={openPassword}>
        <Icon data={Key} size={18} />
        <span>{t("auth.changePassword")}</span>
      </button>
      {updateAvailable && (
        <button type="button" className="cm-nav__item" onClick={openUpdate}>
          <Icon data={ArrowRotateRight} size={18} />
          <span>{t("common.actions.update")}</span>
          <span className="cm-nav__badge" aria-hidden="true" />
        </button>
      )}
    </nav>
  );

  const accountFooter = (
    <footer className="cm-sidebar__footer">
      <EnvBadge />
      <div className="cm-sidebar__utility">
        <div className="cm-sidebar__user">
          <span className="cm-sidebar__username">{currentUser?.username}</span>
          <span className="cm-sidebar__role">{currentUser?.role}</span>
        </div>
        <LanguageSwitcher />
        <ThemeToggle />
      </div>
      <button type="button" className="cm-nav__item cm-nav__item--danger" onClick={logOut}>
        <Icon data={ArrowRightFromSquare} size={18} />
        <span>{t("auth.logOut")}</span>
      </button>
    </footer>
  );

  return (
    <>
      <aside className={`cm-sidebar${IS_DEV ? " cm-sidebar--development" : ""}`}>
        <header className="cm-sidebar__header">
          <Brand version={version} />
        </header>
        {navigation()}
        {accountFooter}
      </aside>

      <header className="cm-mobile-header">
        <Button
          ref={mobileMenuButton}
          type="button"
          view="flat-secondary"
          size="l"
          aria-label={t("navigation.more")}
          onClick={() => setMobileNavOpen(true)}
        >
          <Icon data={Bars} />
        </Button>
        <Brand compact />
        <div className="cm-mobile-header__actions">
          {["/passwords", "/entries/new"].includes(location.pathname) ? (
            <span className="cm-mobile-header__action-spacer" aria-hidden="true" />
          ) : (
            <Tooltip content={t("navigation.newEntry")}>
              <Button
                component={Link}
                to="/entries/new"
                view="action"
                size="l"
                aria-label={`${t("common.actions.add")} — ${t("navigation.newEntry")}`}
              >
                <Icon data={Plus} />
                <span className="cm-mobile-header__new-label">{t("common.actions.add")}</span>
              </Button>
            </Tooltip>
          )}
        </div>
      </header>

      <Drawer
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
        placement="left"
        size={304}
        aria-label={t("navigation.workspace")}
        contentClassName="cm-mobile-drawer"
        contentOverflow="auto"
      >
        <div className="cm-mobile-drawer__content">
          <header className="cm-sidebar__header">
            <Brand version={version} onClick={closeMobileNav} />
            <Button
              type="button"
              view="flat-secondary"
              size="l"
              aria-label={t("common.actions.close")}
              onClick={closeMobileNav}
            >
              <Icon data={Xmark} />
            </Button>
          </header>
          {navigation(true)}
          {accountFooter}
        </div>
      </Drawer>

      {admin && <SettingsModal open={settingsOpen} onClose={() => closeUtility(setSettingsOpen)} />}
      <PasswordChangeDialog open={passwordOpen} onClose={() => closeUtility(setPasswordOpen)} />
      <UpdateDialog open={updateOpen} onClose={() => closeUtility(setUpdateOpen)} />
    </>
  );
};

export default TopMenu;

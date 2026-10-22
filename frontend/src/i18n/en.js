const en = {
  common: {
    actions: {
      add: "Add",
      cancel: "Cancel",
      close: "Close",
      confirm: "Confirm",
      create: "Create",
      delete: "Delete",
      done: "Done",
      download: "Download",
      edit: "Edit",
      import: "Import",
      later: "Later",
      remove: "Remove",

      save: "Save",
      update: "Update",
    },
    fields: {
      actions: "Actions",
      description: "Description",
      folder: "Folder",
      name: "Name",
      password: "Password",
      tags: "Tags",
      usernameEmail: "Username / email",
    },
    labels: {
      configured: "Configured",
      loading: "Loading…",
      secondsShort: "sec",
      working: "Working…",
    },
    duration: {
      minutes_one: "{{count}} minute",
      minutes_few: "{{count}} minutes",
      minutes_many: "{{count}} minutes",
      minutes_other: "{{count}} minutes",
      seconds_one: "{{count}} second",
      seconds_few: "{{count}} seconds",
      seconds_many: "{{count}} seconds",
      seconds_other: "{{count}} seconds",
    },
  },
  language: {
    label: "Language",
    english: "English",
    russian: "Russian",
  },
  theme: {
    toLight: "Coax the moth into the light",
    toDark: "Send the moth back into the dark",
    switchToLight: "Switch to light theme",
    switchToDark: "Switch to dark theme",
  },
  environment: {
    development: "DEV",
    live: "LIVE",
    developmentAria: "Development environment",
    liveAria: "Live vault",
    developmentTooltip:
      "Development sandbox. Throwaway data only. make clean wipes it, and your real vault lives on a separate stack.",
    liveTooltip: "Your real vault. These are the passwords that actually matter.",
  },
  auth: {
    tagline: "Your secrets stay in the dark.",
    setupTitle: "Create the first administrator",
    setupDescription:
      "Registration stays closed. Use this administrator account to create people and service accounts.",
    masterPassword: "Password",

    confirmMasterPassword: "Confirm password",
    noRecoveryWarning:
      "CipherMoth cannot reset the only administrator account. Add another administrator and keep an encrypted backup so access can be recovered safely.",
    noRecoveryAcknowledgement:
      "I understand recovery requires another active administrator or an encrypted backup.",
    unlock: "Unlock Vault",
    create: "Create Vault",
    closeLocks: "Closing this tab locks your vault. That is by design.",
    unlocking: "UNLOCKING",
    logIn: "Log in",
    logOut: "Log out",
    username: "Username",
    currentPassword: "Current password",
    newPassword: "New password",
    changePassword: "Change password",
    changePasswordTitle: "Change your password",
    passwordChangeReminder: "An administrator is asking you to change your current password.",

    validation: {
      enterMasterPassword: "Please enter your password.",

      enterUsername: "Please enter your username.",
      enterPasswordChange: "Enter both passwords.",
      enterNewMasterPassword: "Please enter an administrator password.",
      passwordsDoNotMatch: "Passwords don't match.",
      weakPassword: "Password is too weak. Use at least 12 characters with mixed types.",
      currentPasswordIncorrect: "Current password is incorrect.",
      confirmNoRecovery: "Please confirm the recovery requirement.",
    },
  },
  topMenu: {
    runningVersion: "Running version",
    updateAvailable: "A new CipherMoth release is available",
    settings: "Settings",
  },
  vault: {
    title: "The Vault",
    subtitle: {
      empty: "Nothing here yet. Your secrets are waiting for the dark.",
      secretCount_one: "{{count}} secret in the dark",
      secretCount_few: "{{count}} secrets in the dark",
      secretCount_many: "{{count}} secrets in the dark",
      secretCount_other: "{{count}} secrets in the dark",
      backedUp: "{{countText}} · backed up and locked tight.",
      outdated: "{{countText}} · backup is outdated.",
      noBackup: "{{countText}} · no backup yet.",
    },
    health: "Health",
    backup: "Backup",
    import: "Import",
    trash: "Trash",
    trashCount: "Trash ({{count}})",
    searchPlaceholder: "Search name, username, website or tag…",
    allFolders: "All folders",
    noSearchResults: "No passwords match “{{search}}”.",
    emptyTitle: "The vault is empty",
    emptyDescription:
      "Nobody is watching. Add your first password and let it disappear into the dark.",
    addFirstPassword: "Add First Password",
    messages: {
      noteUpdated: "Secure note updated.",
      passwordUpdated: "Password updated.",
      noteCreated: "Secure note created.",
      passwordCreated: "Password created.",
      movedToTrash: "Moved to trash.",
      restored: "Restored from trash.",
      permanentlyDeleted: "Permanently deleted.",
      backupCreated: "Backup created: keep this file safe.",
    },
    moveToTrash: {
      title: "Move to Trash",
      message: "Move <strong>{{name}}</strong> to Trash? You can restore it later from the Trash.",
    },
    columns: {
      attachment_one: "{{count}} attachment",
      attachment_few: "{{count}} attachments",
      attachment_many: "{{count}} attachments",
      attachment_other: "{{count}} attachments",
      secureNote: "Secure note",
      copyUsername: "Copy username",
      hidePassword: "Hide password",
      revealPassword: "Reveal password",
      copyPassword: "Copy password",
      openWebsite: "Open website",
      removeFavorite: "Remove from favorites",
      markFavorite: "Mark as favorite",
      passwordBackedUp: "Password backed up",
      passwordNotBackedUp: "Password not backed up",
      updateRecommended: "We recommend updating this password.",
      looksGood: "This password looks good.",
      twoFactor: "2FA",
    },
  },
  entry: {
    title: {
      editNote: "Edit Secure Note",
      editPassword: "Edit Password",
      addNote: "Add Secure Note",
      addPassword: "Add Password",
    },
    kind: {
      login: "Login",
      note: "Secure note",
    },
    labels: {
      label: "Label",
      value: "Value",
      note: "Note",
      usernameOptional: "Username / email (optional)",
      websiteOptional: "Website (optional)",
      folderOptional: "Folder (optional)",
      twoFactor: "Two-factor",
      twoFactorSecret: "Two-factor secret (optional)",
      customFields: "Custom fields",
      notes: "Notes",
      attachments: "Attachments",
      passwordHistory: "Password history",
    },
    placeholders: {
      customLabel: "e.g. PIN",
      note: "Anything you want to keep encrypted and safe.",
      username: "e.g. john@example.com",
      website: "e.g. https://github.com",
      folder: "e.g. Work, Personal",
      tags: "Add a tag and press Enter",
      description: "e.g. Personal account, work email…",
      noteName: "e.g. Recovery codes, Wi-Fi, Passport",
      passwordName: "e.g. GitHub, Gmail, Netflix",
    },
    help: {
      nameCannotChange: "Name cannot be changed",
      twoFactor: "Paste a base32 secret or an otpauth:// link to show 2FA codes here.",
      twoFactorTooltip:
        "This is for the rolling 6-digit code some sites ask for after your password. When you turn on authenticator-app 2FA (Google Authenticator, Authy and similar), the site shows a setup key or QR code. Paste that key here (a base32 secret or an otpauth:// link) and CipherMoth will show the live code in your vault. Leave blank if you keep 2FA on your phone.",
    },
    actions: {
      valueHidden: "Value hidden - click to reveal in views",
      hideValue: "Hide value in views",
      removeField: "Remove field",
      closeGenerator: "Close generator",
      generatePassword: "Generate password",
      addField: "Add field",
    },
    validation: {
      nameRequired: "Name is required.",
      noteRequired: "Note content is required.",
      passwordRequired: "Password value is required.",
    },
  },
  passwordField: {
    hide: "Hide",
    show: "Show",
  },
  generator: {
    length: "Length",
    regenerate: "Regenerate",
  },
  strength: {
    veryWeak: "Very Weak",
    weak: "Weak",
    fair: "Fair",
    strong: "Strong",
    veryStrong: "Very Strong",
    tooShort: "Too short",
    recommendation: "consider a longer or more complex password",
  },
  totp: {
    invalid: "invalid",
    copy: "Copy 2FA code",
  },
  attachments: {
    empty: "No files attached yet. Files are encrypted with your vault key.",
    tooLarge: "“{{filename}}” is larger than 5 MB.",
    attached: "Attached “{{filename}}”.",
    removed: "Removed “{{filename}}”.",
    removeFile: "Remove file",
    attachFile: "Attach file",
    limits: "Up to 5 MB each, 25 MB total.",
    removeTitle: "Remove attachment?",
    removeMessage: "Permanently delete “{{filename}}” from this entry? This cannot be undone.",
  },
  backup: {
    title: "Create Backup",
    description:
      "Your visible entries will be exported to an encrypted .cmbackup file protected with your current account password.",
    passwordRequired: "Account password is required.",
  },
  importDialog: {
    title: "Import Passwords",
    completeTitle: "Import Complete",
    backupMode: "CipherMoth backup",
    csvMode: "CSV from another app",
    csvDescription:
      "Upload a CSV exported from Chrome, Bitwarden, KeePass, Proton Pass and similar. Columns are matched automatically.",
    backupDescription:
      "Upload a CipherMoth .cmbackup file and enter its backup password to restore entries.",
    chooseCsv: "Choose CSV file (.csv)",
    chooseBackup: "Choose backup file (.cmbackup)",
    selectCsv: "Please select a CSV file.",
    selectBackup: "Please select a backup file.",
    existingLabel: "If a password already exists",
    keepExisting: "Keep existing (skip)",
    overwrite: "Overwrite with imported value",
    noPasswords: "No passwords found in the file.",
    imported_one: "<strong>{{count}}</strong> password added.",
    imported_few: "<strong>{{count}}</strong> passwords added.",
    imported_many: "<strong>{{count}}</strong> passwords added.",
    imported_other: "<strong>{{count}}</strong> passwords added.",
    overwritten_one: "<strong>{{count}}</strong> password overwritten.",
    overwritten_few: "<strong>{{count}}</strong> passwords overwritten.",
    overwritten_many: "<strong>{{count}}</strong> passwords overwritten.",
    overwritten_other: "<strong>{{count}}</strong> passwords overwritten.",
    skipped_one: "<strong>{{count}}</strong> password skipped (already exists).",
    skipped_few: "<strong>{{count}}</strong> passwords skipped (already exist).",
    skipped_many: "<strong>{{count}}</strong> passwords skipped (already exist).",
    skipped_other: "<strong>{{count}}</strong> passwords skipped (already exist).",
  },
  health: {
    title: "Vault Health",
    healthy: "Healthy",
    needsAttention: "Needs attention",
    atRisk: "At risk",
    weak: "Weak",
    reused: "Reused",
    old: "Old",
    localOnly: "This check runs entirely on your device. Nothing is sent anywhere.",
    allClear: "Everything looks healthy. Nice work.",
    weakHint: "Short or simple passwords worth strengthening.",
    reusedHint: "The same password is used on more than one entry.",
    oldHint: "Not changed in over a year.",
  },
  settings: {
    title: "Settings",
    saved: "Settings saved.",
    warningValidation: "Warning before logout must be less than the inactivity timeout.",
    fields: {
      inactivity: "Inactivity timeout",
      inactivityHelp:
        "How long the app waits without any user activity before logging you out automatically.",
      warning: "Warning before logout",
      warningHelp:
        "How far in advance of the inactivity timeout a warning is shown. Must be less than the inactivity timeout.",
      hidden: "Hidden tab timeout",
      hiddenHelp:
        "How long the tab can stay in the background (minimised or switched away) before you are logged out.",
      debounce: "Activity debounce",
      debounceHelp:
        "Minimum interval between activity detections. Prevents the inactivity timer from being reset too aggressively.",
      clipboard: "Clipboard clear delay",
      clipboardHelp: "How long after copying a password the clipboard is automatically wiped.",
      updates: "Check for updates",
      updatesHelp:
        "Lets your browser ask GitHub whether a newer CipherMoth release exists. Your vault never leaves this machine; turn it off to stay fully third-party-free.",
    },
  },
  updateDialog: {
    title: "A new moult is ready",
    releaseNotes: "Read the release notes on GitHub",
    automaticDescription:
      "CipherMoth will verify the new images are signed by the official release, back up your database, restart, and roll back automatically if anything looks wrong. Your account password is never needed and your vault stays encrypted throughout.",
    manualDescription:
      "One-click updates aren't enabled on this instance. Update from a terminal in your CipherMoth folder:",
    updateNow: "Update now",
    complete: "Update complete. Reloading…",
    background: "Still updating in the background, refresh in a moment.",
    states: {
      requested: "Starting…",
      verifying: "Verifying image signatures…",
      applying: "Applying update and restarting…",
      success: "Updated. Reloading…",
      failed: "Update failed, your vault is untouched.",
      rolledBack: "Update failed and was rolled back, you're on the previous version.",
    },
  },
  trashDialog: {
    empty: "Trash is empty. Deleted secrets rest here until you restore or purge them.",
    deleted: "Deleted",
    restore: "Restore",
    deleteForever: "Delete forever",
    deleteForeverTitle: "Delete Forever",
    deleteForeverMessage: "Permanently delete <strong>{{name}}</strong>? This cannot be undone.",
    deleteAll: "Delete all",
    deleteAllTitle: "Empty trash?",
    deleteAllMessage:
      "All of your trashed entries will be permanently deleted: {{count}}. This cannot be undone.",
    deletedAll_one: "Permanently deleted {{count}} entry.",
    deletedAll_few: "Permanently deleted {{count}} entries.",
    deletedAll_many: "Permanently deleted {{count}} entries.",
    deletedAll_other: "Permanently deleted {{count}} entries.",
  },
  autoLogout: {
    countdown: "You'll be logged out in {{seconds}}s due to inactivity.",
    loggedOut: "Logged out due to inactivity.",
  },
  clipboard: {
    copied: "Copied! Clipboard clears in {{duration}}.",
  },
  sharing: {
    addAccess: "Add access",
    currentAccess: "Current access",
    noAvailableTargets: "No other users are available.",
    title: "Share {{name}}",
    manage: "Manage sharing",
    manageOptional: "Manage sharing (optional)",
    access: "Owner / access",
    user: "User",
    selectUser: "Select",
    permission: "Permission",
    read: "Read",
    write: "Write",
    owner: "Owner",
    empty: "This entry is not shared.",
    revoke: "Revoke",
    savedWithEntry: "Access changes are applied when you save the entry.",
  },
  users: {
    title: "Users",
    subtitle: "Manage accounts, roles, access status, and active sessions.",
    backToVault: "Back to vault",
    columns: {
      account: "Account",
      role: "Role",
      status: "Status",
      actions: "Actions",
    },
    create: "Create user",
    createDescription:
      "A regular user sees owned and explicitly shared entries in the encrypted vault. A service account gets a separate MCP token and only explicit grants.",
    temporaryPassword: "Temporary password",
    serviceToken: "MCP bearer token",
    serviceTokenOnce: "Copy this token now. It will not be shown again.",
    copyToken: "Copy token",
    role: "Role",
    active: "Active",
    inactive: "Disabled",
    passwordChangePending: "Password change reminder",
    revokeSessions: "Revoke sessions",
    requirePasswordChange: "Remind about password change",
    confirm: {
      sessions: {
        title: "Revoke all sessions?",
        message: "{{username}} will need to sign in again on every device.",
      },
      password: {
        title: "Enable the password change reminder?",
        message: "{{username}} will see a reminder until they change their current password.",
      },
      delete: {
        title: "Delete user?",
        message:
          "{{username}} and their granted access will be deleted. Deletion is blocked while they own vault entries or service agents.",
      },
    },
    messages: {
      created: "User created.",
      sessions: "All user sessions were revoked.",
      password: "The password change reminder is enabled.",
      delete: "User deleted.",
    },
    roles: { admin: "Admin", member: "Member", service: "Service" },
  },
  errors: {
    invalidMasterPassword: "Invalid password.",
    tooManyAttempts: "Too many attempts. Please try again in an hour.",
    generic: "An error occurred.",
    saveSettings: "Failed to save settings.",
    loadPasswords: "Failed to load passwords.",
    createPassword: "Failed to create password.",
    updatePassword: "Failed to update password.",
    deletePassword: "Failed to delete password.",
    loadTrash: "Failed to load trash.",
    restorePassword: "Failed to restore password.",
    updateFavorite: "Failed to update favorite.",
    loadAttachments: "Failed to load attachments.",
    uploadAttachment: "Failed to upload attachment.",
    downloadAttachment: "Failed to download attachment.",
    deleteAttachment: "Failed to delete attachment.",
    importFailed: "Import failed.",
    backupFailed: "Backup failed.",
    changePassword: "Failed to change password.",
    loadUsers: "Failed to load users.",
    createUser: "Failed to create user.",
    updateUser: "Failed to update user.",
    revokeUserSessions: "Failed to revoke user sessions.",
    requirePasswordChange: "Failed to enable the password change reminder.",
    deleteUser: "Failed to delete user.",
    loadShareTargets: "Failed to load share targets.",
    loadShares: "Failed to load shares.",
    saveShare: "Failed to save sharing.",
    revokeShare: "Failed to revoke access.",
    startUpdate: "Failed to start the update.",
  },
};

Object.assign(en.common.actions, { dismiss: "Dismiss", retry: "Retry" });
Object.assign(en.auth, {
  administratorUsername: "Administrator username",
  sessionEnded: "Your vault was locked. Unlock it to continue.",
  confirmNewPassword: "Confirm new password",
  changeTemporaryPassword: "Change your temporary password",
  passwordChangeRequired:
    "An administrator requested a password change before you continue using the vault.",
  passwordChangeNoSession: "Password changed, but no session was returned.",
});
Object.assign(en.auth.validation, {
  enterAdministratorUsername: "Please enter an administrator username.",
  passwordChangeWeak: "Use at least 12 characters with mixed character types.",
});
Object.assign(en.vault.messages, {
  backupRequested: "Download requested. Check that the backup file was saved and keep it safe.",
});
Object.assign(en.vault, {
  damage: {
    message_one:
      "{{count}} item in the vault file cannot be read (damaged or altered), so it is not shown. Backups wait until you restore a snapshot or remove it.",
    message_other:
      "{{count}} items in the vault file cannot be read (damaged or altered), so they are not shown. Backups wait until you restore a snapshot or remove them.",
    removed: "Damaged rows removed.",
    removeTitle: "Remove damaged items",
    removeMessage_one:
      "Permanently remove {{count}} unreadable item? A removed entry takes its attachments with it. If you have a snapshot from before the damage, restoring it keeps them instead.",
    removeMessage_other:
      "Permanently remove {{count}} unreadable items? A removed entry takes its attachments with it. If you have a snapshot from before the damage, restoring it keeps them instead.",
  },
});
Object.assign(en.backup, {
  descriptionFull:
    "An encrypted portable copy of the entries available to your account, including trash, password history, attachments and settings, in one .cmbackup file protected with your current account password.",
  restoreAdvice:
    "Restore it here with Import, into this vault or a new one. Keep the file somewhere safe: anyone who knows its backup password can open it, even after you change your account password.",
  desktopAdvice: "Choose a new filename in the Save dialog. Existing files are never replaced.",
  webAdvice: "Check that your browser actually saves the file.",
});
Object.assign(en.importDialog, {
  enterBackupPassword: "Enter the backup's password.",
  filePickerError: "Could not open the file picker.",
  backupPassword: "Backup password",
  backupPasswordHelp: "The account password used when the backup was made.",
  alsoRestored: "Also restored: {{items}}.",
  andMore_one: "and {{count}} more",
  andMore_other: "and {{count}} more",
  renamed_one: "item renamed:",
  renamed_other: "items renamed:",
  ignored_one: "record not imported:",
  ignored_other: "records not imported:",
  restoredExtras: {
    trash_one: "{{count}} in the trash",
    trash_other: "{{count}} in the trash",
    attachments_one: "{{count}} attachment",
    attachments_other: "{{count}} attachments",
    grants_one: "{{count}} access grant",
    grants_other: "{{count}} access grants",
    settings: "your settings",
  },
});
Object.assign(en.sharing, {
  ownerOnly: "Only the owner can access this entry.",
  grantAccess: "Grant access",
  selectTarget: "Select account",
  readWrite: "Read and write",
  grant: "Grant",
  readOnlyAccess: "Read-only access",
});
Object.assign(en.users, {
  title: "Users and service access",
  subtitle: "Registration is closed. Administrators create accounts and service tokens here.",
  createAccount: "Create account",
  passwordChangeRequested: "Password change requested",
  serviceAccount: "Non-interactive MCP account",
  interactiveAccount: "Interactive account",
  rotateToken: "Rotate token",
  resetPassword: "Reset password",
  resetPasswordFor: "Reset password for {{username}}",
  resetPasswordDescription:
    "Existing sessions will be revoked. The user will be asked to change this temporary password.",
  deleteConfirm: "Delete {{username}}?",
});
Object.assign(en.users.messages, {
  passwordReset: "Temporary password set and active sessions revoked.",
  tokenRotated: "Service token rotated. The previous token no longer works.",
  roleUpdated: "Role updated.",
  statusUpdated: "Status updated.",
  sessionsRevoked: "Sessions revoked.",
  deleted: "User deleted.",
});
Object.assign(en.errors, {
  invalidCredentials: "Invalid username or password.",
  authentication: "Authentication failed.",
  resetPassword: "Failed to reset password.",
  rotateServiceToken: "Failed to rotate service token.",
  invalidEntryName:
    "Browsers can't address an entry named “{{name}}”. Edit the entry to rename it, then try again.",
  damageCheck:
    "The vault damage check failed. Some entries or attachments may be missing from this view. Retry the check before relying on this list.",
  removeDamaged: "Failed to remove the damaged rows.",
});
Object.assign(en.updateDialog, {
  manualBackupDescription:
    "Update from a terminal in your CipherMoth folder. The first command keeps a raw snapshot of the encrypted vault file, so you can always go back. It requires a valid account credential from that snapshot; for a portable copy, use Backup.",
});
en.desktopUpdate = {
  installDescription:
    "Download from GitHub and verify its signature, then lock your vault and restart CipherMoth. Your local vault stays in place.",
  debianDescription:
    "This Debian installation updates through your package manager. Download the new .deb from GitHub and install it over this version. Your local vault stays in place.",
  installing: "Installing…",
  downloading: "Downloading and verifying…",
  releaseNotes: "Release notes and downloads",
  cancelDownload: "Cancel download",
  downloadInstall: "Download and install",
};
en.desktopGate = {
  opening: "OPENING CIPHERMOTH",
  openFailedTitle: "Your vault could not be opened",
  openFailedDescription:
    "Close other CipherMoth windows and check that this application is complete. Your vault has not been replaced.",
};

export default en;

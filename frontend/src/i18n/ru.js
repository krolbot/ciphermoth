const ru = {
  common: {
    actions: {
      add: "Добавить",
      cancel: "Отмена",
      close: "Закрыть",
      confirm: "Подтвердить",
      create: "Создать",
      delete: "Удалить",
      done: "Готово",
      download: "Скачать",
      edit: "Изменить",
      import: "Импортировать",
      later: "Позже",
      remove: "Удалить",

      save: "Сохранить",
      update: "Обновить",
    },
    fields: {
      actions: "Действия",
      description: "Описание",
      folder: "Папка",
      name: "Название",
      password: "Пароль",
      tags: "Метки",
      usernameEmail: "Логин или почта",
    },
    labels: {
      configured: "Настроено",
      loading: "Загрузка…",
      secondsShort: "с",
      working: "Обновляем…",
    },
    duration: {
      minutes_one: "{{count}} минута",
      minutes_few: "{{count}} минуты",
      minutes_many: "{{count}} минут",
      minutes_other: "{{count}} минуты",
      seconds_one: "{{count}} секунда",
      seconds_few: "{{count}} секунды",
      seconds_many: "{{count}} секунд",
      seconds_other: "{{count}} секунды",
    },
  },
  language: {
    label: "Язык",
    english: "Английский",
    russian: "Русский",
  },
  theme: {
    toLight: "Позвать мотылька на свет",
    toDark: "Вернуть мотылька в темноту",
    switchToLight: "Включить светлую тему",
    switchToDark: "Включить тёмную тему",
  },
  environment: {
    development: "DEV",
    live: "LIVE",
    developmentAria: "Среда разработки",
    liveAria: "Рабочее хранилище",
    developmentTooltip:
      "Тестовая среда. Данные здесь временные: make clean сотрёт их. Рабочее хранилище находится отдельно.",
    liveTooltip: "Рабочее хранилище. Здесь лежат пароли, которые вам действительно нужны.",
  },
  auth: {
    tagline: "Ваши секреты остаются в темноте.",
    setupTitle: "Создайте первого администратора",
    setupDescription:
      "Регистрация закрыта. Через эту учётную запись вы создадите пользователей и служебные аккаунты.",
    masterPassword: "Пароль",

    confirmMasterPassword: "Повторите пароль",
    noRecoveryWarning:
      "CipherMoth не может сбросить пароль единственного администратора. Создайте второго администратора и храните зашифрованную резервную копию.",
    noRecoveryAcknowledgement:
      "Я понимаю: для восстановления нужен другой активный администратор или зашифрованная резервная копия.",
    unlock: "Открыть хранилище",
    create: "Создать хранилище",
    closeLocks: "Закроете вкладку — хранилище заблокируется. Так и задумано.",
    unlocking: "Открываем…",
    logIn: "Войти",
    logOut: "Выйти",
    username: "Имя пользователя",
    usernameRules:
      "От 2 до 64 символов: латинские буквы, цифры и . _ @ -. Первый символ — буква или цифра. Заглавные буквы сохраняются как строчные.",
    currentPassword: "Текущий пароль",
    newPassword: "Новый пароль",
    changePassword: "Сменить пароль",
    changePasswordTitle: "Смените пароль",
    passwordChangeReminder: "Администратор просит сменить текущий пароль.",

    validation: {
      enterMasterPassword: "Введите пароль.",

      enterUsername: "Введите имя пользователя.",
      enterPasswordChange: "Введите оба пароля.",
      enterNewMasterPassword: "Задайте пароль администратора.",
      passwordsDoNotMatch: "Пароли не совпадают.",
      weakPassword: "Слишком слабый пароль. Используйте не менее 12 символов разных типов.",
      currentPasswordIncorrect: "Текущий пароль неверен.",
      confirmNoRecovery: "Подтвердите, что понимаете условия восстановления доступа.",
    },
  },
  topMenu: {
    runningVersion: "Установленная версия",
    updateAvailable: "Вышла новая версия CipherMoth",
    settings: "Настройки",
  },
  vault: {
    title: "Хранилище",
    subtitle: {
      empty: "Пока здесь пусто. Темнота ждёт первого секрета.",
      secretCount_one: "{{count}} секрет хранится в темноте",
      secretCount_few: "{{count}} секрета хранятся в темноте",
      secretCount_many: "{{count}} секретов хранятся в темноте",
      secretCount_other: "{{count}} секрета хранятся в темноте",
      backedUp: "{{countText}} · резервная копия свежая, всё под замком.",
      outdated: "{{countText}} · резервная копия устарела.",
      noBackup: "{{countText}} · резервной копии ещё нет.",
    },
    health: "Состояние",
    backup: "Резервная копия",
    import: "Импорт",
    trash: "Корзина",
    trashCount: "Корзина ({{count}})",
    searchPlaceholder: "Поиск по хранилищу…",
    browser: {
      sort: "Порядок",
      favoritesFirst: "Избранное",
      nameAscending: "Название А–Я",
      nameDescending: "Название Я–А",
      dateAdded: "По времени добавления",
      entries: "Записи хранилища",
      details: "Просмотр записи",
      back: "К списку записей",
      open: "Открыть {{name}}",
      copyValue: "Скопировать {{label}}",
      copyNote: "Скопировать заметку",
      favorite: "Избранное",
      tools: "Действия с хранилищем",
    },
    allFolders: "Все папки",
    noSearchResults: "По запросу «{{search}}» ничего не нашлось.",
    emptyTitle: "Хранилище пусто",
    emptyDescription: "Никто не смотрит. Добавьте первый секрет — пусть исчезнет в темноте.",
    addFirstPassword: "Добавить первый секрет",
    messages: {
      noteUpdated: "Защищённая заметка обновлена.",
      passwordUpdated: "Пароль обновлён.",
      noteCreated: "Защищённая заметка создана.",
      passwordCreated: "Пароль создан.",
      movedToTrash: "Запись перемещена в корзину.",
      restored: "Запись восстановлена.",
      permanentlyDeleted: "Запись удалена навсегда.",
      backupCreated: "Резервная копия готова. Сохраните файл в надёжном месте.",
    },
    moveToTrash: {
      title: "Переместить в корзину?",
      message: "Запись <strong>{{name}}</strong> можно будет восстановить из корзины.",
    },
    columns: {
      attachment_one: "{{count}} вложение",
      attachment_few: "{{count}} вложения",
      attachment_many: "{{count}} вложений",
      attachment_other: "{{count}} вложения",
      secureNote: "Защищённая заметка",
      copyUsername: "Скопировать логин",
      hidePassword: "Скрыть пароль",
      revealPassword: "Показать пароль",
      copyPassword: "Скопировать пароль",
      openWebsite: "Открыть сайт",
      removeFavorite: "Убрать из избранного",
      markFavorite: "Добавить в избранное",
      passwordBackedUp: "Есть в резервной копии",
      passwordNotBackedUp: "Нет в резервной копии",
      updateRecommended: "Этот пароль лучше заменить.",
      looksGood: "Пароль выглядит надёжным.",
      twoFactor: "2FA",
    },
  },
  entry: {
    draft: {
      savedLocally:
        "Черновик сохраняется в зашифрованном виде в этой вкладке и восстановится после входа. Закрытие вкладки удалит его.",
      failed: "Не удалось сохранить черновик. Не закрывайте страницу, пока не сохраните запись.",
      unavailable:
        "Не удалось подготовить или восстановить защищённый черновик. Повторите попытку. Повреждённый черновик можно удалить, чтобы создать новую запись.",
      discard: "Удалить черновик",
    },
    title: {
      editNote: "Изменить защищённую заметку",
      editPassword: "Изменить пароль",
      addNote: "Добавить защищённую заметку",
      addPassword: "Добавить пароль",
    },
    kind: {
      login: "Логин и пароль",
      note: "Защищённая заметка",
    },
    labels: {
      label: "Название поля",
      value: "Значение",
      note: "Заметка",
      usernameOptional: "Логин или почта (необязательно)",
      websiteOptional: "Сайт (необязательно)",
      folderOptional: "Папка (необязательно)",
      twoFactor: "Двухфакторная защита",
      twoFactorSecret: "Секретный ключ 2FA (необязательно)",
      customFields: "Дополнительные поля",
      notes: "Примечания",
      attachments: "Вложения",
      passwordHistory: "История паролей",
    },
    placeholders: {
      customLabel: "PIN",
      note: "Текст, который нужно сохранить в зашифрованном виде",
      username: "john@example.com",
      website: "https://github.com",
      folder: "Работа, личное",
      tags: "Метка + Enter",
      description: "Личный аккаунт, рабочая почта…",
      noteName: "Коды восстановления, Wi-Fi, паспорт",
      passwordName: "GitHub, Gmail, Netflix",
    },
    help: {
      nameCannotChange: "Название нельзя изменить после создания",
      twoFactor: "Вставьте ключ Base32 или ссылку otpauth:// — код появится здесь.",
      twoFactorTooltip:
        "Это секретный ключ для одноразовых кодов 2FA. Скопируйте его со страницы настройки сайта в формате Base32 или как ссылку otpauth://. CipherMoth будет показывать актуальный код прямо в записи. Оставьте поле пустым, если получаете коды только в приложении на телефоне.",
    },
    actions: {
      valueHidden: "Значение скрыто. Нажмите, чтобы показывать его при просмотре записи",
      hideValue: "Скрывать значение при просмотре записи",
      removeField: "Удалить поле",
      closeGenerator: "Закрыть генератор",
      generatePassword: "Сгенерировать пароль",
      addField: "Добавить поле",
    },
    validation: {
      nameRequired: "Укажите название.",
      noteRequired: "Введите текст заметки.",
      passwordRequired: "Введите пароль.",
    },
  },
  passwordField: {
    hide: "Скрыть",
    show: "Показать",
  },
  generator: {
    length: "Длина",
    regenerate: "Сгенерировать заново",
  },
  strength: {
    veryWeak: "Очень слабый",
    weak: "Слабый",
    fair: "Средний",
    strong: "Надёжный",
    veryStrong: "Очень надёжный",
    tooShort: "Слишком короткий",
    recommendation: "лучше увеличить длину или добавить разные символы",
  },
  totp: {
    invalid: "неверный секрет 2FA",
    copy: "Скопировать код 2FA",
  },
  attachments: {
    empty: "Вложений пока нет. Каждый файл шифруется ключом хранилища.",
    tooLarge: "Файл «{{filename}}» превышает лимит 5\u00a0МБ.",
    attached: "Файл «{{filename}}» прикреплён.",
    removed: "Файл «{{filename}}» удалён.",
    removeFile: "Удалить файл",
    attachFile: "Прикрепить файл",
    limits: "Не более 5\u00a0МБ на файл и 25\u00a0МБ на запись.",
    removeTitle: "Удалить вложение?",
    removeMessage: "Удалить файл «{{filename}}» из записи навсегда? Отменить это действие нельзя.",
  },
  backup: {
    title: "Создать резервную копию",
    description:
      "CipherMoth сохранит доступные вам записи в зашифрованном файле .cmbackup, защищённом текущим паролем учётной записи.",
    passwordRequired: "Введите пароль учётной записи.",
  },
  importDialog: {
    title: "Импорт паролей",
    completeTitle: "Импорт завершён",
    backupMode: "Резервная копия CipherMoth",
    csvMode: "CSV из другого приложения",
    csvDescription:
      "Выберите CSV, экспортированный из Chrome, Bitwarden, KeePass, Proton Pass или другого менеджера паролей. CipherMoth сам распознает столбцы.",
    backupDescription: "Выберите файл .cmbackup CipherMoth и введите пароль резервной копии.",
    chooseCsv: "Выбрать CSV-файл (.csv)",
    chooseBackup: "Выбрать резервную копию (.cmbackup)",
    selectCsv: "Сначала выберите CSV-файл.",
    selectBackup: "Сначала выберите файл резервной копии.",
    existingLabel: "Если запись уже существует",
    keepExisting: "Оставить существующую запись",
    overwrite: "Заменить данными из файла",
    noPasswords: "В этом файле нет записей.",
    imported_one: "Добавлена <strong>{{count}}</strong> запись.",
    imported_few: "Добавлено <strong>{{count}}</strong> записи.",
    imported_many: "Добавлено <strong>{{count}}</strong> записей.",
    imported_other: "Добавлено <strong>{{count}}</strong> записи.",
    overwritten_one: "Заменена <strong>{{count}}</strong> запись.",
    overwritten_few: "Заменено <strong>{{count}}</strong> записи.",
    overwritten_many: "Заменено <strong>{{count}}</strong> записей.",
    overwritten_other: "Заменено <strong>{{count}}</strong> записи.",
    skipped_one: "Пропущена <strong>{{count}}</strong> существующая запись.",
    skipped_few: "Пропущено <strong>{{count}}</strong> существующие записи.",
    skipped_many: "Пропущено <strong>{{count}}</strong> существующих записей.",
    skipped_other: "Пропущено <strong>{{count}}</strong> существующей записи.",
  },
  health: {
    title: "Состояние хранилища",
    healthy: "Надёжно",
    needsAttention: "Требует внимания",
    atRisk: "Есть риск",
    weak: "Слабые пароли",
    reused: "Повторяющиеся",
    old: "Давно не менялись",
    localOnly: "Проверка проходит на этом устройстве. Данные никуда не уходят.",
    allClear: "Слабых, повторяющихся или давно не менявшихся паролей не найдено.",
    weakHint: "Короткие или простые пароли стоит заменить более надёжными.",
    reusedHint: "Один пароль используется в нескольких записях.",
    oldHint: "Пароли, которые не менялись больше года.",
  },
  settings: {
    title: "Настройки",
    saved: "Настройки сохранены.",
    warningValidation: "Время предупреждения должно быть меньше времени до выхода.",
    fields: {
      inactivity: "Время до выхода",
      inactivityHelp: "Сколько ждать бездействия перед автоматическим выходом.",
      warning: "Предупреждение перед выходом",
      warningHelp: "За сколько времени до автоматического выхода показать предупреждение.",
      hidden: "Время до выхода в фоне",
      hiddenHelp:
        "Сколько ждать после перехода на другую вкладку или сворачивания браузера перед выходом.",
      debounce: "Интервал учёта активности",
      debounceHelp:
        "Как часто учитывать действия пользователя. Чем больше значение, тем реже сбрасывается таймер бездействия.",
      clipboard: "Время до очистки буфера",
      clipboardHelp: "Через сколько секунд после копирования удалить пароль из буфера обмена.",
      updates: "Проверять обновления",
      updatesHelp:
        "CipherMoth будет проверять новые версии через GitHub. Содержимое хранилища при этом никуда не отправляется. Отключите, если не хотите обращаться к GitHub.",
    },
  },
  updateDialog: {
    title: "Мотылёк готов обновиться",
    releaseNotes: "Что изменилось на GitHub",
    automaticDescription:
      "CipherMoth проверит подписи образов, сделает резервную копию базы и перезапустится. Если обновление не удастся, CipherMoth вернётся к предыдущей версии. Пароль учётной записи не нужен: хранилище останется зашифрованным.",
    manualDescription:
      "Автоматическое обновление здесь отключено. Выполните команду в папке CipherMoth:",
    updateNow: "Обновить сейчас",
    complete: "Обновление установлено. Перезагружаем CipherMoth…",
    background: "Обновление ещё идёт. Перезагрузите страницу через минуту.",
    states: {
      requested: "Готовим обновление…",
      verifying: "Проверяем подписи образов…",
      applying: "Устанавливаем обновление и перезапускаем CipherMoth…",
      success: "Обновление установлено. Перезагружаем CipherMoth…",
      failed: "Не удалось обновить CipherMoth. Хранилище не пострадало.",
      rolledBack: "Обновление не удалось, поэтому CipherMoth вернулся к предыдущей версии.",
    },
  },
  trashDialog: {
    empty:
      "Корзина пуста. Здесь будут лежать удалённые секреты, пока вы их не восстановите или не сотрёте навсегда.",
    deleted: "Удалено",
    restore: "Восстановить",
    deleteForever: "Удалить навсегда",
    deleteForeverTitle: "Удалить навсегда?",
    deleteForeverMessage:
      "Удалить <strong>{{name}}</strong> навсегда? Вернуть запись уже не получится.",
    deleteAll: "Удалить всё",
    deleteAllTitle: "Очистить корзину?",
    deleteAllMessage:
      "Будут навсегда удалены все ваши записи в корзине: {{count}}. Отменить это действие нельзя.",
    deletedAll_one: "Навсегда удалена {{count}} запись.",
    deletedAll_few: "Навсегда удалены {{count}} записи.",
    deletedAll_many: "Навсегда удалено {{count}} записей.",
    deletedAll_other: "Навсегда удалено {{count}} записи.",
  },
  autoLogout: {
    countdown: "До выхода из-за бездействия: {{seconds}} с",
    loggedOut: "CipherMoth закрыл хранилище из-за бездействия.",
  },
  clipboard: {
    copied: "Скопировано. Буфер очистится через {{duration}}.",
  },
  sharing: {
    addAccess: "Добавить доступ",
    currentAccess: "Текущий доступ",
    noAvailableTargets: "Нет других доступных пользователей.",
    title: "Открыть доступ к {{name}}",
    manage: "Настроить доступ",
    manageOptional: "Настроить доступ (необязательно)",
    access: "Владелец / доступ",
    user: "Пользователь",
    selectUser: "Выберите",
    permission: "Доступ",
    read: "Чтение",
    write: "Изменение",
    owner: "Владелец",
    empty: "Доступ к этой записи никому не открыт.",
    revoke: "Отозвать",
    savedWithEntry: "Изменения доступа применятся после сохранения записи.",
  },
  users: {
    title: "Пользователи",
    subtitle: "Управляйте учётными записями, ролями, состоянием доступа и активными сеансами.",
    backToVault: "К хранилищу",
    columns: {
      account: "Учётная запись",
      role: "Роль",
      status: "Состояние",
      actions: "Действия",
    },
    create: "Создать пользователя",
    createDescription:
      "Обычный пользователь видит свои и явно доступные ему записи в зашифрованном хранилище. Служебная учётная запись получает отдельный MCP-токен и только явно выданные доступы.",
    temporaryPassword: "Временный пароль",
    serviceToken: "Bearer-токен MCP",
    serviceTokenOnce: "Скопируйте токен сейчас — повторно он не показывается.",
    copyToken: "Скопировать токен",
    role: "Роль",
    active: "Активен",
    inactive: "Отключён",
    passwordChangePending: "Напоминание о смене пароля",
    revokeSessions: "Завершить сеансы",
    requirePasswordChange: "Напомнить о смене пароля",
    confirm: {
      sessions: {
        title: "Завершить все сеансы?",
        message: "Пользователь {{username}} должен будет войти заново на всех устройствах.",
      },
      password: {
        title: "Напоминать о смене пароля?",
        message:
          "Пользователь {{username}} будет видеть напоминание, пока не сменит текущий пароль.",
      },
      delete: {
        title: "Удалить пользователя?",
        message:
          "Пользователь {{username}} и выданные ему доступы будут удалены. Если он владеет записями или служебными агентами, удаление будет запрещено.",
      },
    },
    messages: {
      created: "Пользователь создан.",
      sessions: "Все сеансы пользователя завершены.",
      password: "Напоминание о смене пароля включено.",
      delete: "Пользователь удалён.",
    },
    roles: { admin: "Администратор", member: "Участник", service: "Служебный" },
  },
  errors: {
    invalidMasterPassword: "Неверный пароль.",
    tooManyAttempts: "Слишком много попыток. Попробуйте снова через час.",
    generic: "Произошёл сбой. Попробуйте ещё раз.",
    saveSettings: "Не удалось сохранить настройки.",
    loadPasswords: "Не удалось загрузить содержимое хранилища.",
    createPassword: "Не удалось сохранить запись.",
    updatePassword: "Не удалось сохранить изменения.",
    deletePassword: "Не удалось удалить запись.",
    loadTrash: "Не удалось загрузить корзину.",
    restorePassword: "Не удалось восстановить запись.",
    updateFavorite: "Не удалось изменить отметку «Избранное».",
    loadAttachments: "Не удалось загрузить вложения.",
    uploadAttachment: "Не удалось прикрепить файл.",
    downloadAttachment: "Не удалось скачать файл.",
    deleteAttachment: "Не удалось удалить вложение.",
    importFailed: "Импорт не удался. Проверьте файл и попробуйте ещё раз.",
    backupFailed: "Не удалось создать резервную копию. Попробуйте ещё раз.",
    changePassword: "Не удалось сменить пароль.",
    loadUsers: "Не удалось загрузить пользователей.",
    createUser: "Не удалось создать пользователя.",
    updateUser: "Не удалось обновить пользователя.",
    revokeUserSessions: "Не удалось завершить сеансы пользователя.",
    requirePasswordChange: "Не удалось включить напоминание о смене пароля.",
    deleteUser: "Не удалось удалить пользователя.",
    loadShareTargets: "Не удалось загрузить список пользователей.",
    loadShares: "Не удалось загрузить доступы.",
    saveShare: "Не удалось сохранить доступ.",
    revokeShare: "Не удалось отозвать доступ.",
    startUpdate: "Не удалось начать обновление. Попробуйте ещё раз.",
  },
};

Object.assign(ru.common.actions, { dismiss: "Скрыть", retry: "Повторить" });
Object.assign(ru.auth, {
  administratorUsername: "Имя администратора",
  sessionEnded: "Хранилище заблокировано. Разблокируйте его, чтобы продолжить.",
  confirmNewPassword: "Подтвердите новый пароль",
  changeTemporaryPassword: "Смените временный пароль",
  passwordChangeRequired:
    "Администратор запросил смену пароля, прежде чем вы продолжите работу с хранилищем.",
  passwordChangeNoSession: "Пароль изменён, но сервер не вернул сессию.",
});
Object.assign(ru.auth.validation, {
  enterAdministratorUsername: "Введите имя администратора.",
  passwordChangeWeak: "Используйте не менее 12 символов разных типов.",
});
Object.assign(ru.vault.messages, {
  backupRequested:
    "Запрошено скачивание. Убедитесь, что файл резервной копии сохранён, и храните его в безопасном месте.",
});
Object.assign(ru.vault, {
  damage: {
    message_one:
      "{{count}} элемент в файле хранилища не удаётся прочитать (он повреждён или изменён), поэтому он не показан. Резервное копирование будет недоступно, пока вы не восстановите снимок или не удалите его.",
    message_few:
      "{{count}} элемента в файле хранилища не удаётся прочитать (они повреждены или изменены), поэтому они не показаны. Резервное копирование будет недоступно, пока вы не восстановите снимок или не удалите их.",
    message_many:
      "{{count}} элементов в файле хранилища не удаётся прочитать (они повреждены или изменены), поэтому они не показаны. Резервное копирование будет недоступно, пока вы не восстановите снимок или не удалите их.",
    message_other:
      "{{count}} элемента в файле хранилища не удаётся прочитать (они повреждены или изменены), поэтому они не показаны. Резервное копирование будет недоступно, пока вы не восстановите снимок или не удалите их.",
    removed: "Повреждённые строки удалены.",
    removeTitle: "Удалить повреждённые элементы",
    removeMessage_one:
      "Удалить безвозвратно {{count}} нечитаемый элемент? Вместе с записью будут удалены её вложения. Если у вас есть снимок до повреждения, восстановите его, чтобы сохранить данные.",
    removeMessage_few:
      "Удалить безвозвратно {{count}} нечитаемых элемента? Вместе с записями будут удалены их вложения. Если у вас есть снимок до повреждения, восстановите его, чтобы сохранить данные.",
    removeMessage_many:
      "Удалить безвозвратно {{count}} нечитаемых элементов? Вместе с записями будут удалены их вложения. Если у вас есть снимок до повреждения, восстановите его, чтобы сохранить данные.",
    removeMessage_other:
      "Удалить безвозвратно {{count}} нечитаемых элемента? Вместе с записями будут удалены их вложения. Если у вас есть снимок до повреждения, восстановите его, чтобы сохранить данные.",
  },
});
Object.assign(ru.backup, {
  descriptionFull:
    "Переносимая зашифрованная копия доступных вам записей, включая корзину, историю паролей, вложения и настройки, в одном файле .cmbackup, защищённом текущим паролем учётной записи.",
  restoreAdvice:
    "Восстановите её через «Импорт» в это или новое хранилище. Храните файл безопасно: любой, кто знает пароль резервной копии, сможет открыть её даже после смены пароля учётной записи.",
  desktopAdvice:
    "Выберите новое имя файла в окне сохранения. Существующие файлы не перезаписываются.",
  webAdvice: "Проверьте, что браузер действительно сохранил файл.",
});
Object.assign(ru.importDialog, {
  enterBackupPassword: "Введите пароль резервной копии.",
  filePickerError: "Не удалось открыть выбор файла.",
  backupPassword: "Пароль резервной копии",
  backupPasswordHelp: "Пароль учётной записи, использованный при создании копии.",
  alsoRestored: "Также восстановлено: {{items}}.",
  andMore_one: "и ещё {{count}}",
  andMore_few: "и ещё {{count}}",
  andMore_many: "и ещё {{count}}",
  andMore_other: "и ещё {{count}}",
  renamed_one: "элемент переименован:",
  renamed_few: "элемента переименовано:",
  renamed_many: "элементов переименовано:",
  renamed_other: "элемента переименовано:",
  ignored_one: "запись не импортирована:",
  ignored_few: "записи не импортированы:",
  ignored_many: "записей не импортировано:",
  ignored_other: "записи не импортированы:",
  restoredExtras: {
    trash_one: "{{count}} запись в корзине",
    trash_few: "{{count}} записи в корзине",
    trash_many: "{{count}} записей в корзине",
    trash_other: "{{count}} записи в корзине",
    attachments_one: "{{count}} вложение",
    attachments_few: "{{count}} вложения",
    attachments_many: "{{count}} вложений",
    attachments_other: "{{count}} вложения",
    grants_one: "{{count}} право доступа",
    grants_few: "{{count}} права доступа",
    grants_many: "{{count}} прав доступа",
    grants_other: "{{count}} права доступа",
    settings: "ваши настройки",
  },
});
Object.assign(ru.sharing, {
  ownerOnly: "Доступ к этой записи есть только у владельца.",
  grantAccess: "Выдать доступ",
  selectTarget: "Выберите аккаунт",
  readWrite: "Чтение и запись",
  grant: "Выдать",
  readOnlyAccess: "Только чтение",
});
Object.assign(ru.users, {
  title: "Пользователи и сервисный доступ",
  subtitle: "Регистрация закрыта. Здесь администраторы создают аккаунты и сервисные токены.",
  createAccount: "Создать аккаунт",
  passwordChangeRequested: "Требуется смена пароля",
  serviceAccount: "Неитерактивный MCP-аккаунт",
  interactiveAccount: "Интерактивный аккаунт",
  rotateToken: "Перевыпустить токен",
  resetPassword: "Сбросить пароль",
  resetPasswordFor: "Сбросить пароль для {{username}}",
  resetPasswordDescription:
    "Текущие сессии будут отозваны. Пользователю будет предложено сменить этот временный пароль.",
  deleteConfirm: "Удалить {{username}}?",
});
Object.assign(ru.users.messages, {
  passwordReset: "Временный пароль установлен, активные сессии отозваны.",
  tokenRotated: "Сервисный токен перевыпущен. Предыдущий токен больше не работает.",
  roleUpdated: "Роль обновлена.",
  statusUpdated: "Статус обновлён.",
  sessionsRevoked: "Сессии отозваны.",
  deleted: "Пользователь удалён.",
});
Object.assign(ru.errors, {
  invalidCredentials: "Неверное имя пользователя или пароль.",
  authentication: "Не удалось войти.",
  resetPassword: "Не удалось сбросить пароль.",
  rotateServiceToken: "Не удалось перевыпустить сервисный токен.",
  invalidEntryName:
    "Браузер не может обратиться к записи с именем «{{name}}». Переименуйте запись и повторите попытку.",
  damageCheck:
    "Проверка повреждений хранилища не удалась. Некоторые записи или вложения могут отсутствовать в этом списке. Повторите проверку, прежде чем полагаться на список.",
  removeDamaged: "Не удалось удалить повреждённые строки.",
});
Object.assign(ru.updateDialog, {
  manualBackupDescription:
    "Обновите CipherMoth из терминала в его папке. Первая команда сохранит исходный снимок зашифрованного файла хранилища, поэтому вы всегда сможете вернуться назад. Для него нужны действующие на момент снимка данные учётной записи; для переносимой копии используйте резервное копирование.",
});
ru.desktopUpdate = {
  installDescription:
    "Скачайте обновление с GitHub, проверьте его подпись, затем заблокируйте хранилище и перезапустите CipherMoth. Локальное хранилище останется на месте.",
  debianDescription:
    "Эта установка Debian обновляется через менеджер пакетов. Скачайте новый .deb с GitHub и установите его поверх текущей версии. Локальное хранилище останется на месте.",
  installing: "Установка…",
  downloading: "Скачивание и проверка…",
  releaseNotes: "Примечания к выпуску и загрузки",
  cancelDownload: "Отменить скачивание",
  downloadInstall: "Скачать и установить",
};
ru.desktopGate = {
  opening: "ОТКРЫВАЕМ CIPHERMOTH",
  openFailedTitle: "Не удалось открыть хранилище",
  openFailedDescription:
    "Закройте другие окна CipherMoth и проверьте, что приложение установлено полностью. Ваше хранилище не было заменено.",
};

export default ru;

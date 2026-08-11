import assert from "node:assert/strict";
import test from "node:test";

import i18n, {
  LANGUAGE_STORAGE_KEY,
  SUPPORTED_LANGUAGES,
  translationResources,
} from "../src/i18n/index.js";

const flattenKeys = (value, prefix = "") =>
  Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof child === "object" && child !== null ? flattenKeys(child, path) : [path];
  });

test("English and Russian catalogs expose the same non-empty keys", () => {
  const english = translationResources.en.translation;
  const russian = translationResources.ru.translation;

  assert.deepEqual(flattenKeys(russian).sort(), flattenKeys(english).sort());
  for (const catalog of [english, russian]) {
    for (const key of flattenKeys(catalog)) {
      const value = key.split(".").reduce((current, part) => current[part], catalog);
      assert.equal(typeof value, "string");
      assert.notEqual(value.trim(), "");
    }
  }
});

test("Russian catalog uses all required cardinal plural forms", async () => {
  await i18n.changeLanguage("ru");

  assert.equal(i18n.t("vault.subtitle.secretCount", { count: 1 }), "1 секрет в темноте");
  assert.equal(i18n.t("vault.subtitle.secretCount", { count: 2 }), "2 секрета в темноте");
  assert.equal(i18n.t("vault.subtitle.secretCount", { count: 5 }), "5 секретов в темноте");
});

test("Unsupported languages resolve to the English fallback", async () => {
  await i18n.changeLanguage("de");

  assert.equal(i18n.resolvedLanguage, "en");
  assert.equal(i18n.t("common.actions.cancel"), "Cancel");
});

test("Password strength exposes translation keys instead of fixed English labels", async () => {
  const { getMasterPasswordStrength, getPasswordStrength } =
    await import("../src/lib/passwordStrength.js");

  assert.equal(getPasswordStrength("abc").labelKey, "strength.veryWeak");
  assert.equal(getPasswordStrength("Abcd1234!Abcd1234!").labelKey, "strength.veryStrong");
  assert.equal(getMasterPasswordStrength("short").labelKey, "strength.tooShort");
  assert.equal(getMasterPasswordStrength("LongAndStrong123!").labelKey, "strength.strong");
});

test("Changing language updates the document language and persistent preference", async () => {
  const attributes = new Map();
  const stored = new Map();
  globalThis.document = {
    documentElement: {
      setAttribute: (name, value) => attributes.set(name, value),
    },
  };
  globalThis.localStorage = {
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => stored.set(key, value),
  };

  await i18n.changeLanguage("ru");

  assert.deepEqual(SUPPORTED_LANGUAGES, ["en", "ru"]);
  assert.equal(attributes.get("lang"), "ru");
  assert.equal(stored.get(LANGUAGE_STORAGE_KEY), "ru");

  delete globalThis.document;
  delete globalThis.localStorage;
});

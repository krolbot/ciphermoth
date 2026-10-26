import { gcm } from "@noble/ciphers/aes.js";

const PREFIX = "ciphermoth-entry-draft:v1:";
const MAX_DRAFT_BYTES = 1024 * 1024;
const NONCE_BYTES = 12;
const encode = (bytes) => btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(""));
const decode = (text) => Uint8Array.from(atob(text), (char) => char.charCodeAt(0));

export const createEntryDraftStore = ({ user_id, key: encodedKey }) => {
  if (!Number.isSafeInteger(user_id) || user_id <= 0) throw new Error("Invalid draft owner");
  const key = decode(encodedKey);
  if (key.length !== 32) throw new Error("Invalid draft key");
  const storageKey = `${PREFIX}${user_id}`;
  const additionalData = new TextEncoder().encode(storageKey);

  return {
    read() {
      const stored = sessionStorage.getItem(storageKey);
      if (!stored) return null;
      if (stored.length > MAX_DRAFT_BYTES * 2) throw new Error("Draft is too large");
      const sealed = decode(stored);
      const plaintext = gcm(key, sealed.slice(0, NONCE_BYTES), additionalData).decrypt(
        sealed.slice(NONCE_BYTES)
      );
      try {
        return JSON.parse(new TextDecoder().decode(plaintext));
      } finally {
        plaintext.fill(0);
      }
    },
    write(form) {
      const plaintext = new TextEncoder().encode(JSON.stringify(form));
      try {
        if (plaintext.length > MAX_DRAFT_BYTES) throw new Error("Draft is too large");
        // Native lock can destroy the renderer without a JS callback. Persist in
        // this input event, not in an async encryption or a later React effect.
        const iv = crypto.getRandomValues(new Uint8Array(NONCE_BYTES));
        const ciphertext = gcm(key, iv, additionalData).encrypt(plaintext);
        const sealed = new Uint8Array(NONCE_BYTES + ciphertext.length);
        sealed.set(iv);
        sealed.set(ciphertext, NONCE_BYTES);
        sessionStorage.setItem(storageKey, encode(sealed));
      } finally {
        plaintext.fill(0);
      }
    },
    clear() {
      sessionStorage.removeItem(storageKey);
    },
  };
};

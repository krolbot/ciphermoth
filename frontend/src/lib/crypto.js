import { argon2id } from "hash-wasm";

const encoder = new TextEncoder();
const FERNET_VERSION = 0x80;
const WRAP_INFO = "ciphermoth-entry-key-v1";

const bytesToBase64 = (bytes) => {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
};

export const toBase64Url = (bytes, padded = false) => {
  const value = bytesToBase64(bytes).replaceAll("+", "-").replaceAll("/", "_");
  return padded ? value : value.replace(/=+$/, "");
};

export const fromBase64Url = (value) => {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const binary = atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
};

const concat = (...parts) => {
  const result = new Uint8Array(parts.reduce((size, part) => size + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
};

export const deriveVaultKey = async (password, salt) => {
  const raw = await argon2id({
    password,
    salt: fromBase64Url(salt),
    parallelism: 4,
    iterations: 3,
    memorySize: 65536,
    hashLength: 32,
    outputType: "binary",
  });
  return toBase64Url(raw, true);
};

export const encryptBytes = async (key, plaintext) => {
  const rawKey = fromBase64Url(key);
  if (rawKey.length !== 32) throw new Error("Invalid Fernet key.");

  const signingKey = await crypto.subtle.importKey(
    "raw",
    rawKey.slice(0, 16),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const encryptionKey = await crypto.subtle.importKey(
    "raw",
    rawKey.slice(16),
    "AES-CBC",
    false,
    ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(16));
  const timestamp = new Uint8Array(8);
  new DataView(timestamp.buffer).setBigUint64(0, BigInt(Math.floor(Date.now() / 1000)));
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-CBC", iv }, encryptionKey, plaintext)
  );
  const signed = concat(Uint8Array.of(FERNET_VERSION), timestamp, iv, ciphertext);
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", signingKey, signed));
  return toBase64Url(concat(signed, signature), true);
};

export const decryptBytes = async (key, token) => {
  const rawKey = fromBase64Url(key);
  const rawToken = fromBase64Url(token);
  if (rawKey.length !== 32 || rawToken.length < 73 || rawToken[0] !== FERNET_VERSION) {
    throw new Error("Invalid encrypted value.");
  }

  const signed = rawToken.slice(0, -32);
  const signature = rawToken.slice(-32);
  const signingKey = await crypto.subtle.importKey(
    "raw",
    rawKey.slice(0, 16),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  if (!(await crypto.subtle.verify("HMAC", signingKey, signature, signed))) {
    throw new Error("Invalid encrypted value.");
  }

  const encryptionKey = await crypto.subtle.importKey(
    "raw",
    rawKey.slice(16),
    "AES-CBC",
    false,
    ["decrypt"]
  );
  try {
    return new Uint8Array(
      await crypto.subtle.decrypt(
        { name: "AES-CBC", iv: rawToken.slice(9, 25) },
        encryptionKey,
        rawToken.slice(25, -32)
      )
    );
  } catch {
    throw new Error("Invalid encrypted value.");
  }
};

const privateKeyPkcs8 = (key) => {
  if (key.length !== 32) return key;
  return concat(
    Uint8Array.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x6e, 0x04, 0x22, 0x04, 0x20]),
    key
  );
};

const wrapKey = async (sharedSecret, context, usages) =>
  crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new Uint8Array(),
      info: encoder.encode(`${WRAP_INFO}:${context}`),
    },
    await crypto.subtle.importKey("raw", sharedSecret, "HKDF", false, ["deriveKey"]),
    { name: "AES-GCM", length: 256 },
    false,
    usages
  );

export const generateEntryKey = () =>
  toBase64Url(crypto.getRandomValues(new Uint8Array(32)), true);

export const wrapEntryKey = async (publicKey, entryKey, context = "") => {
  const recipient = await crypto.subtle.importKey(
    "raw",
    fromBase64Url(publicKey),
    "X25519",
    false,
    []
  );
  const ephemeral = await crypto.subtle.generateKey("X25519", true, ["deriveBits"]);
  const sharedSecret = await crypto.subtle.deriveBits(
    { name: "X25519", public: recipient },
    ephemeral.privateKey,
    256
  );
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const authenticatedContext = encoder.encode(`${WRAP_INFO}:${context}`);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv: nonce,
        additionalData: authenticatedContext,
        tagLength: 128,
      },
      await wrapKey(sharedSecret, context, ["encrypt"]),
      encoder.encode(entryKey)
    )
  );
  const ephemeralPublic = new Uint8Array(
    await crypto.subtle.exportKey("raw", ephemeral.publicKey)
  );
  return toBase64Url(concat(Uint8Array.of(1), ephemeralPublic, nonce, ciphertext));
};

export const generateUserKeyMaterial = async (password, salt = null) => {
  const saltBytes = salt ? fromBase64Url(salt) : crypto.getRandomValues(new Uint8Array(16));
  const encodedSalt = toBase64Url(saltBytes);
  const vaultKey = await deriveVaultKey(password, encodedSalt);
  const pair = await crypto.subtle.generateKey("X25519", true, ["deriveBits"]);
  const publicKey = toBase64Url(
    new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey))
  );
  const privateKeyBytes = new Uint8Array(
    await crypto.subtle.exportKey("pkcs8", pair.privateKey)
  );
  const authPair = await crypto.subtle.generateKey("Ed25519", true, ["sign", "verify"]);
  const authPublicKey = toBase64Url(
    new Uint8Array(await crypto.subtle.exportKey("raw", authPair.publicKey))
  );
  const authPrivateKeyBytes = new Uint8Array(
    await crypto.subtle.exportKey("pkcs8", authPair.privateKey)
  );
  return {
    salt: encodedSalt,
    publicKey,
    encryptedPrivateKey: await encryptBytes(vaultKey, privateKeyBytes),
    authPublicKey,
    encryptedAuthPrivateKey: await encryptBytes(vaultKey, authPrivateKeyBytes),
    vaultKey,
    privateKey: toBase64Url(privateKeyBytes),
    authPrivateKey: toBase64Url(authPrivateKeyBytes),
  };
};

export const unlockUserKeyMaterial = async (password, session) => {
  const vaultKey = await deriveVaultKey(password, session.salt);
  const privateKey = toBase64Url(
    await decryptBytes(vaultKey, session.encrypted_private_key)
  );
  const authPrivateKey = toBase64Url(
    await decryptBytes(vaultKey, session.encrypted_auth_private_key)
  );
  return { vaultKey, privateKey, authPrivateKey };
};

export const enrollLegacyUserAuth = async (password, challenge) => {
  const vaultKey = await deriveVaultKey(password, challenge.salt);
  const privateKeyBytes = await decryptBytes(vaultKey, challenge.encrypted_private_key);
  const privateKey = await crypto.subtle.importKey(
    "pkcs8",
    privateKeyPkcs8(privateKeyBytes),
    "X25519",
    false,
    ["deriveBits"]
  );
  const serverPublicKey = await crypto.subtle.importKey(
    "raw",
    fromBase64Url(challenge.nonce),
    "X25519",
    false,
    []
  );
  const shared = await crypto.subtle.deriveBits(
    { name: "X25519", public: serverPublicKey },
    privateKey,
    256
  );
  const proofKey = await crypto.subtle.importKey(
    "raw",
    shared,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const authPair = await crypto.subtle.generateKey("Ed25519", true, ["sign", "verify"]);
  const authPrivateKeyBytes = new Uint8Array(
    await crypto.subtle.exportKey("pkcs8", authPair.privateKey)
  );
  return {
    vaultKey,
    privateKey: toBase64Url(privateKeyBytes),
    authPrivateKey: toBase64Url(authPrivateKeyBytes),
    authPublicKey: toBase64Url(
      new Uint8Array(await crypto.subtle.exportKey("raw", authPair.publicKey))
    ),
    encryptedAuthPrivateKey: await encryptBytes(vaultKey, authPrivateKeyBytes),
    proof: toBase64Url(
      new Uint8Array(
        await crypto.subtle.sign("HMAC", proofKey, encoder.encode(challenge.challenge))
      )
    ),
  };
};

export const rewrapPrivateKeys = async (password, privateKey, authPrivateKey) => {
  const salt = toBase64Url(crypto.getRandomValues(new Uint8Array(16)));
  const vaultKey = await deriveVaultKey(password, salt);
  return {
    salt,
    vaultKey,
    encryptedPrivateKey: await encryptBytes(vaultKey, fromBase64Url(privateKey)),
    encryptedAuthPrivateKey: await encryptBytes(
      vaultKey,
      fromBase64Url(authPrivateKey)
    ),
  };
};

const signAuthBytes = async (authPrivateKey, message) => {
  const key = await crypto.subtle.importKey(
    "pkcs8",
    fromBase64Url(authPrivateKey),
    "Ed25519",
    false,
    ["sign"]
  );
  return toBase64Url(
    new Uint8Array(await crypto.subtle.sign("Ed25519", key, message))
  );
};

export const signAuthChallenge = (authPrivateKey, challenge) =>
  signAuthBytes(authPrivateKey, fromBase64Url(challenge));

export const signPasswordChange = async (authPrivateKey, token, keyMaterial) => {
  const tokenHash = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(token))),
    (byte) => byte.toString(16).padStart(2, "0")
  ).join("");
  return signAuthBytes(
    authPrivateKey,
    encoder.encode(
      [
        "ciphermoth-rekey-v1",
        tokenHash,
        keyMaterial.salt,
        keyMaterial.encryptedPrivateKey,
        keyMaterial.encryptedAuthPrivateKey,
      ].join("\n")
    )
  );
};

export const encryptJson = (key, value) =>
  encryptBytes(key, encoder.encode(JSON.stringify(value)));

export const decryptJson = async (key, token) =>
  JSON.parse(new TextDecoder().decode(await decryptBytes(key, token)));

export const unwrapEntryKey = async (privateKey, wrappedKey, context = "") => {
  const wrapped = fromBase64Url(wrappedKey);
  if (wrapped.length < 62 || wrapped[0] !== 1) throw new Error("Invalid wrapped key.");

  try {
    const privateCryptoKey = await crypto.subtle.importKey(
      "pkcs8",
      privateKeyPkcs8(fromBase64Url(privateKey)),
      "X25519",
      false,
      ["deriveBits"]
    );
    const ephemeralPublic = await crypto.subtle.importKey(
      "raw",
      wrapped.slice(1, 33),
      "X25519",
      false,
      []
    );
    const sharedSecret = await crypto.subtle.deriveBits(
      { name: "X25519", public: ephemeralPublic },
      privateCryptoKey,
      256
    );
    const authenticatedContext = encoder.encode(`${WRAP_INFO}:${context}`);
    const entryKey = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: wrapped.slice(33, 45),
        additionalData: authenticatedContext,
        tagLength: 128,
      },
      await wrapKey(sharedSecret, context, ["decrypt"]),
      wrapped.slice(45)
    );
    return new TextDecoder().decode(entryKey);
  } catch {
    throw new Error("Invalid wrapped key.");
  }
};

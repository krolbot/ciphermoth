import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export const API_URL_PLACEHOLDER = "__CIPHERMOTH_API_URL__";
export const DEFAULT_API_URL = "http://localhost:8000/api";
export const DEFAULT_GITHUB_REPO = "mr-grj/ciphermoth";

const RELATIVE_PATH = /^\/(?!\/)[A-Za-z0-9._~\-/]*$/;
const GITHUB_REPO = /^[A-Za-z0-9-]+\/[A-Za-z0-9._-]+$/;
const UNSAFE = /[\s'";,<>\\`{}|^]/;

export class ConfigError extends Error {}

export const parseApiUrl = (value) => {
  const raw = (value ?? "").trim() || DEFAULT_API_URL;
  if (RELATIVE_PATH.test(raw)) {
    return { url: raw, source: null, warning: null };
  }
  if (UNSAFE.test(raw)) {
    throw new ConfigError(`VITE_API_URL contains characters a URL may not: ${raw}`);
  }
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new ConfigError(`VITE_API_URL is not a valid URL or absolute path: ${raw}`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new ConfigError(`VITE_API_URL must use http or https: ${raw}`);
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new ConfigError(`VITE_API_URL must not contain credentials, a query or a fragment: ${raw}`);
  }
  if (url.hostname.startsWith("[")) {
    return {
      url: raw,
      source: url.protocol,
      warning:
        "CSP cannot name an IPv6 address, so the UI may connect to any " +
        `${url.protocol.slice(0, -1)} host. Use a host name for VITE_API_URL to restrict it.`,
    };
  }
  return { url: raw, source: url.origin, warning: null };
};

export const parseGithubRepo = (value) => {
  const repo = (value ?? "").trim() || DEFAULT_GITHUB_REPO;
  if (!GITHUB_REPO.test(repo)) {
    throw new ConfigError(`CIPHERMOTH_GITHUB_REPO must look like owner/name: ${repo}`);
  }
  return repo;
};

export const connectSources = ({ apiSource, githubRepo }) =>
  [
    "'self'",
    apiSource,
    `https://api.github.com/repos/${githubRepo}/releases/latest`,
  ].filter(Boolean);

export const withConnectSrc = (policy, sources) => {
  const directives = policy
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .filter((part) => !/^connect-src(\s|$)/i.test(part));
  directives.push(`connect-src ${sources.join(" ")}`);
  return directives.join("; ");
};

export const renderServeConfig = (config, sources) => ({
  ...config,
  headers: config.headers.map((rule) => ({
    ...rule,
    headers: rule.headers.map((header) =>
      header.key.toLowerCase() === "content-security-policy"
        ? { ...header, value: withConnectSrc(header.value, sources) }
        : header
    ),
  })),
});

const scriptsIn = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return scriptsIn(path);
    return path.endsWith(".js") ? [path] : [];
  });

export const injectApiUrl = (distDir, apiUrl) => {
  for (const path of scriptsIn(distDir)) {
    const text = readFileSync(path, "utf8");
    if (text.includes(API_URL_PLACEHOLDER)) {
      writeFileSync(path, text.split(API_URL_PLACEHOLDER).join(apiUrl));
    }
  }
};

export const configure = ({ env, distDir, serveConfig, output, log }) => {
  const api = parseApiUrl(env.VITE_API_URL);
  const githubRepo = parseGithubRepo(env.CIPHERMOTH_GITHUB_REPO);
  if (api.warning) log(`Warning: ${api.warning}`);
  const sources = connectSources({ apiSource: api.source, githubRepo });
  injectApiUrl(distDir, api.url);
  const config = JSON.parse(readFileSync(serveConfig, "utf8"));
  writeFileSync(output, JSON.stringify(renderServeConfig(config, sources), null, 2));
  log(`API URL: ${api.url}`);
  log(`connect-src ${sources.join(" ")}`);
};

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const [distDir, serveConfig, output] = process.argv.slice(2);
  try {
    configure({ env: process.env, distDir, serveConfig, output, log: console.log });
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    console.error(`CipherMoth cannot start: ${error.message}`);
    process.exit(1);
  }
}

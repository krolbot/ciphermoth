import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  ConfigError,
  configure,
  connectSources,
  parseApiUrl,
  parseGithubRepo,
  withConnectSrc,
} from "./runtime-config.mjs";

const RELEASES = "https://api.github.com/repos/mr-grj/ciphermoth/releases/latest";
const SERVE_JSON = new URL("../../frontend/serve.json", import.meta.url);

test("absolute API URLs allow exactly their origin", () => {
  for (const [url, origin] of [
    ["http://localhost:8000/api", "http://localhost:8000"],
    ["https://vault.example.com/api", "https://vault.example.com"],
    ["https://vault.example.com:443/api/", "https://vault.example.com"],
    ["http://192.168.1.20:8000/api", "http://192.168.1.20:8000"],
    ["https://API.Example.COM:8443/ciphermoth/api", "https://api.example.com:8443"],
    ["http://vault_backend:8000/api", "http://vault_backend:8000"],
  ]) {
    assert.deepEqual(parseApiUrl(url), { url, source: origin, warning: null });
  }
});

test("a relative API path is served by the UI's own origin", () => {
  assert.deepEqual(parseApiUrl("/api"), { url: "/api", source: null, warning: null });
  assert.deepEqual(connectSources({ apiSource: null, githubRepo: "mr-grj/ciphermoth" }), [
    "'self'",
    RELEASES,
  ]);
});

test("an unset API URL keeps the documented default", () => {
  assert.equal(parseApiUrl(undefined).source, "http://localhost:8000");
  assert.equal(parseApiUrl("  ").source, "http://localhost:8000");
});

test("an IPv6 API host falls back to its scheme, with a warning", () => {
  const api = parseApiUrl("http://[::1]:8000/api");
  assert.equal(api.source, "http:");
  assert.match(api.warning, /IPv6/);
});

test("unsafe or unusable API URLs stop the container", () => {
  for (const url of [
    "javascript:alert(1)",
    "ftp://vault.example.com/api",
    "http://vault.example.com/api'; script-src *",
    "http://vault.example.com/api\"",
    "http://vault.example.com/api;connect-src *",
    "http://vault.example.com/a b",
    "http://user:pass@vault.example.com/api",
    "http://vault.example.com/api?x=1",
    "http://vault.example.com/api#x",
    "//vault.example.com/api",
    "api",
    "http://",
  ]) {
    assert.throws(() => parseApiUrl(url), ConfigError, url);
  }
});

test("the GitHub repository must be owner/name", () => {
  assert.equal(parseGithubRepo(undefined), "mr-grj/ciphermoth");
  assert.equal(parseGithubRepo("someone/fork.of-moth"), "someone/fork.of-moth");
  for (const repo of ["mr-grj", "a/b/c", "a/b releases", "*/*", "a/b;x"]) {
    assert.throws(() => parseGithubRepo(repo), ConfigError, repo);
  }
});

test("only connect-src is replaced and nothing else in the policy changes", () => {
  const policy = JSON.parse(readFileSync(SERVE_JSON, "utf8")).headers[0].headers.find(
    (header) => header.key === "Content-Security-Policy"
  ).value;
  assert.match(policy, /connect-src 'self';/);
  assert.doesNotMatch(policy, /connect-src \*/);
  const rendered = withConnectSrc(policy, ["'self'", "http://localhost:8000", RELEASES]);
  const directives = Object.fromEntries(
    rendered.split("; ").map((part) => [part.split(" ")[0], part])
  );
  assert.equal(directives["connect-src"], `connect-src 'self' http://localhost:8000 ${RELEASES}`);
  assert.equal(directives["script-src"], "script-src 'self'");
  assert.equal(directives["default-src"], "default-src 'self'");
  assert.equal(rendered.match(/connect-src/g).length, 1);
  assert.doesNotMatch(rendered, /\*/);
});

test("configure injects the API URL and writes the rendered serve.json", () => {
  const dir = mkdtempSync(join(tmpdir(), "ciphermoth-runtime-"));
  mkdirSync(join(dir, "dist", "assets"), { recursive: true });
  const bundle = join(dir, "dist", "assets", "index.js");
  writeFileSync(bundle, 'const a="__CIPHERMOTH_API_URL__";const b="__CIPHERMOTH_API_URL__";');
  const output = join(dir, "serve.json");
  const logs = [];

  configure({
    env: { VITE_API_URL: "https://vault.example.com/api" },
    distDir: join(dir, "dist"),
    serveConfig: SERVE_JSON,
    output,
    log: (line) => logs.push(line),
  });

  assert.equal(
    readFileSync(bundle, "utf8"),
    'const a="https://vault.example.com/api";const b="https://vault.example.com/api";'
  );
  const csp = JSON.parse(readFileSync(output, "utf8")).headers[0].headers.find(
    (header) => header.key === "Content-Security-Policy"
  ).value;
  assert.match(csp, /connect-src 'self' https:\/\/vault\.example\.com https:\/\/api\.github\.com/);
  assert.ok(logs.some((line) => line.startsWith("connect-src")));
});

test("configure refuses before touching the bundle", () => {
  const dir = mkdtempSync(join(tmpdir(), "ciphermoth-runtime-"));
  mkdirSync(join(dir, "dist"));
  const bundle = join(dir, "dist", "index.js");
  writeFileSync(bundle, 'const a="__CIPHERMOTH_API_URL__";');
  assert.throws(
    () =>
      configure({
        env: { VITE_API_URL: "http://x/api'; script-src *" },
        distDir: join(dir, "dist"),
        serveConfig: SERVE_JSON,
        output: join(dir, "serve.json"),
        log: () => {},
      }),
    ConfigError
  );
  assert.equal(readFileSync(bundle, "utf8"), 'const a="__CIPHERMOTH_API_URL__";');
});

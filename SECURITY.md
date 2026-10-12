# Security

This is a password manager. Security isn't a feature here - it's the whole point. If you find something wrong, please don't open a public issue about it. Tell me privately first.

## Found something? Tell me here

Open a [GitHub Security Advisory](https://github.com/mr-grj/ciphermoth/security/advisories/new) - it's private by default, only visible to you and me. Describe what you found, how to reproduce it, and what you think the impact is. That's all I need to get started.

I'll acknowledge it within a few days. If it's real, I'll fix it and credit you in the release notes - unless you'd rather stay anonymous, which is also fine.

## What I actually care about

Things I want to know about:

- Anything that lets someone read passwords they shouldn't be able to
- Authentication or session bypass
- Encryption weaknesses or key leakage
- SQL injection, command injection, that whole family
- Anything that could expose the vault to an unauthorized party

Things that are out of scope:

- Attacks that require physical access to the machine running the instance - if someone has that, it's already over
- Vulnerabilities in third-party dependencies that don't directly affect ciphermoth - please report those upstream
- Self-XSS or anything only exploitable by someone already authenticated with their own master password

## What the server knows

So you can judge reports (and your own deployment) against what CipherMoth actually does:

- The master password is only ever stored as a bcrypt hash. The vault key is derived from it with Argon2id and is never written to disk or logs.
- When you unlock, the server keeps the vault key in its own memory and gives your browser (or the CLI) a random session token instead. Only a SHA-256 digest of the token is kept. Every request checks the session, then checks its key against an encrypted check value in the vault. Sessions end after the configured inactivity timeout (plus at most 5 seconds for request latency), after 12 hours at most, on logout, when the master password changes, and when the server restarts; nothing about them is written to disk or logs. The inactivity timeout is a vault setting, so anyone holding a session can raise it (to 60 minutes at most); the 12-hour limit cannot be changed. While you're using the vault, the server process sees your secrets in plaintext, and Python cannot reliably erase a key from memory after a session ends.
- The modern web UI and CLI never receive the vault key, but the deprecated `/check` route still returns it to any client that sends the correct master password, and accepts it back in the `x-ciphermoth-key-derivation` header, so that v1.4.x CLIs and open browser tabs keep working until v1.6.0, when both are removed. `CIPHERMOTH_LEGACY_KEY_AUTH=false` turns them off now (installs from before v1.5.0 must also add that variable to their own compose file; `/api/meta` stops listing `legacy-key-auth` once it is off).
- Passwords, notes, URLs, 2FA secrets, tags, folders, custom fields, password history and attachments are encrypted in the database. Entry **names, usernames and descriptions are not** (nor the entry type, favorite flag, timestamps and attachment sizes), so a copy of the database reveals which entries you have and their usernames.
- Backup ZIPs are AES-256 encrypted with your master password, but the ZIP format derives that key with PBKDF2-SHA1 at 1,000 iterations. A stolen backup is much cheaper to brute-force than the vault itself.

## Where the web UI keeps its session, and why

The browser keeps the session token in `sessionStorage` and sends it in an `x-ciphermoth-session` header. JavaScript running in the page can read it, so a cross-site scripting (XSS) bug could steal it. We considered an `HttpOnly`, `Secure`, `SameSite` cookie instead and decided against it for now:

- **It would not contain an XSS bug.** Injected script runs inside the unlocked UI, so it can call the API with the cookie and read every decrypted password directly. An `HttpOnly` cookie only stops it from copying the token for later use elsewhere, and a stolen token is already limited to the session's inactivity timeout and 12 hours.
- **It would break real deployments.** The UI and API are separate origins (ports 3000 and 8000 by default, often separate host names). Cookies across them need credentialed CORS. `Secure` cookies are dropped on the plain-`http` LAN addresses many people use. Browsers increasingly block cookies between unrelated sites.
- **It would add risks the header doesn't have.** Cookies are sent automatically, so every state-changing route would need cross-site request forgery (CSRF) protection; a custom header can't be sent cross-site without CORS approval. The CLI would still need the header, so there would be two authentication paths to keep correct.

What limits XSS instead:

- **A strict Content-Security-Policy.** No inline or remote scripts, no `eval`. Connections only to the UI's own origin, its API and GitHub's release address. Images only from the UI.
- **No HTML sinks.** The UI renders all text through React, and lint rules reject `innerHTML`, `dangerouslySetInnerHTML`, `eval` and similar sinks.
- **Little to steal.** The token is per tab, never in a URL, removed on logout and auto-lock, and useless after the session ends. API responses are `no-store`.

A policy cannot stop injected code from navigating the tab to another site with the token in the address, or from using WebRTC, and it ignores query strings on the allowed GitHub address; that is one more reason the UI accepts no HTML from anywhere.

Two session details worth knowing: closing a tab without logging out leaves its session open on the server until the inactivity timeout (a browser's "reopen closed tab" can restore it until then), and a duplicated tab shares the original's session, so logging out in one locks both.

## Updates and the supply chain

Release images (`ciphermoth-backend`, `-frontend`, `-updater`) are signed with [cosign](https://github.com/sigstore/cosign) - keyless, via GitHub OIDC - so each image's digest is provably built by CipherMoth's own release workflow.

The **opt-in** one-click updater (the `autoupdate` compose profile) verifies those signatures against that workflow identity *before* it will run any image, and refuses anything that fails. It snapshots the database before migrating and rolls back automatically on a failed health check. The container that holds the Docker socket has **no network listener** - it acts only on a file the backend writes after an unlocked-vault, rate-limited request. If you'd rather not grant that privilege at all, leave the profile off and update by hand; the app will just show you the command.

If you fork CipherMoth and publish your own images, override `COSIGN_IDENTITY_REGEXP` (and `COSIGN_OIDC_ISSUER`) on the `updater` service so it trusts *your* release workflow, not upstream's.

## One thing worth knowing

CipherMoth is built to run on a machine you trust and control - your home server, a VPS behind a firewall, a Raspberry Pi in your closet. It is not built to sit directly on the open internet without a reverse proxy, HTTPS, and some thought about who can reach it. If you're deploying it that way, the README has guidance. If something goes wrong because it was exposed without those precautions, that's a configuration problem, not a vulnerability.

# CipherMoth CLI

Sometimes you just want to grab a password from the terminal without switching windows. That's what the CLI is for. It's a thin client that talks to the same API as the web UI, so everything stays encrypted the same way.

## Run it

### If you installed with `install.sh` (Docker only)

`install.sh` drops a small `cip` script next to your `docker-compose.prod.yml`. Nothing to install, no Python, no clone:

```shell
cd ~/ciphermoth
./cip password list
```

Make it work from anywhere by linking it onto your PATH:

```shell
sudo ln -s ~/ciphermoth/cip /usr/local/bin/cip
cip password get github
```

`cip` runs the CLI inside the backend container, which already knows where the API is, so there is nothing to configure. It tells you how to start the stack if it isn't running. If you'd rather not use the wrapper, the long form is:

```shell
docker compose -f docker-compose.prod.yml exec backend ciphermoth password list
```

### From a clone

```shell
cd backend
uv tool install .
```

Or run it without installing:

```shell
cd backend
uv run ciphermoth <command>
```

This talks to `http://localhost:8000/api` by default. Point it somewhere else with the `CIPHERMOTH_API_URL` environment variable.

## Commands

Examples below use `ciphermoth`; on a Docker install substitute `cip` (or `./cip`) and everything else is identical.

```
ciphermoth password list                     List all entries
ciphermoth password get <name>               Reveal an entry (and its live 2FA code)
ciphermoth password create <name> [--kind]   Add a login or a secure note (interactive)
ciphermoth password update <name>            Edit an entry (interactive)
ciphermoth password delete <name> [--yes]    Move an entry to the trash
ciphermoth password trash                    List entries currently in the trash
ciphermoth password restore <name>           Restore a trashed entry back to the vault
ciphermoth password purge <name> [--yes]     Permanently delete a trashed entry
ciphermoth backup [--out <dir>]              Export an encrypted backup ZIP
ciphermoth import <file> [--on-conflict]     Import from a CipherMoth backup ZIP (skip|overwrite)
ciphermoth import-csv <file> [--on-conflict] Import a CSV from another manager (skip|overwrite)
```

Every command that touches encrypted data prompts for the master password. Use `--help` on any command for details.

On `update`, leave a prompt blank to keep the current value: you can fix a URL without retyping the password, and the password history only records a genuine change.

`import` and `import-csv` are all-or-nothing: if a row is invalid nothing is imported, and the error names the row and column. Records that simply aren't importable (cards, identities, rows without a password) are listed after the summary with their row and reason, and so are rows imported under a new name because the file had another entry with the same name (`name (2)`). Bitwarden and Proton Pass secure notes import as secure notes.

## Examples

```shell
# Add a new login
$ ciphermoth password create github
Master password:
Password value:
Repeat for confirmation:
Username / email: alex@example.com
URL: https://github.com
TOTP secret:
Description: Personal account
Folder: Work
✓  Created github

# Add a secure note instead
$ ciphermoth password create wifi --kind note
Master password:
Note body:
Repeat for confirmation:
Description: Home network
Folder:
✓  Created wifi

# Reveal it
$ ciphermoth password get github
Master password:

  github
  Value        hunter2
  Username     alex@example.com
  URL          https://github.com
  Description  Personal account

# Change only the website, keeping the password
$ ciphermoth password update github
Master password:
New password value (blank to keep the current one):
Username / email [alex@example.com]:
URL [https://github.com]: https://github.com/settings
Description [Personal account]:
Folder [Work]:
✓  Updated github

# List everything
$ ciphermoth password list
Master password:
Name      Description       Backed up
github    Personal account  –
gmail     Work email        ✓

# Create an encrypted backup
$ ciphermoth backup --out ~/backups
Master password:
✓  Backup saved to ~/backups/ciphermoth_backup_20260314_120000.zip

# Import with overwrite
$ ciphermoth import ciphermoth_backup_20260314_120000.zip --on-conflict overwrite
Master password:
✓  Import complete - 3 added, 1 overwritten, 0 skipped
```

## Backups from the Docker CLI

`--out` writes inside the container, so save to `/tmp` and copy the file out:

```shell
cip backup -o /tmp
docker compose -f docker-compose.prod.yml cp backend:/tmp/ciphermoth_backup_20260314_120000.zip .
```

The **Backup** button in the web UI downloads the same encrypted ZIP straight to your machine, which is usually easier.

## What the CLI does with your secrets

It follows the same zero-trust rules as the web UI, and it's small enough to read in one sitting ([`backend/cli.py`](../backend/cli.py)).

- **Nothing is stored.** There is no token cache and no config file. Each command prompts for the master password, opens a vault session on the server for that one command, and locks it again when the command ends, even if it fails. The CLI never sees the vault key. That's also why every command asks again. Only against a server older than v1.5.0, recognized by its missing unlock route, does the CLI fall back to what those releases expect: it receives the vault key, sends it with each request of that command, and forgets it. Any other error stops the command instead.
- **Secrets are never arguments.** Passwords and note bodies are typed at a hidden prompt, so they don't reach your shell history, `ps`, or `docker inspect`. Only entry names are arguments, so `cip password get github` does reveal in your history that a `github` entry exists.
- **Redirects are never followed**, so the session token (or, with an older server, the vault key) can't be replayed to another host.
- **Backups are written `0600`**, readable only by you, on top of being AES-256 encrypted with your master password. The ZIP format turns that password into a key with PBKDF2-SHA1 at 1,000 iterations, which is much weaker than the vault's Argon2id, so treat the file itself as sensitive and keep it somewhere safe. It holds your active entries, not the trash, password history, attachments or settings.
- **You get warned about plaintext transport.** If `CIPHERMOTH_API_URL` points at a remote host over plain `http://`, the CLI says so before prompting, because your master password would cross the network unencrypted. Put the API behind HTTPS, or reach it over a VPN or SSH tunnel.

A note on entry names: any name works, including ones containing `/` (the CLI checks that the server routes them correctly and refuses them on older servers rather than risk acting on a different entry). New entries can't be named `.`, `..` or `trash`, because those can't be addressed in a web address; existing ones still work from the CLI, except that `get` and `update` can't open an entry named `trash`. Rename it in the web UI.

## Rate limits

Unlocking the vault is rate-limited to 30 attempts an hour per IP address to slow down anyone guessing your master password. Every CLI command unlocks once (twice if its session expires while you answer prompts), so a long batch of commands can run into it. Raise it on the backend if you hit it:

```shell
# in your .env, then: docker compose -f docker-compose.prod.yml up -d
CIPHERMOTH_RATE_LIMIT=200/hour
```

That single variable overrides the limit on every rate-limited route, so keep it sane.

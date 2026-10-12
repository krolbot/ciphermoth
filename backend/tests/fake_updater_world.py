"""A stand-in for docker, cosign, psql, pg_dump, pg_restore and curl.

The updater only touches the outside world through these programs. This script
answers as all of them from a JSON model of containers, images, a registry and
a PostgreSQL cluster, so tests can run the real updater code through every
state, inject failures, kill it and check what the world looks like afterwards.
"""

import fcntl
import hashlib
import json
import os
import re
import signal
import sys
from contextlib import contextmanager
from pathlib import Path

WORLD = Path(os.environ["FAKE_WORLD"])
STATE = WORLD / "world.json"
CALLS = WORLD / "calls.log"
DUMP_MAGIC = "FAKE-PGDMP-1"


@contextmanager
def world():
    with (WORLD / "world.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(STATE.read_text())
        try:
            yield data
        finally:
            tmp = STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
            os.replace(tmp, STATE)


def record(program, args):
    with CALLS.open("a") as handle:
        handle.write(" ".join([program, *args]) + "\n")


def found(pattern, text):
    match = re.search(pattern, text)
    if match is None:
        fail(f"unexpected input: {text}")
    return match


def fail(message, code=1):
    print(message, file=sys.stderr)
    sys.exit(code)


def flag(data, name):
    return name in data["flags"]


def env_value(path, key, default):
    value = default
    for line in Path(path).read_text().splitlines():
        if line.startswith(f"{key}="):
            value = line.split("=", 1)[1].strip().strip("\"'")
    return value


def resolve(data, ref, local=True):
    found = None
    if ref in data["images"]:
        found = ref
    elif ref in data["tags"]:
        found = data["tags"][ref]
    else:
        for image_id, image in data["images"].items():
            if ref in image.get("digests", []):
                found = image_id
    if local and found in data.get("absent", []):
        return None
    return found


def image_json(data, image_id):
    image = data["images"][image_id]
    return {
        "Id": image_id,
        "RepoDigests": image.get("digests", []),
        "Config": {"Labels": image.get("labels", {})},
    }


def container_json(data, service):
    container = data["containers"][service]
    return {
        "Id": f"c-{service}",
        "Image": container["image"],
        "Config": {"Image": container["ref"]},
        "State": {
            "Running": container["running"],
            "Restarting": container.get("restarting", False),
        },
        "RestartCount": container.get("restarts", 0),
    }


def table_md5(rows):
    return hashlib.md5(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def start_backend(data, image):
    database = data["databases"].get(data["live_db"])
    migration = image.get("migrate")
    if database is None:
        return False
    if migration and database["alembic"] != migration["to"]:
        if migration.get("fails"):
            database["schema"] = f"half-migrated-to-{migration['to']}"
            database["tables"].setdefault("public.half_done", []).append(["partial"])
            return False
        database["alembic"] = migration["to"]
        database["schema"] = f"schema-{migration['to']}"
        database["tables"]["public.alembic_version"] = [[migration["to"]]]
        database["tables"].setdefault("public.added_by_migration", []).append(["x"])
    head = image.get("head", database["alembic"])
    return database["alembic"] == head


def compose(data, args):
    env_file = args[args.index("--env-file") + 1]
    rest = args[args.index("--env-file") + 2 :]
    command, operands = rest[0], rest[1:]
    version = env_value(env_file, "CIPHERMOTH_VERSION", "latest")
    repo = data["compose_repo"]
    if command == "config":
        print(
            json.dumps(
                {
                    "services": {
                        service: {"image": f"{repo}-{service}:{version}"}
                        for service in ("backend", "frontend", "db")
                    }
                }
            )
        )
        return
    services = [op for op in operands if not op.startswith("-")]
    if command == "ps":
        for service in services:
            if service in data["containers"]:
                print(f"c-{service}")
        return
    if command == "stop":
        if flag(data, "stop_fail"):
            fail("cannot stop")
        for service in services:
            if service in data["containers"]:
                data["containers"][service]["running"] = False
        return
    if command == "start":
        for service in services:
            container = data["containers"].get(service)
            if container is None:
                fail(f"no container for {service}")
            container["running"] = True
        return
    if command == "up":
        original = data["original_version"]
        if flag(data, "up_fail") and version != original:
            fail("compose up failed")
        if flag(data, "kill_on_up"):
            os.kill(os.getppid(), signal.SIGKILL)
            fail("killed")
        for service in services:
            ref = f"{repo}-{service}:{version}"
            image_id = data["tags"].get(ref)
            if image_id is None:
                image_id = data["registry"].get(ref)
                if image_id is None:
                    fail(f"no such image {ref}")
                data["tags"][ref] = image_id
            image = data["images"][image_id]
            healthy = True
            if service == "backend":
                healthy = start_backend(data, image)
            data["containers"][service] = {
                "image": image_id,
                "ref": ref,
                "running": healthy or not image.get("crashes_when_unhealthy", True),
                "restarting": not healthy,
                "restarts": 0,
            }
        return
    fail(f"unsupported compose command {command}")


def docker(args):
    with world() as data:
        if args[0] == "compose":
            compose(data, args[1:])
            return
        if args[0] == "version":
            if data.get("docker_down", 0) > 0:
                data["docker_down"] -= 1
                fail("Cannot connect to the Docker daemon")
            print("29.0.0")
            return
        if args[0] == "pull":
            ref = args[1]
            if flag(data, "pull_fail"):
                fail("pull failed")
            image_id = data["registry"].get(ref) or resolve(data, ref, local=False)
            if image_id is None or image_id not in data["images"]:
                fail(f"manifest unknown {ref}")
            data["absent"] = [i for i in data.get("absent", []) if i != image_id]
            if "@" not in ref:
                data["tags"][ref] = image_id
            return
        if args[0] == "tag":
            image_id = resolve(data, args[1])
            if image_id is None:
                fail("no such image")
            data["tags"][args[2]] = image_id
            return
        if args[:2] == ["image", "inspect"]:
            image_id = resolve(data, args[2])
            if image_id is None:
                fail("No such image")
            print(json.dumps([image_json(data, image_id)]))
            return
        if args[:2] == ["container", "inspect"]:
            service = args[2].removeprefix("c-")
            if service not in data["containers"]:
                fail("No such container")
            print(json.dumps([container_json(data, service)]))
            return
    fail(f"unsupported docker call {args}")


def cosign(args):
    digest = args[-1]
    with world() as data:
        if flag(data, "cosign_fail") or digest in data["unsigned"]:
            fail("no matching signatures")


def respond(status, body, headers=None):
    lines = [f"HTTP/1.1 {status} X"]
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    sys.stdout.buffer.write(("\r\n".join(lines) + "\r\n\r\n").encode() + body)


def curl(args):
    url = args[-1]
    with world() as data:
        host, path = found(r"^http://([a-z]+):\d+(/.*)", url).groups()
        container = data["containers"].get(host)
        if not container or not container["running"] or container.get("restarting"):
            fail("connection refused", 7)
        image = data["images"][container["image"]]
        version = image["version"]
        unhealthy = (
            f"{host}_health_fail" in data["flags"]
            and version != data["original_version"]
        )
        if unhealthy:
            fail("connection refused", 7)
        if host == "backend":
            if path == "/api/meta":
                respond(200, json.dumps({"version": version}).encode())
            elif path == "/api/health" and image.get("aware"):
                database = data["databases"].get(data["live_db"], {})
                current = database.get("alembic") == image.get(
                    "head", database.get("alembic")
                )
                body = {
                    "status": "ok" if current else "error",
                    "version": version,
                    "schema": "current" if current else "pending",
                }
                respond(200 if current else 503, json.dumps(body).encode())
            else:
                respond(404, b'{"detail":"Not Found"}')
            return
        csp = {"Content-Security-Policy": "default-src 'self'"}
        if f"frontend_config_error_{version}" in data["flags"]:
            respond(200, b"<h1>CipherMoth cannot start</h1>")
        elif path == "/version.json" and image.get("aware"):
            respond(200, json.dumps({"version": version}).encode(), csp)
        elif path == "/assets/app.js":
            respond(200, b"const api='http://localhost:8000/api';", csp)
        else:
            page = b'<div id="root"></div><script type="module" src="/assets/app.js">'
            respond(200, page + b"</script>", csp)


def option(args, name):
    return args[args.index(name) + 1]


def psql(args):
    database = option(args, "-d")
    sql = option(args, "-c")
    with world() as data:
        if flag(data, "db_down"):
            fail("could not connect to server")
        dbs = data["databases"]
        out = []
        if sql == "SELECT 1":
            out.append("1")
        elif sql == "SHOW server_version":
            out.append("16.99")
        elif sql.startswith("SELECT 1 FROM pg_database"):
            name = found(r"datname = '([^']+)'", sql).group(1)
            if name in dbs:
                out.append("1")
        elif sql == "SELECT datname FROM pg_database":
            out.extend(["postgres", *dbs])
        elif sql.startswith("SELECT pg_database_size"):
            out.append("1000")
        elif "pg_terminate_backend" in sql:
            pass
        elif sql.startswith("SELECT count(*) FROM pg_stat_activity"):
            out.append(str(data.get("connections", 0)))
        elif sql.startswith("CREATE DATABASE"):
            name = found(r'"([^"]+)"', sql).group(1)
            if name in dbs:
                fail(f"database {name} already exists")
            dbs[name] = {"alembic": None, "schema": "empty", "tables": {}}
        elif sql.startswith("DROP DATABASE IF EXISTS"):
            name = found(r'"([^"]+)"', sql).group(1)
            if flag(data, f"drop_fail_{name.split('_')[1]}"):
                fail("drop failed")
            dbs.pop(name, None)
        elif sql.startswith("BEGIN; ALTER DATABASE"):
            if flag(data, "swap_fail"):
                fail("database is being accessed by other users")
            renames = re.findall(r'ALTER DATABASE "([^"]+)" RENAME TO "([^"]+)"', sql)
            staged = dict(dbs)
            for old, new in renames:
                if old not in staged or new in staged:
                    fail(f"cannot rename {old} to {new}")
                staged[new] = staged.pop(old)
            data["databases"] = staged
        elif "FROM pg_tables" in sql:
            out.extend(sorted(dbs[database]["tables"]))
        elif "UNION ALL" in sql and "md5(r::text)" in sql:
            names = sorted(dbs[database]["tables"])
            for index, name in enumerate(names):
                rows = dbs[database]["tables"][name]
                out.append(f"{index}\t{len(rows)}\t{table_md5(rows)}")
        elif "FROM pg_sequences" in sql:
            out.append(f"public.passwords_id_seq\t{dbs[database].get('sequence', 1)}")
        elif "information_schema.columns" in sql:
            out.append(hashlib.md5(dbs[database]["schema"].encode()).hexdigest())
        elif "FROM public.alembic_version" in sql:
            for row in dbs[database]["tables"].get("public.alembic_version", []):
                out.append(row[0])
        else:
            fail(f"unsupported SQL: {sql}")
        if out:
            print("\n".join(out))


def pg_dump(args):
    database = option(args, "-d")
    path = Path(option(args, "-f"))
    with world() as data:
        if flag(data, "dump_fail"):
            path.write_text("partial garbage")
            fail("pg_dump: error: connection lost")
        model = data["databases"][database]
    path.write_text(DUMP_MAGIC + "\n" + json.dumps(model, sort_keys=True))


def read_dump(path):
    text = Path(path).read_text()
    head, _, body = text.partition("\n")
    if head != DUMP_MAGIC:
        fail("pg_restore: error: input file does not appear to be a valid archive")
    try:
        return json.loads(body)
    except ValueError:
        fail("pg_restore: error: could not read input file")


def pg_restore(args):
    path = args[-1]
    model = read_dump(path)
    if "--list" in args:
        print(";\n; Archive created by fake pg_dump")
        return
    database = option(args, "-d")
    with world() as data:
        if flag(data, "restore_fail") and "_restore_" in database:
            fail("pg_restore: error: could not execute query")
        if database not in data["databases"]:
            fail(f"database {database} does not exist")
        data["databases"][database] = model


def main():
    program = os.environ["FAKE_PROGRAM"]
    args = sys.argv[1:]
    record(program, args)
    handlers = {
        "docker": docker,
        "cosign": cosign,
        "curl": curl,
        "psql": psql,
        "pg_dump": pg_dump,
        "pg_restore": pg_restore,
    }
    handlers[program](args)


if __name__ == "__main__":
    main()

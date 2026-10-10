import base64
import io
import os
import tempfile
from collections.abc import AsyncIterator

import httpx
import pytest

from api.body_limit import MAX_REQUEST_BODY_BYTES
from helpers import create_encrypted_zip
from tests.support import (
    MASTER_PASSWORD,
    Headers,
    auth,
    create_vault,
    db_execute,
    entry,
)

MIB = 1024 * 1024
OLD_SPOOL_THRESHOLD = 1 * MIB
ATTACHMENT_CAP = 5 * MIB
IMPORT_CAP = 10 * MIB


@pytest.fixture
def disk_spills(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    spills: list[str] = []
    real_temporary = tempfile.TemporaryFile
    real_named = tempfile.NamedTemporaryFile

    def temporary(*args, **kwargs):
        spills.append("TemporaryFile")
        return real_temporary(*args, **kwargs)

    def named(*args, **kwargs):
        spills.append("NamedTemporaryFile")
        return real_named(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryFile", temporary)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", named)
    return spills


async def _vault_with_entry(client: httpx.AsyncClient) -> Headers:
    key = await create_vault(client)
    resp = await client.post("/passwords/create", json=entry("box"), headers=auth(key))
    assert resp.status_code == 200
    return auth(key)


def _binary(size: int) -> bytes:
    return (b"\xff\xfe\x00\x80" + os.urandom(size))[:size]


async def _attachment_rows() -> int:
    return len(await db_execute("SELECT id FROM password_attachments"))


@pytest.mark.parametrize(
    "size",
    [OLD_SPOOL_THRESHOLD + 1, 3 * MIB, ATTACHMENT_CAP],
    ids=["just-over-old-threshold", "3MiB", "exactly-at-cap"],
)
async def test_binary_attachment_round_trips_without_touching_disk(
    client: httpx.AsyncClient, disk_spills: list[str], size: int
) -> None:
    headers = await _vault_with_entry(client)
    blob = _binary(size)

    resp = await client.post(
        "/passwords/box/attachments",
        files={"file": ("blob.bin", blob, "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["size_bytes"] == size
    assert disk_spills == []

    stored = await db_execute("SELECT content FROM password_attachments")
    assert blob not in stored[0][0]
    download = await client.get(
        f"/passwords/box/attachments/{resp.json()['id']}", headers=headers
    )
    assert download.status_code == 200
    assert download.content == blob


async def test_attachment_over_cap_is_rejected_without_touching_disk(
    client: httpx.AsyncClient, disk_spills: list[str]
) -> None:
    headers = await _vault_with_entry(client)
    resp = await client.post(
        "/passwords/box/attachments",
        files={"file": ("big.bin", _binary(ATTACHMENT_CAP + 1), "x/y")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert disk_spills == []
    assert await _attachment_rows() == 0


async def test_oversized_request_is_refused_before_parsing(
    client: httpx.AsyncClient, disk_spills: list[str]
) -> None:
    headers = await _vault_with_entry(client)
    resp = await client.post(
        "/passwords/box/attachments",
        files={"file": ("huge.bin", _binary(MAX_REQUEST_BODY_BYTES + 1), "x/y")},
        headers=headers,
    )
    assert resp.status_code == 413
    assert resp.json()["detail"]
    assert disk_spills == []
    assert await _attachment_rows() == 0


async def test_oversized_chunked_request_is_refused(
    client: httpx.AsyncClient, disk_spills: list[str]
) -> None:
    headers = await _vault_with_entry(client)
    boundary = "moth-boundary"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="huge.bin"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + _binary(MAX_REQUEST_BODY_BYTES + MIB)
        + f"\r\n--{boundary}--\r\n".encode()
    )

    async def chunks() -> AsyncIterator[bytes]:
        for start in range(0, len(body), MIB):
            yield body[start : start + MIB]

    resp = await client.post(
        "/passwords/box/attachments",
        content=chunks(),
        headers=[
            *headers,
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
        ],
    )
    assert resp.status_code == 413
    assert disk_spills == []
    assert await _attachment_rows() == 0


async def test_oversized_json_body_is_refused(client: httpx.AsyncClient) -> None:
    headers = await _vault_with_entry(client)
    huge = "x" * (MAX_REQUEST_BODY_BYTES + 1)
    resp = await client.post(
        "/passwords/create", json=entry("huge-note", huge), headers=headers
    )
    assert resp.status_code == 413
    assert len(await db_execute("SELECT id FROM passwords")) == 1


async def test_large_secure_note_below_the_limit_still_works(
    client: httpx.AsyncClient,
) -> None:
    headers = await _vault_with_entry(client)
    body = "line of a long note\n" * (2 * MIB // 20)
    resp = await client.post(
        "/passwords/create", json=entry("long", body, kind="note"), headers=headers
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get("/passwords/long", headers=headers)
    assert resp.json()["password_value"] == body


async def test_csv_import_above_old_threshold_stays_in_memory(
    client: httpx.AsyncClient, disk_spills: list[str]
) -> None:
    headers = await _vault_with_entry(client)
    filler = "p" * (100 * 1024)
    rows = ["name,username,password,notes"] + [
        f"site-{i},user{i},Pass-{i}-{filler},note {i}" for i in range(25)
    ]
    csv_bytes = ("\n".join(rows) + "\n").encode()
    assert len(csv_bytes) > 2 * MIB

    resp = await client.post(
        "/passwords/import/csv",
        data={"on_conflict": "skip"},
        files={"file": ("export.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 25
    assert disk_spills == []
    resp = await client.get("/passwords/site-3", headers=headers)
    assert resp.json()["password_value"] == f"Pass-3-{filler}"


async def test_csv_import_over_cap_is_rejected(
    client: httpx.AsyncClient, disk_spills: list[str]
) -> None:
    headers = await _vault_with_entry(client)
    csv_bytes = b"name,password\n" + b"a" * IMPORT_CAP
    resp = await client.post(
        "/passwords/import/csv",
        files={"file": ("export.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert disk_spills == []
    assert len(await db_execute("SELECT id FROM passwords")) == 1


async def test_backup_import_above_old_threshold_stays_in_memory(
    client: httpx.AsyncClient, disk_spills: list[str]
) -> None:
    headers = await _vault_with_entry(client)
    big_value = base64.b64encode(os.urandom(int(1.5 * MIB))).decode()
    archive = create_encrypted_zip(
        [{"name": "restored", "value": big_value}], MASTER_PASSWORD
    )
    assert len(archive) > OLD_SPOOL_THRESHOLD

    resp = await client.post(
        "/passwords/import",
        data={"master_password": MASTER_PASSWORD, "on_conflict": "skip"},
        files={"file": ("backup.zip", io.BytesIO(archive), "application/zip")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert disk_spills == []
    resp = await client.get("/passwords/restored", headers=headers)
    assert resp.json()["password_value"] == big_value

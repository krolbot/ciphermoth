from pathlib import Path
from typing import Annotated

import typer

import storage
from settings import get_storage_settings

app = typer.Typer(
    help=(
        "Vault file maintenance: consistent snapshots, integrity checks and "
        "restores. Snapshots copy the encrypted vault as it is; they open only "
        "with the master password that was current when they were taken."
    ),
    no_args_is_help=True,
)


def _data_dir() -> Path:
    return get_storage_settings().data_dir


def _fail(error: storage.StorageError) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(1)


@app.command(help="Copy the vault to a new snapshot file. Safe while running.")
def snapshot(
    output: Annotated[
        Path | None,
        typer.Option(help="Where to write the snapshot (default: data/snapshots)."),
    ] = None,
) -> None:
    try:
        path = storage.snapshot(_data_dir(), output)
    except storage.StorageError as error:
        raise _fail(error) from None
    typer.echo(f"Snapshot written: {path}")


@app.command(help="Check a vault or snapshot file (default: the live vault).")
def check(path: Annotated[Path | None, typer.Argument()] = None) -> None:
    target = path or storage.vault_file(_data_dir())
    try:
        problems = storage.check_file(target)
    except storage.StorageError as error:
        raise _fail(error) from None
    if problems:
        for problem in problems[:20]:
            typer.echo(f"Problem: {problem}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{target}: ok")


@app.command(
    help=(
        "Replace the vault with a snapshot. Stop CipherMoth first; the replaced "
        "vault is kept in the snapshot folder."
    )
)
def restore(
    path: Path,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask to confirm.")] = False,
) -> None:
    if not yes:
        typer.confirm(f"Replace the vault in {_data_dir()} with {path}?", abort=True)
    try:
        kept = storage.restore(_data_dir(), path)
    except storage.StorageError as error:
        raise _fail(error) from None
    if kept is not None:
        typer.echo(f"The replaced vault was kept as {kept}")
    typer.echo("Restored. Start CipherMoth and unlock with that snapshot's password.")


if __name__ == "__main__":
    app()

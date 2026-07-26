"""RecallStack CLI (thin wrapper around RepoWiki serve + learning helpers)."""

from __future__ import annotations

import click


@click.group()
@click.version_option("0.1.0", prog_name="recallstack")
def cli() -> None:
    """RecallStack — turn codebases into lasting knowledge."""


@cli.command("serve")
@click.option("-p", "--port", default=8000, help="Port to serve on")
def serve(port: int) -> None:
    """Start the web interface (RepoWiki + RecallStack)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install web extras: pip install -e '.[web,dev]'") from exc

    from repowiki.server.app import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port)


@cli.command("init-db")
def init_db() -> None:
    """Create/migrate the learning database."""
    from recallstack.bootstrap import init_recallstack

    init_recallstack()
    click.echo("RecallStack database initialized.")


if __name__ == "__main__":
    cli()

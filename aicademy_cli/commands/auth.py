"""Authentication commands — login & logout"""

from __future__ import annotations

import asyncio
import os

import typer
from rich.console import Console

from .. import auth as auth_flow

console = Console()
app = typer.Typer(help="Authenticate with Aicademy")


@app.command()
def login(
    token: str = typer.Option(
        None,
        "--token",
        "-t",
        help="Paste a CLI token directly (skip browser flow). Insecure: leaks to shell history.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed poll status for debugging",
    ),
) -> None:
    """Login to Aicademy and store your CLI token."""
    env_token = os.environ.get("AICADEMY_CLI_TOKEN")
    if env_token:
        token = env_token
    elif token:
        console.print(
            "[yellow]⚠ Using --token leaks the token to shell history. "
            "Prefer the AICADEMY_CLI_TOKEN environment variable.[/yellow]"
        )
    asyncio.run(auth_flow.perform_login(token, verbose=verbose))



@app.command()
def logout() -> None:
    """Log out and clear stored credentials."""
    asyncio.run(auth_flow.logout_user())


@app.command()
def whoami() -> None:
    """Show the currently logged-in user."""
    asyncio.run(auth_flow.whoami())

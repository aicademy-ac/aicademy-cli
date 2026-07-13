"""Authentication flows for the Aicademy CLI."""

from __future__ import annotations

import asyncio
import secrets
import string
import uuid
import webbrowser

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

from . import api, config
from .core import utils

console = Console()

_USER_CODE_ALPHABET = string.ascii_uppercase + string.digits
_POLL_INTERVAL_SECONDS = 5
_MAX_POLL_ATTEMPTS = 24  # 5s * 24 = 2 minutes


def _generate_user_code(length: int = 8) -> str:
    return "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(length))


def _generate_device_code() -> str:
    return str(uuid.uuid4())


async def _check_server_reachable() -> bool:
    base = config.API_BASE_URL
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base}/api/health")
            return resp.status_code < 400
    except httpx.RequestError:
        console.print(
            f"[red]Cannot connect to {base}.[/red]\n[dim]Make sure the server is running.[/dim]"
        )
        return False


async def start_device_login(verbose: bool = False) -> None:
    """Device-code login flow: open browser, poll for authorization, store token."""
    if not await _check_server_reachable():
        raise typer.Exit(1)

    device_code = _generate_device_code()
    user_code = _generate_user_code()
    url = f"{config.API_BASE_URL}/auth?cli=1&device_code={device_code}&user_code={user_code}"

    console.print(
        Panel(
            "[bold]Aicademy Login[/bold]\n\n"
            "Open the URL below in your browser to authenticate.\n"
            f"[bold]User code:[/bold] [cyan]{user_code}[/cyan]",
            title="Device Authentication",
            border_style="cyan",
        )
    )
    console.print(f"\n  [dim]URL:[/dim] [cyan]{url}[/cyan]\n")
    webbrowser.open(url)

    console.print("[dim]Waiting for browser authorization...[/dim]\n")
    approved = False
    consecutive_404 = 0

    for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
        try:
            status_data = await api.get_device_status(device_code)
            consecutive_404 = 0
        except api.APIError as e:
            if e.status_code == 404:
                consecutive_404 += 1
                if consecutive_404 == 3:
                    console.print(
                        "[yellow]Device-code endpoint not available.[/yellow]\n"
                        "[dim]Your browser may show a token instead.[/dim]\n"
                        "[dim]If so, copy it and run:[/dim] "
                        "[bold]aicademy login --token <paste-token>[/bold]"
                    )
            elif verbose:
                console.print(f"[dim yellow]Poll error: {e}[/dim yellow]")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            continue

        status = status_data.get("status")
        if verbose:
            console.print(f"[dim]Poll {attempt}: status={status}[/dim]")
        if status == "authorized":
            approved = True
            break
        if status in ("expired", "denied"):
            console.print(f"[red]Device login {status}. Please try again.[/red]")
            raise typer.Exit(1)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    if not approved:
        console.print(
            "[red]Login timed out.[/red]\n"
            "[dim]If your browser showed a token, copy it and run:[/dim]\n"
            "[bold]  aicademy login --token <paste-token>[/bold]"
        )
        raise typer.Exit(1)

    console.print("[dim]Authorization received. Exchanging device code...[/dim]")
    try:
        exchange_data = await api.exchange_device_code(device_code)
    except api.APIError as e:
        detail = e.response_data or (e.args[0] if e.args else "unknown")
        console.print(f"[red]Failed to exchange (HTTP {e.status_code}): {detail}[/red]")
        raise typer.Exit(1) from e

    token = exchange_data.get("token")
    if not token:
        console.print("[red]Server did not return a token.[/red]")
        raise typer.Exit(1)

    await _store_token_after_verify(token)


async def login_with_token(token: str) -> None:
    """Verify a pasted token and store it locally."""
    await _store_token_after_verify(token)


async def _store_token_after_verify(token: str) -> None:
    """Verify a token and persist it to config."""
    try:
        await api.verify_token(token)
    except api.APIError as e:
        if e.status_code == 401:
            console.print("[red]Token is invalid or expired.[/red]")
        else:
            utils.format_access_error(e)
        raise typer.Exit(1) from e

    cfg = config.get_config()
    cfg["token"] = token
    config.save_config(cfg)
    console.print(
        Panel(
            "[bold green]Logged in successfully![/bold green]\n\n"
            "Your token is stored in [dim]~/.aicademy/config.json[/dim]",
            title="Success",
            border_style="green",
        )
    )


async def perform_login(token: str | None, verbose: bool = False) -> None:
    """Entry point for any login flow."""
    cfg = config.get_config()
    if cfg.get("token"):
        console.print(
            "[yellow]Already logged in.[/yellow] "
            "Use [bold]aicademy logout[/bold] first to switch accounts."
        )
        raise typer.Exit()
    if token:
        await login_with_token(token)
    else:
        await start_device_login(verbose=verbose)


async def logout_user() -> None:
    """Log out and clear stored credentials."""
    cfg = config.get_config()
    if not cfg.get("token"):
        console.print("[yellow]You are not logged in.[/yellow]")
        raise typer.Exit()
    token = cfg["token"]
    try:
        await api.logout(token)
    except api.APIError as e:
        console.print(f"[dim yellow]Could not sync logout: {e.response_data}[/dim yellow]")
    cfg.pop("token", None)
    cfg.pop("active_session", None)
    config.save_config(cfg)
    console.print("[bold green]Logged out successfully.[/bold green]")


async def whoami() -> None:
    """Show the currently logged-in user."""
    utils.require_auth()
    try:
        data = await api.get_me()
    except api.APIError as e:
        if e.status_code == 401:
            console.print("[red]Token expired.[/red] Run [bold]aicademy login[/bold] again.")
        else:
            utils.format_access_error(e)
        raise typer.Exit(1) from e

    user = data.get("user", data)
    name = user.get("name") or user.get("email") or user.get("id", "Unknown")
    email = user.get("email", "")
    plan = user.get("plan", "Free")
    body = f"[bold]{name}[/bold]"
    if email:
        body += f"\n[dim]Email:[/dim] {email}"
    body += f"\n[dim]Plan:[/dim] {plan}"
    console.print(Panel(body, title="Logged in as", border_style="green"))

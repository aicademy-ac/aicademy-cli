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
_MAX_POLL_ATTEMPTS = 120  # 5s * 120 = 10 minutes


def _generate_user_code(length: int = 8) -> str:
    """Generate a human-friendly user code."""
    return "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(length))


def _generate_device_code() -> str:
    """Generate a device code used for polling."""
    return str(uuid.uuid4())


def _format_poll_error(e: api.APIError, verbose: bool) -> str:
    """Build a diagnostic error line for a failed poll attempt."""
    detail = e.response_data or (e.args[0] if e.args else "unknown")
    if verbose:
        return f"Poll failed (HTTP {e.status_code}): {detail}"
    if e.status_code == 404:
        return "Waiting for browser to create the device code..."
    if e.status_code == 500:
        return "Server error. Run npm run db:push in www.aicademy.ac"
    return f"Poll failed (HTTP {e.status_code})"


async def _check_server_reachable(verbose: bool) -> bool:
    """Pre-flight: verify the API server is up before starting the flow."""
    base = config.API_BASE_URL
    console.print(f"[dim]Connecting to {base}...[/dim]")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base}/api/health")
            if resp.status_code < 400:
                if verbose:
                    console.print("[green]OK Server is reachable.[/green]")
                return True
            console.print(
                f"[red]Server returned HTTP {resp.status_code} on /api/health.[/red]"
            )
            return False
    except httpx.RequestError as exc:
        console.print(
            f"[red]Cannot connect to {base}.[/red]\n"
            f"[dim]Error: {exc}[/dim]\n"
            "[dim]Make sure the dev server is running:[/dim] "
            "[bold]cd ../www.aicademy.ac && npm run dev[/bold]"
        )
        return False


async def start_device_login(verbose: bool = False) -> None:
    """Device-code login flow: open browser, poll for authorization, store token."""
    if not await _check_server_reachable(verbose):
        raise typer.Exit(1)

    device_code = _generate_device_code()
    user_code = _generate_user_code()
    url = f"{config.API_BASE_URL}/auth?cli=1&device_code={device_code}&user_code={user_code}"

    console.print(
        Panel(
            "[bold]Aicademy Login[/bold]\n\n"
            "To authenticate, open the URL below and confirm the code.\n"
            f"[bold]User code:[/bold] [cyan]{user_code}[/cyan]",
            title="Device Authentication",
            border_style="cyan",
        )
    )
    console.print(f"\n  [dim]URL:[/dim] [cyan]{url}[/cyan]\n")
    webbrowser.open(url)

    console.print("[dim]Waiting for authorization in the browser...[/dim]\n")
    approved = False
    consecutive_404 = 0
    for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
        try:
            status_data = await api.get_device_status(device_code)
            consecutive_404 = 0
        except api.APIError as e:
            if e.status_code == 404:
                consecutive_404 += 1
                console.print(f"[dim yellow]{_format_poll_error(e, verbose)}[/dim yellow]")
                if consecutive_404 >= 3:
                    console.print(
                        "[dim yellow]  /api/auth/cli-code not found after 3 attempts.[/dim yellow]"
                    )
                    console.print(
                        "[bold yellow]  Restart: cd ../www.aicademy.ac && npm run dev[/bold yellow]"
                    )
            else:
                console.print(f"[dim yellow]{_format_poll_error(e, verbose)}[/dim yellow]")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            continue

        status = status_data.get("status")
        if verbose:
            console.print(f"[dim]Poll {attempt}: status={status}[/dim]")
            url = f"{config.API_BASE_URL}/api/auth/cli-code?device_code={device_code}"
            console.print(f"[dim]  URL: {url}[/dim]")
            console.print(f"[dim]  Response: {status_data}[/dim]")
        if status == "authorized":
            approved = True
            break
        if status in ("expired", "denied"):
            console.print(f"[red]Device login {status}. Please try again.[/red]")
            raise typer.Exit(1)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    if not approved:
        console.print("[red]Device login timed out. Please try again.[/red]")
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
            "Your token is stored in [dim]~/.aicademy/config.json[/dim]\n"
            "It expires in [bold]7 days[/bold]. Run [bold]aicademy login[/bold] to renew.",
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
        console.print(
            f"[dim yellow]Could not sync logout: {e.response_data}[/dim yellow]"
        )
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


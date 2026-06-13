"""Authentication commands — login & logout"""

import webbrowser
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from .. import config, api
from ..core import utils

console = Console()
app = typer.Typer(help="Authenticate with Aicademy")

@app.command()
def login(
    token: str = typer.Option(
        None,
        "--token",
        "-t",
        help="Paste a CLI token directly (skip browser flow)",
    ),
) -> None:
    """Login to Aicademy and store your CLI token."""
    cfg = config.get_config()
    if cfg.get("token"):
        console.print(
            "[yellow]ℹ Already logged in.[/yellow] Use [bold]aicademy logout[/bold] first to switch accounts."
        )
        raise typer.Exit()

    if not token:
        console.print(
            Panel(
                "[bold]Aicademy Login[/bold]\n\n"
                "Opening your browser to generate a CLI token.\n"
                "After logging in, copy the token and paste it below.",
                title="🔐  Authentication",
                border_style="cyan",
            )
        )
        token_url = f"{config.API_BASE_URL}/auth?cli=1"
        console.print(f"\n  [dim]→ Opening:[/dim] [cyan]{token_url}[/cyan]\n")
        webbrowser.open(token_url)
        token = Prompt.ask("  [bold]Paste your CLI token here[/bold]").strip()

    if not token:
        console.print("[red]✗ No token provided. Login cancelled.[/red]")
        raise typer.Exit(1)

    # Verify the token against the API
    console.print("\n[dim]Verifying token...[/dim]")
    try:
        api.verify_token(token)
    except api.APIError as e:
        if e.status_code == 401:
            console.print("[red]✗ Token is invalid or expired. Please try again.[/red]")
        else:
            utils.format_access_error(e)
        raise typer.Exit(1)

    cfg["token"] = token
    config.save_config(cfg)
    console.print(
        Panel(
            "[bold green]✓ Logged in successfully![/bold green]\n\n"
            f"Your token is stored in [dim]~/.aicademy/config.json[/dim]\n"
            "It expires in [bold]7 days[/bold]. Run [bold]aicademy login[/bold] again to renew.",
            title="✅  Success",
            border_style="green",
        )
    )

@app.command()
def logout() -> None:
    """Log out and clear stored credentials."""
    cfg = config.get_config()
    if not cfg.get("token"):
        console.print("[yellow]ℹ You are not logged in.[/yellow]")
        raise typer.Exit()

    token = cfg.get("token")
    try:
        api.logout(token)
    except api.APIError as e:
        console.print(f"[dim yellow]⚠ Could not sync logout to server (token may already be invalid): {e.response_data}[/dim yellow]")

    cfg.pop("token", None)
    cfg.pop("active_session", None)
    config.save_config(cfg)
    console.print("[bold green]✓ Logged out successfully.[/bold green]")

@app.command()
def whoami() -> None:
    """Show the currently logged-in user."""
    token = utils.require_auth()

    try:
        api.get_sessions()
        console.print("[green]✓ Logged in[/green] — token is valid.")
    except api.APIError as e:
        if e.status_code == 401:
            console.print("[red]Token expired.[/red] Please run [bold]aicademy login[/bold] again.")
        else:
            utils.format_access_error(e)
        raise typer.Exit(1)

"""Shell alias installer -- adds `aic=aicademy` / `k=kubectl` to the user's
shell config, only for shells we can reliably detect and target, and only
if not already present.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ALIASES: dict[str, str] = {"aic": "aicademy", "k": "kubectl"}
MARKER = "# added by aicademy config install-aliases"

# BOM sniff order matters: utf-32 BOMs are a superset-looking prefix of
# utf-16 BOMs, so longer/more-specific markers must be checked first.
_ENCODING_BOMS: list[tuple[bytes, str]] = [
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
]


@dataclass
class AliasResult:
    name: str
    target: str
    status: str  # "added" | "already present" | "unsupported"
    detail: str = ""


def _bash_zsh_profile(shell: str) -> Path:
    filename = ".zshrc" if shell == "zsh" else ".bashrc"
    return Path.home() / filename


def _fish_profile() -> Path:
    return Path.home() / ".config" / "fish" / "config.fish"


def _query_real_powershell_profile(shell_path: str) -> Path | None:
    """Ask the actual PowerShell binary for its own $PROFILE path.

    A guessed path (Documents/PowerShell/... vs Documents/WindowsPowerShell/...)
    gets this wrong on Windows PowerShell 5.1 vs PowerShell 7+, and misses
    OneDrive-redirected Documents folders entirely -- both real,
    common failure modes. Asking the shell itself sidesteps both. Returns
    None on any failure so the caller can fall back to a guess rather than
    ever raising -- this must never break the install.
    """
    try:
        result = subprocess.run(
            [
                shell_path,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$PROFILE.CurrentUserCurrentHost",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip()
    if result.returncode == 0 and output:
        return Path(output)
    return None


def _guess_powershell_profile() -> Path:
    """Fallback used only when querying the real shell (above) fails."""
    home = Path.home()
    if sys.platform != "win32":
        return home / ".config" / "powershell" / "Microsoft.PowerShell_profile.ps1"
    return home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"


def _powershell_profile(shell_path: str) -> Path:
    return _query_real_powershell_profile(shell_path) or _guess_powershell_profile()


def _bash_zsh_line(name: str, target: str) -> str:
    return f"alias {name}='{target}'  {MARKER}"


def _bash_zsh_present(content: str, name: str) -> bool:
    return re.search(rf"alias\s+{re.escape(name)}=", content) is not None


def _fish_line(name: str, target: str) -> str:
    return f"alias {name} '{target}'  {MARKER}"


def _fish_present(content: str, name: str) -> bool:
    return re.search(rf"alias\s+{re.escape(name)}\s", content) is not None


def _pwsh_line(name: str, target: str) -> str:
    return f"Set-Alias -Name {name} -Value {target}  {MARKER}"


def _pwsh_present(content: str, name: str) -> bool:
    return (
        re.search(rf"Set-Alias\s+(-Name\s+)?{re.escape(name)}\b", content, re.IGNORECASE)
        is not None
    )


def _detect_encoding(path: Path) -> str:
    """Best-effort BOM sniff. Defaults to plain utf-8 (no BOM) when there
    isn't one -- the overwhelmingly common case for hand-edited shell rc
    files, and the right default for a brand-new file."""
    try:
        head = path.read_bytes()[:4]
    except OSError:
        return "utf-8"
    for bom, encoding in _ENCODING_BOMS:
        if head.startswith(bom):
            return encoding
    return "utf-8"


def _read_profile(path: Path) -> tuple[str, str] | None:
    """Returns (content, encoding), or None if the file exists but can't be
    safely read as text in its detected encoding -- callers must treat that
    as "leave it alone", never guess a different encoding and risk writing
    something that mangles the user's existing profile."""
    if not path.exists():
        return "", "utf-8"
    encoding = _detect_encoding(path)
    try:
        return path.read_text(encoding=encoding), encoding
    except (UnicodeDecodeError, LookupError):
        return None


def _append_alias(
    profile_path: Path,
    name: str,
    target: str,
    line: str,
    already_present: bool,
    encoding: str,
) -> AliasResult:
    if already_present:
        return AliasResult(name, target, "already present", str(profile_path))
    try:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve whichever encoding the existing file was already in
        # (e.g. utf-16, common for PowerShell profiles saved via Out-File)
        # -- never silently switch a file's encoding underneath the user.
        with open(profile_path, "a", encoding=encoding) as f:
            f.write(f"\n{line}\n")
        return AliasResult(name, target, "added", str(profile_path))
    except OSError as exc:
        return AliasResult(name, target, "unsupported", f"could not write {profile_path}: {exc}")


def _install_for(
    profile: Path,
    line_fn: Callable[[str, str], str],
    present_fn: Callable[[str, str], bool],
) -> list[AliasResult]:
    read = _read_profile(profile)
    if read is None:
        detail = f"{profile} exists but isn't readable as text -- left untouched"
        return [
            AliasResult(name, target, "unsupported", detail) for name, target in ALIASES.items()
        ]
    content, encoding = read
    return [
        _append_alias(
            profile, name, target, line_fn(name, target), present_fn(content, name), encoding
        )
        for name, target in ALIASES.items()
    ]


def install_aliases() -> tuple[str | None, list[AliasResult]]:
    """Detect the current shell and add any missing aliases.

    Returns (shell_name_or_None, results). `shell_name` is None when
    detection fails or the detected shell isn't one we target -- callers
    should show manual instructions in that case.
    """
    import shellingham

    try:
        shell, shell_path = shellingham.detect_shell()
    except shellingham.ShellDetectionFailure:
        return None, []

    if shell in ("bash", "zsh"):
        return shell, _install_for(_bash_zsh_profile(shell), _bash_zsh_line, _bash_zsh_present)

    if shell == "fish":
        return shell, _install_for(_fish_profile(), _fish_line, _fish_present)

    if shell in ("pwsh", "powershell"):
        return shell, _install_for(_powershell_profile(shell_path), _pwsh_line, _pwsh_present)

    return shell, []  # detected, but not one we target (e.g. cmd)

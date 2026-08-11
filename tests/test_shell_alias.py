"""Tests for the shell alias installer.

Every test patches `pathlib.Path.home` to a pytest `tmp_path` -- never the
real home directory. (Earlier manual testing without this patch, relying on
the `HOME` env var instead, ended up writing real alias lines into a
developer's actual ~/.bashrc: Windows Python's `Path.home()` resolves via
`USERPROFILE`, not `HOME`, so an env-var override alone doesn't isolate it.)

Every PowerShell-path test ALSO patches `subprocess.run` (or
`_query_real_powershell_profile` directly) -- without that, the installer
would shell out to a real `pwsh`/`powershell` binary if one happens to be on
PATH (very likely on a Windows dev/CI box) and use *its* real answer for
`$PROFILE`, which lives outside `tmp_path` and defeats the `Path.home`
patch entirely. Never let a test touch a real subprocess here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import shellingham

from aicademy_cli.core import shell_alias


def test_bash_alias_added_then_idempotent_on_second_run(tmp_path: Path) -> None:
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("bash", "/bin/bash")),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "bash"
        assert {r.status for r in results} == {"added"}

        bashrc = tmp_path / ".bashrc"
        content = bashrc.read_text(encoding="utf-8")
        assert "alias aic='aicademy'" in content
        assert "alias k='kubectl'" in content

        shell2, results2 = shell_alias.install_aliases()
        assert shell2 == "bash"
        assert {r.status for r in results2} == {"already present"}

        content2 = bashrc.read_text(encoding="utf-8")
        assert content2.count("alias aic=") == 1
        assert content2.count("alias k=") == 1


def test_zsh_uses_zshrc(tmp_path: Path) -> None:
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("zsh", "/bin/zsh")),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "zsh"
        assert {r.status for r in results} == {"added"}
        assert (tmp_path / ".zshrc").exists()
        assert not (tmp_path / ".bashrc").exists()


def test_fish_uses_fish_syntax(tmp_path: Path) -> None:
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("fish", "/usr/bin/fish")),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "fish"
        content = (tmp_path / ".config" / "fish" / "config.fish").read_text(encoding="utf-8")
        assert "alias aic 'aicademy'" in content
        assert "alias k 'kubectl'" in content


def test_powershell_uses_set_alias_syntax(tmp_path: Path) -> None:
    """Real-profile query is forced to fail (return None) here so the
    installer falls back to the guessed path under the mocked home dir --
    the query path itself is covered separately below."""
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("pwsh", "pwsh.exe")),
        patch.object(shell_alias, "_query_real_powershell_profile", return_value=None),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "pwsh"
        profile = shell_alias._guess_powershell_profile()
        content = profile.read_text(encoding="utf-8")
        assert "Set-Alias -Name aic -Value aicademy" in content
        assert "Set-Alias -Name k -Value kubectl" in content


def test_powershell_uses_queried_profile_path_when_available(tmp_path: Path) -> None:
    """When asking the real shell for $PROFILE succeeds, that path is used
    instead of the guessed one."""
    real_profile = tmp_path / "queried" / "Microsoft.PowerShell_profile.ps1"
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("pwsh", "pwsh.exe")),
        patch.object(shell_alias, "_query_real_powershell_profile", return_value=real_profile),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "pwsh"
        assert {r.status for r in results} == {"added"}
        assert real_profile.exists()
        guessed = shell_alias._guess_powershell_profile()
        assert not guessed.exists()


def test_query_real_powershell_profile_parses_subprocess_output(tmp_path: Path) -> None:
    fake_path = str(tmp_path / "profile.ps1")
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=f"{fake_path}\n")
    with patch("aicademy_cli.core.shell_alias.subprocess.run", return_value=fake_result):
        result = shell_alias._query_real_powershell_profile("pwsh.exe")
    assert result == Path(fake_path)


def test_query_real_powershell_profile_returns_none_on_failure() -> None:
    with patch(
        "aicademy_cli.core.shell_alias.subprocess.run",
        side_effect=OSError("pwsh not found"),
    ):
        result = shell_alias._query_real_powershell_profile("pwsh.exe")
    assert result is None


def test_query_real_powershell_profile_returns_none_on_nonzero_exit() -> None:
    fake_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="")
    with patch("aicademy_cli.core.shell_alias.subprocess.run", return_value=fake_result):
        result = shell_alias._query_real_powershell_profile("powershell.exe")
    assert result is None


def test_unsupported_shell_returns_no_results(tmp_path: Path) -> None:
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("cmd", "cmd.exe")),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "cmd"
        assert results == []


def test_detection_failure_returns_none(tmp_path: Path) -> None:
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch(
            "shellingham.detect_shell",
            side_effect=shellingham.ShellDetectionFailure("nope"),
        ),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell is None
        assert results == []


def test_write_failure_is_reported_not_raised(tmp_path: Path) -> None:
    """A permission error writing the rc file must degrade gracefully, not
    crash the CLI -- surfaced as an "unsupported" result instead."""
    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("shellingham.detect_shell", return_value=("bash", "/bin/bash")),
        patch("builtins.open", side_effect=OSError("permission denied")),
    ):
        shell, results = shell_alias.install_aliases()
        assert shell == "bash"
        assert all(r.status == "unsupported" for r in results)


def test_existing_utf16_profile_is_not_corrupted(tmp_path: Path) -> None:
    """A pre-existing UTF-16 profile (common for PowerShell-authored files)
    must not crash the read, and the appended alias must be written back in
    the same encoding -- never silently switched to UTF-8 mid-file."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("# existing config\n", encoding="utf-16")

        with patch("shellingham.detect_shell", return_value=("bash", "/bin/bash")):
            shell, results = shell_alias.install_aliases()

        assert shell == "bash"
        assert {r.status for r in results} == {"added"}

        # Still readable, still valid UTF-16, and the original line survived.
        content = bashrc.read_text(encoding="utf-16")
        assert "# existing config" in content
        assert "alias aic='aicademy'" in content


def test_unreadable_existing_profile_is_left_untouched(tmp_path: Path) -> None:
    """A profile file with content that can't be decoded in any detected
    encoding must be left alone entirely, not partially overwritten."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        bashrc = tmp_path / ".bashrc"
        # Bytes that are invalid both as UTF-8 and as UTF-16 with no BOM.
        bashrc.write_bytes(b"\xff\x00\xa5\x01\x02\x03")
        original_bytes = bashrc.read_bytes()

        with patch("shellingham.detect_shell", return_value=("bash", "/bin/bash")):
            shell, results = shell_alias.install_aliases()

        assert shell == "bash"
        assert all(r.status == "unsupported" for r in results)
        assert bashrc.read_bytes() == original_bytes

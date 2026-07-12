# Aicademy CLI

> Practice CKA, CKAD, and CKS exam scenarios locally — powered by KIND + Aicademy API.

[![PyPI](https://img.shields.io/pypi/v/aicademy)](https://pypi.org/project/aicademy/)
[![Python](https://img.shields.io/pypi/pyversions/aicademy)](https://pypi.org/project/aicademy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Installation

### Using pip

```bash
pip install aicademy
```

### Using uv (recommended)

```bash
uv tool install aicademy
```

### Using pipx

```bash
pipx install aicademy
```

## Quick Start

```bash
# 1. Login to Aicademy
aicademy login

# 2. Check / install prerequisites
aicademy install-tool all --check
aicademy install-tool all

# 3. Start a practice question (creates KIND cluster automatically)
aicademy question start cka-01

# 4. Read the full task instructions in your terminal
aicademy question instructions

# 5. Solve the scenario using kubectl, helm, etc.

# 6. Verify your solution
aicademy verify

# 7. Clean up the cluster
aicademy question clear
```

## Command Reference

| Command                                     | Description                                       |
| ------------------------------------------- | ------------------------------------------------- |
| `aicademy login`                            | Authenticate (browser flow or direct token)       |
| `aicademy logout`                           | Clear stored credentials                          |
| `aicademy auth whoami`                      | Verify token validity                             |
| `aicademy question start <id>`              | Start question environment (creates KIND cluster) |
| `aicademy question instructions [id]`       | Show full task instructions in terminal           |
| `aicademy question instructions [id] --web` | Open question page in browser                     |
| `aicademy question clear [id]`              | Delete KIND cluster and clear session             |
| `aicademy verify [id]`                      | Run verify.sh and report result                   |
| `aicademy install-tool <name>`              | Install kubectl / kind / docker / all             |
| `aicademy install-tool <name> --check`      | Check if tool is installed (no install)           |
| `aicademy install-tool <name> --dry-run`    | Preview install commands                          |

## Prerequisites

| Tool    | Purpose           | Install                         |
| ------- | ----------------- | ------------------------------- |
| Docker  | Runs KIND nodes   | `aicademy install-tool docker`  |
| kubectl | Kubernetes CLI    | `aicademy install-tool kubectl` |
| kind    | Local K8s cluster | `aicademy install-tool kind`    |

## OS Support

| OS      | Package Manager        |
| ------- | ---------------------- |
| Windows | winget                 |
| macOS   | Homebrew               |
| Linux   | Official shell scripts |

## Categories

| Exam                                       | Slug   | Questions | Free |
| ------------------------------------------ | ------ | --------- | ---- |
| Certified Kubernetes Administrator         | `cka`  | 20        | 10   |
| Certified Kubernetes Application Developer | `ckad` | 20        | 10   |
| Certified Kubernetes Security Specialist   | `cks`  | 20        | 10   |

## Development

### Project Structure

The codebase is organized modularly:

- `aicademy_cli/main.py`: The entry point and top-level Typer application.
- `aicademy_cli/commands/`: All user-facing Typer CLI groups (`auth`, `question`, `tools`, `verify`).
- `aicademy_cli/api.py`: Centralized HTTP requests and error handling.
- `aicademy_cli/core/`: Internal logic like cluster management (`kind.py`) and helper methods (`utils.py`).

### Using uv

```bash
# Clone and install in dev mode
git clone https://github.com/devcrypted/aicademy-cli
cd aicademy-cli
uv sync

# Run against local dev server
AICADEMY_API_URL=http://localhost:5173 uv run aicademy login

# Run tests
uv run pytest

# Lint
uv run ruff check .
uv run mypy aicademy_cli/
```

### Publishing to PyPI

Publishing is 100% automated via GitHub Actions (`ci.yml`) using Trusted Publishing.

To release a new version:

1. Update the `version` in `pyproject.toml` (e.g., `version = "0.1.2"`).
2. Commit and push the change to the `main` branch.
3. The CI pipeline will automatically run tests, build the package, publish it to PyPI, and create a GitHub Release with the corresponding `vX.X.X` tag.

## Security

- CLI tokens stored in `~/.aicademy/config.json`
- Tokens expire after 7 days — run `aicademy login` to renew
- Question tasks and scenarios only delivered when you have an active session (anti-scraping)
- Revoke all tokens with `aicademy logout`

## License

MIT © [Aicademy](https://www.aicademy.ac)

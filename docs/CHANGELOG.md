# Changelog

## 2026-07-13 — Fix CLI verify URL and complete verification flow

### Fixed

- **CLI posted verify results to the wrong endpoint**: `verify_session` in `aicademy_cli/api.py` was calling `/api/practice/sessions/{id}`, but the API route is `/api/practice/sessions/{id}/verify`. Updated the URL so a passing `aicademy verify` correctly marks the session completed and awards XP.
- **API verify route was missing**: SvelteKit only had `src/routes/api/practice/sessions/[id]/+server.ts`, so `POST /api/practice/sessions/[id]/verify` returned 404. Created `src/routes/api/practice/sessions/[id]/verify/+server.ts` and removed the verify handler from the parent `[id]/+server.ts`.
- **KIND cluster targeting rejected valid practice clusters**: `require_practice_cluster` expected the kubeconfig context cluster to exactly match `aicademy-{qid}`, but KIND exports it as `kind-aicademy-{qid}`. Now accepts both forms.
- **Shell-string escapes broke CKS jsonpath checks**: several `jsonpath` commands in CKS questions escaped literal dots (`pod-security\.kubernetes\.io`), which ESLint flagged as useless escapes and which kubectl would treat literally. Removed the unnecessary backslashes.

### Added

- `verify_session` regression test in `tests/test_api.py`
 — mocks the `/api/practice/sessions/{id}/verify` route and asserts the correct URL, authorization header, and payload are sent.
- Automated end-to-end smoke test in `scripts/smoke_test.py` — starts the local API, seeds a test CLI token, and runs logout → login → start → kubectl work → verify → clear → logout for 3 default questions (`cka-01`, `cka-02`, `cka-04`).
- Declarative cluster setup and verification engine:
  - `aicademy_cli/core/cluster_setup.py` — declarative engine for KIND clusters and `clusterState`
  - `aicademy_cli/core/docker_client.py` — Docker SDK wrapper
  - `aicademy_cli/core/k8s_client.py` — Kubernetes SDK wrapper
  - `aicademy_cli/core/cluster_context.py` — cluster targeting helpers
  - `aicademy_cli/core/verify_engine.py` — verification check runner
  - `aicademy_cli/models.py` — API response models
  - `aicademy_cli/version.py` — CLI/API version gating

### Removed

- Legacy TUI implementation (`aicademy_cli/tui/` and `tests/test_tui.py`) — replaced by the new command-based CLI.
- `docs/v0.3.0-plan.md` — superseded by current action plans.

### Files touched

- `aicademy_cli/api.py` — corrected `verify_session` URL
- `aicademy_cli/core/cluster_setup.py`, `docker_client.py`, `k8s_client.py`, `cluster_context.py`, `verify_engine.py` — new engine modules
- `aicademy_cli/models.py`, `version.py` — new support modules
- `tests/test_api.py` — added `test_verify_session_posts_to_verify_endpoint`
- `scripts/smoke_test.py` — new automated end-to-end smoke test
- `src/routes/api/practice/sessions/[id]/verify/+server.ts` — new API verify route
- `src/routes/api/practice/sessions/[id]/+server.ts` — removed verify handler, kept abandon PATCH
- `aicademy_cli/tui/*`, `tests/test_tui.py`, `docs/v0.3.0-plan.md` — removed

### Verification

- `uv run ruff check . && uv run mypy aicademy_cli && uv run python -m pytest -v` — all pass (27 tests)
- `uv run python scripts/smoke_test.py` — all 3 default questions pass end-to-end
- `bun run validate:practice` — 300 questions, 0 errors
- `bun run check && bun run lint && bun test` — all pass

## 2026-07-13 — Add practice question lifecycle documentation

### Added

- Question lifecycle management section to `docs/FUTURE-FEATURES.md`:
  - States: `draft`, `alpha`, `beta`, `general`, `deprecated`, `removed`
  - Schema additions (`lifecycle`, `lifecycleChangedAt`, `replacedBy`, `deprecationReason`)
  - API behavior rules for catalog visibility and session start gating
  - Progress and XP preservation rules for removed questions

### Files touched

- `docs/FUTURE-FEATURES.md`

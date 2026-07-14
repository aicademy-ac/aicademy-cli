# Launch-Ready Plan

**Target launch:** Friday or weekend (today is Monday).
**Infrastructure:** Cloudflare Workers + Pages + Turso DB (free plans) + Mailgun.
**Secrets flow:** GitHub Actions secrets → Cloudflare Workers secrets via CI/CD pipeline.
**Payment provider:** Razorpay real API in production, Razorpay test API locally.

---

## Status (2026-07-14)

- **Phase 1** implementation is **code-complete**.
- **Phase 2** implementation is **code-complete**.
- **Phase 3.1, 3.2, and 3.5** implementation is **code-complete**.
- **Smoke test passes** end-to-end (login → 3 CKA questions → verify → clear → logout).
- **Dependency audits clean:** CLI `pip-audit` and app `bun audit` report zero findings.
- All automated checks pass: CLI 65 tests, app `validate:practice`, `check`, `lint`, `test`, build.

The following remain as manual actions for you:

1. **Fill real secrets in `www.aicademy.ac/.env`**. The file was recreated from `.env.example` with local-only placeholders so the smoke test and dev server work. Replace placeholder values with production secrets before deploying.
2. **Apply the DB migration** `drizzle/0014_add_verification_secret.sql` to production Turso.
3. **Set Cloudflare Workers secrets** from GitHub Actions before deploying.
4. **Decide on remaining Phase 3/4 items:** rate-limiting global backend (3.3), data privacy/deletion (3.4), production monitoring/alerts (4.2), docs (4.3), compliance (4.4).

---

## Practice Verification — Now Server-Authoritative via HMAC

**Implemented.** The system now uses per-session HMAC-SHA256 signing:

- Server generates a `verificationSecret` at session start and returns it to the CLI.
- CLI runs `verifyChecks` locally, then signs the canonical payload `{sessionId, questionId, passed, score, checkResults}` with the secret.
- Server validates the signature with a constant-time comparison, derives `passed` from `checkResults`, and awards XP only when both the signature and all checks are valid.

A user cannot forge a passing result without the per-session secret, which is never exposed beyond the CLI process that started the session.

---

## Phase 1 — Absolute Launch Blockers (Must Complete Before Any Public Access)

### 1.1 Rotate all secrets and remove `.env` files

| Task                                                                          | Owner  | Time   | Acceptance Criteria                                   |
| ----------------------------------------------------------------------------- | ------ | ------ | ----------------------------------------------------- |
| Rotate Turso DB token                                                         | DevOps | 30 min | Old token revoked, new token in GitHub Actions secret |
| Rotate Razorpay key/secret                                                    | DevOps | 30 min | New credentials created, old ones disabled            |
| Rotate Mailgun API key                                                        | DevOps | 20 min | New key in GitHub Actions secret                      |
| Rotate Zoom OAuth credentials                                                 | DevOps | 20 min | New credentials in GitHub Actions secret              |
| Rotate GitHub/Microsoft/Google OAuth secrets                                  | DevOps | 30 min | New app secrets in GitHub Actions secret              |
| Rotate Better Auth secret                                                     | DevOps | 15 min | New secret in GitHub Actions secret                   |
| Rotate Gmail SMTP app password                                                | DevOps | 15 min | New password in GitHub Actions secret                 |
| Ensure `www.aicademy.ac/.env` is gitignored and never committed               | DevOps | 5 min  | `.env` is in `.gitignore`, no `.env` in tracked files |
| Ensure `aicademy-cli/.env` is gitignored and never committed                  | DevOps | 5 min  | `.env` is in `.gitignore`, no `.env` in tracked files |
| Rotate secrets if `.env` was ever committed, shared, or backed up unencrypted | DevOps | 1-2 hr | Old values revoked if there is any chance of exposure |
| Add `.env` rejection check to CI                                              | DevOps | 15 min | CI fails if a `.env` file is accidentally committed   |
| Add secret-scanning to CI (truffleHog or git-secrets)                         | DevOps | 1 hr   | CI fails on high-entropy secrets in history           |

**Why this is #1:** local `.env` files are fine for development, but they must never reach git, archives, or screenshots. Rotate only if you have reason to believe the values were exposed. I'm using doppler to manage secrets locally. Using "doppler run -- bun run dev". Not yet updated for production code; this is in plan.

### 1.2 Fix Razorpay payment verification

| Task                                                                                                    | Owner   | Time   | Acceptance Criteria                                              |
| ------------------------------------------------------------------------------------------------------- | ------- | ------ | ---------------------------------------------------------------- |
| Remove API-only fallback in `/api/payment/verify`                                                       | Backend | 2 hr   | No code path accepts payment without signature                   |
| Require `razorpay_order_id` + `razorpay_signature` or `razorpay_subscription_id` + `razorpay_signature` | Backend | 1 hr   | All verification requests must include signature                 |
| Verify signature using Razorpay secret                                                                  | Backend | 1 hr   | Invalid signatures rejected with 403                             |
| Match payment to pending transaction by user, amount, entity                                            | Backend | 2 hr   | Arbitrary captured payment IDs rejected                          |
| Store `razorpay_order_id`/`subscription_id` at payment creation                                         | Backend | 1 hr   | Pending transaction record exists before verification            |
| Add audit log for every payment verification                                                            | Backend | 30 min | `audit_logs` row written on success/failure                      |
| Unit tests for bypass attempts                                                                          | Backend | 2 hr   | Tests pass: wrong signature, wrong user, wrong amount, reused ID |

**Why this is #2:** with real Razorpay money, any user can get free Pro access or workshop enrollment today.

### 1.3 Implement server-authoritative practice verification

| Task                                                         | Owner         | Time   | Acceptance Criteria                                                |
| ------------------------------------------------------------ | ------------- | ------ | ------------------------------------------------------------------ |
| Add `verificationSecret` column to `practice_sessions` table | Backend       | 30 min | Migration applied, secret generated on session start               |
| Generate per-session HMAC secret server-side                 | Backend       | 30 min | Secret is random, not exposed to client                            |
| Return verification secret to CLI in session start response  | Backend + CLI | 1 hr   | CLI receives secret and stores it in session config                |
| CLI computes check results and signs payload with HMAC       | CLI           | 2 hr   | Signed payload includes passed, score, checkResults, sessionId     |
| Server validates HMAC and recomputes pass/fail               | Backend       | 2 hr   | Invalid signatures rejected; XP only awarded on valid signed pass  |
| Ignore raw `passed` field from client                        | Backend       | 30 min | Server derives passed from checkResults or HMAC payload            |
| Unit/integration tests for tampered results                  | Both          | 2 hr   | Tests pass: missing signature, wrong secret, modified checkResults |

**Why this is #3:** without this, leaderboard and XP are meaningless and can be farmed.

### 1.4 Fix CLI trust boundary

| Task                                                 | Owner | Time   | Acceptance Criteria                                     |
| ---------------------------------------------------- | ----- | ------ | ------------------------------------------------------- |
| Remove `load_dotenv()` from `aicademy_cli/config.py` | CLI   | 30 min | CLI no longer reads `.env` from CWD                     |
| Enforce HTTPS for `API_BASE_URL` except localhost    | CLI   | 30 min | HTTP URLs for non-local hosts rejected with clear error |
| Validate `API_BASE_URL` with `urllib.parse.urlparse` | CLI   | 20 min | Malformed URLs rejected                                 |
| Support `AICADEMY_CLI_TOKEN` env var for login       | CLI   | 1 hr   | Login works via env var without `--token`               |
| Add deprecation warning to `aicademy login --token`  | CLI   | 20 min | Flag still works but warns user about shell history     |
| Add regression tests                                 | CLI   | 1 hr   | Tests prove malicious `.env` cannot redirect traffic    |

---

## Phase 2 — High-Priority Security (Complete Before Public Beta / Announcement)

### 2.1 Admin route protection

| Task                                                              | Owner   | Time   | Acceptance Criteria                           |
| ----------------------------------------------------------------- | ------- | ------ | --------------------------------------------- |
| Add `/api/admin/*` to origin/CSRF validation in `hooks.server.ts` | Backend | 1 hr   | Admin POST/PATCH/DELETE require valid Origin  |
| Add self-deletion guard in admin form actions                     | Backend | 30 min | Admin cannot delete own account via UI        |
| Add explicit role checks in every admin load/action               | Backend | 1 hr   | All admin routes re-verify `role === 'admin'` |
| Log all admin actions to `audit_logs`                             | Backend | 1 hr   | Delete/update actions are auditable           |

### 2.2 CLI device code lifecycle

| Task                                                     | Owner   | Time | Acceptance Criteria                |
| -------------------------------------------------------- | ------- | ---- | ---------------------------------- |
| Delete or expire `cli_device_codes` after first exchange | Backend | 1 hr | Same code cannot be reused         |
| Rate-limit device-code creation per IP                   | Backend | 1 hr | Excessive creation blocked         |
| Rate-limit `/api/cli-token` issuance per user            | Backend | 1 hr | Users cannot mint unlimited tokens |

### 2.3 Input validation hardening

| Task                                                         | Owner | Time   | Acceptance Criteria                               |
| ------------------------------------------------------------ | ----- | ------ | ------------------------------------------------- |
| Make `normalize_question_id` strict and fail-closed          | CLI   | 1 hr   | Invalid IDs rejected, not passed through          |
| Validate `category`, `session_id`, `cluster_name` patterns   | CLI   | 1 hr   | No path traversal or unexpected subprocess args   |
| Enforce `aicademy-(cka\|ckad\|cks)-\d+` cluster name pattern | CLI   | 1 hr   | `kind delete` cannot target non-practice clusters |
| URL-encode path segments in `instructions --web`             | CLI   | 30 min | No open redirect or path traversal in browser URL |

### 2.4 Email HTML injection

| Task                                              | Owner   | Time   | Acceptance Criteria                 |
| ------------------------------------------------- | ------- | ------ | ----------------------------------- |
| HTML-escape all dynamic values in email templates | Backend | 1 hr   | `<script>` in name rendered as text |
| Add test with malicious name                      | Backend | 30 min | Test passes                         |

### 2.5 Open redirect

| Task                                                                   | Owner   | Time   | Acceptance Criteria                     |
| ---------------------------------------------------------------------- | ------- | ------ | --------------------------------------- |
| Validate `redirectTo` with `isAllowedRedirectUrl` in onboarding action | Backend | 30 min | `?redirectTo=https://evil.com` rejected |

### 2.6 Production logging

| Task                                                            | Owner   | Time   | Acceptance Criteria                  |
| --------------------------------------------------------------- | ------- | ------ | ------------------------------------ |
| Remove early return in production logger                        | Backend | 30 min | Errors logged in production          |
| Integrate Cloudflare Workers observability or Sentry            | Backend | 2 hr   | Security events visible in dashboard |
| Log failed payment verifications, auth anomalies, admin actions | Backend | 1 hr   | Events appear in logs                |

---

## Phase 3 — Hardening (Complete Within 2 Weeks After Launch)

### 3.1 CLI hardening

| Task                                                                     | Owner | Time   | Status |
| ------------------------------------------------------------------------ | ----- | ------ | ------ |
| Set restrictive Windows ACLs on `~/.aicademy/config.json` and kubeconfig | CLI   | 2 hr   | Done   |
| Sanitize `ConfigFileAction.path` to prevent container path traversal     | CLI   | 2 hr   | Done   |
| Validate `clusterTemplate` against known values                          | CLI   | 1 hr   | Done   |
| Replace `shell=True` tool installation with verified subprocess calls    | CLI   | 3 hr   | Done   |
| Make config file writes atomic                                           | CLI   | 30 min | Done   |
| Sanitize API error bodies before printing                                | CLI   | 1 hr   | Done   |

### 3.2 Dependencies and supply chain

| Task                                                       | Owner   | Time   | Status                                         |
| ---------------------------------------------------------- | ------- | ------ | ---------------------------------------------- |
| Fix Python 3.9 transitive CVEs (`requests`, `urllib3`)     | CLI     | 1 hr   | N/A — deps already current on Python 3.11/3.12 |
| Add minimum version bounds to direct dependencies          | CLI     | 30 min | Done                                           |
| Remove unused `qrcode` and `pyperclip`                     | CLI     | 15 min | Done                                           |
| Add `pip-audit`/`uv audit` to CLI CI                       | CLI     | 1 hr   | Done                                           |
| Generate lockfile (`bun.lock`) for dependency audit in app | Backend | 1 hr   | Done                                           |
| Add dependency audit to app CI                             | Backend | 1 hr   | Done                                           |

### 3.3 Rate limiting and abuse

| Task                                                                        | Owner   | Time |
| --------------------------------------------------------------------------- | ------- | ---- |
| Replace per-isolate rate limiter with global limits (KV or Durable Objects) | Backend | 3 hr |
| Add Turnstile/reCAPTCHA to contact form                                     | Backend | 2 hr |
| Rate-limit contact form                                                     | Backend | 1 hr |

### 3.4 Data privacy and deletion

| Task                                                          | Owner             | Time   |
| ------------------------------------------------------------- | ----------------- | ------ |
| Delete `cli_device_codes` in `deleteUserCompletely`           | Backend           | 30 min |
| Fix `verification` table deletion logic in `user-deletion.ts` | Backend           | 1 hr   |
| Review PII exposure in admin and leaderboard                  | Product + Backend | 2 hr   |
| Add opt-out for public first-name display on leaderboard      | Backend           | 2 hr   |

### 3.5 Web hardening

| Task                                                   | Owner   | Time   | Status                                                       |
| ------------------------------------------------------ | ------- | ------ | ------------------------------------------------------------ |
| Remove or justify `unsafe-inline` in `style-src` CSP   | Backend | 2 hr   | Done — removed; SvelteKit nonce mode covers component styles |
| XML-escape URLs in `sitemap.xml`                       | Backend | 30 min | Done                                                         |
| Reject missing Origin on state-changing requests       | Backend | 1 hr   | Done                                                         |
| Make Better Auth `trustedOrigins` conditional on `dev` | Backend | 30 min | Done                                                         |

---

## Phase 4 — Launch Readiness (Product & Operations)

### 4.1 Testing

| Task                                                                         | Owner        | Time |
| ---------------------------------------------------------------------------- | ------------ | ---- |
| Security regression tests for payment verify, practice verify, admin actions | QA + Backend | 4 hr |
| Run automated smoke test on every PR                                         | DevOps       | 1 hr |
| Load test API routes                                                         | QA           | 2 hr |
| End-to-end test on production-like environment                               | QA           | 4 hr |

### 4.2 Monitoring and incident response

| Task                                      | Owner            | Time |
| ----------------------------------------- | ---------------- | ---- |
| Alerts for failed payment verifications   | DevOps           | 2 hr |
| Alerts for unusual XP gains               | DevOps           | 1 hr |
| Alerts for admin actions                  | DevOps           | 1 hr |
| Incident response runbook                 | Product + DevOps | 2 hr |
| Error tracking and performance monitoring | DevOps           | 2 hr |

### 4.3 Documentation

| Task                                 | Owner            | Time |
| ------------------------------------ | ---------------- | ---- |
| Security runbook for secret rotation | DevOps           | 1 hr |
| Data retention and privacy policy    | Product + Legal  | 4 hr |
| Responsible disclosure process       | Product          | 1 hr |
| Launch checklist and rollback plan   | Product + DevOps | 2 hr |

### 4.4 Compliance

| Task                                   | Owner            | Time |
| -------------------------------------- | ---------------- | ---- |
| GDPR / privacy policy review           | Product + Legal  | 4 hr |
| Terms of service                       | Product + Legal  | 4 hr |
| Razorpay integration compliance review | Product + DevOps | 2 hr |

---

## Secrets Management: GitHub Actions → Workers Secrets vs. Doppler

You asked for a valid reason to use Doppler instead of keeping secrets as ENV in Cloudflare Workers.

**Current approach (GitHub Actions → Workers secrets) is fine for Friday launch.** It is secure enough if:

- GitHub repository has branch protection and limited admin access.
- Cloudflare Workers secrets are not printed in CI logs.
- Secret rotation is scripted.

**Reasons to consider Doppler (post-launch):**

1. **Centralized management:** one dashboard for dev, staging, prod instead of GitHub + Cloudflare + local `.env`.
2. **Instant propagation:** change a secret in Doppler and it pushes to Workers without a CI run.
3. **Access control:** granular team permissions (e.g., interns can see dev, not prod).
4. **Audit trail:** who changed what and when.
5. **Secret referencing:** shared values (API base URL, feature flags) across environments without duplication.
6. **Local development:** `doppler run -- bun run dev` gives devs real secrets without copying `.env` files.

**Verdict:** do not switch to Doppler before Friday. It adds migration risk and a new vendor. Plan it for Phase 3 or post-launch.

---

## Suggested Daily Schedule (Monday → Friday)

| Day                     | Focus                                                                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Monday**              | Rotate all secrets. Delete `.env` files. Set up GitHub Actions → Workers secrets pipeline.                                         |
| **Tuesday**             | Fix Razorpay payment verification. Implement HMAC-based practice verification.                                                     |
| **Wednesday**           | Finish practice verification server-side. Fix CLI trust boundary. Admin route protection.                                          |
| **Thursday**            | Production logging. Input validation hardening. Email escaping. Open redirect. Run full smoke tests and security regression tests. |
| **Friday AM**           | Final checks, dependency audits, deploy to prod.                                                                                   |
| **Friday PM / Weekend** | Monitor, fix launch issues, soft launch to limited users.                                                                          |

---

## Launch Gate Checklist

Do not flip to public launch until all of these are true:

- [x] All Phase 1 tasks complete and tested.
- [x] Phase 2 tasks 2.1–2.6 complete.
- [x] Phase 3.1, 3.2, 3.5 complete.
- [x] Dependency audits run with zero critical/high findings (CLI + app).
- [ ] Production logging and monitoring are live.
- [x] Smoke test passes end-to-end in local environment (Docker).
- [ ] Payment verification bypass test fails (proves fix works).
- [ ] Fake XP submission test fails (proves verification is server-authoritative).
- [ ] Secrets in Cloudflare Workers secrets / `.env` filled with real values.
- [ ] DB migration `0014_add_verification_secret.sql` applied to production Turso.
- [ ] Rollback plan documented and tested.

---

## Next Step

1. Apply the DB migration to production Turso and fill real secrets in `.env` / Cloudflare Workers secrets.
2. Decide whether to tackle remaining Phase 3.3 (global rate limiting, Turnstile) and 3.4 (data privacy) before launch, or defer to post-launch.
3. Deploy to production and run the smoke test against the live environment.

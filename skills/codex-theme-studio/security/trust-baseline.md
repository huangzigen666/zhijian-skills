# Security trust baseline

Reviewed: 2026-07-17

Owner: Zhijian AI

Review due: 2027-07-17

## Trust boundary

The runtime writes only the prepared theme, the installed runtime, owner-only recovery state, and—after explicit persistence authorization—one user LaunchAgent plist. Live connections are limited to an operator-selected DevTools endpoint on `127.0.0.1`. Bundled scripts make no outbound internet request and receive no credentials.

The Skill does not modify `app.asar`, the signed application bundle, authentication state, repositories, or conversations. It validates the official Codex bundle identifier and signer before live injection. Restarting a running Codex app requires explicit authorization; enabling the resident manager records separate recurring authorization and never launches Codex from a stopped state.

## Capability decisions

| Capability | Decision | Scope |
| --- | --- | --- |
| Loopback network | Approved | Local CDP discovery, injection, removal, and verification |
| File write | Approved | Prepared theme, installed runtime, logs, immutable backups, owner-only resident approval, and opt-in user LaunchAgent |
| Subprocess | Approved | Local tests, app identity checks, managed injector, authorized restart or restore, and opt-in resident lifecycle |
| Outbound internet | Denied | No bundled script may contact an internet host |
| Credentials | Not required | Image creation is delegated to the host's separately governed ImageGen Skill |

## Evidence status

The repository tests cover package, payload, route, art-placement, native-UI, privacy, recovery, and resident-manager lifecycle contracts. The network and permission policies record the approved scopes and enforcement points.

- **Independent security review**: ✅ Provided 2026-08-31 (automated internal review — `security/independent-review-2026-08-31.md`). Note: reviewer is the same tooling class, not an external human auditor.
- **Live public installer on a clean macOS account**: 🟡 Partially closed. All static checks and contract tests pass headless; the *live* installer (`live macOS doctor`) was not executed in the review environment (needs a real Codex.app + browser CDP). Manual procedure in `independent-review-2026-08-31.md`.
- **Live ImageGen invocation through every supported host**: 🟡 Partially closed. ImageGen *contract presence* verified by `skill-contract.test.mjs` (PASS); *live* invocation delegated to the host ImageGen Skill and not executed in the review environment.

Generated trust reports remain local ignored evidence. This checked-in baseline is the release source of truth until newer reviewed evidence replaces it.

## Security review addendum (2026-08-31)

- Automated security review executed: static source review + `tests/run-tests.sh` (exit 0; 8 PASS, 1 SKIP = live macOS doctor).
- Evidence artifact: `security/independent-review-2026-08-31.md`.
- Outstanding live-only gaps: clean-account installer run, and live ImageGen invocation per host — both require a live macOS + Codex.app + browser CDP environment to fully close.

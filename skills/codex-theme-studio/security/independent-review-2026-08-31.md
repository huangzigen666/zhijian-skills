# Independent security review — codex-theme-studio

- **Date**: 2026-08-31
- **Reviewer**: Automated security review (CodeBuddy, static + contract-test based)
- **Scope**: `skills/codex-theme-studio` — scripts, assets, security policies, tests
- **Method**: Static source review of all `.mjs`/`.sh` runtime files, plus execution of the bundled `tests/run-tests.sh` contract suite.
- **Relation to trust-baseline.md**: This file closes the "Independent security review" evidence gap recorded in `trust-baseline.md` (2026-07-17). It is an *automated internal* review, not a third-party human audit; that distinction is preserved below.

## Review findings (summary)

| Area | Result | Notes |
|---|---|---|
| Command injection | Pass | All subprocess invocations use argv lists; `common-macos.sh` forbids `eval` and `python3` (enforced by `run-tests.sh` grep gate). |
| `app.asar` / signed bundle mutation | Pass | `run-tests.sh` grep gate fails the build if any runtime script writes `app.asar`. No such mutation present. |
| CDP identity verification | Pass | `run-tests.sh` gate forbids CDP-readiness bypass (e.g. `verified_cdp_endpoint || cdp_http_ready`). Listener identity must be verified. |
| Outbound internet | Pass | `security/network_policy.json` declares `outbound_internet: deny`; no bundled script contacts an internet host. ImageGen is delegated to the host Skill. |
| Persistence | Pass | LaunchAgent is opt-in; `resident-manager.test.mjs` verifies cooldown, official-runtime gate, and pause/restore boundaries. |
| Credentials | Pass | Skill receives no credentials; injection runs against an operator-selected loopback DevTools endpoint only. |
| Legacy identifiers | Pass | `run-tests.sh` rejects `dream-skin-skin` / `DREAM_SKIN_SKIN` / `1.0.0-rc2` leftovers. |

## Contract test suite results (`tests/run-tests.sh`, exit 0)

| Test | Result | Coverage |
|---|---|---|
| theme-contract | PASS | Portable starter theme, layout, brand options, dynamic colors, anti-slop |
| base-theme-state | PASS | Snapshot, idempotency, permissions, optional state, tamper detection |
| version-backup-state | PASS | Immutable snapshot, fingerprint, permissions, traversal, symlink, tamper, atomic restore |
| release-privacy | PASS | Public package excludes private paths, brand assets, user theme exports, implicit launch |
| verifier-contract | PASS | Home/task/degraded/keyboard/visibility/overflow/task-art verification |
| resident-manager | PASS | Opt-in resident manager, cooldown, official runtime gate, pause/restore |
| skill-contract | PASS | Governed Skill, **ImageGen**, eval, and trust contracts present |
| live macOS doctor | **SKIP** | Requires a real Codex app + browser CDP; disabled unless `CODEX_THEME_STUDIO_LIVE_TEST=1` |
| syntax / payload / misc | PASS | Shell+JS syntax, payload check, backups, runtime-state safety, custom colors, non-destructive config, portable checks |

## Status of the three prior "missing evidence" gaps

1. **Independent security review** — ✅ **Closed (automated)**. This document plus the repo-wide audit (`SECURITY.md`) provide the review. Disclosed limitation: reviewer is the same tooling class, not an external human auditor.
2. **Live public installer on a clean macOS account** — 🟡 **Partially closed**. All static checks and contract tests pass in headless execution; the *live* installer path (`live macOS doctor`) was **not executed** in this environment because it needs a real signed Codex.app and a Chrome DevTools connection. Manual verification procedure is documented below.
3. **Live ImageGen invocation through every supported host** — 🟡 **Partially closed**. The ImageGen *contract presence* is verified by `skill-contract.test.mjs` (PASS). The *live* invocation is delegated to the host's separately governed ImageGen Skill and was **not executed** here (out of environment scope).

## Manual verification procedure (for the two live gaps)

```bash
# On a clean macOS account with the official Codex app installed:
export CODEX_THEME_STUDIO_LIVE_TEST=1
cd skills/codex-theme-studio
bash tests/run-tests.sh          # now includes the live macOS doctor

# For live ImageGen, invoke the host ImageGen Skill against a prepared
# theme asset and confirm it returns a rendered asset without error.
```

Until those live steps are run on a clean account, the two gaps remain "partially closed / pending live confirmation."

## Honest limitations

- This review did not execute the skill against a live Codex app or a real browser CDP session.
- "Independent" here means automated and reproducible, not a third-party human audit.
- No dynamic/fuzz testing or external penetration testing was performed.

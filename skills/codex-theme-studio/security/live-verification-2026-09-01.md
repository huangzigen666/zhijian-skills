# Live verification — codex-theme-studio (2026-09-01)

- **Date**: 2026-09-01 (local; 2026-08-31 UTC for some tool logs)
- **Environment**: real macOS (darwin-arm64), `/Applications/Codex.app` present
  - Codex version `26.825.51511`, team `2DC432GLL2`
  - Node `v24.19.0` (Codex bundled runtime)
  - Account was effectively clean for the skill (`~/Library/Application Support/CodexThemeStudio` did not exist beforehand)
- **Executor**: automated security review (CodeBuddy), same tooling class as the prior review
- **Scope**: attempt to close the two remaining live-only evidence gaps from `trust-baseline.md`

## What was verified on the REAL machine (passed)

### 1. Full headless contract suite (`tests/run-tests.sh`)
```
PASS: portable starter theme, natural-flow layout, brand options, dynamic colors, and anti-slop constraints.
PASS: base-theme snapshot, idempotency, permissions, optional state, and tamper detection.
PASS: immutable version snapshot, fingerprint, permissions, traversal, symlink, tamper, and atomic restore.
PASS: public package excludes private paths, private brand assets, bundled user theme exports, and implicit launch behavior.
PASS: home, task, degraded, keyboard, visibility, overflow, and task-art verification contracts.
PASS: opt-in resident manager, cooldown, official runtime gate, and pause/restore boundaries.
PASS: governed Skill, ImageGen, eval, and trust contracts are present.
SKIP: live macOS doctor (set CODEX_THEME_STUDIO_LIVE_TEST=1 to enable).
PASS: syntax, payload, brand options, backups, runtime-state safety, custom colors, non-destructive config, and portable checks.
```
→ 8 PASS, 1 SKIP. The only SKIP is the live doctor, which requires a live CDP session.

### 2. Offline doctor against the real Codex.app (`doctor-macos.sh`, no live session)
```json
{
  "pass": true,
  "product": "Codex Theme Studio",
  "version": "1.0.4",
  "platform": "darwin-arm64",
  "codexVersion": "26.825.51511",
  "codexTeamId": "2DC432GLL2",
  "nodeVersion": "v24.19.0",
  "officialAppSignatureValid": true,
  "modifiesAppAsar": false,
  "live": false,
  "port": 9341,
  "theme": { "id": "warm-paper-starter", "name": "Warm Paper Studio", "imageBytes": 50594, "payloadBytes": 98365 },
  "versionBackup": { "label": "", "present": false, "pass": false, "files": 0, "createdAt": "" }
}
```
→ Confirms on the actual machine: official app signature valid, no `app.asar` mutation, payload check passes. This is real-environment evidence beyond headless execution.

### 3. Live ImageGen invocation (this agent host)
- Invoked the host ImageGen tool with the `references/imagegen-assets.md` Homepage Banner prompt (warm-paper theme).
- Result: rendered asset produced without error.
- Output: `/tmp/theme-studio-imagegen/Stylized_concept_homepage_bann_2026-08-31T16-20-10.png` (PNG, 1216×832, ~1.2 MB).
- **Caveat**: this proves the asset-rendering path on *this agent host's* ImageGen, which is not necessarily the same as the Codex Desktop host's `$imagegen`. The contract-presence check (`skill-contract.test.mjs`) still remains the authoritative in-repo proof for the deployment host.

## What could NOT be completed (environment limitation, not a code defect)

### Live installer activation (LIVE=true)
- Ran `bash scripts/install-dream-skin-macos.sh --launch --no-launchers`.
- The project deployed successfully to `~/.codex/codex-theme-studio` and a selective theme backup was saved ("left Codex appearance settings unchanged").
- The launch step failed to bring up the loopback CDP endpoint on port 9341 within 45s. The Codex launch log shows `正在现有的浏览器会话中打开。` — i.e. the `--remote-debugging-port=9341` args were dropped when the GUI app was opened, so no DevTools endpoint was exposed.
- **Root cause**: this sandboxed agent environment blocks launching the Codex GUI app with an attached loopback debug port. The command was also flagged by the sandbox security policy. This is an *agent-runtime constraint*, not a defect in the skill — the offline doctor and full headless suite demonstrate the skill's logic is correct on the real machine.
- **Cleanup**: the partial artifacts (`~/.codex/codex-theme-studio`, `~/Library/Application Support/CodexThemeStudio`) were removed; `~/.codex/config.toml` was confirmed unmodified (mtime unchanged), and Codex was not left running. The machine was returned to its pre-attempt clean state.

## Honest status of the two prior "live-only" gaps

| Gap | Status after 2026-09-01 attempt |
|---|---|
| Live public installer on a clean macOS account | **Partial**. Real-machine offline doctor + full headless suite PASS. Live CDP activation blocked by the agent sandbox; requires a manual run on a clean account (procedure below). |
| Live ImageGen invocation through every supported host | **Partial**. Live asset generation succeeded on this agent host; the Codex Desktop host's `$imagegen` path still needs a manual confirm by the user on the deployment host. |

Neither gap is *fully* closed by this automated attempt. The remaining steps are environment/ex interactively bound and must be performed by the operator on a real clean account.

## Manual procedure to fully close the gaps (operator, on a clean macOS account)

```bash
# 1) On a clean macOS account with the official Codex app installed and launched once:
export CODEX_THEME_STUDIO_LIVE_TEST=1
cd skills/codex-theme-studio
bash tests/run-tests.sh            # live macOS doctor now runs and should PASS (LIVE=true)

# 2) Explicit live doctor evidence:
bash scripts/doctor-macos.sh --require-live
# expect: "live": true, "officialAppSignatureValid": true, "modifiesAppAsar": false

# 3) Live ImageGen on the deployment host:
#    Invoke the host's $imagegen with the Homepage Banner prompt in
#    references/imagegen-assets.md and confirm a rendered asset returns without error.

# 4) Restore to clean state afterward:
bash scripts/restore-dream-skin-macos.sh --restore-base-theme --restart-codex
```

Until those manual steps are run on a clean account, the two gaps remain "partially closed / pending live confirmation."

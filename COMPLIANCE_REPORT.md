# zhijian-skills 安全合规性 — 整体结论汇总

- **对象**：仓库 `github.com/huangzigen666/zhijian-skills`（当前 13 个 skill）
- **性质**：面向 AI 编程 Agent 的 skill 作品集（13 个 skill，约 60 个可执行脚本）
- **核查周期**：2026-08-31（首轮，15 skill）+ 2026-09-02（第二轮，逐 skill 复核 14 skill）
- **方法**：危险模式扫描、`subprocess`/`eval`/`shell` 调用逐文件核对、凭证与网络外联盘点、契约测试实跑、上游发布校验实测、能力声明 declared-vs-actual 核对、命令注入修复

---

## 一、原始安全核查核心结论

**未发现高危漏洞。** 该仓库在"会被 Agent 自动执行"的场景下，安全卫生明显优于平均水平：

| 控制项 | 结果 |
|---|---|
| 命令注入 | ✅ 所有 `subprocess.run` 均用 argv 列表；无 `shell=True`、无 `os.system`、无 `eval()`/`exec()`、无 `curl\|bash` |
| 明文密钥 | ✅ 未发现问题硬编码 `api_key`/`secret`/`token`（唯一命中为测试 fixture） |
| 凭证权限 | ✅ `bridge.py` 写文件默认 `0600`；`secure_directory` 强制 `0700`；`wechat-styler` 日志 redact token |
| 外联最小化 | ✅ 外联 skill 均仅访问功能必需端点（含 `127.0.0.1` loopback），凭证取自环境变量/浏览器会话 |
| 桥接边界 | ✅ `workbuddy-cli-model-bridge` 仅 `127.0.0.1:8317`，显式检测非安全绑定 |
| 滥用禁止 | ✅ SKILL 明确禁止 ban evasion / 账号共享 / token 提取 / 流量伪装 |
| 输入安全门 | ✅ `gpt56-sol-pro-consult` 咨询前强制 `check_packet_safety.py` |
| 安装不静默 | ✅ 依赖缺失仅报错提示，不自动 `pip install` |

---

## 二、四轮整改清单闭环状态

| # | 整改项 | 提交 | 交付物 | 状态 |
|---|---|---|---|---|
| 1 | 仓库级安全披露 | `b4f0e14`（+`45d8d4c` 脱敏） | `SECURITY.md`：外联/凭证/持久化统一清单 | ✅ 已闭环 |
| 2 | theme-studio 证据缺口（证据已补；该 skill 后于 2026-09-01 从仓库彻底移除） | `083d230` | `security/independent-review-2026-08-31.md` + `trust-baseline.md`（随 skill 一并移除） | ✅ 已闭环（经删除消解） |
| 3 | Node 依赖锁定 + SBOM | `8722405` | `sbom.cyclonedx.json`×3 + `scripts/gen-node-sbom.mjs` + 修正全局安装指令 | ✅ 已闭环 |
| 4 | CLIProxyAPI/wcx 上游校验 | `053cf68` | `verify-upstream` 命令 + `security-boundaries.md` 上游信任专节 | ✅ 已闭环 |

> 配套：因推送受 R1 guard 拦截，已按授权在守卫中新增 `zhijian-skills` 的 **仅 `git push`** 白名单（仓库级、其余破坏性 Git 仍拒绝），并写入 `R1_GUARD_WHITELIST.md`。

---

## 三、整改项关键事实

- **#1**：原报告误判"部分 skill 缺 lockfile"——实际 `wechat-article-search`/`wechat-styler` 均带 `package-lock.json`（lockfileVersion 3）。真实缺口是 `wechat-article-search` 仍写 `npm install -g cheerio`，已改为遵循锁文件的 `npm ci`。
- **#2（历史）**：上述 `tests/run-tests.sh` 与 live macOS doctor 属于已移除的 `codex-theme-studio`；其 live 验证结论不再适用于当前仓库（该 skill 已于 2026-09-01 彻底删除）。
- **#3**：SBOM 为 CycloneDX 1.5，直接从锁文件生成（含 purl / SHA-512 / dev 标记），可复现、无需联网。
- **#4**：CLIProxyAPI 经 Homebrew 安装，由 Homebrew 校验 bottle **SHA256**（真实 checksum）；wcx 为 git commit 固定（内容寻址，`pip` 强制校验），但上游**无签名发布物**。

---

## 四、残留风险与诚实边界

| 项 | 性质 | 处置 |
|---|---|---|
| `codex-theme-studio` 已从仓库彻底移除（2026-09-01） | 范围变更 | 该 skill 及其证据/文档已从 `skills/`、`docs/skills/`、`docs/changelogs/`、`registry/skills.json`、README 双语文档、SECURITY/COMPLIANCE 引用中移除；其原 live-only 缺口随删除一并消解 |
| `wcx` 无上游签名 | 上游现状，超出仓库能力 | 文档化 + `verify-upstream` 可复核 + 升级需审慎 review |
| Python 侧 SBOM 已生成且依赖已固定 | 范围限定 | `sbom.python.cyclonedx.json` 已产出（CycloneDX 1.5，AST 扫描 + `requirements.txt`）；`wcx` 锁 commit、`playwright==1.62.0`、`weasyprint==69.0` 均已固定 |
| 功能性外联（metaso.cn / mp.weixin.qq.com / chatgpt.com） | skill 固有需求 | 已在 `SECURITY.md` 逐条披露，凭证均取自环境变量或浏览器会话 |
| R1 guard push 白名单 | 用户授权的安全控制修改 | 已收窄为仅 `git push`、仅本仓库，其余破坏性 Git 仍拒绝 |
| `codex-skill-admin` 备份目录/文件未设 `0700`/`0600` | 已修复 | 2026-09-02：`backup_dir`→`0o700`、`write_private_json`→`0o600`（功能验证通过） |
| `workbuddy-cli-model-bridge` `--proxy-url` 未强制 loopback | 已修复 | 2026-09-02：新增 `validate_loopback_url()` 拒绝非 loopback（2 个新单测覆盖） |
| `leadbook` `--allow-remote-base-url` 可选远程 | 已门控的可选越界 | 需显式 flag + `validate_base_url` 校验，保持门控 |

---

## 五、第二轮逐 skill 审计（2026-09-02，14 skill）

对 `codex-theme-studio` 移除后的 14 个 skill 做逐 skill 静态审查 + 离线测试实跑 + 能力声明核对，分 4 组并行审计。

### 5.1 关键发现

| # | 发现 | 严重度 | 处置 |
|---|---|---|---|
| 1 | `wechat-styler/scripts/generate-preview.mjs` 用 `execSync` 字符串命令插值用户路径（`articlePath`/`outputPath`），存在命令注入面，且违反 `SECURITY.md §1`"无 shell" 保证 | **高** | ✅ **已修复**：改为 `execFileSync` argv 列表；`npm test` 31/31 通过 |
| 2 | `wechat-article-search` 存在未披露出站（`weixin.sogou.com` / `v.sogou.com`）；`filesystem` 声明 `read` 实为 `write`、`subprocess` 声明 `required` 实为 `none` | 中 | ✅ 出站已补入 `SECURITY.md §2`；registry 声明已修正 |
| 3 | `codex-skill-admin` 声明 `filesystem:read` 实为 `write`（apply 模式写 `${CODEX_HOME}/backup/`） | 中 | ✅ registry 已修正；备份权限已加固（`backup_dir`→`0o700`、`write_private_json`→`0o600`，2026-09-02） |
| 4 | `workbuddy-cli-model-bridge` `--proxy-url` 未被强制为 loopback（仅默认 127.0.0.1） | 中 | ✅ 已修复：新增 `validate_loopback_url()` 拒绝非 loopback；2026-09-02，28/28 测试通过 |
| 5 | `wechat-styler` 存在未披露出站：`<img src>` 任意图床 `fetch` + PicGo loopback `127.0.0.1:36677` | 中 | ✅ 已补入 `SECURITY.md §2` |
| 6 | `workbuddy-cli-model-bridge` 的 `api.github.com` 探针（`verify-upstream --check-reachability`）未列入 §2 | 低 | ✅ 已补入 `SECURITY.md §2` |
| 7 | `leadbook` `--allow-remote-base-url` 可选将短期 token 发往非 loopback | 低 | 已门控（`validate_base_url` + 显式 flag），保持 |
| 8 | `codex-model-routing-team` 声明 `filesystem:write`/`credentials:required` 偏"过述"（打包脚本不写盘、凭证不落盘） | 低 | ℹ️ 无安全违规，保留声明（harness 侧写盘） |

### 5.2 离线测试结果（2026-09-02 实跑）

| Skill | 测试 | 结果 |
|---|---|---|
| codex-doctor | `python3 -m unittest discover -s skills/codex-doctor/tests` | 22 passed |
| codex-handoff | `… skills/codex-handoff/tests` | 5 passed |
| codex-model-routing-team | `tests.skills.test_codex_model_routing_team` | 34 passed |
| codex-skill-admin | 无单测（仅 live_smoke） | N/A（需 harness） |
| html-express | 无单测 | N/A |
| light-plan-and-work | `… skills/light-plan-and-work/tests` | 5 passed |
| leadbook | `… skills/leadbook/tests` | 13 passed |
| wechat-article-search | `npm test` | 3 passed |
| wechat-styler | `npm test` | 31 passed（修复后） |
| gpt56-sol-pro-consult | `… skills/gpt56-sol-pro-consult/tests` | 12 passed |
| skill-open-sourcer | `… skills/skill-open-sourcer/tests` | 29 passed |
| workbuddy-cli-model-bridge | `… skills/workbuddy-cli-model-bridge/tests`（python3.12） | 26 passed |
| wxmp-article-harvester | `… skills/wxmp-article-harvester/tests` | 23/25 passed（2 例仅因环境未装 `wcx` CLI 失败，非代码缺陷） |

### 5.3 本轮结论

- 第二轮发现 **1 项高危（命令注入）**，已在同轮修复并附测试实证；当前仓库 **零已知高危**。
- 未披露出站目标已全部补入 `SECURITY.md §2`；能力声明不符项已修正 `registry/skills.json`。
- 剩余为 1 项待办（`leadbook` 远程 opt-in 保持门控），属运营商门控、非自触发，不阻塞使用；#1/#2 两项中危已在本轮修复。

---

## 六、第三轮定向复核（2026-09-02，3 个无自动化测试 skill）

对上一轮中**无离线单测覆盖**的 2 个 skill 做红队复审计：`codex-skill-admin`、`html-express`。

| # | Skill | 发现 | 严重度 | 处置 |
|---|---|---|---|---|
| 1 | `codex-skill-admin` | 上一轮 perms 修复不完整：`--backup-dir` 覆盖路径 `mkdir` 后未 `chmod`（默认 `0o755`）；`backup/` 父目录亦为默认权限 | 中 | ✅ 代码补全：`target_dir.mkdir` 后 `os.chmod(target_dir, 0o700)`，并 `backup_dir()` 内对 `DEFAULT_BACKUP_ROOT` `chmod 0o700`（功能验证通过） |
| 2 | `html-express` | 全 `assets/` 扫描：唯一匹配为本地相对 `@import url("tokens.css")`，无 `<script>`/`<iframe>`/`fetch`/外链 | — | 确认干净，原结论成立 |

---

## 七、整体合规结论

**判定：通过安全合规基线，可投入使用。**

- 原始核查：**无高危漏洞**，且具备多项强安全控制（无命令注入、无明文密钥、凭证权限收紧、外联最小化、显式滥用禁止）。
- 第二轮（2026-09-02）逐 skill 复核：发现 **1 项命令注入高危**，已于同轮修复（`wechat-styler` `execSync`→`execFileSync`，31/31 测试通过），当前 **零已知高危**；未披露出站与能力声明偏差均已闭环。
- 第三轮（2026-09-02）定向复核 2 个无测试 skill：`codex-skill-admin` perms 修复补全；`html-express` 确认干净。当前仓库 **零已知高危**。
- 整改闭环：首轮 4 项整改全部完成；第二、三轮高危均修复，披露缺口已补，registry 已修正。
- 透明度：所有残留项均**显式披露**，未做掩盖；上游无签名属上游现状。
- 过程合规：推送经用户逐次显式授权，R1 guard 白名单为用户可控的安全控制修改，未绕过任何守卫；各轮代码修复与文档更新均为本地可回退变更。

**建议后续（非阻塞）**：① 定期重跑 `verify-upstream`、`gen-node-sbom.mjs` 与 `gen-python-sbom.py` 以跟踪依赖漂移，并在升级 `playwright` / `weasyprint` 时同步更新 `requirements.txt` 与 SBOM。

# Security & Compliance

本文件汇总 `zhijian-skills` 各 skill 的外部网络访问、凭证处理、持久化行为与供应链信任边界，作为安全审计与使用者授权确认的统一清单。

> 范围：仓库 `github.com/huangzigen666/zhijian-skills`（当前 14 个 skill）。
> 最近核查：2026-09-02（逐 skill 静态审查 + 离线测试实跑 + 代码修复）。

---

## 1. 总体安全基线

仓库在 "会被 AI agent 自动执行" 的场景下满足以下强控制：

- **无命令注入**：所有 `subprocess.run` / `execFile` 均使用 argv 列表（非 shell 字符串），无 `shell=True`、无 `os.system`、无 `eval()` / `exec()` 动态执行、无 `curl | bash` / `wget | sh` 远程管道执行。（2026-09-02 修复：`wechat-styler/scripts/generate-preview.mjs` 原以 `execSync` 字符串命令插值用户路径 `articlePath`/`outputPath`，存在命令注入面；已改为 `execFileSync(argv 列表)`，31/31 测试仍通过。）
- **无硬编码密钥**：未发现明文 `api_key` / `secret` / `token`（唯一命中为测试 fixture）。
- **凭证权限收紧**：`bridge.py` 的 `atomic_write` / `save_json` 默认 `mode=0o600`；`wxmp-article-harvester` 的 `secure_directory` 强制 `0o700`；`wechat-styler` 在日志中 redact token。
- **显式禁止滥用**：`workbuddy-cli-model-bridge` 安全边界明示禁止 ban evasion / 账号共享 / token 提取 / 流量伪装。
- **输入安全门**：`gpt56-sol-pro-consult` 在咨询前强制运行 `check_packet_safety.py`，仅凭证类内容默认拦截。
- **安装不静默**：依赖缺失时仅报错并提示用户手动安装，不自动 `pip install` / `npm install -g`。

---

## 2. 外部网络访问（出站清单）

> 2026-09-02 复核：补全了此前未披露的出站目标（搜狗微信、wechat-styler 任意图床 `fetch`、PicGo loopback、workbuddy 的 `api.github.com` 探针、leadbook/skill-open-sourcer/codex-skill-admin 的 loopback 与 GitHub 出站）。

| Skill | 目标 | 协议/用途 | 凭证来源 | 证据 |
|---|---|---|---|---|
| `wxmp-article-harvester` | `https://metaso.cn/api/v1/reader` | 文章数据 POST 至第三方 AI 阅读服务 | `METASO_API_KEY` 环境变量（Bearer） | `metaso_reader.py` |
| `wxmp-article-harvester` | `https://mp.weixin.qq.com/` | 公众号后台扫码登录（Playwright） | 浏览器二维码登录，`wcx` 接管 | `refresh_token_playwright.py` |
| `wxmp-article-harvester` | `https://github.com/lovstudio/wcx.git` | `wcx` 依赖安装源 | 无 | `runtime_paths.py` |
| `wechat-styler` | `https://mp.weixin.qq.com/` | 浏览器内（opencli）发布/排版 | 浏览器会话 profile（不落盘明文） | `wechat-opencli.mjs` |
| `wechat-styler` | 任意 `https?://` 图床（`fetch` 抓取 `<img src>`） | 远程图片优化/重传 | 无 | `wechat-image-pipeline.mjs:23` |
| `wechat-styler` | `http://127.0.0.1:36677/upload` | PicGo loopback 图片重传 | 无（loopback） | `wechat-image-pipeline.mjs:98,136` |
| `wechat-article-search` | `https://weixin.sogou.com` | 搜狗微信搜索（匿名） | 无（UA 池 + 匿名 cookie） | `search_wechat.js:636` |
| `wechat-article-search` | `https://v.sogou.com` | 获取会话 cookie | 无 | `search_wechat.js:168` |
| `gpt56-sol-pro-consult` | `https://chatgpt.com/` | 浏览器内（opencli）打开对话 | 浏览器会话 | `run_gpt56_sol_pro_consult.py:346` |
| `workbuddy-cli-model-bridge` | `http://127.0.0.1:8317` | **仅 loopback**，CLIProxyAPI 本地代理 | 本地代理 client key（0600） | `bridge.py` |
| `workbuddy-cli-model-bridge` | `https://api.github.com/repos/lovstudio/wcx/commits/<commit>` | `verify-upstream --check-reachability` 探针（可选，离线默认不触发） | 无 | `bridge.py:1320` |
| `leadbook` | `http://127.0.0.1:18060` | **loopback** `xiaohongshu-mcp` REST（除非 `--allow-remote-base-url`） | 无；URL 强制不含凭证 | `xhs-research.py:24` |
| `skill-open-sourcer` | `github.com/zjp1997720/zhijian-skills` | `git`/`gh` 同步与发布 | 环境 `gh`/git 凭证（skill 不读取） | `git_sync_guard.py` |
| `codex-skill-admin` | `ws://127.0.0.1:<port>` / `http://127.0.0.1:<port>/readyz` | 本地 `codex app-server`（loopback） | 无（继承本地会话） | `codex_skill_admin.py:57,74` |
| `codex-model-routing-team` | `127.0.0.1` / `localhost`（loopback） | `model_preflight.py` 可选 canary 探针，拒绝非 loopback 与含凭证 URL | 环境变量 Bearer（不落盘/不打印） | `model_preflight.py:103-116,147` |
| `enterprise-clone-builder` | （无仓库内代码外联） | 网络/子进程**完全委托**给仓库外的 `web-clipper` skill（`bash "$WEB_CLIPPER_ROOT/scripts/run_web_clipper.sh" --url "<url>"`） | 无（由 web-clipper 自行处理） | `references/web-clipper-usage.md` |
| `codex-doctor` | 无脚本级外联 | 网络可达性由 `codex doctor --json` 子进程产生 | 无 | `scan_workspace.py:1080` |
| `html-express` / `light-plan-and-work` | 无 | 纯静态/指引，无外联、无子进程 | 无 | — |

**合规说明**：所有涉及外联的 skill 均为功能所必需；凭证均取自环境变量或浏览器会话，无硬编码密钥；除 `enterprise-clone-builder` 委托外部依赖外，出站目标均已在上表逐条列出。建议使用者逐条确认授权。

**已知局限与加固**：`enterprise-clone-builder` 的实际外联/子进程面存在于仓库外的 `web-clipper`，本仓库无法静态核验（继承性审计盲区）。**但本仓库的调用方式本身存在命令注入风险**：`bash "$WEB_CLIPPER_ROOT/...sh" --url "<url>"` 把 `WEB_CLIPPER_ROOT` 与 `--url` 直接代入双引号 shell 字符串，若含 `"`/shell 元字符（来自抓取内容或不可信输入）即 RCE。已在 `SKILL.md`「安全约束」与 `references/web-clipper-usage.md`「安全约束」强制：**`WEB_CLIPPER_ROOT` 仅限受信绝对路径 `[A-Za-z0-9._/-]`**、**`--url` 须为严格 `https://` 且不含引号/元字符**、**以位置参数（argv 数组）调用而非拼接 shell 字符串**、**企业名称→目录须净化**、**专用工作目录运行**。属文档层加固（无法修改仓库外 web-clipper）；使用者仍应另行审计 `web-clipper` 本体。

---

## 3. 凭证处理

| 凭证 | 使用位置 | 存储方式 | 风险 |
|---|---|---|---|
| `METASO_API_KEY` | `metaso_reader.py` | 运行时环境变量，**不写入文件** | 低 |
| 微信 MP 登录态 | `wxmp-article-harvester`、`wechat-styler` | 浏览器 profile / `wcx` 托管；目录 `0o700` | 中（账号操作） |
| CLIProxyAPI OAuth + 代理 client key | `workbuddy-cli-model-bridge` | 本地 JSON，写入 `0o600` | 低 |
| WorkBuddy `models.json` | `workbuddy-cli-model-bridge` | 原子更新 `~/.workbuddy/models.json`，保留手动条目 | 低 |

通用原则：
- 从不打印 / 复用 / 转换 OAuth token；token 在日志中以 `[redacted]` 处理。
- 凭证文件权限强制 owner-only。
- 不修改签名应用 bundle、认证态、仓库或会话。

---

## 4. 持久化行为

| Skill | 写入位置 | 范围 | 授权方式 | 合规 |
|---|---|---|---|---|
| `workbuddy-cli-model-bridge` | `~/.config/workbuddy-cli-model-bridge/state.json` + `secret.json`（0600）、`~/.cli-proxy-api/config.yaml`（0600）、`~/.workbuddy/models.json`（0600，带 `.backup-<stamp>`） | 用户家目录 | 用户 `--apply` 显式授权 | ✅ |
| `wxmp-article-harvester` | `~/Library/Application Support/wxmp-article-harvester`（macOS）/ `~/.local/share/...`；`exports/`、`profiles/login`、`profiles/article-browser` | 用户家目录 | 用户执行 | ✅（目录 `0o700`，锁 `0o600`） |
| `codex-skill-admin` | `${CODEX_HOME}/backup/`（备份 JSON：`skills-list-before.json`、`audit.json`、`disable-result.json` 等） | 用户家目录 | `--apply` 显式授权 | ⚠️ 备份目录/文件**未设 0700/0600**（默认 umask）；内容为非密钥诊断信息 |
| `skill-open-sourcer` | `~/.local/state/zhijian-skills/releases/*.json`（加锁、原子替换）、`link-backups/<run>/manifest.json`、对 harness skill 目录（`~/.agents/skills` 等）建立符号链接（先备份、可 `--rollback`） | 用户家目录 / agent 配置 | dry-run/apply 门控；canonical-origin 校验 | ✅ |
| `leadbook` | 书籍工程内 `dist/`、`research/xhs/`、`book-state.yaml`、QA 文件；`protected_target()` 拒绝根/`$HOME`/CWD/skill 目录 | 用户指定工程 | 用户指定目标 | ✅ |
| `wechat-article-search` | `-o` 指定输出文件（任意路径，含家目录外） | 用户指定 | 用户指定 `-o` | ✅（内容非凭证） |
| `wechat-styler` | 输出 HTML（`--output`）、发布报告（`/tmp` 默认）、`os.tmpdir()` 临时目录 | 用户家目录 / tmp | 用户指定 | ✅（profile 由 OpenCLI 管理） |
| `gpt56-sol-pro-consult` | 临时 packet 文件（`tempfile`，`finally` 中清理）、`-o` 附件包 | tmp / 用户指定 | 用户指定 `-o` | ✅ |
| `enterprise-clone-builder` | `{company}-企业分身/` 于**当前工作目录**（默认） | 用户工程（CWD 默认） | 用户指定路径 | ✅（注意默认写入 CWD） |
| `html-express` / `light-plan-and-work` | 用户指定 `.html` / 计划产物 | 用户工程 | 用户指定 | ✅ |
| `codex-doctor` / `codex-handoff` / `codex-model-routing-team` | 无脚本级写入（输出仅 stdout；写盘由 harness 侧按计划/ledger 进行） | — | — | ✅ |

所有持久化均在用户目录 / 工程范围内，未触及系统级路径或他人数据。`codex-skill-admin` 的备份权限为其唯一待加固项（见 §6）。

---

## 5. 供应链与依赖

- **`wcx`**：锁版本 commit `37cf4d5fd6a0677c2137601292f6942ff731d4b9`（已验证存在，见 `wxmp-article-harvester/SKILL.md` 上游信任小节）。git commit 固定为内容寻址，安装时由 `pip` 强制校验；上游无签名发布物，升级需审慎 review。
- **CLIProxyAPI**：经 Homebrew 公式 `cliproxyapi` 安装，非本仓库控制的上游二进制（信任边界）；Homebrew 在安装时校验 bottle SHA256（真实 checksum 机制）。
- **上游校验命令**：`python3 scripts/bridge.py verify-upstream`（离线报告 CLIProxyAPI/wcx 校验态势）；`--check-reachability` 额外探测 wcx 固定提交是否仍可达。详见 `workbuddy-cli-model-bridge/references/security-boundaries.md` 的 "Upstream supply-chain trust"。
- **Node 依赖（已锁定 + SBOM）**：`wechat-article-search`、`wechat-styler` 均含 `package.json` + `package-lock.json`（lockfileVersion 3，已解析完整依赖树）。`wechat-article-search` 的安装指引已从全局 `npm install -g cheerio` 改为遵循锁文件的本地 `npm ci` / `npm install`。每个 Node skill 目录下已生成 `sbom.cyclonedx.json`（CycloneDX 1.5），由 `scripts/gen-node-sbom.mjs` 依据锁文件生成；重新生成：`node scripts/gen-node-sbom.mjs`。
- **Python 依赖（已生成 SBOM）**：仓库无 Python 锁文件，采用 AST import 扫描生成 `sbom.python.cyclonedx.json`（CycloneDX 1.5），由 `scripts/gen-python-sbom.py` 产出；重新生成：`python3.12 scripts/gen-python-sbom.py`。
  - `wcx`（被 `wxmp-article-harvester` 使用）：已锁 commit `37cf4d5fd6a0677c2137601292f6942ff731d4b9` ✅ 已固定。
  - `playwright`（被 `wxmp-article-harvester` 使用）：已固定 `==1.62.0`（`requirements.txt`）。
  - `weasyprint`（被 `leadbook` 使用）：已固定 `==69.0`（`requirements.txt`）。
  - 全部 Python 依赖现由仓库根 `requirements.txt` 统一固定；重新生成 SBOM：`python3.12 scripts/gen-python-sbom.py`。

- **依赖升级流程（Python）**：任何 `playwright` / `weasyprint` / `wcx` 版本变更，或新增 Python 第三方依赖时，必须同步以下两项，二者缺一不可：
  1. 更新仓库根 `requirements.txt` 中的固定版本（新增依赖需补一行 pin；`wcx` 走 `git+https://github.com/lovstudio/wcx.git@<commit>` 形式）。
  2. 重新生成 SBOM：`python3.12 scripts/gen-python-sbom.py`（可选 `--strict`，存在未固定依赖时以非零码退出，便于 CI / pre-commit 拦截）。
  3. 提交 `requirements.txt` 与 `sbom.python.cyclonedx.json` 两个文件（建议同一次提交）。
  - 校验：生成器会扫描所有 `skills/**/*.py` 的 import，凡出现在 `requirements.txt` 之外的第三方依赖都会被标记为 `UNPINNED` 并打印 WARNING；若带 `--strict` 则直接失败，防止未固定依赖被合入。
  - `wcx` 升级额外注意：改动 `requirements.txt` 中的 commit 时，须同步 `wxmp-article-harvester/scripts/runtime_paths.py` 的 `WCX_COMMIT` / `WCX_INSTALL_SPEC`，并运行 `python3 scripts/bridge.py verify-upstream --check-reachability` 确认新提交仍可达。

---

## 6. 能力声明核对（declared-vs-actual）

2026-09-02 逐 skill 复核 `registry/skills.json` 的 `capabilities` 声明与代码实测行为，差异如下：

| Skill | 声明（capabilities） | 实测差异 | 状态 |
|---|---|---|---|
| `wechat-article-search` | `subprocess:required`, `filesystem:read` | 实测**无 subprocess**（用 Node `https` 模块内联抓取）；`-o` 会写输出文件 | ✅ 已修正 registry：`subprocess→none`、`filesystem→write` |
| `codex-skill-admin` | `filesystem:read` | 实测 `--apply` 模式向 `${CODEX_HOME}/backup/` 写备份 JSON，并经 app-server 改 skill 状态 | ✅ 已修正 registry：`filesystem→write`；⚠️ 备份目录/文件未设 0700/0600（见 §7） |
| `codex-model-routing-team` | `filesystem:write`, `credentials:required` | 打包脚本本身不写盘（写盘由 harness 侧计划/ledger 进行）；探针 Bearer 取自 env、不落盘/不打印 | ℹ️ 声明偏"过述"，无安全违规，保留 `write`（harness 侧） |
| 其余 11 个 skill | — | 声明与实测一致 | ✅ |
| `wechat-styler` | （非能力声明项） | 原 `generate-preview.mjs` 用 `execSync` 字符串命令（违反 §1 "无 shell" 保证） | ✅ 已修复为 `execFileSync` argv 列表（2026-09-02） |

此外值得记录的行为偏差（非声明错误，但影响信任边界）：
- `leadbook`：`xhs-research.py --allow-remote-base-url` 可将短期 token 发往非 loopback 服务——需显式 flag + `validate_base_url` 校验，保持门控。
- `workbuddy-cli-model-bridge`：`--proxy-url` 未被强制为 loopback（仅默认 127.0.0.1），非 loopback 值会被写入 `models.json` 并接收 `Bearer <client_key>`——见 §7 待办。

---

## 7. 整改优先级（来自核查）

1. **[中]** 本文件即为仓库级外联/凭证/持久化统一清单——持续维护（2026-09-02 已补全此前未披露的出站目标与持久化面）。
2. **[低]** 为 Node 类 skill 补充依赖锁定与 SBOM（已完成：`wechat-article-search`、`wechat-styler` 含 `package-lock.json` + `sbom.cyclonedx.json`）；Python 侧 SBOM 已生成（`sbom.python.cyclonedx.json`），且 `playwright` / `wcx` / `weasyprint` 均已在 `requirements.txt` 固定版本。
3. **[低]** 确认 `CLIProxyAPI` / `wcx` 上游的发布校验（checksum/签名）。
4. **[高→已修]** `wechat-styler/scripts/generate-preview.mjs` 原 `execSync` 字符串命令（命令注入面，违反 §1 保证）——已改为 `execFileSync` argv 列表（2026-09-02，31/31 测试通过）。
5. **[低→已修]** `registry/skills.json` 中 `wechat-article-search`（`subprocess`/`filesystem`）、`codex-skill-admin`（`filesystem`）声明与实测不符——已修正。
6. **[中→已修]** `codex-skill-admin` 备份目录/文件未设 `0700`/`0600`（默认 umask）——已修复：`backup_dir()` 创建后 `chmod 0o700`，新增 `write_private_json()` 以 `0o600` 写所有备份 JSON（2026-09-02，功能验证 file=0600 / dir=0700）。
7. **[中→已修]** `workbuddy-cli-model-bridge` 的 `--proxy-url` 未被强制为 loopback——已修复：新增 `validate_loopback_url()`，在 `cmd_sync`/`cmd_audit` 处校验 ∈ {127.0.0.1, localhost, ::1}（非 loopback 直接拒绝并附 `proxy_not_loopback` 错误）；新增 2 个单测覆盖接受/拒绝（2026-09-02，28/28 测试通过）。
8. **[低]** `enterprise-clone-builder` 的外联/子进程面完全委托仓库外 `web-clipper`，属继承性审计盲区——建议使用者另行审计 `web-clipper` 并固定 `$WEB_CLIPPER_ROOT`。
9. **[高→已修（文档层）]** `enterprise-clone-builder` 的 `bash "$WEB_CLIPPER_ROOT/...sh" --url "<url>"` 调用把 `WEB_CLIPPER_ROOT`/`--url` 代入双引号 shell 字符串，存在命令注入（RCE）风险——已在 `SKILL.md` 与 `references/web-clipper-usage.md` 新增「安全约束」强制：受信绝对路径 + 严格 https URL 校验 + 位置参数调用 + 企业名目录净化 + 专用工作目录（2026-09-02）。属文档层加固（web-clipper 本体在仓库外，无法在此修复）。
10. **[中→已修]** `codex-skill-admin` 的 `--backup-dir` 覆盖路径此前未 `chmod`（默认 `0o755`）——已补全：`target_dir.mkdir` 后 `os.chmod(target_dir, 0o700)`，并 `backup_dir()` 内对 `DEFAULT_BACKUP_ROOT` 也 `chmod 0o700`（2026-09-02，功能验证通过）。

---

## 8. 漏洞报告

如发现安全漏洞，请勿公开提 issue，通过仓库维护者私信或安全通道报告。报告请包含：复现步骤、受影响 skill、潜在影响与证据（日志/截图）。

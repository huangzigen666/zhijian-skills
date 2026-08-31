# Security & Compliance

本文件汇总 `zhijian-skills` 各 skill 的外部网络访问、凭证处理、持久化行为与供应链信任边界，作为安全审计与使用者授权确认的统一清单。

> 范围：`/private/tmp/zhijian-skills`（origin `github.com/huangzigen666/zhijian-skills`）。
> 最近核查：2026-08-31（静态审查）。

---

## 1. 总体安全基线

仓库在 "会被 AI agent 自动执行" 的场景下满足以下强控制：

- **无命令注入**：所有 `subprocess.run` 均使用 argv 列表（非 shell 字符串），无 `shell=True`、无 `os.system`、无 `eval()` / `exec()` 动态执行、无 `curl | bash` / `wget | sh` 远程管道执行。
- **无硬编码密钥**：未发现明文 `api_key` / `secret` / `token`（唯一命中为测试 fixture）。
- **凭证权限收紧**：`bridge.py` 的 `atomic_write` / `save_json` 默认 `mode=0o600`；`wxmp-article-harvester` 的 `secure_directory` 强制 `0o700`；`wechat-styler` 在日志中 redact token。
- **显式禁止滥用**：`workbuddy-cli-model-bridge` 安全边界明示禁止 ban evasion / 账号共享 / token 提取 / 流量伪装。
- **输入安全门**：`gpt56-sol-pro-consult` 在咨询前强制运行 `check_packet_safety.py`，仅凭证类内容默认拦截。
- **安装不静默**：依赖缺失时仅报错并提示用户手动安装，不自动 `pip install` / `npm install -g`。

---

## 2. 外部网络访问（出站清单）

| Skill | 目标 | 协议/用途 | 凭证来源 | 披露位置 |
|---|---|---|---|---|
| `wxmp-article-harvester` (`metaso_reader.py`) | `https://metaso.cn/api/v1/reader` | 文章数据 POST 至第三方 AI 阅读服务 | `METASO_API_KEY` 环境变量（Bearer） | skill 内 |
| `wxmp-article-harvester` (`refresh_token_playwright.py`) | `https://mp.weixin.qq.com/` | 微信公众号后台扫码登录（Playwright） | 浏览器二维码登录，由 `wcx` CLI 接管 | skill 内 |
| `wxmp-article-harvester` (`runtime_paths.py`) | `https://github.com/lovstudio/wcx.git` | `wcx` 依赖安装源 | 无 | skill 内 |
| `wechat-styler` | `https://mp.weixin.qq.com/` | 浏览器内（opencli）发布/排版操作 | 浏览器会话 profile（不落盘明文） | skill 内 |
| `gpt56-sol-pro-consult` | `https://chatgpt.com/` | 浏览器内（opencli）打开对话 | 浏览器会话 | skill 内 |
| `workbuddy-cli-model-bridge` | `http://127.0.0.1:8317` | **仅 loopback**，CLIProxyAPI 本地代理 | 本地代理 client key（0600） | skill / `bridge.py` |
| `codex-theme-studio` | `127.0.0.1`（Chrome DevTools） | **仅 loopback**，本地 CDP 注入/校验 | 无 | `security/network_policy.json`（`outbound_internet: deny`） |

**合规说明**：除 `codex-theme-studio` 明确声明 `outbound_internet: deny` 外，其余涉及外联的 skill 均为功能所必需，且凭证均取自环境变量或浏览器会话，无硬编码。建议使用者对上表逐条确认授权。

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

| Skill | 行为 | 授权方式 | 合规 |
|---|---|---|---|
| `codex-theme-studio` | 可选 LaunchAgent `~/Library/LaunchAgents`；owner-only 恢复态 `~/Library/Application Support/CodexThemeStudio`；写入 `~/.codex/codex-theme-studio` | **显式 opt-in + 独立持久化授权**，不主动启动应用 | ✅ 已 gate |
| `workbuddy-cli-model-bridge` | 启动 CLIProxyAPI loopback 服务（Homebrew 安装） | 用户 `--apply` 显式授权 | ✅ |
| `codex-theme-studio` 脚本 `rm -rf` | 删除 `$INSTALL_ROOT.installing.$$` / `.previous.$$` 等派生临时目录 | 目标由固定 `INSTALL_ROOT` 派生，非用户可控 | ✅ 无宽泛删除 |

所有持久化均为用户目录范围内，未触及系统级路径或他人数据。

---

## 5. 供应链与依赖

- **`wcx`**：锁版本 commit `37cf4d5fd6a0677c2137601292f6942ff731d4b9`（已验证存在，见 `wxmp-article-harvester/SKILL.md` 上游信任小节）。git commit 固定为内容寻址，安装时由 `pip` 强制校验；上游无签名发布物，升级需审慎 review。
- **CLIProxyAPI**：经 Homebrew 公式 `cliproxyapi` 安装，非本仓库控制的上游二进制（信任边界）；Homebrew 在安装时校验 bottle SHA256（真实 checksum 机制）。
- **上游校验命令**：`python3 scripts/bridge.py verify-upstream`（离线报告 CLIProxyAPI/wcx 校验态势）；`--check-reachability` 额外探测 wcx 固定提交是否仍可达。详见 `workbuddy-cli-model-bridge/references/security-boundaries.md` 的 "Upstream supply-chain trust"。
- **Node 依赖（已锁定 + SBOM）**：`codex-theme-studio`、`wechat-article-search`、`wechat-styler` 均含 `package.json` + `package-lock.json`（lockfileVersion 3，已解析完整依赖树）。`wechat-article-search` 的安装指引已从全局 `npm install -g cheerio` 改为遵循锁文件的本地 `npm ci` / `npm install`。每个 Node skill 目录下已生成 `sbom.cyclonedx.json`（CycloneDX 1.5），由 `scripts/gen-node-sbom.mjs` 依据锁文件生成；重新生成：`node scripts/gen-node-sbom.mjs`。
- **Python 依赖**：`playwright`（pip）、各 skill 自有脚本；`wxmp-article-harvester` 的 `wcx` 已锁 commit。Python 侧 SBOM 暂未生成（本项范围限于 Node skill）。

---

## 6. 已知证据缺口（透明度）

依据 `codex-theme-studio/security/trust-baseline.md` 的自述，以下证据**仍缺失**，不影响当前代码合规判断，但作为合规交付物应补齐：

- 独立安全评审证据（missing）
- 干净 macOS 账号现场安装器验证（missing）
- 各 host 的 ImageGen 调用验证（missing）

---

## 7. 整改优先级（来自核查）

1. **[中]** 本文件即为仓库级外联/凭证/持久化统一清单——持续维护。
2. **[中]** `codex-theme-studio` 补 "现场安装器验证" 与 "独立安全评审" 证据，闭合 trust-baseline 缺口。
3. **[低]** 为 Node 类 skill 补充依赖锁定与 SBOM。
4. **[低]** 确认 `CLIProxyAPI` / `wcx` 上游的发布校验（checksum/签名）。

---

## 8. 漏洞报告

如发现安全漏洞，请勿公开提 issue，通过仓库维护者私信或安全通道报告。报告请包含：复现步骤、受影响 skill、潜在影响与证据（日志/截图）。

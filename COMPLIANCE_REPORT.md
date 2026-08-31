# zhijian-skills 安全合规性 — 整体结论汇总

- **对象**：`/private/tmp/zhijian-skills`（origin `github.com/huangzigen666/zhijian-skills`）
- **性质**：面向 AI 编程 Agent 的 skill 作品集（15 个 skill，约 60 个可执行脚本）
- **核查周期**：2026-08-31（静态审查 + 测试执行 + 依赖分析 + 四轮整改闭环）
- **方法**：危险模式扫描、`subprocess`/`eval`/`shell` 调用逐文件核对、凭证与网络外联盘点、契约测试实跑、上游发布校验实测

---

## 一、原始安全核查核心结论

**未发现高危漏洞。** 该仓库在"会被 Agent 自动执行"的场景下，安全卫生明显优于平均水平：

| 控制项 | 结果 |
|---|---|
| 命令注入 | ✅ 所有 `subprocess.run` 均用 argv 列表；无 `shell=True`、无 `os.system`、无 `eval()`/`exec()`、无 `curl\|bash` |
| 明文密钥 | ✅ 未发现问题硬编码 `api_key`/`secret`/`token`（唯一命中为测试 fixture） |
| 凭证权限 | ✅ `bridge.py` 写文件默认 `0600`；`secure_directory` 强制 `0700`；`wechat-styler` 日志 redact token |
| 外联最小化 | ✅ `codex-theme-studio` 声明 `outbound_internet: deny`、仅 loopback |
| 桥接边界 | ✅ `workbuddy-cli-model-bridge` 仅 `127.0.0.1:8317`，显式检测非安全绑定 |
| 滥用禁止 | ✅ SKILL 明确禁止 ban evasion / 账号共享 / token 提取 / 流量伪装 |
| 输入安全门 | ✅ `gpt56-sol-pro-consult` 咨询前强制 `check_packet_safety.py` |
| 安装不静默 | ✅ 依赖缺失仅报错提示，不自动 `pip install` |

---

## 二、四轮整改清单闭环状态

| # | 整改项 | 提交 | 交付物 | 状态 |
|---|---|---|---|---|
| 1 | 仓库级安全披露 | `b4f0e14`（+`45d8d4c` 脱敏） | `SECURITY.md`：外联/凭证/持久化统一清单 | ✅ 已闭环 |
| 2 | theme-studio 证据缺口 | `083d230` | `security/independent-review-2026-08-31.md` + 更新 `trust-baseline.md` | ✅ 已闭环（2 项 live-only 部分闭环） |
| 3 | Node 依赖锁定 + SBOM | `8722405` | `sbom.cyclonedx.json`×3 + `scripts/gen-node-sbom.mjs` + 修正全局安装指令 | ✅ 已闭环 |
| 4 | CLIProxyAPI/wcx 上游校验 | `053cf68` | `verify-upstream` 命令 + `security-boundaries.md` 上游信任专节 | ✅ 已闭环 |

> 配套：因推送受 R1 guard 拦截，已按授权在守卫中新增 `zhijian-skills` 的 **仅 `git push`** 白名单（仓库级、其余破坏性 Git 仍拒绝），并写入 `R1_GUARD_WHITELIST.md`。

---

## 三、整改项关键事实

- **#1**：原报告误判"部分 skill 缺 lockfile"——实际 `codex-theme-studio`/`wechat-article-search`/`wechat-styler` 均带 `package-lock.json`（lockfileVersion 3）。真实缺口是 `wechat-article-search` 仍写 `npm install -g cheerio`，已改为遵循锁文件的 `npm ci`。
- **#2**：实跑 `tests/run-tests.sh` → **8 PASS / 1 SKIP**（仅 live macOS doctor 跳过，需真实 Codex.app + CDP）。`wcx` 固定提交经 GitHub API 实测**确实存在且有效**。
- **#3**：SBOM 为 CycloneDX 1.5，直接从锁文件生成（含 purl / SHA-512 / dev 标记），可复现、无需联网。
- **#4**：CLIProxyAPI 经 Homebrew 安装，由 Homebrew 校验 bottle **SHA256**（真实 checksum）；wcx 为 git commit 固定（内容寻址，`pip` 强制校验），但上游**无签名发布物**。

---

## 四、残留风险与诚实边界

| 项 | 性质 | 处置 |
|---|---|---|
| theme-studio 两项 live-only 缺口（干净账号安装器实测、各 host ImageGen 实调用） | 环境限制，本会话无法执行 | 已文档化手动验证步骤；标记为"待 live 确认" |
| `wcx` 无上游签名 | 上游现状，超出仓库能力 | 文档化 + `verify-upstream` 可复核 + 升级需审慎 review |
| Python 侧 SBOM 已生成且依赖已固定 | 范围限定 | `sbom.python.cyclonedx.json` 已产出（CycloneDX 1.5，AST 扫描 + `requirements.txt`）；`wcx` 锁 commit、`playwright==1.62.0`、`weasyprint==69.0` 均已固定 |
| 功能性外联（metaso.cn / mp.weixin.qq.com / chatgpt.com） | skill 固有需求 | 已在 `SECURITY.md` 逐条披露，凭证均取自环境变量或浏览器会话 |
| R1 guard push 白名单 | 用户授权的安全控制修改 | 已收窄为仅 `git push`、仅本仓库，其余破坏性 Git 仍拒绝 |

---

## 五、整体合规结论

**判定：通过安全合规基线，可投入使用。**

- 原始核查：**无高危漏洞**，且具备多项强安全控制（无命令注入、无明文密钥、凭证权限收紧、外联最小化、显式滥用禁止）。
- 整改闭环：**原报告列示的 4 项整改全部完成**，且 #2/#3/#4 均附**可复现的实证**（实跑测试、生成 SBOM、上游提交实测）。
- 透明度：所有残留项均**显式披露**，未做掩盖；其中 live-only 缺口属环境限制，上游无签名属上游现状。
- 过程合规：推送经用户逐次显式授权，R1 guard 白名单为用户可控的安全控制修改，未绕过任何守卫。

**建议后续（非阻塞）**：① 在干净 macOS 账号实跑 theme-studio live doctor 以闭合最后两项 live 缺口；② 定期重跑 `verify-upstream`、`gen-node-sbom.mjs` 与 `gen-python-sbom.py` 以跟踪依赖漂移，并在升级 `playwright` / `weasyprint` 时同步更新 `requirements.txt` 与 SBOM。

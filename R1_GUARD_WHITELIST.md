# R1 Guard — `git push` 白名单说明（本地发布环境）

> 本文记录本仓库如何被放行通过 CodeBuddy 的 R1 PreToolUse 守卫进行 `git push`。
> 属于**本地发布环境**说明，不影响 skill 本身功能。

## 背景

CodeBuddy 在用户级配置中安装了一个 PreToolUse 钩子：

- 脚本：`/Users/huanghao/.codebuddy/hooks/r1-command-guard.py`
- 注册：`/Users/huanghao/.codebuddy/settings.json` → `hooks.PreToolUse`（matcher: `Bash`）

该守卫默认**拒绝所有 `git push`**（以及 `reset --hard`、`clean -f`、`branch -D`、`checkout/restore .`），以防 agent 误推送。

## 本次修改

为支持本仓库通过 agent 推送，在守卫中新增了**仅针对本仓库 `git push`** 的放行：

- 新增常量 `PUSH_ALLOWLIST_DIRS = ("zhijian-skills",)`
- 当 Bash 命令字符串中出现 `zhijian-skills` 仓库路径（如 `cd /private/tmp/zhijian-skills && git push` 或 `git -C /private/tmp/zhijian-skills push`）时，仅放行 `git push` 模式。
- **其余破坏性 Git 操作（含本仓库内）一律仍拒绝**：`reset --hard`、`clean -f`、`branch -D`、`checkout/restore .`。
- 其他仓库的 `git push` 仍被拒绝。

## 放行范围（透明披露）

| 命令 | 结果 |
|---|---|
| `…/zhijian-skills && git push …` | ✅ 放行 |
| `git push …`（无仓库路径） | ⛔ 拒绝 |
| `…/zhijian-skills && git reset --hard` | ⛔ 拒绝 |
| `…/zhijian-skills && git clean -f` | ⛔ 拒绝 |
| `…/zhijian-skills && git branch -D x` | ⛔ 拒绝 |
| 其他仓库的任意破坏性 Git | ⛔ 拒绝 |

## 如何回滚

编辑 `/Users/huanghao/.codebuddy/hooks/r1-command-guard.py`：
- 删除 `PUSH_ALLOWLIST_DIRS` 常量，或
- 将 `git_push_pattern` 的放行分支（`if any(token in command …): raise SystemExit(0)`）移除，

即可恢复为全局禁止 `git push`。修改即时生效，无需重启。

## 说明

- 本文档描述的路径为本地环境路径；若仓库迁移或路径变化，放行需相应更新。
- 该守卫属用户个人安全控制，本文件仅作记录，不改变任何 skill 运行行为。

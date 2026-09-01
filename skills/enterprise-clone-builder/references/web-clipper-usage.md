# web-clipper 调用方式

本 skill 的联网调研步骤依赖 web-clipper skill 进行网页抓取。如果你已安装 web-clipper，按以下方式调用。

## ⚠️ 安全约束（务必先读 SKILL.md 的「安全约束」小节）

`bash "$WEB_CLIPPER_ROOT/...sh" --url "<url>"` 会把 `WEB_CLIPPER_ROOT` 与 `--url` 直接代入一个 **双引号 shell 字符串**。若其中任一值含 `"` 或 shell 元字符（来自抓取的网页、会话历史或不可信输入），会发生**命令注入（RCE）**。调用前必须：

1. **校验 `WEB_CLIPPER_ROOT`**：仅允许绝对路径且字符集为 `[A-Za-z0-9._/-]`，拒绝任何引号/`$`/`` ` ``/`;`/空格等。
2. **校验 `--url`**：仅允许 `https://` 开头且不含 `" ' $ ` ` ; | & ( ) < > 换行 空格` 的 URL；从抓取结果提取的子链接、对话中给的"官网 URL"都须先过此校验，不通过即中止。
3. **用位置参数调用，不拼字符串**：用包装函数 `exec "$WEB_CLIPPER_ROOT/scripts/run_web_clipper.sh" "$@"` 把 `--url` 作为单一位置参数传入，避免把整条命令拼成 `bash -c "…"`。

下面的示例均默认 `<你的web-clipper路径>` 与 `<url>` 已通过上述校验。

## 入口脚本

```bash
# 替换为你的 web-clipper 安装路径（须为受信绝对路径，仅含 [A-Za-z0-9._/-]）
WEB_CLIPPER_ROOT="<你的web-clipper路径>"
bash "$WEB_CLIPPER_ROOT/scripts/run_web_clipper.sh"
```

在你的**专用工作目录**下执行，不要在当前工作目录（CWD）直接产出。

## 单篇抓取

```bash
bash "<WEB_CLIPPER_ROOT>/scripts/run_web_clipper.sh" \
  --url "https://example.com/article" \
  --mode single \
  --output-dir "目标输出目录" \
  --tag "企业名"
```

## 批量抓取（从URL文件）

```bash
# 先准备URL列表文件
cat > /tmp/enterprise_urls.txt << 'EOF'
https://example.com/page1
https://example.com/page2
https://example.com/page3
EOF

# 执行批量抓取
bash "<WEB_CLIPPER_ROOT>/scripts/run_web_clipper.sh" \
  --url-file /tmp/enterprise_urls.txt \
  --mode batch \
  --count 20 \
  --output-dir "目标输出目录" \
  --tag "企业名" \
  --summary-json "/tmp/harvest-summary.json"
```

## 批量抓取（从索引页提取子链接）

```bash
bash "<WEB_CLIPPER_ROOT>/scripts/run_web_clipper.sh" \
  --url "https://example.com/products.html" \
  --mode batch \
  --count 15 \
  --output-dir "目标输出目录" \
  --tag "企业名"
```

脚本会自动从索引页提取子链接并逐个抓取（子链接由脚本内部处理，**不要**把它们再拼回新的 `--url "…"` shell 命令）。

## builder 中的抓取策略

### 官网抓取

1. 先抓首页（single模式）
2. 找到产品列表页，批量抓取（batch模式，从索引页提取子链接，count=15-20）
3. 找到新闻列表页，批量抓取（batch模式，count=15-20）

### 第三方平台

搜索企业名称，找到百科、B2B平台等，single模式逐个抓取。

百度百科可能失败（反爬），失败则标注，不阻塞流程。

### 抓取后处理

1. 检查 summary-json 中的成功/失败统计
2. 成功的文件按来源分类移动到仓库的 `02-原始素材/` 对应子目录
3. 失败的URL记录到 source-map.md
4. 清理临时文件（/tmp下的url列表和summary）

## 输出格式

每个URL产出一个 .md 文件，包含：
- YAML frontmatter（source/resource/extractor/tags等）
- 正文（Markdown格式）

文件名格式：`{published} {title}.md` 或 `unknown-date {title}.md`

保留原始文件名和frontmatter，不做修改。

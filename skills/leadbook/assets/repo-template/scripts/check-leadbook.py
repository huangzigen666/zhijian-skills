#!/usr/bin/env python3
"""Leadbook quality checks for reader-facing prose, evidence, visuals, and package state."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


HARD_CTA = [
    "加企微",
    "添加企微",
    "加微信",
    "添加微信",
    "领取资料",
    "购买课程",
    "报名课程",
    "咨询我",
    "私信我",
]

CLICHE = [
    "赋能",
    "重构",
    "拥抱",
    "范式",
    "生态",
    "闭环",
    "抓手",
    "破局",
    "底层逻辑",
    "认知升级",
    "打造",
    "全链路",
]

INTERNAL_TERMS = [
    "SOURCE_MAP",
    "CLAIM_LEDGER",
    "CASE_LIBRARY",
    "BEHAVIOR_LEDGER",
    "TRANSACTION_LEDGER",
    "Layer A",
    "Layer B",
    "Layer C",
    "Layer D",
    "L1-fact",
    "L2-demand",
    "L3-behavior",
    "L4-transaction",
    "L5-discourse",
    "L6-owned",
    "A-authority",
    "B-demand",
    "C-discourse",
    "D-local-context",
    "高权重来源",
    "需求侧样本",
    "行为层样本",
    "交易层样本",
    "公众号元数据",
    "文章池",
    "抓取结果",
    "小红书样本",
    "线索",
    "适合放在",
]

BAD_DRAFT_PHRASES = [
    "待填写",
    "后续补",
    "这里先提炼",
    "可以继续使用",
    "待补充",
    "待完善",
]

CHAPTER_CONTRACT = {
    "结论/判断": ["本章结论", "结论", "判断"],
    "读者问题": ["读者真实问题", "读者问题", "真实问题", "处境", "读者场景", "卡在哪里", "卡点"],
    "证据/来源": ["证据", "来源", "事实", "数据", "公开"],
    "案例/反例": ["案例", "反例", "场景"],
    "行动产出": ["本章产出", "操作方法", "行动", "步骤", "清单", "模板", "自测"],
    "作者判断": ["作者判断", "我的判断", "我认为", "边界"],
}

HANDBOOK_H2_HEADINGS = ["本章结论", "本章产出", "常见误区", "操作方法", "自测问题", "本章小结"]
HANDBOOK_WORKBOOK_HEADINGS = ["本章产出", "操作方法", "自测问题"]
STRICT_BOOK_FEEL_PROFILES = {"whitepaper", "methodology-book", "business-report"}
BOOK_OPENING_MIN_UNITS = 180

LOCAL_CONTEXT_MARKERS = [
    "Nowledge",
    "nowledge",
    "Obsidian",
    "obsidian",
    "Vault",
    "vault",
    "memory",
    "Memory",
    "D-local-context",
    "L6-owned",
    "自有层",
]

DEMAND_MARKERS = [
    "小红书",
    "xiaohongshu",
    "xhs",
    "B-demand",
    "L2-demand",
    "需求层",
]

DISCOURSE_MARKERS = [
    "公众号",
    "wxmp",
    "wechat",
    "C-discourse",
    "L5-discourse",
    "观点层",
]

FACT_AUTHORITY_MARKERS = [
    "A-authority",
    "L1-fact",
    "事实层",
    "official",
    "report",
    "官方",
    "报告",
]

AUTHORITY_STATUS_MARKERS = [
    "selected",
    "fetched",
    "exported",
    "done",
    "已选",
    "已抓取",
    "已导出",
]

MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
DIAGRAM_TOKEN_RE = re.compile(r"\{\{\s*kami-diagram:([a-zA-Z0-9_.-]+)\s*\}\}")
SECTION_IMAGE_TOKEN_RE = re.compile(r"\{\{\s*section-image:([a-zA-Z0-9_.-]+)\s*\}\}")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
STATE_RE = re.compile(r"^([a-z_]+):\s*\"?([^\"\n]+)\"?\s*$")
YAML_KV_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
URL_RE = re.compile(r"https?://[^\s<>|)\]`\"]+")

TARGETS = ("draft", "review-ready", "publish-ready")
CURRENT_YEAR = date.today().year
RECENT_SOURCE_YEAR_FLOOR = CURRENT_YEAR - 3
MIN_REVIEW_CHAPTERS = 3
MIN_PUBLISH_CHAPTERS = 5
MIN_DRAFT_CHAPTERS = 1
MIN_DRAFT_TOTAL_UNITS = 300
MIN_PUBLISH_TOTAL_UNITS = 9000
MIN_PUBLISH_CHAPTER_UNITS = 1000
MIN_BEHAVIOR_SIGNALS = 3
MIN_TRANSACTION_SIGNALS = 3
MIN_REVIEW_BIBLIOGRAPHY_ENTRIES = 6
MIN_PUBLISH_BIBLIOGRAPHY_ENTRIES = 8
MIN_REVIEW_PUBLIC_BIBLIOGRAPHY_ENTRIES = 5
MIN_PUBLISH_PUBLIC_BIBLIOGRAPHY_ENTRIES = 6
TRUTHY_STATE = {
    "true",
    "yes",
    "done",
    "ready",
    "complete",
    "completed",
    "full",
    "generated",
    "exported",
    "passed",
    "review-ready",
    "publish-ready",
}
PARTIAL_STATE = {"partial", "rate-limited", "blocked", "false", "no", "planned", "todo", "not-started"}
WXMP_CLOSED_STATE = {"true", "yes", "done", "ready", "complete", "completed", "full", "passed"}
OWNED_REFERENCE_MARKERS = [
    "自有案例",
    "作者经验",
    "实践经验",
    "作者在",
    "作者的",
    "不作为行业通用事实",
    "Nowledge",
    "Obsidian",
    "Vault",
]
USED_SOURCE_STATES = {"used", "selected", "fetched", "exported", "done", "已选", "已抓取", "已导出"}
AUDIT_CHECKED_VALUES = {"yes", "true", "checked", "pass", "passed", "已检查", "通过"}
AUDIT_PENDING_VALUES = {"", "open", "pending", "todo", "no", "not-run", "pending-review", "未检查"}


def infer_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.parent.name == "dist":
        return resolved.parent.parent
    return Path.cwd().resolve()


def count_occurrences(text: str, words: list[str]) -> dict[str, int]:
    return {word: text.count(word) for word in words if word in text}


def chapter_blocks(text: str) -> list[str]:
    parts = re.split(r"(?m)^#\s+(?:Chapter\s+\d+[:：].*|第\s*\d+\s*章[:：]?\s*.*)$", text)
    return [part for part in parts[1:] if part.strip()]


def chapter_h2_headings(block: str) -> list[str]:
    return [heading.strip() for heading in re.findall(r"(?m)^##\s+(.+?)\s*$", block)]


def preface_block(text: str) -> str:
    body = re.sub(r"(?s)^---\n.*?\n---\n", "", text).lstrip()
    title_match = re.search(r"(?m)^#\s+.+$", body)
    if not title_match:
        return ""
    remainder = body[title_match.end() :]
    chapter_match = re.search(r"(?m)^#\s+Chapter\s+\d+[:：].*$", remainder)
    if not chapter_match:
        return remainder.strip()
    return remainder[: chapter_match.start()].strip()


def has_any(text: str, markers: list[str]) -> bool:
    return any(marker in text for marker in markers)


def has_fact_authority(text: str) -> bool:
    return has_any(text, FACT_AUTHORITY_MARKERS)


def is_blank_cell(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"", "待填写", "none", "无", "n/a", "-"}


def row_value(row: dict[str, str], *names: str) -> str:
    lowered = {key.strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()].strip()
    return ""


def public_urls(value: str) -> list[str]:
    return URL_RE.findall(value or "")


def is_specific_public_url(value: str, *, allow_homepage: bool = False) -> bool:
    for candidate in public_urls(value):
        parsed = urlparse(candidate.rstrip(".,;，。；"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if allow_homepage or (parsed.path and parsed.path != "/") or parsed.query:
            return True
    return False


def prose_units(text: str) -> int:
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    words = re.findall(r"[A-Za-z0-9]+", text)
    return len(cjk) + len(words)


def extract_years(value: str) -> list[int]:
    return [int(match) for match in re.findall(r"(20\d{2}|19\d{2})", value)]


def table_rows_with_lines(path: Path) -> list[tuple[int, dict[str, str], str]]:
    if not path.exists():
        return []
    rows: list[tuple[int, dict[str, str], str]] = []
    headers: list[str] | None = None
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if headers is None:
            headers = cells
            continue
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        if any("待填写" == cell for cell in cells) and any("/" in cell for cell in cells):
            continue
        rows.append((line_no, row, stripped))
    return rows


def meaningful_table_rows(path: Path) -> list[tuple[int, dict[str, str], str]]:
    rows = []
    for line_no, row, stripped in table_rows_with_lines(path):
        if "待填写" in stripped:
            continue
        if count_occurrences(stripped, BAD_DRAFT_PHRASES):
            continue
        rows.append((line_no, row, stripped))
    return rows


def missing_chapter_contract(block: str) -> list[str]:
    return [
        contract_name
        for contract_name, markers in CHAPTER_CONTRACT.items()
        if not has_any(block, markers)
    ]


def read_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = STATE_RE.match(line.strip())
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def clean_yaml_value(raw: str) -> str:
    value = raw.split("#", 1)[0].strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.strip()


def read_state_flat(path: Path) -> dict[str, str]:
    """Parse the simple book-state.yaml template into dotted keys without requiring PyYAML."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            continue
        match = YAML_KV_RE.match(stripped)
        if not match:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, raw_value = match.group(1), match.group(2).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        dotted = ".".join([item[1] for item in stack] + [key])
        if raw_value:
            value = clean_yaml_value(raw_value)
            values[dotted] = value
            if "." not in dotted:
                values[key] = value
        else:
            stack.append((indent, key))
    return values


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate_artifact_digests(root: Path) -> dict[str, str | None]:
    return {
        "dist/book.md": file_sha256(root / "dist" / "book.md"),
        "dist/book.html": file_sha256(root / "dist" / "book.html"),
        "dist/book.pdf": file_sha256(root / "dist" / "book.pdf"),
        "dist/qa/pdf-visual-audit.md": file_sha256(root / "dist" / "qa" / "pdf-visual-audit.md"),
        "bibliography.md": file_sha256(root / "bibliography.md"),
    }


def gate_receipt_path(root: Path, target: str) -> Path:
    return root / "dist" / "qa" / "gates" / f"{target}.json"


def verify_gate_receipt(root: Path, target: str) -> list[str]:
    path = gate_receipt_path(root, target)
    if not path.is_file():
        return [f"book-state.yaml 声明 {target}，但缺少检查器签发的 gate receipt: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path} 不是有效 JSON: {exc}"]
    errors: list[str] = []
    if data.get("target") != target or data.get("passed") is not True:
        errors.append(f"{path} 没有记录通过的 {target} 质量门。")
    recorded = data.get("artifact_digests")
    current = gate_artifact_digests(root)
    if not isinstance(recorded, dict) or recorded != current:
        errors.append(f"{path} 已过期：书稿、PDF、视觉审计或参考资料在签发后发生变化。")
    return errors


def set_state_scalars(path: Path, updates: dict[str, str]) -> None:
    if not path.is_file():
        raise SystemExit(f"Missing book-state.yaml: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    stack: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index, raw_line in enumerate(lines):
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or raw_line.lstrip().startswith("- "):
            continue
        stripped = raw_line.strip()
        match = YAML_KV_RE.match(stripped)
        if not match:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, raw_value = match.group(1), match.group(2).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        dotted = ".".join([item[1] for item in stack] + [key])
        if dotted in updates:
            lines[index] = " " * indent + f"{key}: {updates[dotted]}"
            seen.add(dotted)
        if not raw_value:
            stack.append((indent, key))
    missing = sorted(set(updates) - seen)
    if missing:
        raise SystemExit("book-state.yaml is missing required keys: " + ", ".join(missing))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)


def update_gate_state(
    root: Path,
    target: str,
    passed: bool,
    errors: list[str],
    warnings: list[str],
) -> Path:
    state_path = root / "book-state.yaml"
    existing_review_valid = not verify_gate_receipt(root, "review-ready")
    if passed and target == "publish-ready":
        status = "publish-ready"
        review_ready = "true"
        publish_ready = "true"
    elif passed and target == "review-ready":
        status = "review-ready"
        review_ready = "true"
        publish_ready = "false"
    elif target == "publish-ready" and existing_review_valid:
        status = "review-ready"
        review_ready = "true"
        publish_ready = "false"
    else:
        status = "draft"
        review_ready = "false"
        publish_ready = "false"
    visual_audit_valid = status in {"review-ready", "publish-ready"}
    set_state_scalars(
        state_path,
        {
            "status": status,
            "quality.target": status,
            "quality.review_ready": review_ready,
            "quality.publish_ready": publish_ready,
            "quality.final_report_state": status,
            "completion_metrics.visual_coverage": "1.0" if visual_audit_valid else "0.0",
            "outputs.pdf_visual_audit": "true" if visual_audit_valid else "false",
        },
    )

    receipt = {
        "schema_version": 1,
        "target": target,
        "passed": passed,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_digests": gate_artifact_digests(root),
        "errors": errors,
        "warnings": warnings,
    }
    receipt_path = gate_receipt_path(root, target)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    receipt_path.write_text(serialized, encoding="utf-8")
    (root / "dist" / "qa" / "gate-result.json").write_text(serialized, encoding="utf-8")
    return receipt_path


def check_claimed_gate_state(root: Path, target: str, skip: bool) -> tuple[list[str], list[str]]:
    if skip:
        return [], []
    state = read_state_flat(root / "book-state.yaml")
    errors: list[str] = []
    status = normalized_state(state.get("status"))
    claims_review = is_truthy_state(state.get("quality.review_ready")) or status in {"review-ready", "publish-ready"}
    claims_publish = is_truthy_state(state.get("quality.publish_ready")) or status == "publish-ready"
    if claims_review:
        errors.extend(verify_gate_receipt(root, "review-ready"))
    if claims_publish:
        errors.extend(verify_gate_receipt(root, "publish-ready"))
    return errors, []


def read_chapter_state(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    chapters: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- id:"):
            current = {"id": clean_yaml_value(stripped.split(":", 1)[1])}
            chapters.append(current)
            continue
        if current is None or not stripped or stripped.startswith("#"):
            continue
        match = YAML_KV_RE.match(stripped)
        if not match:
            continue
        key, raw_value = match.group(1), match.group(2).strip()
        if raw_value:
            current[key] = clean_yaml_value(raw_value)
    return chapters


def normalized_state(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'").lower()


def is_truthy_state(value: str | None) -> bool:
    return normalized_state(value) in TRUTHY_STATE


def is_partial_state(value: str | None) -> bool:
    return normalized_state(value) in PARTIAL_STATE


def is_closed_wxmp_state(value: str | None) -> bool:
    return normalized_state(value) in WXMP_CLOSED_STATE


def is_closed_pack_state(value: str | None) -> bool:
    return normalized_state(value) in WXMP_CLOSED_STATE


def resolve_project_path(root: Path, raw: str) -> Path | None:
    raw = raw.strip()
    if not raw or raw.startswith(("http://", "https://", "data:", "#")):
        return None
    raw = raw.split()[0]
    path = Path(raw)
    if path.is_absolute():
        return path
    candidates = [root / path, root / "dist" / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def safe_int(value: str | None) -> int:
    try:
        return int((value or "").strip())
    except (TypeError, ValueError):
        return 0


def count_numbered_or_bulleted_entries(text: str) -> int:
    entries = 0
    in_entry = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            in_entry = False
            continue
        if re.match(r"^(\d+\.\s+|[-*]\s+)", line):
            entries += 1
            in_entry = True
            continue
        if not in_entry and not line.startswith("#"):
            entries += 1
            in_entry = True
    return entries


def count_reference_entries(path: Path) -> int:
    if not path.exists():
        return 0
    rows = meaningful_table_rows(path)
    if rows:
        return len(rows)
    text = path.read_text(encoding="utf-8")
    if count_occurrences(text, BAD_DRAFT_PHRASES):
        return 0
    return count_numbered_or_bulleted_entries(text)


def count_case_entries(path: Path) -> int:
    if not path.exists():
        return 0
    rows = meaningful_table_rows(path)
    if rows:
        return len(rows)
    text = path.read_text(encoding="utf-8")
    if count_occurrences(text, BAD_DRAFT_PHRASES):
        return 0
    heading_count = len(re.findall(r"(?m)^##+\s+.+$", text))
    if heading_count:
        return heading_count
    list_count = count_numbered_or_bulleted_entries(text)
    if list_count:
        return list_count
    body = "\n".join(
        line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")
    ).strip()
    return 1 if len(body) >= 80 else 0


def bibliography_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = HTML_COMMENT_RE.sub("", path.read_text(encoding="utf-8")).splitlines()
    entries: list[str] = []
    current: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current:
                entries.append(" ".join(current).strip())
                current = []
            continue
        if line.startswith("#"):
            continue
        if re.match(r"^(\d+\.\s+|[-*]\s+)", line):
            if current:
                entries.append(" ".join(current).strip())
            current = [re.sub(r"^(\d+\.\s+|[-*]\s+)", "", line).strip()]
            continue
        if current:
            current.append(line)
        else:
            current = [line]
    if current:
        entries.append(" ".join(current).strip())
    return [entry for entry in entries if entry]


def bibliography_metrics(path: Path) -> tuple[int, int, int]:
    entries = bibliography_entries(path)
    public_entries = [
        entry
        for entry in entries
        if not any(marker.lower() in entry.lower() for marker in OWNED_REFERENCE_MARKERS)
    ]
    url_backed_entries = [entry for entry in public_entries if is_specific_public_url(entry)]
    return len(entries), len(public_entries), len(url_backed_entries)


def parse_visual_plan(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    table_lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if len(table_lines) < 3:
        return []
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def check_claim_ledger(path: Path, allow_missing: bool, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        message = f"缺少 CLAIM_LEDGER: {path}"
        if allow_missing:
            warnings.append(message)
        else:
            errors.append(message)
        return errors, warnings

    for line_no, row, stripped in table_rows_with_lines(path):
        claim = row.get("Claim", "")
        claim_type = row.get("Type", "")
        layer = row.get("Layer", "")
        source = row.get("Source", "")
        source_url = row_value(row, "URL", "Source URL")
        source_date = row.get("Date", "")
        confidence = row.get("Confidence", "")
        cross_check = row.get("Cross-check", "")
        reader_wording = row.get("Reader-facing wording", "")
        row_context = " ".join([claim, claim_type, layer, source, source_url, source_date, confidence, cross_check, reader_wording, row.get("Notes", "")])
        lowered = row_context.lower()
        is_high = "high" in confidence.lower()
        is_fact = "fact" in claim_type.lower()

        def add_evidence_issue(message: str) -> None:
            if target in {"review-ready", "publish-ready"}:
                errors.append(message)
            else:
                warnings.append(message)

        if has_any(row_context, LOCAL_CONTEXT_MARKERS) and is_high:
            errors.append(
                f"CLAIM_LEDGER.md:{line_no} 把 Nowledge/Obsidian/Vault 这类本地上下文标成 high confidence。"
            )
        if has_any(row_context, LOCAL_CONTEXT_MARKERS) and is_fact:
            warnings.append(
                f"CLAIM_LEDGER.md:{line_no} 本地上下文不适合单独作为 fact，优先转入 CASE_LIBRARY.md。"
            )
        if is_fact and is_high and is_blank_cell(source):
            add_evidence_issue(f"CLAIM_LEDGER.md:{line_no} high fact 缺少 Source。")
        if is_fact and not is_specific_public_url(source_url):
            add_evidence_issue(
                f"CLAIM_LEDGER.md:{line_no} fact 缺少可直接核验的具体 URL。"
            )
        if is_fact and is_high and has_any(row_context, DEMAND_MARKERS) and not has_fact_authority(row_context):
            add_evidence_issue(
                f"CLAIM_LEDGER.md:{line_no} 小红书需求侧材料支撑了 high fact，需补 L1-fact 或交叉验证。"
            )
        if is_fact and is_high and has_any(row_context, DISCOURSE_MARKERS) and not has_fact_authority(row_context):
            add_evidence_issue(
                f"CLAIM_LEDGER.md:{line_no} 公众号/网页观点支撑了 high fact，需追到原始权威来源。"
            )
        if is_fact and is_high and is_blank_cell(cross_check) and not has_fact_authority(row_context):
            add_evidence_issue(f"CLAIM_LEDGER.md:{line_no} high fact 缺少 cross-check。")
        if is_fact and is_high and not has_fact_authority(row_context) and is_blank_cell(cross_check):
            add_evidence_issue(f"CLAIM_LEDGER.md:{line_no} high fact 既没有 L1-fact，也没有有效交叉验证。")
        if is_fact and is_high:
            years = extract_years(source_date)
            if not years:
                add_evidence_issue(f"CLAIM_LEDGER.md:{line_no} high fact 缺少可识别年份。")
            elif max(years) < RECENT_SOURCE_YEAR_FLOOR and "evergreen" not in lowered and "historical" not in lowered:
                add_evidence_issue(
                    f"CLAIM_LEDGER.md:{line_no} high fact 来源年份早于近三年，需标记 evergreen/historical 或补新来源。"
                )
        if any(term in reader_wording for term in INTERNAL_TERMS):
            errors.append(f"CLAIM_LEDGER.md:{line_no} Reader-facing wording 仍包含后台词。")
    return errors, warnings


def check_authority_accounts(path: Path) -> list[str]:
    warnings: list[str] = []
    if not path.exists():
        warnings.append(f"缺少 AUTHORITY_ACCOUNTS: {path}")
        return warnings

    selected = 0
    rows = 0
    missing_urls = 0
    for _, row, stripped in meaningful_table_rows(path):
        rows += 1
        lowered = stripped.lower()
        if any(marker in lowered for marker in AUTHORITY_STATUS_MARKERS):
            if is_specific_public_url(row_value(row, "URL"), allow_homepage=True):
                selected += 1
            else:
                missing_urls += 1

    if rows == 0:
        warnings.append("AUTHORITY_ACCOUNTS.md 还没有有效候选来源。")
    elif selected == 0:
        warnings.append("AUTHORITY_ACCOUNTS.md 有候选来源，但没有标记 selected/fetched/exported。")
    elif selected < 3:
        warnings.append(f"AUTHORITY_ACCOUNTS.md 已选来源偏少：{selected} 个。建议至少 5 个，最低 3 个。")
    if missing_urls:
        warnings.append(f"AUTHORITY_ACCOUNTS.md 有 {missing_urls} 个已选来源缺少真实 URL，不计入有效来源。")
    return warnings


def authority_account_counts(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    rows = 0
    selected = 0
    for _, row, stripped in meaningful_table_rows(path):
        rows += 1
        if any(marker in stripped.lower() for marker in AUTHORITY_STATUS_MARKERS) and is_specific_public_url(
            row_value(row, "URL"), allow_homepage=True
        ):
            selected += 1
    return rows, selected


def check_state(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    state = read_state(root / "book-state.yaml")
    if not state:
        errors.append("缺少 book-state.yaml。")
        return errors, warnings
    if not state.get("content_profile") and not state.get("profile"):
        errors.append("book-state.yaml 缺少 content_profile。")
    if not state.get("voice_profile"):
        errors.append("book-state.yaml 缺少 voice_profile。")
    if not state.get("voice_anchor"):
        errors.append("book-state.yaml 缺少 voice_anchor。")
    return errors, warnings


def check_chapter_evidence_map(root: Path, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    chapters = read_chapter_state(root / "book-state.yaml")
    if not chapters:
        return errors, warnings

    severity = errors if target in {"review-ready", "publish-ready"} else warnings
    mapped_refs = 0
    mapped_cases = 0

    for chapter in chapters:
        chapter_id = chapter.get("id", "")
        if not chapter_id:
            continue
        chapter_dir = root / "src" / chapter_id
        refs_path = chapter_dir / "refs.md"
        cases_path = chapter_dir / "cases.md"
        expected_refs = safe_int(chapter.get("refs"))
        expected_cases = safe_int(chapter.get("cases"))
        actual_refs = count_reference_entries(refs_path)
        actual_cases = count_case_entries(cases_path)

        mapped_refs += actual_refs
        mapped_cases += actual_cases

        if expected_refs > 0 and actual_refs == 0:
            severity.append(f"{chapter_id} 在 book-state.yaml 声明 refs={expected_refs}，但 {refs_path.name} 仍未回填。")
        elif expected_refs > actual_refs > 0:
            severity.append(
                f"{chapter_id} 在 book-state.yaml 声明 refs={expected_refs}，但 {refs_path.name} 只有 {actual_refs} 条有效记录。"
            )
        elif expected_refs == 0 and actual_refs > 0:
            warnings.append(f"{chapter_id} 的 {refs_path.name} 已有 {actual_refs} 条记录，但 book-state.yaml 仍写 refs=0。")

        if expected_cases > 0 and actual_cases == 0:
            severity.append(f"{chapter_id} 在 book-state.yaml 声明 cases={expected_cases}，但 {cases_path.name} 仍未回填。")
        elif expected_cases > actual_cases > 0:
            severity.append(
                f"{chapter_id} 在 book-state.yaml 声明 cases={expected_cases}，但 {cases_path.name} 只有 {actual_cases} 条有效记录。"
            )
        elif expected_cases == 0 and actual_cases > 0:
            warnings.append(f"{chapter_id} 的 {cases_path.name} 已有 {actual_cases} 条记录，但 book-state.yaml 仍写 cases=0。")

    if target in {"review-ready", "publish-ready"}:
        if mapped_refs == 0:
            errors.append("整本书没有有效的章节 refs.md 映射。review-ready 不能只靠总表和正文口头引用。")
        if mapped_cases == 0:
            errors.append("整本书没有有效的章节 cases.md 映射。review-ready 不能只在 CASE_LIBRARY.md 里堆案例。")

    return errors, warnings


def check_reference_state(root: Path, book_text: str, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    state = read_state_flat(root / "book-state.yaml")
    bibliography = root / "bibliography.md"
    has_reference_page = has_reader_facing_references(root, book_text)
    entry_count, public_count, url_backed_count = bibliography_metrics(bibliography)
    outputs_references = is_truthy_state(state.get("outputs.references"))
    quality_reference_page = is_truthy_state(state.get("quality.reference_page"))

    if target == "publish-ready":
        min_entries = MIN_PUBLISH_BIBLIOGRAPHY_ENTRIES
        min_public = MIN_PUBLISH_PUBLIC_BIBLIOGRAPHY_ENTRIES
    else:
        min_entries = MIN_REVIEW_BIBLIOGRAPHY_ENTRIES
        min_public = MIN_REVIEW_PUBLIC_BIBLIOGRAPHY_ENTRIES

    if bibliography.exists() and entry_count < min_entries:
        message = f"bibliography.md 有效条目偏少：当前 {entry_count} 条，{target} 建议至少 {min_entries} 条。"
        if target in {"review-ready", "publish-ready"}:
            errors.append(message)
        else:
            warnings.append(message)

    if bibliography.exists() and public_count < min_public:
        message = f"bibliography.md 公开来源偏少：当前 {public_count} 条，{target} 建议至少 {min_public} 条。"
        if target in {"review-ready", "publish-ready"}:
            errors.append(message)
        else:
            warnings.append(message)

    if bibliography.exists() and url_backed_count < min_public:
        message = (
            f"bibliography.md 可直接核验的公开 URL 偏少：当前 {url_backed_count} 条，"
            f"{target} 最低 {min_public} 条。网站名、搜索入口和无 URL 条目不计数。"
        )
        if target in {"review-ready", "publish-ready"}:
            errors.append(message)
        else:
            warnings.append(message)

    if outputs_references and not has_reference_page:
        errors.append("book-state.yaml 把 outputs.references 标成 true，但读者可见参考资料页并未闭环。")
    if quality_reference_page and not has_reference_page:
        errors.append("book-state.yaml 把 quality.reference_page 标成 true，但主书或 dist/ 中没有可用参考资料页。")

    if outputs_references and entry_count < MIN_REVIEW_BIBLIOGRAPHY_ENTRIES:
        errors.append(
            f"book-state.yaml 把 outputs.references 标成 true，但 bibliography.md 只有 {entry_count} 条有效条目。"
        )
    if quality_reference_page and public_count < MIN_REVIEW_PUBLIC_BIBLIOGRAPHY_ENTRIES:
        errors.append(
            "book-state.yaml 把 quality.reference_page 标成 true，但公开来源数量仍不足以支撑读者参考页。"
        )

    if has_reference_page and not outputs_references and entry_count >= MIN_REVIEW_BIBLIOGRAPHY_ENTRIES:
        warnings.append("参考资料页已经存在，但 book-state.yaml 仍写 outputs.references=false。")
    if has_reference_page and not quality_reference_page and public_count >= MIN_REVIEW_PUBLIC_BIBLIOGRAPHY_ENTRIES:
        warnings.append("参考资料页已经达到基本厚度，但 book-state.yaml 仍写 quality.reference_page=false。")

    return errors, warnings


def has_reader_facing_references(root: Path, book_text: str) -> bool:
    reference_heading = re.search(
        r"(?m)^#{1,3}\s*(参考资料|参考来源|延伸阅读|Bibliography|References)\s*$",
        book_text,
    )
    if reference_heading:
        return True
    for candidate in [root / "dist" / "references.md", root / "dist" / "bibliography.md"]:
        if candidate.exists() and candidate.stat().st_size > 80:
            text = candidate.read_text(encoding="utf-8")
            return not count_occurrences(text, BAD_DRAFT_PHRASES)
    return False


def non_gitkeep_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [
        item
        for item in path.rglob("*")
        if item.is_file() and item.name != ".gitkeep" and item.stat().st_size > 20
    ]


def check_file_without_draft(path: Path, label: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        errors.append(f"缺少 {label}: {path}")
        return errors, warnings
    text = path.read_text(encoding="utf-8")
    draft_hits = count_occurrences(text, BAD_DRAFT_PHRASES)
    if draft_hits:
        errors.append(f"{label} 残留草稿语言: " + ", ".join(f"{k}×{v}" for k, v in draft_hits.items()))
    if len(text.strip()) < 120:
        warnings.append(f"{label} 内容过短，可能还不是可发布物料。")
    return errors, warnings


def check_file_sections(path: Path, label: str, sections: list[str]) -> tuple[list[str], list[str]]:
    errors, warnings = check_file_without_draft(path, label)
    if errors:
        return errors, warnings
    text = path.read_text(encoding="utf-8")
    missing = [section for section in sections if section not in text]
    if missing:
        errors.append(f"{label} 缺少必要结构: " + ", ".join(missing))
    return errors, warnings


def check_source_map_urls(path: Path, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return [f"缺少 SOURCE_MAP.md: {path}"], warnings
    used_rows = []
    invalid_lines = []
    for line_no, row, _ in meaningful_table_rows(path):
        status = row_value(row, "Status").lower()
        if status not in USED_SOURCE_STATES:
            continue
        used_rows.append(line_no)
        if not is_specific_public_url(row_value(row, "URL")):
            invalid_lines.append(line_no)
    if not used_rows:
        message = "SOURCE_MAP.md 没有标记 used/selected/fetched/exported/done 的真实来源。"
        (errors if target in {"review-ready", "publish-ready"} else warnings).append(message)
    for line_no in invalid_lines:
        message = f"SOURCE_MAP.md:{line_no} 已标记使用，但缺少可直接核验的具体 URL。"
        (errors if target in {"review-ready", "publish-ready"} else warnings).append(message)
    return errors, warnings


def check_ledger_rows(
    path: Path,
    label: str,
    minimum: int,
    allow_missing: bool,
    *,
    require_urls: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        message = f"缺少 {label}: {path}"
        if allow_missing:
            warnings.append(message)
        else:
            errors.append(message)
        return errors, warnings
    rows = meaningful_table_rows(path)
    valid_rows = rows
    invalid_url_lines: list[int] = []
    if require_urls:
        valid_rows = []
        for line_no, row, stripped in rows:
            if is_specific_public_url(row_value(row, "URL")):
                valid_rows.append((line_no, row, stripped))
            else:
                invalid_url_lines.append(line_no)
        for line_no in invalid_url_lines:
            message = f"{label}:{line_no} 缺少可直接核验的具体 URL，不计入有效记录。"
            (warnings if allow_missing else errors).append(message)
    if len(valid_rows) < minimum:
        message = f"{label} 有效记录不足：当前 {len(valid_rows)} 条，最低 {minimum} 条。"
        if allow_missing:
            warnings.append(message)
        else:
            errors.append(message)
    return errors, warnings


def pdf_page_count(pdf_path: Path, pages_dir: Path) -> int:
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        result = None
    if result and result.returncode == 0:
        match = re.search(r"(?m)^Pages:\s*(\d+)\s*$", result.stdout)
        if match:
            return int(match.group(1))
    page_numbers = []
    for path in pages_dir.glob("page-*.png") if pages_dir.exists() else []:
        match = re.fullmatch(r"page-(\d+)\.png", path.name)
        if match:
            page_numbers.append(int(match.group(1)))
    return max(page_numbers, default=0)


def expected_visual_ids(root: Path) -> set[str]:
    expected: set[str] = set()
    for row in parse_visual_plan(root / "VISUAL_PLAN.md"):
        required = row.get("Required", "").lower() in {"yes", "true", "必须"}
        rejected = row.get("Status", "").lower() == "rejected"
        visual_id = row.get("ID", "")
        if visual_id and required and not rejected:
            expected.add(visual_id)
    return expected


def check_pdf_visual_audit(root: Path, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if target not in {"review-ready", "publish-ready"}:
        return errors, warnings
    path = root / "dist" / "qa" / "pdf-visual-audit.md"
    if not path.exists():
        errors.append(f"{target} 需要 PDF 页面级视觉审计文件: {path}")
        return errors, warnings
    text = path.read_text(encoding="utf-8")
    draft_hits = count_occurrences(text, BAD_DRAFT_PHRASES)
    if draft_hits:
        errors.append("pdf-visual-audit.md 残留草稿语言: " + ", ".join(f"{k}×{v}" for k, v in draft_hits.items()))
    required_terms = ["Render Command", "Page Images", "Figure Coverage", "Checklist", "Summary"]
    missing = [term for term in required_terms if term not in text]
    if missing:
        errors.append("pdf-visual-audit.md 缺少必要结构: " + ", ".join(missing))
    state_match = re.search(r"(?m)^audit_state:\s*(\S+)\s*$", text)
    audit_state = normalized_state(state_match.group(1) if state_match else "")
    if audit_state != "passed":
        errors.append(f"pdf-visual-audit.md audit_state 必须为 passed，当前 {audit_state or 'missing'}。")

    pdf_path = root / "dist" / "book.pdf"
    pages_dir = root / "dist" / "qa" / "pages"
    expected_pages = pdf_page_count(pdf_path, pages_dir)
    if expected_pages <= 0:
        errors.append("无法确认 dist/book.pdf 的实际页数。")
        return errors, warnings

    declared_match = re.search(r"(?m)^page_count:\s*(\d+)\s*$", text)
    declared_pages = int(declared_match.group(1)) if declared_match else 0
    if declared_pages != expected_pages:
        errors.append(f"pdf-visual-audit.md page_count={declared_pages}，实际 PDF 为 {expected_pages} 页。")

    digest_match = re.search(r"(?m)^pdf_sha256:\s*([0-9a-f]{64})\s*$", text)
    actual_digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path.is_file() else ""
    if not digest_match or digest_match.group(1) != actual_digest:
        errors.append("pdf-visual-audit.md 对应的 PDF 摘要已过期；重新渲染并检查当前 PDF。")

    page_rows: dict[int, tuple[int, dict[str, str]]] = {}
    observed_figures: set[str] = set()
    for line_no, row, _ in meaningful_table_rows(path):
        page_raw = row_value(row, "Page")
        if not page_raw.isdigit():
            continue
        page_number = int(page_raw)
        if page_number in page_rows:
            errors.append(f"pdf-visual-audit.md:{line_no} 重复记录第 {page_number} 页。")
            continue
        page_rows[page_number] = (line_no, row)
        image_raw = row_value(row, "Image Path")
        image_path = resolve_project_path(root, image_raw)
        if image_path is None or not image_path.is_file():
            errors.append(f"pdf-visual-audit.md:{line_no} 页面图片不存在: {image_raw}")
        checked = normalized_state(row_value(row, "Checked"))
        if checked not in AUDIT_CHECKED_VALUES:
            errors.append(f"pdf-visual-audit.md:{line_no} 第 {page_number} 页尚未实际检查。")
        fix_status = normalized_state(row_value(row, "Fix Status"))
        if fix_status in AUDIT_PENDING_VALUES:
            errors.append(f"pdf-visual-audit.md:{line_no} 第 {page_number} 页仍是未关闭状态: {fix_status or 'missing'}。")
        if is_blank_cell(row_value(row, "Issues")):
            errors.append(f"pdf-visual-audit.md:{line_no} 第 {page_number} 页缺少视觉结论。")
        figures = row_value(row, "Figures")
        if figures and figures != "-":
            observed_figures.update(re.findall(r"[A-Za-z0-9_.-]+", figures))

    expected_numbers = set(range(1, expected_pages + 1))
    missing_pages = sorted(expected_numbers - set(page_rows))
    extra_pages = sorted(set(page_rows) - expected_numbers)
    if missing_pages:
        errors.append("pdf-visual-audit.md 缺少页面记录: " + ", ".join(map(str, missing_pages)))
    if extra_pages:
        errors.append("pdf-visual-audit.md 包含超出 PDF 的页面记录: " + ", ".join(map(str, extra_pages)))

    missing_figures = sorted(expected_visual_ids(root) - observed_figures)
    if missing_figures:
        errors.append("pdf-visual-audit.md 没有标出必检图表所在页: " + ", ".join(missing_figures))

    unchecked_items = re.findall(r"(?m)^- \[ \] .+$", text)
    if unchecked_items:
        errors.append(f"pdf-visual-audit.md Checklist 仍有 {len(unchecked_items)} 项未确认。")

    if target == "publish-ready" and not re.search(
        r"(?m)^- \[[xX]\].*参考资料分页.*(?:孤项|空白尾页)", text
    ):
        errors.append("publish-ready 的视觉审计必须确认参考资料分页没有单条孤项或大面积空白尾页。")

    if re.search(r"\b(open|pending|todo|pending-review)\b", text, re.I):
        errors.append(f"{target} 的 pdf-visual-audit.md 不能保留 open/pending/todo 状态。")
    return errors, warnings


def worksheet_has_action_structure(text: str) -> bool:
    return has_any(text, ["工作表", "填写", "自测", "清单", "模板", "步骤", "问题"]) and has_any(
        text, ["完成标准", "输出", "Reader Input", "Output"]
    )


def check_target_state(
    root: Path,
    book_text: str,
    target: str,
    authority_path: Path,
    allow_partial_wxmp: bool,
    allow_missing_behavior: bool,
    allow_missing_transaction: bool,
    skip_distribution_pack: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    state = read_state_flat(root / "book-state.yaml")

    if target not in TARGETS:
        errors.append(f"未知 target: {target}")
        return errors, warnings

    if target in {"review-ready", "publish-ready"}:
        required_outputs = {
            "outputs.markdown": root / "dist" / "book.md",
            "outputs.kami_html": root / "dist" / "book.html",
            "outputs.kami_pdf": root / "dist" / "book.pdf",
        }
        for key, file_path in required_outputs.items():
            if not file_path.exists() or file_path.stat().st_size < 100:
                errors.append(f"{target} 缺少输出文件: {file_path}")
            if state and not is_truthy_state(state.get(key)):
                errors.append(f"book-state.yaml 未标记 {key}=true/ready。")

        bibliography = root / "bibliography.md"
        if not bibliography.exists() or bibliography.stat().st_size < 80:
            errors.append("review-ready 需要 bibliography.md 有有效参考来源。")
        if not has_reader_facing_references(root, book_text):
            errors.append("review-ready 需要读者可见的参考资料页：写入 dist/book.md，或生成 dist/references.md。")

        if target == "review-ready" and is_closed_pack_state(state.get("research.behavior_pack")):
            behavior_errors, behavior_warnings = check_ledger_rows(
                root / "BEHAVIOR_LEDGER.md",
                "BEHAVIOR_LEDGER.md",
                MIN_BEHAVIOR_SIGNALS,
                False,
                require_urls=True,
            )
            errors.extend(behavior_errors)
            warnings.extend(behavior_warnings)
        if target == "review-ready" and is_closed_pack_state(state.get("research.transaction_pack")):
            transaction_errors, transaction_warnings = check_ledger_rows(
                root / "TRANSACTION_LEDGER.md",
                "TRANSACTION_LEDGER.md",
                MIN_TRANSACTION_SIGNALS,
                False,
                require_urls=True,
            )
            errors.extend(transaction_errors)
            warnings.extend(transaction_warnings)

    if target == "publish-ready":
        wxmp_value = state.get("research.wxmp_pack")
        wxmp_rate_limited = state.get("research.wxmp_rate_limited")
        if not allow_partial_wxmp and not is_closed_wxmp_state(wxmp_value):
            errors.append(
                f"publish-ready 不能使用未闭环的 wxmp 证据包：research.wxmp_pack={wxmp_value or 'missing'}。"
            )
        if not allow_partial_wxmp and is_truthy_state(wxmp_rate_limited):
            errors.append("publish-ready 不能保留 research.wxmp_rate_limited=true。")

        behavior_errors, behavior_warnings = check_ledger_rows(
            root / "BEHAVIOR_LEDGER.md",
            "BEHAVIOR_LEDGER.md",
            MIN_BEHAVIOR_SIGNALS,
            allow_missing_behavior,
            require_urls=True,
        )
        transaction_errors, transaction_warnings = check_ledger_rows(
            root / "TRANSACTION_LEDGER.md",
            "TRANSACTION_LEDGER.md",
            MIN_TRANSACTION_SIGNALS,
            allow_missing_transaction,
            require_urls=True,
        )
        errors.extend(behavior_errors)
        errors.extend(transaction_errors)
        warnings.extend(behavior_warnings)
        warnings.extend(transaction_warnings)

        if not allow_missing_behavior and not is_closed_pack_state(state.get("research.behavior_pack")):
            errors.append(
                f"publish-ready 不能缺少闭环行为层证据：research.behavior_pack={state.get('research.behavior_pack') or 'missing'}。"
            )
        if not allow_missing_transaction and not is_closed_pack_state(state.get("research.transaction_pack")):
            errors.append(
                "publish-ready 不能缺少闭环交易层证据："
                f"research.transaction_pack={state.get('research.transaction_pack') or 'missing'}。"
            )

        _, selected = authority_account_counts(authority_path)
        if selected < 5:
            errors.append(f"publish-ready 需要至少 5 个有效权威账号/来源，当前 {selected} 个。")

        worksheets = non_gitkeep_files(root / "dist" / "worksheets")
        if not worksheets:
            errors.append("publish-ready 需要 dist/worksheets/ 下至少 1 个可交付工作表，不能只有 .gitkeep。")
        else:
            for worksheet in worksheets:
                text = worksheet.read_text(encoding="utf-8", errors="ignore")
                draft_hits = count_occurrences(text, BAD_DRAFT_PHRASES)
                if draft_hits:
                    errors.append(f"工作表 {worksheet} 残留草稿语言: " + ", ".join(draft_hits))
                if not worksheet_has_action_structure(text):
                    errors.append(f"工作表 {worksheet} 缺少可填写行动结构。")

        if not skip_distribution_pack:
            distribution_errors, distribution_warnings = check_file_sections(
                root / "dist" / "distribution-note.md",
                "distribution-note.md",
                ["书籍定位", "适合读者", "读完能得到什么", "分发边界"],
            )
            private_errors, private_warnings = check_file_sections(
                root / "dist" / "private-domain-pack.md",
                "private-domain-pack.md",
                ["欢迎语", "标签问题", "读者分层", "后续内容", "边界说明"],
            )
            errors.extend(distribution_errors)
            errors.extend(private_errors)
            warnings.extend(distribution_warnings)
            warnings.extend(private_warnings)

    return errors, warnings


def check_images_and_tokens(text: str, root: Path, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for raw_src in MD_IMAGE_RE.findall(text):
        path = resolve_project_path(root, raw_src)
        if path:
            resolved = path.resolve()
            if resolved != root.resolve() and root.resolve() not in resolved.parents:
                errors.append(f"Markdown 图片路径逃逸项目目录: {raw_src}")
            elif not resolved.exists():
                errors.append(f"Markdown 图片路径不存在: {raw_src}")

    for visual_id in DIAGRAM_TOKEN_RE.findall(text):
        path = root / "assets" / "diagrams" / f"{visual_id}.svg"
        if not path.exists():
            message = f"Kami diagram 占位符未生成文件: {visual_id} -> {path}"
            if target == "draft":
                warnings.append(message)
            else:
                errors.append(message)

    for visual_id in SECTION_IMAGE_TOKEN_RE.findall(text):
        candidates = [
            root / "assets" / "images" / visual_id,
            root / "assets" / "images" / f"{visual_id}.png",
            root / "assets" / "images" / f"{visual_id}.jpg",
            root / "assets" / "images" / f"{visual_id}.jpeg",
            root / "assets" / "images" / f"{visual_id}.webp",
        ]
        if not any(path.exists() for path in candidates):
            message = f"section-image 占位符未找到图片: {visual_id}"
            if target == "draft":
                warnings.append(message)
            else:
                errors.append(message)

    return errors, warnings


def check_visual_plan(root: Path, target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = root / "VISUAL_PLAN.md"
    if not path.exists():
        errors.append("缺少 VISUAL_PLAN.md。")
        return errors, warnings
    rows = [
        row
        for row in parse_visual_plan(path)
        if not any("待填写" in row.get(key, "") for key in ("Reader Problem", "Visual Purpose", "Caption"))
    ]
    if not rows:
        warnings.append("VISUAL_PLAN.md 没有有效图表计划。若正文确实不需要图，请在文档里说明原因。")
        return errors, warnings

    for row in rows:
        row_id = row.get("ID", "unknown")
        if any("待填写" in row.get(key, "") for key in ("Reader Problem", "Visual Purpose", "Caption")):
            continue
        required = row.get("Required", "").lower() in {"yes", "true", "必须"}
        rejected = row.get("Status", "").lower() == "rejected"
        output = row.get("Output Path", "")
        visual_type = row.get("Type", "")
        caption = row.get("Caption", "")
        if required and not rejected:
            if not output:
                errors.append(f"VISUAL_PLAN.md:{row_id} 必填图缺少 Output Path。")
            elif not (root / output).exists() and visual_type not in {"cover-visual", "section-visual"}:
                message = f"VISUAL_PLAN.md:{row_id} 必填信息图文件不存在: {output}"
                if target == "draft":
                    warnings.append(message)
                else:
                    errors.append(message)
            if not caption or "待填写" in caption:
                errors.append(f"VISUAL_PLAN.md:{row_id} 必填图缺少 caption。")
    return errors, warnings


def check_html(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    html_path = root / "dist" / "book.html"
    if not html_path.exists():
        return errors, warnings
    text = html_path.read_text(encoding="utf-8")
    if "{{" in text or "}}" in text:
        errors.append("dist/book.html 仍包含 placeholder。")
    if '<span class="toc-page">—</span>' in text:
        errors.append("dist/book.html 目录仍包含假的页码占位符 `—`。")
    return errors, warnings


def check_book_feel(
    text: str,
    chapters: list[str],
    content_profile: str,
    target: str,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if target not in {"review-ready", "publish-ready"}:
        return errors, warnings

    intro = preface_block(text)
    if prose_units(intro) < BOOK_OPENING_MIN_UNITS:
        warnings.append("H1 后缺少真正的开场或导言，成书会更像手册。建议补 hook、问题重定义和阅读路径。")

    if len(chapters) < 3:
        return errors, warnings

    signatures = [tuple(chapter_h2_headings(block)) for block in chapters]
    signature_counts = Counter(signatures)
    dominant_signature, dominant_count = signature_counts.most_common(1)[0]
    if dominant_signature and dominant_count == len(chapters) and len(dominant_signature) >= 4:
        warnings.append("全书章节二级标题完全一致，结构过于均质，容易写成课程手册或说明书。")
    elif dominant_signature and dominant_count >= max(3, round(len(chapters) * 0.8)):
        warnings.append("大多数章节沿用同一套二级标题骨架，书感偏弱。建议按章节任务拉开节奏。")

    heading_counts = Counter()
    for signature in signatures:
        heading_counts.update(signature)

    heavy_repeat_threshold = max(3, round(len(chapters) * 0.7))
    repeated_workbook = [heading for heading in HANDBOOK_WORKBOOK_HEADINGS if heading_counts[heading] >= heavy_repeat_threshold]

    if content_profile in STRICT_BOOK_FEEL_PROFILES and repeated_workbook:
        warnings.append(
            f"{content_profile} 不应在大多数章节重复 {' / '.join(repeated_workbook)}，正文正在滑向工作手册。"
        )
    elif content_profile == "playbook" and len(repeated_workbook) == len(HANDBOOK_WORKBOOK_HEADINGS):
        warnings.append("playbook 也不应每章机械重复“本章产出 / 操作方法 / 自测问题”。把部分填写任务移到 worksheets。")

    if content_profile != "course-manual":
        handbook_threshold = max(4, round(len(chapters) * 0.8))
        repeated_handbook = [heading for heading in HANDBOOK_H2_HEADINGS if heading_counts[heading] >= handbook_threshold]
        if len(repeated_handbook) >= 5:
            warnings.append("全书大量重复手册型标题，读者更容易记住模板而不是作者判断。")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="dist/book.md")
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="review-ready",
        help="Completion state to validate. draft checks prose; review-ready checks the main book; publish-ready checks the whole distribution package.",
    )
    parser.add_argument("--ledger", default="CLAIM_LEDGER.md")
    parser.add_argument("--authority-accounts", default="AUTHORITY_ACCOUNTS.md")
    parser.add_argument("--allow-missing-evidence", action="store_true")
    parser.add_argument("--allow-partial-wxmp", action="store_true")
    parser.add_argument("--allow-missing-behavior", action="store_true")
    parser.add_argument("--allow-missing-transaction", action="store_true")
    parser.add_argument("--skip-distribution-pack", action="store_true")
    parser.add_argument(
        "--update-state",
        action="store_true",
        help="Atomically derive book-state maturity and write a digest-bound gate receipt.",
    )
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    root = infer_root(path)
    text = path.read_text(encoding="utf-8")

    errors: list[str] = []
    warnings: list[str] = []

    cta_hits = count_occurrences(text, HARD_CTA)
    if cta_hits:
        errors.append("正文包含硬 CTA: " + ", ".join(f"{k}×{v}" for k, v in cta_hits.items()))

    internal_hits = count_occurrences(text, INTERNAL_TERMS)
    if internal_hits:
        errors.append("正文包含后台证据语言: " + ", ".join(f"{k}×{v}" for k, v in internal_hits.items()))

    draft_hits = count_occurrences(text, BAD_DRAFT_PHRASES)
    if draft_hits:
        errors.append("正文残留草稿语言: " + ", ".join(f"{k}×{v}" for k, v in draft_hits.items()))

    cliché_hits = count_occurrences(text, CLICHE)
    if cliché_hits:
        warnings.append("发现空泛商业词，需人工判断是否有明确定义: " + ", ".join(cliché_hits))

    chapters = chapter_blocks(text)
    if args.target == "draft" and len(chapters) < MIN_DRAFT_CHAPTERS:
        errors.append(f"draft 至少需要 {MIN_DRAFT_CHAPTERS} 个已写章节，当前 {len(chapters)} 个。")
    if args.target in {"review-ready", "publish-ready"} and len(chapters) < MIN_REVIEW_CHAPTERS:
        errors.append(f"{args.target} 至少需要 {MIN_REVIEW_CHAPTERS} 个正式章节，当前 {len(chapters)} 个。")
    if args.target == "publish-ready" and len(chapters) < MIN_PUBLISH_CHAPTERS:
        errors.append(f"publish-ready 至少需要 {MIN_PUBLISH_CHAPTERS} 个正式章节，当前 {len(chapters)} 个。")

    total_units = prose_units(text)
    if args.target == "draft" and total_units < MIN_DRAFT_TOTAL_UNITS:
        errors.append(f"draft 正文体量不足：当前约 {total_units} units，最低 {MIN_DRAFT_TOTAL_UNITS}。")
    if args.target == "publish-ready" and total_units < MIN_PUBLISH_TOTAL_UNITS:
        errors.append(f"publish-ready 正文体量不足：当前约 {total_units} units，最低 {MIN_PUBLISH_TOTAL_UNITS}。")

    for index, block in enumerate(chapters, 1):
        missing = missing_chapter_contract(block)
        chapter_units = prose_units(block)
        if missing:
            message = f"Chapter {index:02d} 缺少章节契约: " + ", ".join(missing)
            if args.target in {"review-ready", "publish-ready"}:
                errors.append(message)
            else:
                warnings.append(message)
        if args.target == "publish-ready" and chapter_units < MIN_PUBLISH_CHAPTER_UNITS:
            errors.append(
                f"Chapter {index:02d} 内容过短：当前约 {chapter_units} units，最低 {MIN_PUBLISH_CHAPTER_UNITS}。"
            )

    text_without_visual_tokens = DIAGRAM_TOKEN_RE.sub("", SECTION_IMAGE_TOKEN_RE.sub("", text))
    if "{{" in text_without_visual_tokens or "}}" in text_without_visual_tokens:
        warnings.append("正文仍包含占位符花括号。")

    ledger_path = Path(args.ledger)
    if not ledger_path.is_absolute():
        ledger_path = root / ledger_path
    authority_path = Path(args.authority_accounts)
    if not authority_path.is_absolute():
        authority_path = root / authority_path

    state_errors, state_warnings = check_state(root)
    visual_errors, visual_warnings = check_visual_plan(root, args.target)
    image_errors, image_warnings = check_images_and_tokens(text, root, args.target)
    html_errors, html_warnings = check_html(root)
    ledger_errors, ledger_warnings = check_claim_ledger(ledger_path, args.allow_missing_evidence, args.target)
    source_map_errors, source_map_warnings = check_source_map_urls(root / "SOURCE_MAP.md", args.target)
    target_errors, target_warnings = check_target_state(
        root,
        text,
        args.target,
        authority_path,
        args.allow_partial_wxmp,
        args.allow_missing_behavior,
        args.allow_missing_transaction,
        args.skip_distribution_pack,
    )
    audit_errors, audit_warnings = check_pdf_visual_audit(root, args.target)
    chapter_map_errors, chapter_map_warnings = check_chapter_evidence_map(root, args.target)
    reference_state_errors, reference_state_warnings = check_reference_state(root, text, args.target)
    state_flat = read_state_flat(root / "book-state.yaml")
    content_profile = state_flat.get("content_profile") or state_flat.get("profile") or "methodology-book"
    book_feel_errors, book_feel_warnings = check_book_feel(text, chapters, content_profile, args.target)
    claimed_state_errors, claimed_state_warnings = check_claimed_gate_state(
        root, args.target, args.update_state
    )

    errors.extend(state_errors)
    errors.extend(visual_errors)
    errors.extend(image_errors)
    errors.extend(html_errors)
    errors.extend(ledger_errors)
    errors.extend(source_map_errors)
    errors.extend(target_errors)
    errors.extend(audit_errors)
    errors.extend(chapter_map_errors)
    errors.extend(reference_state_errors)
    errors.extend(book_feel_errors)
    errors.extend(claimed_state_errors)
    warnings.extend(state_warnings)
    warnings.extend(visual_warnings)
    warnings.extend(image_warnings)
    warnings.extend(html_warnings)
    warnings.extend(ledger_warnings)
    warnings.extend(source_map_warnings)
    warnings.extend(target_warnings)
    warnings.extend(audit_warnings)
    warnings.extend(chapter_map_warnings)
    warnings.extend(reference_state_warnings)
    warnings.extend(book_feel_warnings)
    warnings.extend(claimed_state_warnings)
    warnings.extend(check_authority_accounts(authority_path))

    receipt_path = None
    if args.update_state:
        receipt_path = update_gate_state(root, args.target, not errors, errors, warnings)

    if args.output_json:
        print(
            json.dumps(
                {
                    "target": args.target,
                    "passed": not errors,
                    "errors": errors,
                    "warnings": warnings,
                    "state_updated": args.update_state,
                    "gate_receipt": str(receipt_path) if receipt_path else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for warning in warnings:
            print("[WARN]", warning)
        for error in errors:
            print("[ERROR]", error)

    if errors:
        return 1
    if not args.output_json:
        if receipt_path:
            print(f"Gate receipt: {receipt_path}")
        print(f"Leadbook checks passed for target={args.target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

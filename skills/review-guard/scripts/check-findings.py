#!/usr/bin/env python3
"""校验评审问题清单是否满足 finding-and-report-contract.md 的准入门槛。

用法：
    check-findings.py <findings.json> [--repo-root PATH] [--head REF]
                      [--change-map <change-map.json>] [--allow-open]

findings.json 可以是数组，或含 "findings" 键的对象。
退出码：0 通过；4 违反问题契约。违规原因用简体中文输出到 stderr。

只校验能机器判定的部分：词汇表、必填字段、锚点是否真实存在、锚点是否落在变更行
上、中文输出、按 fingerprint 去重、数量上限。它不判断问题本身是否成立。
"""
import hashlib
import json
import os
import re
import subprocess
import sys

SEVERITY = ("P0", "P1", "P2")
MIN_CONFIDENCE = 7
MAX_REPORTED = 5
REQUIRED = ("severity", "confidence", "file", "trigger", "impact", "evidence", "action")
ZH_FIELDS = ("trigger", "impact", "evidence", "action")

CJK = re.compile(r'[一-鿿]')


def has_zh(text):
    return bool(CJK.search(str(text)))


def fingerprint(f):
    """规范化 file + 符号/区域 + 事实主张；autopilot 用它跨来源去重。"""
    parts = [
        str(f.get("file", "")).strip().lower(),
        re.sub(r'\s+', " ", str(f.get("symbol_or_region") or f.get("action", ""))).strip().lower(),
        re.sub(r'\s+', " ", str(f.get("impact", ""))).strip().lower(),
    ]
    return hashlib.sha256(" ".join(parts).encode("utf-8")).hexdigest()[:16]


def file_line_count(repo, head, path):
    """锁定 head 上该文件的行数；-1 表示文件不存在，None 表示无法判定。"""
    if not repo or not path:
        return None
    if head:
        out = subprocess.run(["git", "-C", repo, "show", f"{head}:{path}"],
                             capture_output=True, text=True, check=False)
        return -1 if out.returncode != 0 else len(out.stdout.splitlines())
    full = os.path.join(repo, path)
    if not os.path.isfile(full):
        return -1
    with open(full, "rb") as fh:
        return len(fh.read().splitlines())


def check(findings, repo=None, head=None, change_map=None, allow_open=False):
    problems = []
    hunks = (change_map or {}).get("hunk_lines", {})
    changed = set((change_map or {}).get("changed_files", []))
    seen = {}

    for i, f in enumerate(findings):
        tag = f"第 {i + 1} 条（{f.get('file', '?')}）"

        for key in REQUIRED:
            if key not in f or str(f.get(key, "")).strip() == "":
                problems.append(f"{tag}：缺少必填字段 {key}")

        sev = f.get("severity")
        if sev not in SEVERITY:
            problems.append(f"{tag}：severity 必须是 P0/P1/P2，实际 {sev!r}")

        conf = f.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, int) or not 1 <= conf <= 10:
            problems.append(f"{tag}：confidence 必须是 1-10 的整数，实际 {conf!r}")
        elif conf < MIN_CONFIDENCE and not allow_open:
            problems.append(
                f"{tag}：置信度 {conf}/10 低于 {MIN_CONFIDENCE}，不得作为 P0-P2 问题上报；"
                "5-6 只能进入待确认风险")

        for key in ZH_FIELDS:
            if f.get(key) and not has_zh(f[key]):
                problems.append(f"{tag}：{key} 不含简体中文")

        line = f.get("line_start", f.get("line"))
        if line is None:
            problems.append(f"{tag}：缺少行锚点 line_start")
        elif isinstance(line, bool) or not isinstance(line, int) or line < 1:
            problems.append(f"{tag}：行锚点必须是正整数，实际 {line!r}")
        else:
            end = f.get("line_end", line)
            total = file_line_count(repo, head, f.get("file", ""))
            if total == -1:
                problems.append(f"{tag}：锚点文件在锁定 head 上不存在")
            elif total is not None and end > total:
                problems.append(f"{tag}：行锚点 {line}-{end} 超出文件行数 {total}（行号已过期）")
            if change_map:
                if f.get("file") not in changed:
                    problems.append(f"{tag}：锚点文件不在本次变更集内，且未标注审计边界理由")
                else:
                    spans = hunks.get(f.get("file"), [])
                    if spans and not any(a <= line <= b for a, b in spans):
                        problems.append(
                            f"{tag}：行锚点 {line} 不在变更行上（该文件变更区间 {spans}）；"
                            "如确属被变更暴露的既有代码，须在 evidence 中说明")

        fp, want = f.get("fingerprint"), fingerprint(f)
        if fp and fp != want:
            problems.append(f"{tag}：fingerprint 与规范计算值不符，应为 {want}")
        if want in seen:
            problems.append(f"{tag}：与第 {seen[want] + 1} 条同根因重复，应按根因去重后只留一个锚点")
        else:
            seen[want] = i

    reported = [f for f in findings if f.get("severity") in SEVERITY]
    p0 = [f for f in reported if f.get("severity") == "P0"]
    if len(reported) > MAX_REPORTED and len(p0) < len(reported):
        problems.append(
            f"共 {len(reported)} 个问题超过默认上限 {MAX_REPORTED}；"
            f"必须保留全部 P0（{len(p0)} 个）与风险最高者，其余归并说明，不得逐条罗列")
    return problems


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path, repo, head, cmap, allow_open = argv[0], None, None, None, False
    i = 1
    while i < len(argv):
        if argv[i] == "--repo-root":
            repo = argv[i + 1]; i += 2
        elif argv[i] == "--head":
            head = argv[i + 1]; i += 2
        elif argv[i] == "--change-map":
            cmap = argv[i + 1]; i += 2
        elif argv[i] == "--allow-open":
            allow_open = True; i += 1
        else:
            raise SystemExit(f"未知参数：{argv[i]}")

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    findings = data.get("findings", []) if isinstance(data, dict) else data
    change_map = None
    if cmap:
        with open(cmap, encoding="utf-8") as fh:
            change_map = json.load(fh)

    problems = check(findings, repo, head, change_map, allow_open)
    for line in problems:
        sys.stderr.write(line + "\n")
    if problems:
        sys.stderr.write(f"=> {len(problems)} 项违反问题契约\n")
        return 4
    print(f"ok：{len(findings)} 条问题满足准入门槛")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

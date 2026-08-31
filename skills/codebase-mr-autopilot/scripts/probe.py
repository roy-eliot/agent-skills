#!/usr/bin/env python3
"""轻量只读探针：调用 bytedcli，把原始响应确定性投影为规范 probe 对象和组合 fingerprint。

用法：
    scripts/probe.py <MR_URL> [--raw-dir <dir>] [--last <fingerprint>]

分层调用：基础三调用（mr get / mr status / comment list）总是执行；只有 MR 为 open、
无待处理评论且无失败 check 时（即真正接近合并）才补调 reviewer list 与 queue entries。
未补调的两项 fingerprint 取固定占位值，因此不会造成 fingerprint 抖动。

stdout 只输出规范 probe JSON；原始响应只写入 --raw-dir，绝不进入调用方上下文。
退出码：0 fingerprint 变化或首次；10 与 --last 相同（无需处理）；2 探针失败。
"""
import hashlib
import json
import os
import subprocess
import sys

TIMEOUT = 120


class ProbeError(Exception):
    pass


def run_json(args, raw_dir, name):
    """执行 bytedcli 并返回解析后的 JSON；原始输出只落盘。"""
    try:
        proc = subprocess.run(
            ["bytedcli", "--json"] + args,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f"{name} 执行失败：{type(exc).__name__}")
    if proc.returncode != 0:
        raise ProbeError(f"{name} 返回非零退出码 {proc.returncode}")
    if raw_dir:
        with open(os.path.join(raw_dir, f"{name}.json"), "w") as fh:
            fh.write(proc.stdout)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ProbeError(f"{name} 输出不是合法 JSON")


def _norm(key):
    return key.replace("_", "").replace("-", "").lower()


def pick(obj, *names, required=True, default=None):
    """在嵌套结构中广度优先查找第一个匹配 key 的标量值。"""
    wanted = {_norm(n) for n in names}
    queue = [obj]
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            for k, v in node.items():
                if _norm(k) in wanted and not isinstance(v, (dict, list)):
                    return v
            queue.extend(node.values())
        elif isinstance(node, list):
            queue.extend(node)
    if required:
        raise ProbeError(f"响应中找不到字段：{'/'.join(names)}")
    return default


def records(obj):
    """定位响应中的记录列表：优先常见容器 key，否则取第一个 dict 列表。"""
    for key in ("data", "items", "list", "entries", "comments", "threads", "results"):
        for node in _walk(obj):
            if isinstance(node, dict) and key in node:
                v = node[key]
                if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                    return v
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return obj
    for node in _walk(obj):
        if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
            return node
    return []


def _walk(obj):
    queue = [obj]
    while queue:
        node = queue.pop(0)
        yield node
        if isinstance(node, dict):
            queue.extend(node.values())
        elif isinstance(node, list):
            queue.extend(node)


def stable_hash(items):
    """对规范化记录做稳定 hash；空集合返回固定值，不返回 None。"""
    payload = json.dumps(sorted(items), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


NOT_PROBED = "not-probed"


FAILED_CHECK = {"failure", "failed", "error", "cancelled", "canceled", "timed_out"}


def check_states(status):
    """从 mr status 响应中取出每个 check 的结论字符串。"""
    return [str(pick(r, "conclusion", "result", "state", "status", required=False, default=""))
            for r in records(status)]


def near_merge(state, open_thread_count, check_states_list):
    """是否接近合并：只有此时 reviewer/queue 的变化才影响路由。"""
    return (state == "open"
            and open_thread_count == 0
            and not any(c.lower() in FAILED_CHECK for c in check_states_list))


def project(mr, status, comments, reviewers=None, queue=None):
    """把原始响应收敛为规范 probe 对象；只保留机器字段，剔除全部自由文本。

    reviewers/queue 为 None 表示本次未补调，对应 fingerprint 取 NOT_PROBED 占位。
    """
    state = str(pick(mr, "state", "status", "mr_state")).lower()
    if state in ("opened", "open"):
        state = "open"
    elif "merge" in state:
        state = "merged"
    else:
        state = "closed"

    threads = [
        (
            str(pick(r, "thread_id", "threadId", "id", required=True)),
            str(pick(r, "comment_id", "commentId", "latest_comment_id", "id", required=False, default="")),
            str(pick(r, "updated_at", "updatedAt", "update_time", required=False, default="")),
            str(pick(r, "author", "author_name", "user", "username", required=False, default="")),
        )
        for r in records(comments)
    ]

    checks = [
        (
            str(pick(r, "name", "check_name", "id", required=False, default="")),
            str(pick(r, "conclusion", "result", "state", "status", required=False, default="")),
            str(pick(r, "required", "is_required", required=False, default="")),
        )
        for r in records(status)
    ]

    approval_fp = NOT_PROBED if reviewers is None else stable_hash([
        (
            str(pick(r, "id", "user_id", "username", "name", required=False, default="")),
            str(pick(r, "state", "status", "approved", "review_state", required=False, default="")),
        )
        for r in records(reviewers)
    ])

    queue_fp = NOT_PROBED if queue is None else stable_hash([
        (
            str(pick(r, "id", "entry_id", required=False, default="")),
            str(pick(r, "state", "status", required=False, default="")),
            str(pick(r, "head", "sha", "head_sha", required=False, default="")),
        )
        for r in records(queue)
    ])

    return {
        "mr_state": state,
        "source_head": str(pick(mr, "source_head", "sourceHead", "source_sha", "head_sha", "sha")),
        "target_head": str(pick(mr, "target_head", "targetHead", "target_sha", "base_sha")),
        "patchset": str(pick(mr, "patchset", "patch_set", "version", "iid", required=False, default="")) or None,
        "reviewer_activity": {
            "open_thread_count": len(threads),
            "high_watermark": stable_hash(threads),
        },
        "approval_fingerprint": approval_fp,
        "required_checks_fingerprint": stable_hash(checks),
        "queue_fingerprint": queue_fp,
    }


def fingerprint(p):
    parts = [
        p["mr_state"], p["source_head"], p["target_head"], str(p["patchset"]),
        p["reviewer_activity"]["high_watermark"],
        p["approval_fingerprint"], p["required_checks_fingerprint"], p["queue_fingerprint"],
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    url = argv[0]
    raw_dir = argv[argv.index("--raw-dir") + 1] if "--raw-dir" in argv else None
    last = argv[argv.index("--last") + 1] if "--last" in argv else None
    if raw_dir:
        os.makedirs(raw_dir, exist_ok=True)
    try:
        # 基础三调用
        mr = run_json(["codebase", "mr", "get", url], raw_dir, "mr-get")
        status = run_json(["codebase", "mr", "status", url, "--page-size", "100"], raw_dir, "mr-status")
        comments = run_json(["codebase", "mr", "comment", "list", url, "--status", "open"], raw_dir, "comment-list")
        probe = project(mr, status, comments)
        # 只有接近合并时才补调另外两项
        if near_merge(probe["mr_state"],
                      probe["reviewer_activity"]["open_thread_count"],
                      check_states(status)):
            reviewers = run_json(["codebase", "mr", "reviewer", "list", url], raw_dir, "reviewer-list")
            queue = run_json(["codebase", "mr", "queue", "entries", url], raw_dir, "queue-entries")
            probe = project(mr, status, comments, reviewers, queue)
    except ProbeError as exc:
        sys.stderr.write(f"探针失败（不得解释为“没有工作”）：{exc}\n")
        return 2
    probe["fingerprint"] = fingerprint(probe)
    print(json.dumps(probe, ensure_ascii=False, indent=2, sort_keys=True))
    return 10 if last and last == probe["fingerprint"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

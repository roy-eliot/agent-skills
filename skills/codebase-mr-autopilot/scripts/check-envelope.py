#!/usr/bin/env python3
"""校验直接步骤 Worker 的结果信封、输入/输出 digest 与阶段迁移 allowlist。

用法：
    scripts/check-envelope.py <result.json> [--active-step <active_step.json>]

退出码：0 通过；4 blocked_output_contract；5 blocked_invalid_step_transition。
失败原因输出到 stderr，使用简体中文。
"""
import hashlib
import json
import os
import sys

SCHEMA_VERSION = 4

# 与 references/contracts-and-state.md 的 allowlist 必须逐字同步
TRANSITIONS = {
    "intake_sync": {"review_r1", "review_r2", "review_r3", "commit_reply",
                    "ci_diagnose_fix", "merge_gate", "waiting", "queued", "terminal"},
    "review_r1": {"fix_batch", "terminal"},
    "fix_batch": {"review_r2", "commit_reply", "terminal"},
    "review_r2": {"final_fix", "commit_reply", "terminal"},
    "final_fix": {"review_r3", "terminal"},
    "review_r3": {"commit_reply", "terminal"},
    "commit_reply": {"review_r2", "review_r3", "waiting", "queued", "terminal"},
    "ci_diagnose_fix": {"review_r2", "waiting", "terminal"},
    "merge_gate": {"waiting", "queued", "terminal"},
}

STATUSES = {"idle", "changed", "waiting", "blocked", "queued", "merged", "closed_unmerged"}

REQUIRED = [
    "schema_version", "run_id", "step_id", "step_kind", "status",
    "next_step", "continue_now", "summary_zh", "next_action_zh",
    "input_set_sha256", "output_artifacts", "artifact_path",
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def has_chinese(text):
    return any("一" <= ch <= "鿿" for ch in str(text))


def check(result_path, active_step_path=None):
    contract, transition = [], []
    try:
        env = json.load(open(result_path))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"结果文件无法解析：{exc}"], []

    for key in REQUIRED:
        if key not in env:
            contract.append(f"缺少必需字段：{key}")
    if contract:
        return contract, []

    if env["schema_version"] != SCHEMA_VERSION:
        contract.append(f"schema_version 必须为 {SCHEMA_VERSION}，实际 {env['schema_version']}")
    if env["status"] not in STATUSES:
        contract.append(f"未知 status：{env['status']}")
    if env["step_kind"] not in TRANSITIONS:
        contract.append(f"未知 step_kind：{env['step_kind']}")

    # 中文输出契约：非 idle 结果必须有可读中文
    if env["status"] != "idle":
        for field in ("summary_zh", "next_action_zh"):
            if not str(env.get(field, "")).strip():
                contract.append(f"{field} 为空")
            elif not has_chinese(env[field]):
                contract.append(f"{field} 不含简体中文：{env[field]!r}")

    # 输出产物必须存在且 hash 匹配
    for art in env.get("output_artifacts") or []:
        path, want = art.get("path"), art.get("sha256")
        if not path or not want:
            contract.append(f"输出产物缺少 path/sha256：{art}")
            continue
        if not os.path.isfile(path):
            contract.append(f"输出产物不存在：{path}")
        elif sha256_file(path) != want:
            contract.append(f"输出产物 hash 不匹配：{path}")

    # 迁移 allowlist
    allowed = TRANSITIONS.get(env["step_kind"], set())
    if env["step_kind"] in TRANSITIONS and env["next_step"] not in allowed:
        transition.append(
            f"不允许的迁移：{env['step_kind']} -> {env['next_step']}（允许：{sorted(allowed)}）"
        )

    if active_step_path:
        try:
            active = json.load(open(active_step_path))
        except (OSError, json.JSONDecodeError) as exc:
            contract.append(f"active_step 无法解析：{exc}")
            return contract, transition
        for key in ("run_id", "step_id", "step_kind"):
            if env.get(key) != active.get(key):
                contract.append(f"{key} 与 active_step 不一致：{env.get(key)} != {active.get(key)}")
        if env["input_set_sha256"] != active.get("input_set_sha256"):
            contract.append("input_set_sha256 与 active_step 不一致")
        if os.path.realpath(result_path) != os.path.realpath(active.get("result_path", "")):
            contract.append("结果文件路径与 active_step.result_path 不一致")

    return contract, transition


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    active = argv[argv.index("--active-step") + 1] if "--active-step" in argv else None
    contract, transition = check(argv[0], active)
    for line in contract + transition:
        sys.stderr.write(line + "\n")
    if contract:
        sys.stderr.write("=> blocked_output_contract\n")
        return 4
    if transition:
        sys.stderr.write("=> blocked_invalid_step_transition\n")
        return 5
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

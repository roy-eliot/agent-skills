#!/usr/bin/env python3
"""scripts/ 下确定性逻辑的自检：python3 scripts/selftest.py"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_package_digest():
    pd = load("package-digest")
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "refs"))
        open(os.path.join(d, "SKILL.md"), "w").write("a")
        open(os.path.join(d, "refs", "x.md"), "w").write("b")
        os.makedirs(os.path.join(d, "__pycache__"))
        open(os.path.join(d, "__pycache__", "junk.pyc"), "w").write("noise")
        open(os.path.join(d, ".DS_Store"), "w").write("noise")
        first, manifest = pd.package_digest(d)
        assert manifest == ["SKILL.md", "refs/x.md"], manifest
        # 排除项不影响 digest
        open(os.path.join(d, ".DS_Store"), "w").write("other noise")
        assert pd.package_digest(d)[0] == first
        # 内容变化必须改变 digest
        open(os.path.join(d, "refs", "x.md"), "w").write("c")
        assert pd.package_digest(d)[0] != first
        # 路径与内容拼接不能碰撞（NUL 分隔的意义）
        open(os.path.join(d, "refs", "x.md"), "w").write("b")
        assert pd.package_digest(d)[0] == first


def test_probe_projection():
    p = load("probe")
    mr = {"state": "opened", "source_head": "aaa", "target_head": "bbb", "version": 7}
    status = {"data": [{"name": "build", "conclusion": "success", "required": True}]}
    comments = {"data": [{"thread_id": "t1", "comment_id": "c9",
                          "updated_at": "2026-01-01", "author": "bob"}]}
    reviewers = {"data": [{"id": "u1", "state": "approved"}]}
    queue = {"data": []}

    base = p.project(mr, status, comments, reviewers, queue)
    assert base["mr_state"] == "open" and base["patchset"] == "7"
    assert base["source_head"] == "aaa" and base["target_head"] == "bbb"
    assert base["reviewer_activity"]["open_thread_count"] == 1
    f1 = p.fingerprint(base)
    assert p.fingerprint(p.project(mr, status, comments, reviewers, queue)) == f1

    # 记录顺序变化不改变 fingerprint
    two = {"data": [
        {"thread_id": "t2", "comment_id": "c1", "updated_at": "2026-01-02", "author": "amy"},
        {"thread_id": "t1", "comment_id": "c9", "updated_at": "2026-01-01", "author": "bob"},
    ]}
    rev = {"data": list(reversed(two["data"]))}
    assert p.fingerprint(p.project(mr, status, two, reviewers, queue)) == \
           p.fingerprint(p.project(mr, status, rev, reviewers, queue))

    # 每个规范字段变化都必须改变 fingerprint
    for mutated in ({**mr, "source_head": "zzz"}, {**mr, "target_head": "zzz"},
                    {**mr, "version": 8}, {**mr, "state": "merged"}):
        assert p.fingerprint(p.project(mutated, status, comments, reviewers, queue)) != f1, mutated
    assert p.fingerprint(p.project(mr, status, two, reviewers, queue)) != f1
    assert p.fingerprint(p.project(mr, status, comments,
                                   {"data": [{"id": "u1", "state": "pending"}]}, queue)) != f1
    assert p.fingerprint(p.project(mr, {"data": [{"name": "build", "conclusion": "failure"}]},
                                   comments, reviewers, queue)) != f1

    # 分层：未补调时占位，且占位值稳定（空闲 tick 不抖动）
    lite = p.project(mr, status, comments)
    assert lite["approval_fingerprint"] == p.NOT_PROBED
    assert lite["queue_fingerprint"] == p.NOT_PROBED
    assert p.fingerprint(lite) == p.fingerprint(p.project(mr, status, comments))
    assert p.fingerprint(lite) != f1  # 补调与否是不同的观测，必须可区分

    # near_merge 判据
    assert p.near_merge("open", 0, ["success"]) is True
    assert p.near_merge("open", 1, ["success"]) is False        # 有待处理评论
    assert p.near_merge("open", 0, ["success", "failure"]) is False  # 有失败 check
    assert p.near_merge("merged", 0, ["success"]) is False
    assert p.near_merge("open", 0, ["SUCCESS", "Timed_Out"]) is False  # 大小写不敏感
    assert p.check_states(status) == ["success"]

    # 缺少必需字段必须报错，而不是静默产出 fingerprint
    try:
        p.project({"state": "opened"}, status, comments)
        raise AssertionError("缺少 source_head 时应抛出 ProbeError")
    except p.ProbeError:
        pass


def _env(**over):
    env = {
        "schema_version": 4, "run_id": "r1", "step_id": "s1", "step_kind": "review_r1",
        "status": "changed", "next_step": "fix_batch", "continue_now": True,
        "summary_zh": "首轮评审完成。", "next_action_zh": "正在集中修复。",
        "input_set_sha256": "deadbeef", "output_artifacts": [], "artifact_path": "/tmp/x",
    }
    env.update(over)
    return env


def test_check_envelope():
    ce = load("check-envelope")
    with tempfile.TemporaryDirectory() as d:
        def write(env):
            path = os.path.join(d, "result.json")
            json.dump(env, open(path, "w"))
            return path

        assert ce.check(write(_env())) == ([], [])
        # 非法迁移
        _, tr = ce.check(write(_env(next_step="merge_gate")))
        assert tr and "不允许的迁移" in tr[0]
        # 反向迁移
        _, tr = ce.check(write(_env(step_kind="review_r3", next_step="fix_batch")))
        assert tr
        # 2.1 零变更批次可直达 commit_reply
        assert ce.check(write(_env(step_kind="fix_batch", next_step="commit_reply")))[1] == []
        # 2.2 R1 不能跳过评论分类
        assert ce.check(write(_env(step_kind="review_r1", next_step="commit_reply")))[1] != []
        # 2.4 commit_reply 不能回到 intake_sync（单 Cycle Run 一个批次）
        assert ce.check(write(_env(step_kind="commit_reply", next_step="intake_sync")))[1] != []
        # commit_reply 仍可因实质 churn 回到评审
        assert ce.check(write(_env(step_kind="commit_reply", next_step="review_r3")))[1] == []
        # 2.5 merge_gate 不能回到 intake_sync（紧循环）
        assert ce.check(write(_env(step_kind="merge_gate", next_step="intake_sync")))[1] != []
        assert ce.check(write(_env(step_kind="merge_gate", next_step="waiting")))[1] == []
        # 2.6 CI 批次以 waiting 结束，不回 intake_sync
        assert ce.check(write(_env(step_kind="ci_diagnose_fix", next_step="intake_sync")))[1] != []
        # 1.3 交接续做：intake_sync 可直接进重绑定评审或提交
        for nxt in ("review_r2", "review_r3", "commit_reply"):
            assert ce.check(write(_env(step_kind="intake_sync", next_step=nxt)))[1] == [], nxt
        # 中文契约
        co, _ = ce.check(write(_env(summary_zh="review done")))
        assert co and "简体中文" in co[0]
        co, _ = ce.check(write(_env(next_action_zh="  ")))
        assert co
        # idle 不强制中文摘要
        assert ce.check(write(_env(status="idle", summary_zh="", next_action_zh="",
                                   next_step="terminal")))[0] == []
        # 缺字段
        broken = _env(); del broken["run_id"]
        co, _ = ce.check(write(broken))
        assert co == ["缺少必需字段：run_id"]
        # 产物 hash
        art = os.path.join(d, "a.md")
        open(art, "w").write("hello")
        real = __import__("hashlib").sha256(b"hello").hexdigest()
        assert ce.check(write(_env(output_artifacts=[{"role": "r", "path": art, "sha256": real}])))[0] == []
        co, _ = ce.check(write(_env(output_artifacts=[{"role": "r", "path": art, "sha256": "0" * 64}])))
        assert co and "hash 不匹配" in co[0]
        co, _ = ce.check(write(_env(output_artifacts=[{"role": "r", "path": art + "-missing", "sha256": real}])))
        assert co and "不存在" in co[0]
        # active_step 身份绑定
        rp = write(_env())
        ap = os.path.join(d, "active.json")
        json.dump({"run_id": "r1", "step_id": "s1", "step_kind": "review_r1",
                   "input_set_sha256": "deadbeef", "result_path": rp}, open(ap, "w"))
        assert ce.check(rp, ap) == ([], [])
        json.dump({"run_id": "r1", "step_id": "s2", "step_kind": "review_r1",
                   "input_set_sha256": "deadbeef", "result_path": rp}, open(ap, "w"))
        co, _ = ce.check(rp, ap)
        assert co and "step_id" in co[0]
        # 退出码
        assert subprocess.run([sys.executable, os.path.join(HERE, "check-envelope.py"),
                               write(_env(next_step="merge_gate"))],
                              capture_output=True).returncode == 5
        assert subprocess.run([sys.executable, os.path.join(HERE, "check-envelope.py"),
                               write(_env(summary_zh="x"))],
                              capture_output=True).returncode == 4


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("全部自检通过")

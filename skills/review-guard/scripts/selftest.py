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


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True,
                   capture_output=True, text=True)


def make_repo(d):
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    return d


def write(repo, path, body):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(body)


def test_change_map():
    cm = load("change-map")
    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as d:
        make_repo(d)
        write(d, "go.mod", "module example.com/m\n\ngo 1.21\n")
        write(d, "pkg/a.go", "package pkg\n\n"
                             "func Exported(a string, b int) error { return nil }\n\n"
                             "func helper() {}\n\n"
                             "type T struct {\n\tName string `json:\"name\"`\n}\n")
        write(d, "pkg/a_test.go", "package pkg\n\nfunc TestOld(t *T) {}\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")

        # 签名变化 + 删除测试 + tag 变化 + 新增未导出声明
        write(d, "pkg/a.go", "package pkg\n\n"
                             "func Exported(a string) error { return nil }\n\n"
                             "func helper() {}\n\n"
                             "func fresh() {}\n\n"
                             "type T struct {\n\tName string `json:\"Name\"`\n}\n")
        write(d, "pkg/a_test.go", "package pkg\n")
        write(d, "deployments/values.yaml", "x: 1\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "change")

        out = os.path.join(work, "cm.json")
        rc = cm.main(["--repo-root", d, "--base", "HEAD~1", "--head", "HEAD", "--output", out])
        assert rc == 0
        m = json.load(open(out))

        sig = {x["name"]: x for x in m["declarations"]["signature_changed"]}
        assert "Exported" in sig, m["declarations"]
        assert sig["Exported"]["exported"] is True
        assert "b int" in sig["Exported"]["before"] and "b int" not in sig["Exported"]["after"]
        # 未变化的声明不得出现在任何一侧
        assert not any(x["name"] == "helper" for x in m["declarations"]["added"])
        assert not any(x["name"] == "helper" for x in m["declarations"]["removed"])
        assert any(x["name"] == "fresh" and not x["exported"]
                   for x in m["declarations"]["added"])
        assert [x["name"] for x in m["removed_test_functions"]] == ["TestOld"]
        tag = m["struct_fields"]["tag_changed"]
        assert len(tag) == 1 and tag[0]["before"] == 'json:"name"' \
            and tag[0]["after"] == 'json:"Name"', tag
        assert m["go_modules"]["."]["go"] == "1.21"
        assert "deployments/values.yaml" in m["signals"]["deploy"]
        assert m["hunk_lines"]["pkg/a.go"], "必须给出 hunk 行区间供锚点校验"
        assert m["scope"]["mode"] == "range"

        # 工作区模式必须含 untracked
        write(d, "pkg/newfile.go", "package pkg\n\nfunc Brand() {}\n")
        out2 = os.path.join(work, "cm2.json")
        cm.main(["--repo-root", d, "--working-tree", "--output", out2])
        m2 = json.load(open(out2))
        assert "pkg/newfile.go" in m2["scope"]["untracked_files"]
        assert any(x["name"] == "Brand" for x in m2["declarations"]["added"])

        # 产物绝不能落在被评审仓库内
        try:
            cm.main(["--repo-root", d, "--working-tree", "--output",
                     os.path.join(d, "inside.json")])
            raise AssertionError("应拒绝写入被评审仓库内")
        except SystemExit as exc:
            assert "仓库之外" in str(exc)


def test_docs_only_and_doc_references():
    cm = load("change-map")
    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as d:
        make_repo(d)
        write(d, "pkg/a.go", "package pkg\n\nfunc RealSymbol() {}\n")
        write(d, "docs/guide.md", "# guide\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")

        write(d, "docs/guide.md",
              "# guide\n\n"
              "调用 `RealSymbol` 即可，详见 [代码](pkg/a.go)。\n"
              "也可以用 `GhostSymbol`，见 [说明](docs/gone.md)。\n"
              "设置 `REAL_ENV_VAR` 和 `PHANTOM_ENV_VAR`。\n"
              "api_key = sk_live_0123456789abcdefghij\n"
              "```bash\nkubectl delete pod --all\n```\n")
        write(d, "pkg/a.go", "package pkg\n\nfunc RealSymbol() {}\n\n"
                             "// REAL_ENV_VAR is read at startup\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "docs+code")

        out = os.path.join(work, "mixed.json")
        cm.main(["--repo-root", d, "--base", "HEAD~1", "--head", "HEAD", "--output", out])
        m = json.load(open(out))
        assert m["docs_only"] is False, "混合变更集不得判为 docs_only"
        r = m["doc_references"]
        assert "GhostSymbol" in r["identifiers_not_found_in_code"]
        assert "RealSymbol" not in r["identifiers_not_found_in_code"]
        assert "PHANTOM_ENV_VAR" in r["env_vars_not_found_in_code"]
        assert "REAL_ENV_VAR" not in r["env_vars_not_found_in_code"]
        assert "docs/gone.md" in r["missing_paths"]
        assert "pkg/a.go" not in r["missing_paths"]
        assert r["possible_plaintext_secrets"], "明文凭据必须被标出"
        assert "bash" in r["code_fence_languages"]

        # 纯文档变更
        write(d, "docs/guide.md", "# guide\n\n只改措辞。\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "docs only")
        out2 = os.path.join(work, "docs.json")
        cm.main(["--repo-root", d, "--base", "HEAD~1", "--head", "HEAD", "--output", out2])
        m2 = json.load(open(out2))
        assert m2["docs_only"] is True
        assert m2["doc_references"] is not None

        # 纯代码变更不产出 doc_references
        write(d, "pkg/a.go", "package pkg\n\nfunc RealSymbol(x int) {}\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "code only")
        out3 = os.path.join(work, "code.json")
        cm.main(["--repo-root", d, "--base", "HEAD~1", "--head", "HEAD", "--output", out3])
        m3 = json.load(open(out3))
        assert m3["docs_only"] is False and m3["doc_references"] is None


def _f(**over):
    f = {"severity": "P1", "confidence": 9, "file": "pkg/a.go", "line_start": 3,
         "trigger": "调用方传入空切片时", "impact": "会返回错误结果",
         "evidence": "当前代码路径证明", "action": "补一个长度判断"}
    f.update(over)
    return f


def test_check_findings():
    cf = load("check-findings")

    assert cf.check([_f()]) == []

    def one(**over):
        p = cf.check([_f(**over)])
        return p[0] if p else ""

    assert "severity 必须是 P0/P1/P2" in one(severity="high")
    assert "confidence 必须是 1-10 的整数" in one(confidence="high")
    assert "confidence 必须是 1-10 的整数" in one(confidence=True)   # bool 不是合法整数
    assert "低于 7" in one(confidence=5)
    assert cf.check([_f(confidence=5)], allow_open=True) == []
    assert "缺少必填字段 trigger" in one(trigger="")
    assert "缺少必填字段 action" in one(action="   ")
    assert "不含简体中文" in one(impact="returns a wrong result")
    assert "缺少行锚点" in one(line_start=None)
    assert "行锚点必须是正整数" in one(line_start=0)

    # fingerprint 稳定且可复算
    a, b = _f(), _f(severity="P2", confidence=7)
    assert cf.fingerprint(a) == cf.fingerprint(b)          # 同根因，严重级别不影响
    assert cf.fingerprint(a) != cf.fingerprint(_f(file="pkg/b.go"))
    assert "fingerprint 与规范计算值不符" in one(fingerprint="0" * 16)
    assert cf.check([_f(), _f(line_start=9)])[0].startswith("第 2 条")  # 同根因去重

    # 数量上限：P0 全保留不算违规
    assert any("超过默认上限" in p for p in cf.check([_f(file=f"p/{i}.go") for i in range(6)]))
    assert not any("超过默认上限" in p
                   for p in cf.check([_f(severity="P0", file=f"p/{i}.go") for i in range(6)]))

    # 锚点真实性与 hunk 归属
    with tempfile.TemporaryDirectory() as d:
        make_repo(d)
        write(d, "pkg/a.go", "package pkg\n\nfunc A() {}\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "c")
        assert cf.check([_f()], repo=d) == []
        assert "超出文件行数" in cf.check([_f(line_start=99)], repo=d)[0]
        assert "在锁定 head 上不存在" in cf.check([_f(file="pkg/missing.go")], repo=d)[0]
        assert cf.check([_f()], repo=d, head="HEAD") == []

        cmap = {"changed_files": ["pkg/a.go"], "hunk_lines": {"pkg/a.go": [[3, 3]]}}
        assert cf.check([_f(line_start=3)], repo=d, change_map=cmap) == []
        assert "不在变更行上" in cf.check([_f(line_start=1)], repo=d, change_map=cmap)[0]
        assert any("不在本次变更集内" in x
                   for x in cf.check([_f(file="pkg/other.go", line_start=1)],
                                     repo=d, change_map=cmap))

    # 退出码
    with tempfile.TemporaryDirectory() as d:
        good, bad = os.path.join(d, "g.json"), os.path.join(d, "b.json")
        json.dump([_f()], open(good, "w"))
        json.dump({"findings": [_f(severity="high")]}, open(bad, "w"))
        script = os.path.join(HERE, "check-findings.py")
        assert subprocess.run([sys.executable, script, good],
                              capture_output=True).returncode == 0
        assert subprocess.run([sys.executable, script, bad],
                              capture_output=True).returncode == 4


def test_prepare_diff_still_runs():
    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as d:
        make_repo(d)
        write(d, "a.txt", "one\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "c")
        write(d, "a.txt", "two\n")
        out = os.path.join(work, "diff.patch")
        r = subprocess.run(["bash", os.path.join(HERE, "prepare-diff.sh"),
                            "--repo-root", d, "--working-tree", "--output", out],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out) and os.path.isfile(out + ".meta")
        assert "two" in open(out).read()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("全部自检通过")

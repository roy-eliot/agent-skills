#!/usr/bin/env python3
"""从锁定的 diff 生成变更地图，替代模型的探索性 grep/read。

用法：
    change-map.py --repo-root PATH --base REF --head REF [--output FILE]
    change-map.py --repo-root PATH --range RANGE          [--output FILE]
    change-map.py --repo-root PATH --working-tree         [--output FILE]

只读：只执行 git diff / git ls-files / rg，绝不 fetch、checkout、stage、
stash、clean，也不修改仓库文件。输出 JSON 到 --output 或 stdout。

这是发现阶段的输入，不是结论。声明与字段用正则从 diff 提取，属于线索而非
权威解析；引用列表是文本匹配，可能含同名符号。任何据此提出的问题仍必须回到
源码证实。
"""
import json
import os
import re
import subprocess
import sys

MAX_SYMBOLS_TO_TRACE = 40  # ponytail: 上限防止巨型 diff 把 rg 拖成瓶颈，不够时调大

DECL = re.compile(r'^(?P<kind>func|type|const|var)\s+(?P<rest>.*)$')
METHOD = re.compile(r'^func\s+\((?P<recv>[^)]*)\)\s*(?P<name>\w+)')
FUNC = re.compile(r'^func\s+(?P<name>\w+)')
TYPED = re.compile(r'^(?:type|const|var)\s+(?P<name>\w+)')
FIELD_TAG = re.compile(r'^\s*(?P<name>[A-Za-z_]\w*)\s+[^`]*`(?P<tag>[^`]*)`')
TEST_FUNC = re.compile(r'^func\s+(Test|Benchmark|Fuzz)\w*')
GENERATED = re.compile(r'^// Code generated .* DO NOT EDIT\.?$', re.M)

# 变更触及这些面时，兼容性/运维视角必须展开，不能只看 Go 代码
SIGNAL_PATTERNS = {
    "idl": (".thrift", ".proto", ".idl", ".avsc"),
    "schema": (".sql", "migrations/", "schema/"),
    "deploy": ("helm", "deployments/", "manifests/", "k8s/", "values.yaml"),
    "ci": (".github/", ".gitlab-ci", "jenkinsfile", "/ci/", ".codebase/"),
    "config": ("config", ".env", ".toml", ".ini"),
    "docs": ("docs/", "readme", ".md"),
}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=False).stdout


def decl_name(line):
    """从一行声明取出符号名；取不到返回 None。"""
    m = METHOD.match(line)
    if m:
        recv = re.sub(r'^\w+\s+\*?', '', m.group("recv")).strip("*")
        return f"{recv}.{m.group('name')}", m.group("name")
    for pat in (FUNC, TYPED):
        m = pat.match(line)
        if m:
            return m.group("name"), m.group("name")
    return None


def parse_diff(text):
    """按文件收集 +/- 行、hunk 行区间和声明/字段变化。"""
    files, cur = {}, None
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            files.setdefault(cur, {"added": [], "removed": [], "hunks": []})
        elif line.startswith("@@") and cur:
            m = re.search(r'\+(\d+)(?:,(\d+))?', line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2) or 1)
                if count:
                    files[cur]["hunks"].append([start, start + count - 1])
        elif cur and line.startswith("+") and not line.startswith("+++"):
            files[cur]["added"].append(line[1:])
        elif cur and line.startswith("-") and not line.startswith("---"):
            files[cur]["removed"].append(line[1:])
    return files


def collect(files):
    decls = {"added": [], "removed": [], "signature_changed": []}
    fields = {"added": [], "removed": [], "tag_changed": []}
    removed_tests = []
    by_name = {}

    for path, d in files.items():
        if not path.endswith(".go"):
            continue
        for side in ("added", "removed"):
            for raw in d[side]:
                line = raw.rstrip()
                if DECL.match(line.lstrip()) and not line.startswith((" ", "\t")):
                    got = decl_name(line)
                    if not got:
                        continue
                    full, bare = got
                    entry = {"name": full, "file": path, "exported": bare[:1].isupper(),
                             "signature": line.strip()}
                    decls[side].append(entry)
                    by_name.setdefault((path, full), {})[side] = entry
                    if side == "removed" and TEST_FUNC.match(line):
                        removed_tests.append({"name": full, "file": path})
                m = FIELD_TAG.match(raw)
                if m:
                    fields[side].append({"name": m.group("name"), "tag": m.group("tag"),
                                         "file": path})

    # 同名声明两侧都在 = 签名变化，而非增删
    for (path, name), sides in by_name.items():
        if "added" in sides and "removed" in sides:
            before, after = sides["removed"]["signature"], sides["added"]["signature"]
            if before != after:
                decls["signature_changed"].append({
                    "name": name, "file": path, "exported": sides["added"]["exported"],
                    "before": before, "after": after})
            for s in ("added", "removed"):
                decls[s].remove(sides[s])

    # 同名同文件的字段：tag 变化
    for a in list(fields["added"]):
        for r in list(fields["removed"]):
            if a["name"] == r["name"] and a["file"] == r["file"]:
                if a["tag"] != r["tag"]:
                    fields["tag_changed"].append({"name": a["name"], "file": a["file"],
                                                  "before": r["tag"], "after": a["tag"]})
                fields["added"].remove(a)
                fields["removed"].remove(r)
                break
    return decls, fields, removed_tests


def trace_references(repo, decls, changed_files):
    """用 rg 找出每个变更的导出符号在仓库内的引用；标注是否跨 package。"""
    names, seen = [], set()
    for group in ("signature_changed", "removed", "added"):
        for d in decls[group]:
            bare = d["name"].split(".")[-1]
            if d["exported"] and bare not in seen:
                seen.add(bare)
                names.append((bare, d["file"]))
    truncated = len(names) > MAX_SYMBOLS_TO_TRACE
    refs = {}
    for bare, origin in names[:MAX_SYMBOLS_TO_TRACE]:
        out = subprocess.run(
            ["rg", "-l", "--type", "go", "-w", bare, "."],
            cwd=repo, capture_output=True, text=True, check=False).stdout
        hits = [f.lstrip("./") for f in out.split() if f.strip()]
        outside = [f for f in hits if f not in changed_files]
        if hits:
            refs[bare] = {
                "defined_in": origin,
                "referenced_in": sorted(hits)[:20],
                "reference_count": len(hits),
                "referenced_outside_diff": sorted(outside)[:20],
                "cross_package": any(os.path.dirname(f) != os.path.dirname(origin)
                                     for f in hits),
            }
    return refs, truncated


def signals(repo, files, head):
    out = {k: [] for k in SIGNAL_PATTERNS}
    out["generated"] = []
    for path in files:
        low = path.lower()
        for key, pats in SIGNAL_PATTERNS.items():
            if any(p in low for p in pats):
                out[key].append(path)
        if path.endswith(".go"):
            src = (git(repo, "show", f"{head}:{path}") if head
                   else _read(os.path.join(repo, path)))
            if src and GENERATED.search(src[:4000]):
                out["generated"].append(path)
    return {k: sorted(set(v)) for k, v in out.items() if v}


DOC_EXT = (".md", ".markdown", ".rst", ".txt", ".adoc")
CODE_SPAN = re.compile(r'`([^`\n]{2,80})`')
MD_LINK = re.compile(r'\[[^\]]*\]\(([^)\s#]+)')
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\(\))?$')
ENVVAR = re.compile(r'^[A-Z][A-Z0-9_]{3,}$')
FENCE_LANG = re.compile(r'^```([A-Za-z0-9_+-]+)\s*$')
SECRETISH = re.compile(
    r'(?i)(?:api[_-]?key|secret|passwd|password|token|bearer|private[_-]key)'
    r'\s*[:=]\s*[\x27"]?([A-Za-z0-9/+_.-]{16,})')


def is_doc(path):
    return path.lower().endswith(DOC_EXT) or "/docs/" in f"/{path}" or path.startswith("docs/")


def doc_references(repo, files, head):
    """从变更的文档行里提取可机械核对的事实：引用的路径、标识符、环境变量、
    代码块语言和疑似明文凭据。文档评审据此核对与代码是否一致。"""
    paths, idents, envs, fences, secrets = {}, {}, {}, {}, []
    for path, d in files.items():
        if not is_doc(path):
            continue
        for raw in d["added"]:
            m = FENCE_LANG.match(raw.strip())
            if m:
                fences.setdefault(m.group(1).lower(), []).append(path)
                continue
            if SECRETISH.search(raw):
                secrets.append({"file": path, "line": raw.strip()[:120]})
            for link in MD_LINK.findall(raw):
                if not link.startswith(("http", "mailto", "#")):
                    paths.setdefault(link, []).append(path)
            for span in CODE_SPAN.findall(raw):
                tok = span.strip()
                if "/" in tok and "." in tok.rsplit("/", 1)[-1] and " " not in tok:
                    paths.setdefault(tok, []).append(path)
                elif ENVVAR.match(tok):
                    envs.setdefault(tok, []).append(path)
                elif IDENT.match(tok) and not tok.islower():
                    idents.setdefault(tok.rstrip("()").split(".")[-1], []).append(path)

    def exists(rel):
        base = rel.split("#")[0]
        if head:
            return subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{head}:{base}"],
                                  capture_output=True).returncode == 0
        return os.path.exists(os.path.join(repo, base))

    missing_paths = sorted({p for p in paths if not exists(p)})

    # 只在文档之外搜索：某个名字只出现在文档里，正是"文档说的东西代码里没有"
    doc_globs = []
    for ext in DOC_EXT:
        doc_globs += ["-g", f"!*{ext}"]

    def only_in_docs(name):
        hit = subprocess.run(["rg", "-l", "-w", *doc_globs, "--", name, "."],
                             cwd=repo, capture_output=True, text=True, check=False).stdout
        return not hit.strip()

    unresolved = [n for n in sorted(idents)[:MAX_SYMBOLS_TO_TRACE] if only_in_docs(n)]
    unresolved_envs = [n for n in sorted(envs)[:MAX_SYMBOLS_TO_TRACE] if only_in_docs(n)]

    return {
        "referenced_paths": {k: sorted(set(v)) for k, v in sorted(paths.items())},
        "missing_paths": missing_paths,
        "referenced_identifiers": {k: sorted(set(v)) for k, v in sorted(idents.items())},
        "identifiers_not_found_in_code": unresolved,
        "referenced_env_vars": {k: sorted(set(v)) for k, v in sorted(envs.items())},
        "env_vars_not_found_in_code": unresolved_envs,
        "code_fence_languages": {k: sorted(set(v)) for k, v in sorted(fences.items())},
        "possible_plaintext_secrets": secrets,
    }


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def go_modules(repo, changed):
    """为每个变更的 Go 包向上找最近的 go.mod，返回 module -> 语言版本。

    多 module 仓库里根目录常常没有 go.mod，版本判定必须按 module 走，
    否则会对某个 module 报告它的 Go 版本根本不支持的建议。
    """
    mods, seen = {}, set()
    for path in changed:
        if not path.endswith(".go"):
            continue
        d = os.path.dirname(path)
        while True:
            if d in seen:
                break
            seen.add(d)
            cand = os.path.join(repo, d, "go.mod") if d else os.path.join(repo, "go.mod")
            if os.path.isfile(cand):
                info = {}
                for line in _read(cand).splitlines():
                    m = re.match(r'^(module|go|toolchain)\s+(\S+)', line.strip())
                    if m:
                        info[m.group(1)] = m.group(2)
                mods[d or "."] = info
                break
            if not d:
                break
            d = os.path.dirname(d)
    return mods


def main(argv):
    args = dict(repo=None, base=None, head=None, rng=None, wt=False, out=None)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo-root": args["repo"] = argv[i + 1]; i += 2
        elif a == "--base": args["base"] = argv[i + 1]; i += 2
        elif a == "--head": args["head"] = argv[i + 1]; i += 2
        elif a == "--range": args["rng"] = argv[i + 1]; i += 2
        elif a == "--working-tree": args["wt"] = True; i += 1
        elif a == "--output": args["out"] = argv[i + 1]; i += 2
        elif a in ("-h", "--help"): raise SystemExit(__doc__)
        else: raise SystemExit(f"未知参数：{a}\n{__doc__}")
    if not args["repo"]:
        raise SystemExit("必须提供 --repo-root\n" + __doc__)
    repo = args["repo"]

    if args["wt"]:
        mode, head = "working_tree", None
        text = git(repo, "diff", "-U0", "HEAD")
        untracked = [f for f in git(repo, "ls-files", "--others",
                                    "--exclude-standard").split("\n") if f]
        for path in untracked:
            body = _read(os.path.join(repo, path))
            text += f"\n+++ b/{path}\n@@ -0,0 +1,{len(body.splitlines())} @@\n"
            text += "".join("+" + ln + "\n" for ln in body.splitlines())
        scope = {"mode": mode, "base": "HEAD", "head": "working-tree",
                 "untracked_files": untracked}
    elif args["rng"]:
        mode, head = "range", args["rng"].split("..")[-1] or "HEAD"
        text = git(repo, "diff", "-U0", args["rng"])
        scope = {"mode": mode, "range": args["rng"]}
    elif args["base"] and args["head"]:
        head = args["head"]
        text = git(repo, "diff", "-U0", f'{args["base"]}...{args["head"]}')
        scope = {"mode": "range", "base": args["base"], "head": head,
                 "base_sha": git(repo, "rev-parse", args["base"]).strip(),
                 "head_sha": git(repo, "rev-parse", head).strip()}
    else:
        raise SystemExit("必须提供 --base/--head、--range 或 --working-tree\n" + __doc__)

    files = parse_diff(text)
    decls, fields, removed_tests = collect(files)
    changed = sorted(files)
    refs, truncated = trace_references(repo, decls, set(changed))

    packages = {}
    for path in changed:
        if path.endswith(".go"):
            pkg = os.path.dirname(path) or "."
            packages.setdefault(pkg, {"files": [], "test_files": []})
            key = "test_files" if path.endswith("_test.go") else "files"
            packages[pkg][key].append(path)

    result = {
        "schema_version": 1,
        "caveat": "线索而非结论：声明与字段由正则提取，引用为文本匹配，可能含同名符号；据此提出的问题仍须回源码证实。",
        "scope": scope,
        "go_modules": go_modules(repo, changed),
        "changed_files": changed,
        "hunk_lines": {p: d["hunks"] for p, d in files.items() if d["hunks"]},
        "packages": [{"package": k, **v} for k, v in sorted(packages.items())],
        "declarations": decls,
        "struct_fields": fields,
        "removed_test_functions": removed_tests,
        "references": refs,
        "references_truncated": truncated,
        "signals": signals(repo, changed, head),
        "docs_only": bool(changed) and all(is_doc(p) for p in changed),
        "doc_references": doc_references(repo, files, head) if any(is_doc(p) for p in changed) else None,
    }
    text_out = json.dumps(result, ensure_ascii=False, indent=2)
    if args["out"]:
        # 与 prepare-diff.sh 同一约束：评审产物不得落在被评审仓库内
        if os.path.commonpath([os.path.realpath(args["out"]),
                               os.path.realpath(repo)]) == os.path.realpath(repo):
            raise SystemExit("--output 必须位于被评审仓库之外")
        with open(args["out"], "w", encoding="utf-8") as fh:
            fh.write(text_out + "\n")
        print(args["out"])
    else:
        print(text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

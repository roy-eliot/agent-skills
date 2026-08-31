#!/usr/bin/env python3
"""计算 Skill package digest：按相对 POSIX 路径排序，依次输入 path、NUL、原始字节、NUL。

用法：
    scripts/package-digest.py <package-root>
    scripts/package-digest.py <package-root> --expect <digest>   # 不匹配时退出码 3

排除 .git、.DS_Store、__pycache__、*.pyc。
"""
import hashlib
import os
import sys

EXCLUDE_DIRS = {".git", "__pycache__"}
EXCLUDE_FILES = {".DS_Store"}


def package_digest(root):
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        raise SystemExit(f"包目录不存在：{root}")
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in filenames:
            if name in EXCLUDE_FILES or name.endswith(".pyc"):
                continue
            path = os.path.join(dirpath, name)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            files.append((os.path.relpath(path, root).replace(os.sep, "/"), path))
    if not files:
        raise SystemExit(f"包目录为空：{root}")
    h = hashlib.sha256()
    for rel, path in sorted(files):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        with open(path, "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    return h.hexdigest(), [rel for rel, _ in sorted(files)]


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    root = argv[0]
    expect = None
    if "--expect" in argv:
        expect = argv[argv.index("--expect") + 1]
    digest, manifest = package_digest(root)
    print(digest)
    if expect and digest != expect:
        sys.stderr.write(
            f"digest 不匹配：期望 {expect}，实际 {digest}\n"
            f"规范 root：{os.path.realpath(root)}\n"
            f"文件清单（{len(manifest)}）：\n  " + "\n  ".join(manifest) + "\n"
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

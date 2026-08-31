# Agent Skills

个人维护的可复用 Agent Skills 仓库。每个 Skill 都是 `skills/` 下的独立目录，可以分别安装到 Codex、Claude Code 或其他兼容 Agent 运行时。

## 仓库结构

```text
agent-skills/
├── skills/
│   ├── codebase-mr-autopilot/
│   │   ├── SKILL.md
│   │   ├── agents/
│   │   ├── evals/
│   │   ├── references/
│   │   └── scripts/
│   └── review-guard/
│       ├── SKILL.md
│       ├── agents/
│       ├── evals/
│       ├── references/
│       └── scripts/
├── .gitignore
└── README.md
```

新增 Skill 时直接创建 `skills/<skill-name>/`。目录名必须与 `SKILL.md` frontmatter 中的 `name` 一致。

## 当前 Skills

| Skill | 用途 | 依赖 |
|---|---|---|
| `codebase-mr-autopilot` | 一次处理或持续跟进一个已授权的 Codebase Go MR，处理评论、修复、CI、rebase 和合并 | `review-guard` |
| `review-guard` | 对 Go MR、分支、提交范围或工作区变更进行证据驱动的只读 Review | 无 |

`codebase-mr-autopilot` 与 `review-guard` 是并列 Skill。Autopilot 的 R1/R2/R3 Review 会调用独立的 `review-guard`，因此使用 Autopilot 时必须同时安装两者。不要把 `review-guard` 复制进 Autopilot 目录，也不要在多个发现目录中保留不同实体的同名副本。

两个 Skill 的说明、流程、评测描述和用户可见提示均使用简体中文。为保证跨运行时兼容，Skill 名称、命令、文件路径、JSON key、状态枚举和代码符号仍保留英文原值。

### Autopilot 运行模式

Autopilot 的业务流程只有一个有界 `Cycle Run`，外层支持两种模式：

- `once`：执行一次完整处理后退出，不创建 scheduler。适合手动检查/处理当前评论、CI 或合并状态。
- `loop`：立即执行一次，再由 Agent 运行时的原生固定间隔循环重复；适合持续监听直到真正合并。默认间隔 `1m`，也可以显式指定其他受支持 cadence。

没有明确持续意图时默认 `once`。loop 空闲轮次只比较轻量状态 fingerprint，未变化时不创建业务子 Agent；R1 保持完整评审，R2 默认复审修复影响闭包并在高风险条件下回退全量评审。

## 安装

推荐把这个 Git 仓库作为唯一维护源，再把需要的 Skill 链接到各运行时的发现目录。

### 通用目录

```bash
mkdir -p ~/.agents/skills
ln -s <repo>/skills/codebase-mr-autopilot ~/.agents/skills/codebase-mr-autopilot
ln -s <repo>/skills/review-guard ~/.agents/skills/review-guard
```

### Claude Code

```bash
mkdir -p ~/.claude/skills
ln -s ../../.agents/skills/codebase-mr-autopilot ~/.claude/skills/codebase-mr-autopilot
ln -s ../../.agents/skills/review-guard ~/.claude/skills/review-guard
```

### Codex

如果当前 Codex 已发现 `~/.agents/skills`，无需重复安装。否则可以链接到 `~/.codex/skills`：

```bash
mkdir -p ~/.codex/skills
ln -s ../../.agents/skills/codebase-mr-autopilot ~/.codex/skills/codebase-mr-autopilot
ln -s ../../.agents/skills/review-guard ~/.codex/skills/review-guard
```

安装前先检查目标路径；如果已经存在同名目录或链接，应先比较并确定唯一 canonical copy，不要直接覆盖。

## 维护约定

- 每个 Skill 必须包含合法的 `SKILL.md`，并保持入口简洁、按需加载 `references/`。
- `agents/`、`evals/`、`references/`、`scripts/` 和 `assets/` 只在 Skill 确实需要时创建。
- 修改后运行 Skill validator，并验证所有相对链接、JSON 和脚本。
- `codebase-mr-autopilot` 与 `review-guard` 的兼容 digest 必须同步更新：改动 `review-guard` 后运行 `skills/codebase-mr-autopilot/scripts/package-digest.py skills/review-guard`，把新值写回 `references/review-guard-compatibility.md`。
- 改动 `skills/*/scripts/` 后运行对应 `selftest.py`。
- 不提交个人 owner policy、MR 运行状态、worktree、lease、日志、凭证或其他私密运行数据。

## 更新本地安装

不要再把 Git 仓库内容复制到运行时目录。所有运行时目录都只保留指向本仓库的软链接，因此拉取仓库就是更新本地安装：

```bash
cd <repo>
git pull --ff-only
```

Claude Code 支持 `~/.claude/skills/<skill-name>` 指向磁盘其他位置的目录软链接，并监听现有 Skill 目录中的 `SKILL.md` 变化；普通 Skill 文本更新可以在当前会话被检测到。如果顶层 Skill 目录是在会话启动后才首次创建，则重启一次 Claude Code。

Codex 或其他运行时是否热加载由其自身版本决定。更新后应重新运行校验；已有长期运行的 Agent loop 建议重新载入对应 Skill，避免继续使用旧会话中的缓存指令。

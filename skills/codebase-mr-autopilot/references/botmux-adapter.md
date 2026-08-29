# 可选 Botmux 适配器

只有用户明确选择 botmux 来创建/桥接主控 session、启动直接步骤 Worker 或返回紧凑中文报告时，才读取本文。核心 Skill 无需 botmux 也能运行。

## 严格两层拓扑

Botmux 必须保持以下精确拓扑：

```text
一个主控 bot session
└── 一个或多个全新的直接步骤 Worker session/goal
```

每个步骤 Worker 都必须由主控亲自创建。步骤 Worker 不得调用 `botmux dispatch`、`botmux goal run`，不得 `@mention` 其他 Agent、创建子 topic/session，也不得要求主控把 Worker 创建的 session 当作主控的子级。任何要求 `Main -> Cycle Worker -> Reviewer` 的适配器配置都必须拒绝。

## 适配器预检

实时派发前确认已安装的 botmux 版本和当前 `--help`。botmux 标识符只能持久化在适配器配置中，不要放入可移植的核心范围。

每次调用使用一个主控 topic/session。brief 只包含不可变范围、`once|loop` 模式、loop interval（仅 loop）、Skill 调用、中文输出和紧凑报告要求。绝不能把 MR diff、评论、CI 日志或英文原始信封粘贴进去。

## 创建或桥接主控 session

对于已绑定正确仓库的稳定 bot app：

```text
botmux dispatch --title "MR <id> 自动跟进" \
  --bot-app <larkAppId:role> \
  --brief-file <absolute-brief-file>
```

当前 botmux 不支持同时使用 `--repo` 和 `--bot-app`。不得组合使用。

对于需要明确工作目录、受信任的同机 legacy bot：

```text
botmux dispatch --title "MR <id> 自动跟进" \
  --bot <open_id:name:role> \
  --repo <absolute-repo-path> \
  --brief-file <absolute-brief-file>
```

## once 与 Claude 原生 loop

`once` 只向主控 session 发送：

```text
/codebase-mr-autopilot once <MR_URL>
```

执行一个完整 Cycle Run 后返回。不得配置 `/loop` allowlist，不得注入 schedule，也不得因为缺少 scheduler 权限阻塞。

`loop` 才执行以下流程。在所选 bot 上只允许必需的 slash command：

```json
{
  "tuiSlashAllow": ["/loop"]
}
```

主控立即执行一次 Cycle Run 后，把固定间隔运行时原生循环注入同一个空闲主控 session：

```text
botmux slash "/loop <interval> /codebase-mr-autopilot loop-cycle <MR_URL>"
```

`<interval>` 来自用户或 owner policy，缺省 `1m`；必须显式提供，避免 Claude 动态 loop 改用 Monitor。Botmux 只负责传输 slash command，循环仍由 Claude 持有。把 Claude 返回的精确 scheduled-task ID 记录在核心范围中。进入终止状态时，Claude 必须删除该 task ID 并验证它不再出现在任务列表中。不得用 botmux workflow loop 替代。

## 启动一个全新的直接步骤 Worker

优先使用目标运行时原生的直接子 Agent。如果不可用，主控可以亲自使用所选 botmux 适配器运行一个全新的同级 goal worker：

```text
botmux goal run --goal-file <step-goal-file> \
  --run-id <stable-step-id> \
  --working-dir <absolute-repo-path> \
  --json
```

goal 文件必须包含 [supervisor-and-runtimes.md](supervisor-and-runtimes.md) 中的直接步骤 Worker prompt 契约，包括禁止嵌套委派，以及所有自然语言信封字段必须使用简体中文。只有同一个规范步骤才能复用 Step ID。如果 goal 执行不可用，主控可以直接创建一个可见子 topic/session，但该 topic 仍是叶子节点，并且只能返回紧凑步骤结果信封。

绝不能让修复 Worker 创建 R1/R2/R3 Worker。主控必须先接收修复结果，再把 Reviewer 作为独立同级 Worker 创建。

## 报告与停止

- 实质进展或终止结果可以使用一次紧凑的 `botmux report`，内容必须为简体中文。
- 主控渲染 `summary_zh` 和 `next_action_zh`；绝不能把原始 JSON 或英文 enum 值作为人类报告转发。
- loop 的 fingerprint 未变化、idle 或 waiting tick 不产生冗长 topic 消息；once 只发送一次最终结果。
- 仅 loop 在终止时取消并验证精确运行时 task ID；once 的 scheduler 为 `not_applicable`。
- 除非用户另行要求，否则绝不能 archive/delete botmux topic。

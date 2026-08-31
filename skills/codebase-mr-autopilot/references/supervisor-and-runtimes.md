# 主 Agent 与运行时

启动/初始化和主 Agent 读取本文。业务执行核心见 [execution-core.md](execution-core.md)，持久化状态见 [contracts-and-state.md](contracts-and-state.md)。架构始终只有两层：

```text
主 Agent
├── Intake Sync Worker
├── R1/R2/R3 评审 Worker
├── 修复 Worker
├── Commit/Reply Worker
├── CI Worker
└── 合并 Worker
```

Cycle Run 是主 Agent 持有的执行边界，不是第二层 Agent。以上 Worker 都是主 Agent 的直接同级子级；任何 Worker 都不得创建、派发、mention-route 或请求其他 Agent、task、topic、session、goal worker 或 container。

## 初始化预检

1. 解析用户意图为 `once|loop`；歧义时使用 `once`。持久化 execution mode，再按 [owner-policy-and-worktree.md](owner-policy-and-worktree.md) 优先绑定当前明确调用的默认授权，可选 owner policy 只作为持续授权或工作区配置来源。
2. 确认当前运行时/容器中可使用 `bytedcli` 和 Git；记录已认证 Codebase actor，用于排除 Agent 自己的回复。
3. 应用 [review-guard-compatibility.md](review-guard-compatibility.md)：要求唯一规范兼容包，并证明全新直接评审 Worker 能自行调用。失败时使用 `blocked_review_dependency` 停止；若旧状态是尚未创建 worktree/scope/lease/业务步骤的预检阻塞，新明确调用先按 [contracts-and-state.md](contracts-and-state.md) 重新验证并恢复。
4. 确认 source checkout 指向指定 MR 仓库；它可以为脏。创建或安全复用 MR 专用 worktree；修改工作区必须干净或由 active run 可解释。
5. 确认主 Agent 可以创建不继承 MR 细节的全新直接叶子 Worker，并接收 [step-worker-contract.md](step-worker-contract.md) 的紧凑信封。只能把 Review 实现为 Worker 的子 Worker 时，使用 `blocked_nested_delegation` 停止。
6. 仅 `loop`：确认运行时具有固定间隔原生调度、精确 task ID 和精确取消/查询能力。`once` 跳过全部 scheduler 预检。

初始化后立即执行一次共享 Cycle Run。`once` 执行结束即返回。`loop` 只有在立即 Cycle Run 未进入终止状态时才启用原生循环；如果已终止，持久化 `scheduler.status=not_armed`，不创建 task。

## 当前运行时直接启动

在兼容 Agent 运行时或容器中安装/链接本 Skill。两种模式都直接使用当前 session 的主 Agent，不需要外部 orchestrator、topic、report command 或适配器凭证。

一次执行：

```text
/codebase-mr-autopilot once <MR_URL>
```

持续执行：

```text
/codebase-mr-autopilot loop <MR_URL> --interval 1m
```

命令语法可按运行时改为 `$codebase-mr-autopilot`，但语义不变。用户未给模式且自然语言也不明确时，按 `once` 执行。

所有运行时都必须：

- 保留或从磁盘重建主 Agent 的紧凑状态；
- 创建不继承详细评论/diff/log 的全新直接叶子 Worker；
- 让直接评审 Worker 自行调用已绑定的 `review-guard`；
- 禁止直接 Worker 继续创建子级；
- 只把紧凑信封返回主 Agent。

`loop` 还必须能创建、查询和取消精确原生 task；无法提供时安全失败，但不得影响 `once`。

## Claude Code

`once` 直接运行 Skill，不调用 `/loop`：

```text
/codebase-mr-autopilot once <MR_URL>
```

`loop` 先运行一次 Cycle Run，然后在同一 Claude session 中创建固定间隔任务：

```text
/loop <interval> /codebase-mr-autopilot loop-cycle <MR_URL>
```

`loop-cycle` 是仅供已绑定 scheduler 使用的内部入口：它要求磁盘范围为 `execution.mode=loop`，且当前 session、MR、prompt 与唯一 active task ID 匹配；随后只执行一个 Cycle Run，绝不再次创建 scheduler。用户直接调用 `loop-cycle` 但没有有效绑定时，返回 `blocked_scheduler_binding`。

默认 `<interval>` 为 `1m`，用户可以指定 Claude 当前版本支持的其他固定间隔。固定间隔是硬要求：不得省略 interval，因为 Claude 的动态 `/loop` 可能改用 Monitor；本 Skill 明确禁止 Monitor/后台 watcher。Claude `/loop` 最小粒度为一分钟，秒会向上取整到分钟；启动前实时检查当前 `claude --version` 和官方文档/本地 help。

捕获 Claude 确认的精确 job ID 并只绑定一次。如果当前 session、MR URL、mode 和 prompt 已有一个精确匹配 task，复用其 ID；没有则创建；存在多个匹配项时使用 `blocked_scheduler_binding` 停止，不得猜测。

Claude 忙碌时，到期 prompt 等待当前 turn 结束；错过的间隔不会并行补跑。主 Agent 的 fingerprint 和 Cycle Run lease 是额外的幂等/并发保护。指纹未变化时不得创建业务 Worker。

固定 loop 不会因 `queued`、push 或测试通过而停止。出现 `merged`、`closed_unmerged` 或终止 blocker 时，先持久化、释放当前 lease，再删除精确 task ID 并验证它已消失。Claude recurring task 七天后过期；临近过期且 MR 仍 open 时，先原子创建替代 task、持久化新 ID，再取消旧 ID，绝不能重叠。无法安全替换时报告 `blocked_loop_expiry`。

官方行为参考：<https://code.claude.com/docs/en/scheduled-tasks>。

## 其他运行时适配器契约

启用其他 CLI/容器的 `loop` 前，验证当前本地 help 或官方文档，并记录：

- 固定间隔 prompt 的精确启动形式；
- 是恢复当前 session 还是创建新 session；
- 精确 stop/cancel/query 形式和终止行为；
- 最小/最大执行频率、jitter 和过期时间；
- 直接子 Agent 机制和结果传输；
- 禁止叶子 Worker 继续委派的强制方式；
- 忙碌或错过的迭代会排队、跳过还是重复。

任一项未知时，`loop` 安全失败；如果其余能力满足，可以建议用户改用 `once`，但不得擅自切换。不得发明 schedule directive，也不得用外部 workflow loop 替代运行时原生循环。

`once` 只需验证直接 Worker 和业务工具能力，不验证任何 scheduler 字段。

## 主 Agent 执行 Cycle Run

主 Agent 只执行以下序列：

1. 读取 execution mode、持久化阶段、`active_step`/`step_handoff`、probe fingerprint 和 lease 元数据。
2. 按 [execution-core.md](execution-core.md) 执行最小只读探针。指纹不变且没有未完成 run 时，不获取 lease、不创建业务 Worker。
3. 如果 MR 已是终止状态：持久化；`loop` 取消并验证精确 task，`once` 不接触 scheduler；输出一次中文报告。
4. 如果另一 run 持有有效 lease，保持静默或输出一行中文等待信息，不派发。属于当前 `active_run_id` 时，只按持久化步骤恢复。
5. 否则创建/恢复 `run_id`，获取 Cycle Run lease，持久化直接 Worker 的 `active_step`、输入产物、结果路径和有限 deadline，然后派发。
6. 验证持久化结果文件、输入/输出 hash、中文字段和 allowlist 迁移。原子持久化 `next_step`/`step_handoff`；只有 `continue_now=true` 才立即派发下一个同级 Worker。
7. 串行推进直到 Cycle Run 边界，释放 lease，记录 invocation 结果。
8. `once` 输出结果并退出；`loop` 在非终止结果后等待下一次原生唤醒。

主 Agent 只持有运行模式、scheduler、轻量 probe、lease、phase、active Step 发布、紧凑交接、中文渲染和停止。它不读取详细问题、评论正文、diff 或日志，不执行 Git 操作，不判断/修改代码，不回复，不操作 CI，也不入队合并。

典型评论批次的同级步骤：

```text
intake_sync -> review_r1 -> fix_batch -> review_r2
            -> optional final_fix -> optional review_r3
            -> commit_reply
```

会修改代码的 CI Worker 返回一个允许的后续评审阶段，由主 Agent 创建该评审 Worker；不得自行创建 Reviewer。

## Worker 选择顺序

使用第一个可用选项：

1. 运行时原生直接子 Agent：只继承范围、阶段和产物路径。
2. 运行时原生隔离 task/container：由主 Agent 创建，使用相同最小 prompt 和信封。
3. 用户明确选择的外部适配器：由主 Agent 创建一个同级 Worker。使用 botmux 时读取 [botmux-adapter.md](botmux-adapter.md)。

如果都不可用，安全失败；不要让主 Agent 执行业务工作。后续阶段或下一 Cycle Run 不复用 Worker 对话。Worker 的输入和结果必须遵守 [step-worker-contract.md](step-worker-contract.md)。

## 中文进度与结果

所有用户可见文本使用简体中文。主 Agent绝不能展示原始 JSON 或把英文 enum 直接当作报告。推荐文案：

- `本次检查未发现需要处理的新状态。`
- `检测到 4 条待处理评论，正在同步目标分支并准备首轮评审。`
- `首轮评审完成，确认 2 个问题，正在集中修复。`
- `修复后评审通过，正在提交并逐条回复评论。`
- `已进入 rebase merge 队列；本次执行结束。`（once）
- `已进入 rebase merge 队列，继续监听直到 MR 真正合并。`（loop）
- `自动处理已停止：<中文原因>。详细证据：<artifact_path>`

`loop` 的 fingerprint 未变化时保持静默。实质阶段可各输出一行，不能持续输出 Worker 推理、diff、日志或信封。实质结果缺少有效 `summary_zh`/`next_action_zh` 时记录 `blocked_output_contract`，使用固定中文降级文案。

| 内部 status | once | loop |
|---|---|---|
| `idle` | 报告本次无待办并退出 | 静默等待 |
| `changed` | 报告已推送并退出 | 等待远端状态 |
| `waiting` | 报告等待对象并退出 | 静默等待 |
| `queued` | 报告已入队但未合并并退出 | 继续监听 |
| `blocked` | 报告中文原因并退出 | 取消 task 后报告 |
| `merged` | 报告已合并 | 取消 task 后报告 |
| `closed_unmerged` | 报告已关闭未合并 | 取消 task 后报告 |

除非用户另行要求，不得 archive/delete 运行时 session、container 或适配器 topic。

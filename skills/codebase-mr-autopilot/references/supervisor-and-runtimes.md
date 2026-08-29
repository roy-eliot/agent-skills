# 主控与运行时适配器

启动/初始化和主控模式使用本文。架构严格限制为两层：

```text
主控 Agent
├── Intake/Rebase 步骤 Worker
├── R1/R2/R3 评审步骤 Worker
├── 修复步骤 Worker
├── Commit/Reply 步骤 Worker
├── CI 步骤 Worker
└── 合并步骤 Worker
```

以上每个 Worker 都是主控的直接子级，并且彼此同级。主控与 Reviewer 之间不存在 Cycle Worker 父级。只有主控可以派发；任何步骤 Worker 都不得创建、派发、mention-route 或请求其他 Agent、task、topic、session、goal worker 或 container。

## 初始化预检

创建监听器前：

1. 确认精确 MR URL、运行时、直接子级 Worker 机制和 report adapter。加载 [owner-policy-and-worktree.md](owner-policy-and-worktree.md)，然后持久化 [contracts-and-state.md](contracts-and-state.md) 中的 checkout/worktree 绑定和授权记录。
2. 确认当前运行时/容器中可使用 `bytedcli` 和 Git；记录已认证 Codebase actor，用于区分 Agent 自己的回复。只有用户选择了某个适配器时，才要求该适配器 executable。
3. 应用 [review-guard-compatibility.md](review-guard-compatibility.md)：枚举所有同名发现候选项，要求存在唯一不同的规范兼容包，确认直接评审步骤可以调用，并持久化其 path/digest。如果发现、兼容性或调用不可用或存在歧义，使用 `blocked_review_dependency` 停止；绝不能使用内部替代品。
4. 确认 source checkout 指向指定 MR 仓库。它允许为脏，因为初始化不得修改它。创建或安全复用 MR 专用 worktree；修改工作区必须干净，或由 active run 持有。
5. 确认运行时同时提供原生周期唤醒和原生停止操作。
6. 确认主控可以启动全新的直接子级 Worker，并接收紧凑步骤结果信封。任何只能把 Review 实现为另一个 Worker 子级的机制都必须拒绝。

初始化后立即运行一次主控 tick。只有预检成功且立即 tick 未进入终止状态时，才启用周期循环。如果该 tick 进入终止状态，持久化 `scheduler.status=not_armed`，用简体中文报告一次，并且绝不创建 scheduled task。

## 当前运行时独立启动

在当前兼容 Agent 运行时或容器中安装或链接本 Skill。加载 owner policy，绑定自动创建的专用 worktree，以启动/初始化模式调用 `codebase-mr-autopilot`，立即运行一次主控 tick，然后启用运行时原生周期 prompt。不需要外部 orchestrator、topic、report command 或适配器凭证。

运行时必须能够：

- 保留或重建主控的紧凑状态上下文。
- 进入终止状态时停止/取消自己的周期 task。
- 允许主控启动一个不继承 MR 细节的全新直接子级。
- 允许直接评审步骤自行调用已绑定的 `review-guard` Skill。
- 阻止每个直接子级继续创建子级。
- 只向主控返回紧凑步骤结果信封。

无法提供这些能力时安全失败。

## Claude Code 适配器

把本 Skill 安装或链接到 Claude Code 可发现 project/user skill 的位置。在独立 Claude session 中，先立即运行一次主控 tick，然后调用：

```text
/loop 1m /codebase-mr-autopilot supervisor <MR_URL>
```

需要由外部适配器创建 session、注入 `/loop`、创建 Worker 或返回报告时，只读取对应适配器 reference。使用 botmux 时读取 [botmux-adapter.md](botmux-adapter.md)。独立 Claude session 不加载它。

使用这个固定的一分钟原生调度。捕获 Claude 确认的 8 字符 job ID，并在范围中只绑定一次。如果精确 session、MR URL 和 prompt 已有匹配 task，复用其 ID，不创建重复 task。如果有多个 task 匹配，使用 `blocked_scheduler_binding` 停止，不得猜测。

存在工作时，主控在同一个 active turn 中串行派发全新的同级步骤 Worker，以推进持久化阶段机。主控绝不能要求某个 Worker 派发下一个 Worker。如果没有工作，Intake 步骤返回紧凑 idle 结果，主控等待下一个 tick。Claude 可能应用最多为一分钟间隔一半的确定性 scheduler jitter。Claude 忙碌时，到期 prompt 会等待当前 turn 结束；错过的间隔不会创建并行补跑。写 lease 是第二道并发保护。

固定 loop 不会自行停止。出现 `merged`、`closed_unmerged` 或终止 blocker 时，持久化终止状态，只释放本轮拥有的 lease，对精确绑定的 task ID 调用运行时 scheduled-task delete 操作，验证它已从任务列表消失，并用简体中文报告一次。loop 的范围是 session，七天后过期。如果临近过期时 MR 仍为 open，原子创建替代 task、持久化新 ID，再取消精确旧 ID；否则报告 `blocked_loop_expiry`。绝不能让两个 active task 重叠。

本 Skill 不得使用 Claude Monitor/后台脚本。用户要求使用 scheduler 支持的原生 loop 唤醒。

官方行为参考：<https://code.claude.com/docs/en/scheduled-tasks>。

## 其他运行时适配器契约

启用其他 CLI 前，验证其当前本地 help 或官方文档，并记录：

- 精确的周期 prompt 启动形式。
- 是恢复当前 session，还是创建新 session。
- 精确 stop/cancel 形式和终止状态行为。
- 最小/最大执行频率和过期时间。
- 直接子级子 Agent 机制和结果传输方式。
- 保证或可强制执行的 prompt/policy，确保直接子级不能继续委派。
- 错过/忙碌的迭代会排队、跳过还是重复。

上述任一项未知时安全失败。不得发明原始 schedule directive。不得用任何外部 workflow engine loop 替代运行时原生主控 loop。

## 主控 tick 与阶段派发

主控只执行以下序列：

1. 读取范围、持久化阶段、`active_step`/`step_handoff` 和 lease 元数据；绝不读取详细问题或日志。
2. 如果存在终止状态，取消精确绑定的运行时原生 task ID，验证取消，并用简体中文报告一次。
3. 如果另一个 run 持有有效 lease，保持静默，或只显示下方定义的一行中文等待信息。不得派发。如果 lease 属于当前 `active_run_id`，只能通过持久化步骤协议恢复或继续。
4. 否则创建或恢复一个 `run_id`；主控获取/续期 Cycle Run lease，持久化下一个直接子级的 `active_step`、输入产物、确定性结果路径和有限 deadline，然后派发。
5. 根据持久化结果文件和输入/输出 hash 验证返回信封。原子持久化 `next_step` 与 `step_handoff`；只有 `continue_now=true` 时才派发下一个直接同级 Worker。
6. 串行重复步骤 4，直到批次完成、等待远端状态、达到有界 R1/R2/R3 限制或发生阻塞。同一个 MR 绝不能同时运行两个步骤 Worker。
7. 返回 `queued` 时继续循环但不再次入队。返回 `merged`、`closed_unmerged` 或终止 `blocked` 时，取消精确 task ID 并报告一次。

主控只持有 loop/orchestration 元数据：原生 schedule、lease、phase、active Step 发布、紧凑交接、中文渲染和停止。它仍然不读取 MR 正文/diff/log，不执行 Git/bytedcli 业务操作，不判断问题，不修改代码，不回复，不操作 CI，也不合并。

典型评论批次的同级步骤为：

```text
intake_rebase -> review_r1 -> fix_batch -> review_r2
              -> optional final_fix -> optional review_r3
              -> commit_reply
```

CI 和合并使用直接 `ci_diagnose_fix` 与 `merge_gate` 步骤。会修改代码的 CI 步骤返回 `next_step=review_r2` 或其他已持久化评审阶段；它不得自行创建 Reviewer。

## 直接步骤 Worker 选择顺序

使用第一个可用选项：

1. **运行时原生直接子 Agent：** 由主控创建，除范围、阶段和产物路径外，不继承对话历史。
2. **运行时原生隔离 task/container：** 由主控创建，使用同样的最小 prompt 和紧凑结果契约。
3. **用户明确选择的外部适配器：** 由主控创建一个同级 Worker，并接收相同紧凑信封。使用 botmux 时参考 [botmux-adapter.md](botmux-adapter.md)。

如果都不可用，安全失败；不要让主控执行 MR/Git 工作。绝不能为后续阶段或 tick 复用步骤 Worker 对话。绝不能接受由 Worker 创建的 Reviewer 或修复者。

## 直接步骤 Worker prompt 契约

主控只向 Worker 提供：

```text
使用 $codebase-mr-autopilot 的 Direct Step Worker 模式。
你是主 Agent 的直接子 Agent，只执行下面这一阶段；严禁创建、派发或请求任何子 Agent、子任务、topic、session、goal worker 或容器。
MR：<exact URL>
仓库：<absolute path>
状态根目录：<absolute path>
运行 ID：<run-id>
步骤 ID：<step-id>
步骤类型：<step-kind>
输入产物：<artifact paths only>
授权：<persisted scope subset>
授权来源：<explicit grant or owner-policy path and digest>
评审 Skill：位于 <package root> 的 review-guard，digest 为 <package digest>
所有自然语言字段使用简体中文。只返回紧凑的 Step Result Envelope；详细信息写入运行目录。
```

Claude 子 session 要求 slash-skill 语法时，使用 `/codebase-mr-autopilot` 而不是 `$codebase-mr-autopilot`。评审步骤自行调用 `/review-guard`；它仍不得继续委派。

如果步骤 Worker 收到任何创建其他 Worker 的指令，必须拒绝执行。它使用中文说明记录 `blocked_nested_delegation`，并把控制权返回主控。

## 中文进度与报告

所有用户可见文本都必须使用简体中文：运行时 commentary、botmux 报告、blocker、终止摘要和 Codebase 线程回复。代码符号、命令、ID、路径、SHA、`review-guard` 结论和内部 enum 可以保留原样。

主控绝不能把原始 JSON 或英文 enum 值作为报告输出。它渲染信封中的中文字段。推荐使用以下简洁文案：

- `检测到 4 条待处理评论，正在同步目标分支并准备首轮评审。`
- `首轮评审完成，确认 2 个问题，正在集中修复。`
- `修复后评审通过，正在提交并逐条回复评论。`
- `已进入 rebase merge 队列，继续监听直到 MR 真正合并。`
- `自动处理已停止：<中文原因>。详细证据：<artifact_path>`

没有变更的 tick 保持静默。长时间运行的 active turn 进入实质阶段时可以输出一行中文，但不得持续输出原始 Worker 推理、diff、日志或信封。

如果实质步骤信封缺少可用的中文 `summary_zh`/`next_action_zh`，主控不得转发其中英文文本或原始 JSON。持久化 `blocked_output_contract`，并渲染本地中文降级文案 `自动处理已停止：子任务没有返回符合中文输出契约的结果。`。

状态渲染：

| 内部 status | 用户可见中文 |
|---|---|
| `idle` | 当前没有新的评论或待处理动作。 |
| `changed` | 已完成本轮修复并推送。 |
| `waiting` | 正在等待流水线、审批或合并队列状态更新。 |
| `blocked` | 自动处理已停止：`summary_zh`。 |
| `queued` | 已进入 rebase merge 队列，继续监听。 |
| `merged` | MR 已合并，监听已停止。 |
| `closed_unmerged` | MR 已关闭但未合并，监听已停止。 |

idle/waiting tick 不产生冗长报告。发送唯一一次最终中文报告前，必须持久化终止状态、释放精确持有的 lease，并取消及验证精确原生 task。除非用户另行要求，否则绝不能 archive/delete 运行时 session、container 或适配器拥有的 topic。

---
name: codebase-mr-autopilot
description: 对用户明确指定的 Codebase Go MR 执行一次有界处理，或持续监听直到真正合并；由一个主 Agent 直接调度同级叶子子 Agent，处理评论、review-guard 评审、事实修复或驳回、提交前 rebase、逐线程回复、CI 和 rebase merge。适用于一次性处理当前 MR 状态，或用户明确要求持续跟进的场景；不适用于纯只读评审或非 Go 仓库。
---

# Codebase MR 自动跟进

使用一个共享的有界 `Cycle Run` 处理 MR，再用两个很薄的运行模式决定是否重复它：

- `once`：立即执行一次完整 Cycle Run，然后退出；不创建 scheduler。
- `loop`：立即执行一次 Cycle Run，再用当前 Agent 运行时的原生固定间隔循环重复执行，直到 MR 真正合并、关闭或出现终止阻塞。

架构严格限制为两层：一个主 Agent，加一个或多个由主 Agent 直接创建的同级叶子步骤 Worker。步骤 Worker 绝不能创建、派发或请求其他 Agent。所有用户可见过程和 Codebase 回复使用简体中文。

需要 Git、具备 Codebase 权限的 `bytedcli`、可独立发现的 `review-guard` Skill，以及可创建全新直接子 Agent 的兼容运行时/容器。只有 `loop` 模式要求原生周期调度能力。外部 session/worker 适配器只是可选项，不是核心依赖。

## 选择运行模式

优先采用用户明确指定的模式；没有明确参数时按意图判断：

- “执行一次”“处理一下”“检查当前评论/流水线” -> `once`
- “持续监听”“一直跟进”“直到合并” -> `loop`
- 仍有歧义 -> 默认 `once`，不得擅自创建长期循环

循环间隔只属于 `loop`。用户未指定时默认 `1m`；用户指定时验证当前运行时支持的最小粒度和语法。存在工作时，在同一个 Cycle Run 中连续推进，不等待下一次间隔；只有 `idle`、外部 `waiting` 或 `queued` 后才等待下一次唤醒。

两种模式必须读取 [execution-core.md](references/execution-core.md)。运行时选择、启动和停止读取 [supervisor-and-runtimes.md](references/supervisor-and-runtimes.md)。

## 角色与按需加载

- **启动/初始化：** 解析用户的明确调用和可选 owner policy，验证输入和精确兼容的 `review-guard`，然后自动创建专用 worktree。读取 [owner-policy-and-worktree.md](references/owner-policy-and-worktree.md)、[review-guard-compatibility.md](references/review-guard-compatibility.md)、[execution-core.md](references/execution-core.md)、[supervisor-and-runtimes.md](references/supervisor-and-runtimes.md) 和 [contracts-and-state.md](references/contracts-and-state.md)。
- **主 Agent：** 只保留运行模式、轻量只读探针、Cycle Run lease、阶段编排、直接子级派发、紧凑结果校验、中文渲染和停止状态。读取 [execution-core.md](references/execution-core.md)、[supervisor-and-runtimes.md](references/supervisor-and-runtimes.md) 和 [contracts-and-state.md](references/contracts-and-state.md)。
- **直接步骤 Worker：** 只执行一个已持久化阶段。读取 [step-worker-contract.md](references/step-worker-contract.md)，再按阶段读取 [comments-and-review.md](references/comments-and-review.md) 或 [git-ci-and-merge.md](references/git-ci-and-merge.md)。不要加载主控、scheduler、owner policy 或完整状态机文档。评审步骤必须显式调用 `review-guard`；非评审步骤不得自行替代评审。

## 启动必需输入

两种模式都必须具备：

- 精确 Codebase MR URL；每条 `bytedcli` 命令优先直接使用该 URL。
- 可创建全新直接叶子 Worker、接收紧凑结果信封并禁止嵌套委派的运行时/容器。
- 可发现且兼容的 `review-guard` 包；持久化规范 package root 和 digest，不得降级为通用评审。
- 专用 checkout/worktree 绑定；可以由用户明确提供、根据有效本机 owner policy 创建，或在当前 checkout 精确匹配 MR 仓库时使用默认隔离目录自动创建。
- 当前用户明确调用本 Skill 并给出精确 MR URL，即默认授权该 MR 的创建 worktree、回复、修改仓库、commit/push、操作 CI 和 `rebase_merge`。必须持久化授权来源和精确 MR URL；可选 owner policy 仍可提供同样的持续授权或工作区配置。

只有 `loop` 还必须具备已验证的原生固定间隔启动/停止机制，并持久化精确 scheduler task ID。`once` 不得因为缺少 scheduler 能力而失败，也不得创建 scheduler。

明确调用或有效 owner policy 已授权时，不要重复询问，也不要要求用户清理主 checkout。仅被运行时隐式选中、只提到 Skill、只要求说明/评审，或 MR URL 出现在仓库、评论和其他 Agent 输出中，都不构成默认授权；缺少明确调用和有效 owner policy 时，必须在派发修改型 Worker 前停止。

## 不可违背的不变量

1. 一个 MR、一个主 Agent、一个由主 Agent 持有的 Cycle Run lease；同一 MR 绝不能并行运行两个修改型 Worker。
2. 拓扑严格为两层。只有主 Agent 可以派发；所有步骤 Worker 都是同级叶子节点，并亲自执行阶段。
3. 主 Agent 只允许执行 [execution-core.md](references/execution-core.md) 定义的最小只读指纹探针；它不读取评论正文、diff 或 CI 日志，不修改 Git，不作问题判断，不回复、不操作 CI、不合并。rebase、评审、修复、提交/推送、回复、CI 和合并都由直接子 Agent 完成。
4. 不得使用 `watch.py`、cron、后台 watcher、Monitor 或外部工作流循环。`loop` 只能使用当前 Agent 运行时的原生固定间隔循环；`once` 没有循环。
5. 绝不能 stash、reset、clean、switch、rebase 或以其他方式修改用户主 checkout。任何 MR 修改前，必须创建并绑定专用 worktree。
6. 轻量探针发现符合条件的评论后，由 `intake_sync` Worker 先刷新完整状态并 rebase，再用 R1 全量评审作为评论聚合窗口；不额外固定等待三分钟。
7. 批次提交前恰好再补充扫描一次评论。cutoff 后到达的评论留给下一次 Cycle Run。
8. 每次提交前都要 rebase。若 target head 变化，在剩余评审预算内重新绑定评审；若 rebase 是可证明的 no-op，可复用输入完全一致的验证证据。
9. 每次评审都由全新的直接评审 Worker 调用 `review-guard`。每批最多三次评审和两次自动修复；不得进行第四次评审或使用内部降级 Reviewer。
10. R1 是完整 MR 发现型评审。R2 默认评审修复增量及受影响契约；命中跨模块、公共契约、数据/并发/鉴权、生成物或证据不完整等回退条件时，必须改为完整预期 MR 评审。R3 只做有界定向验证。
11. 在每个相关 Codebase 线程中回复。绝不能 resolve 或关闭 Reviewer 评论；关闭权属于 Reviewer。
12. 先诊断 CI，再执行操作。相同 `HEAD + check + failure fingerprint` 默认最多重试一次。
13. 绝不能执行无保护 force push。只有 rebase 改写已授权 MR 分支时，才使用精确 `--force-with-lease=<branch>:<expected-sha>`。
14. 审批只能观察，不能制造。绝不能 self-approve。
15. 只允许进入 `rebase_merge` 队列。`loop` 继续监听到 MR 报告 `merged`；`once` 可以以 `queued` 结束本次运行，但不得宣称已合并。

## 运行结束与终止

`once` 的 `idle`、`changed`、`waiting`、`queued` 都只是本次执行结果：释放 lease、持久化可恢复状态并退出，不写 MR 终止状态。`loop` 在这些结果后继续等待下一次原生唤醒。

以下才是 MR 级终止结果；`loop` 还要取消并验证精确 scheduler task，`once` 的 scheduler 始终为 `not_applicable`：

- `merged`
- `closed_unmerged`
- `blocked_permission`
- `blocked_rebase_conflict`
- `blocked_target_churn`
- `blocked_review_nonconvergent`
- `blocked_review_dependency`
- `blocked_review_incomplete`
- `blocked_ci_nonconvergent`
- `blocked_ambiguous_feedback`
- `blocked_nested_delegation`
- `blocked_invalid_step_transition`
- `blocked_output_contract`
- `blocked_scheduler_binding`（仅 `loop`）
- `blocked_loop_expiry`（仅 `loop`）

成功 push、进入合并队列、Agent 已回复或本地测试通过，都不能单独视为 MR 已完成。

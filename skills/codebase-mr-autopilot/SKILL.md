---
name: codebase-mr-autopilot
description: 持续监管一个已授权的 Codebase Go MR 直到真正合并，由一个主 Agent 直接调度同级叶子子 Agent，并用简体中文汇报进度。适用于用户明确要求持续监听 MR 评论并自动处理的场景：调用配套的 review-guard Skill、修复事实成立的反馈、每次提交前 rebase、逐线程回复、修复 CI，并进入 rebase merge 队列。可直接运行在兼容的 Agent 运行时或容器中，也支持可选外部适配器。不适用于一次性/只读评审或非 Go 仓库。
---

# Codebase MR 自动跟进

每个 MR 运行一个长期存活、低上下文的主控 Agent（Main/Supervisor）。它把所有 MR 读取、评审、仓库修改、回复、CI 操作和合并操作，直接委派给全新的同级子 Agent。拓扑严格限制为两层：一个主 Agent，加一个或多个直接子级步骤 Worker（Step Worker）。步骤 Worker 绝不能创建、派发或通过另一个子 Agent 通信。持续运行，直到 Codebase 报告 `merged`，或记录终止性阻塞。

需要 Git、具备 Codebase 权限的 `bytedcli`、可独立发现的 `review-guard` Skill，以及已验证具有原生周期循环和全新 Worker 机制的 Agent 运行时/容器。使用已有的 MR 专用 checkout，或根据可信的本机 owner policy 创建一个。外部 session/worker 适配器只是可选项，绝不是核心依赖。

## 选择模式

- **启动/初始化（Start/bootstrap）：** 用户要求创建监听器时使用。加载本机 owner policy，验证输入和精确兼容的 `review-guard` 包；获得授权后自动创建专用 worktree；先执行一次主控 tick，再启用原生循环。只有用户明确选择适配器时才创建外部 session。读取 [owner-policy-and-worktree.md](references/owner-policy-and-worktree.md)、[review-guard-compatibility.md](references/review-guard-compatibility.md)、[supervisor-and-runtimes.md](references/supervisor-and-runtimes.md) 和 [contracts-and-state.md](references/contracts-and-state.md)。
- **主控（Main/Supervisor）：** 上下文中只保留原生循环、lease/阶段检查、直接子级派发、紧凑步骤结果信封（Step Result Envelope）、中文进度渲染和停止状态。它是唯一允许派发子 Agent 的 Agent。只读取 [supervisor-and-runtimes.md](references/supervisor-and-runtimes.md) 和 [contracts-and-state.md](references/contracts-and-state.md)。
- **直接步骤 Worker（Direct Step Worker）：** 只执行一个已持久化阶段，例如 intake/rebase、R1/R2/R3 评审、修复、提交/回复、CI 或合并门禁。它从主控接收阶段和产物路径，返回一个紧凑信封，并且不得派发或请求另一个子 Agent。先读取 [contracts-and-state.md](references/contracts-and-state.md)，再按所分配阶段读取 [comments-and-review.md](references/comments-and-review.md) 或 [git-ci-and-merge.md](references/git-ci-and-merge.md)。评审步骤必须显式调用 `review-guard`；非评审步骤绝不能自行替代评审。

## 启动必需输入

创建实时监听器前必须具备以下全部条件：

- 精确的 Codebase MR URL。每条 `bytedcli` 命令都应优先直接使用该 URL。
- 运行时/容器身份、已验证的原生循环启动/停止机制，以及已验证的全新 Worker 创建方式。适配器专用 selector 为可选项。
- 可发现的 `review-guard` 包，且全新的直接评审步骤能够在不继续委派的情况下自主调用它。持久化其 package root 和 digest；不得静默降级为通用评审。
- 专用 checkout/worktree 绑定。它可以由用户明确提供，也可以根据有效的本机 owner policy 自动创建。
- 创建 worktree、回复、修改仓库、commit/push、操作 CI 和 `rebase_merge` 的授权。可以接受当前请求中的明确授权，也可以接受有效的本机 owner policy；必须持久化授权来源和已授予子集。自动发现 Skill 不等于获得变更授权。

有效 owner policy 已授予所需操作时，不要要求用户重复授权或清理主 checkout。如果仍缺少输入或权限，必须在派发修改型 Worker 前停止。

明确要求启动本自动跟进 Skill，表示用户授权主控创建本文约定的直接子级步骤 Worker，包括只读评审步骤；这绝不授权步骤 Worker 再创建其他 Agent，也不授权超出单独持久化变更范围的任何仓库或远端修改。

## 不可违背的不变量

1. 一个 MR、一个主控、一个由主控持有的 Cycle Run lease。绝不能同时运行两个修改型 Worker。
2. 拓扑严格为两层。只有主控可以派发。每个步骤 Worker 都必须拒绝嵌套委派，并亲自执行所分配阶段，不得创建子 Agent、task、topic、session 或 container。
3. 主控不执行 `bytedcli` MR 读取、不检查 diff/log，也不触碰 Git。它只通过派发全新的直接子级步骤 Worker、消费紧凑信封来推进持久化阶段机。
4. 不得使用 `watch.py`、cron、后台 watcher 或外部工作流循环作为周期机制。必须使用所选 Agent 运行时的原生循环。
5. 绝不能 stash、reset、clean、switch、rebase 或以其他方式修改用户的主 checkout。任何 MR 修改前，必须自动创建并绑定专用 worktree。
6. 出现符合条件的评论时，先 rebase，并用 R1 全量评审作为评论聚合窗口。不得额外固定等待三分钟。
7. 批次提交前，再补充扫描一次评论。扫描 cutoff 之后到达的评论留到下一轮处理。
8. 每次提交前都要 rebase。如果评审后 target head 发生移动，在剩余评审预算内 rebase 并重新验证。
9. 每次评审都由全新的直接子级评审步骤调用 `review-guard`。每个批次最多三次评审调用和两次自动修复。不得进行第四次评审，也不得使用内部降级 Reviewer。
10. 在每个相关 Codebase 线程中回复。绝不能 resolve 或关闭 Reviewer 评论；关闭权属于 Reviewer。
11. 先诊断 CI，再执行操作。默认情况下，相同 `HEAD + check + failure fingerprint` 最多重试一次。
12. 绝不能执行无保护的 force push。只有 rebase 改写了已授权 MR 分支时，才使用明确 source ref 的 `--force-with-lease=<branch>:<expected-sha>`。
13. 审批只能观察，不能制造。绝不能通过自我 approve 满足合并门禁。
14. 只允许进入 `rebase_merge` 队列，然后持续监听，直到 MR 自身报告 `merged`。
15. 所有用户可见进度、阻塞、摘要、终止报告和 Codebase 线程回复都必须使用简体中文。内部 JSON key 和状态 enum 可以保留英文，但主控绝不能把原始信封当作用户报告输出。

## 终止结果

出现以下结果时，停止原生循环、释放 lease、持久化终止状态并简洁报告：

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
- `blocked_scheduler_binding`
- runtime loop 已过期，且没有安全的重新启用路径

仅进入合并队列、成功 push、Agent 已回复或本地测试通过，都不能单独视为任务完成。

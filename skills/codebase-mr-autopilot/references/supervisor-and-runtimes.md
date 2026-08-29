# Supervisor and Runtime Adapters

Use this reference for start/bootstrap and Main/Supervisor modes. The architecture is strictly two layers:

```text
Main/Supervisor Agent
├── Intake/Rebase Step Worker
├── R1/R2/R3 Review Step Worker
├── Fix Step Worker
├── Commit/Reply Step Worker
├── CI Step Worker
└── Merge Step Worker
```

Every worker above is a direct child and peer of the others. There is no Cycle Worker parent between Main and a Reviewer. Only Main may dispatch; no Step Worker may create, dispatch, mention-route, or request another agent, task, topic, session, goal worker, or container.

## Bootstrap preflight

Before creating a listener:

1. Confirm the exact MR URL, runtime, direct-child worker mechanism, and report adapter. Load [owner-policy-and-worktree.md](owner-policy-and-worktree.md), then persist the checkout/worktree binding and authorization record from [contracts-and-state.md](contracts-and-state.md).
2. Confirm `bytedcli` and Git are available in the current runtime/container; record the authenticated Codebase actor used to distinguish the Agent's own replies. Require an adapter executable only when the user selected that adapter.
3. Apply [review-guard-compatibility.md](review-guard-compatibility.md): enumerate all same-name discovery candidates, require one distinct canonical compatible package, confirm that a direct Review Step can invoke it, and persist its path/digest. If discovery, compatibility, or invocation is unavailable or ambiguous, stop with `blocked_review_dependency`; never use an internal substitute.
4. Confirm the source checkout points at the named MR repository. Its dirty state is allowed because bootstrap must not mutate it. Provision or safely reuse the dedicated MR worktree; require that mutation workspace to be clean or owned by the active run.
5. Confirm the runtime exposes both a native recurring wakeup and a native stop operation.
6. Confirm Main can start fresh direct-child workers and receive compact Step Result Envelopes. Reject any mechanism that can only implement Review as a child of another worker.

Run one Main tick immediately after bootstrap. Arm the recurring loop only after preflight succeeds and the immediate tick remains nonterminal. If that tick reaches terminal state, persist `scheduler.status=not_armed`, report once in Simplified Chinese, and never create a scheduled task.

## Standalone current-runtime start

Install or link this Skill in the current compatible agent runtime or container. Load the owner policy, bind the automatically provisioned dedicated worktree, invoke `codebase-mr-autopilot` in Start/bootstrap mode, run one immediate Main tick, then arm the runtime-native recurring prompt. No external orchestrator, topic, report command, or adapter credential is required.

The runtime must be able to:

- Keep or recreate Main's compact state context.
- Stop/cancel its own recurring task on terminal state.
- Let Main start a fresh direct child without inherited MR details.
- Let a direct Review Step invoke the bound `review-guard` Skill itself.
- Prevent every direct child from spawning another child.
- Return only the compact Step Result Envelope to Main.

Fail closed if it cannot provide these capabilities.

## Claude Code adapter

Install or link this Skill where Claude Code discovers project/user skills. In a standalone Claude session, run one immediate Main tick and then invoke:

```text
/loop 1m /codebase-mr-autopilot supervisor <MR_URL>
```

When an external adapter must create the session, inject `/loop`, create workers, or return reports, read only that adapter's reference. For botmux, read [botmux-adapter.md](botmux-adapter.md). A standalone Claude session does not load it.

Use this fixed one-minute native schedule. Capture the 8-character job ID confirmed by Claude and bind it once in scope. If a matching task already exists for the exact session, MR URL, and prompt, reuse its ID instead of creating a duplicate. If multiple tasks match, stop with `blocked_scheduler_binding` rather than guessing.

When work exists, Main advances the persisted phase machine by dispatching fresh peer Step Workers sequentially in the same active turn. It never asks a worker to dispatch the next worker. If no work exists, the Intake Step returns a compact idle result and Main waits for the next tick. Claude may apply deterministic scheduler jitter of up to half the one-minute interval. When Claude is busy, a due prompt waits until the current turn ends and missed intervals do not create parallel catch-up runs. The write lease is the second concurrency guard.

Fixed loops do not self-stop. On `merged`, `closed_unmerged`, or a terminal blocker, persist terminal state, release only the owned lease, call the runtime's scheduled-task delete operation for the exact bound task ID, verify it is absent from the task list, and report once in Simplified Chinese. The loop is session-scoped and expires after seven days. If the MR remains open near expiry, atomically create a replacement task, persist its new ID, then cancel the old exact ID; otherwise report `blocked_loop_expiry`. Never overlap two active tasks.

Do not use Claude Monitor/background scripts for this Skill. The user requires scheduler-backed native loop wakeups.

Official behavior reference: <https://code.claude.com/docs/en/scheduled-tasks>.

## Other runtime adapter contract

Before enabling another CLI, verify its current local help or official documentation and record:

- Exact recurring-prompt start form.
- Whether the current session is resumed or a new session is created.
- Exact stop/cancel form and terminal-state behavior.
- Minimum/maximum cadence and expiry.
- Direct-child subagent mechanism and result transport.
- A guarantee or enforceable prompt/policy that direct children cannot delegate further.
- Whether a missed/busy iteration is queued, skipped, or duplicated.

Fail closed if any of these are unknown. Do not invent raw schedule directives. Do not substitute any external workflow engine's loop for the runtime-native Main loop.

## Main tick and phase dispatch

Main performs only this sequence:

1. Read scope, durable phase, `active_step`/`step_handoff`, and lease metadata; never read detailed findings or logs.
2. If terminal state exists, cancel the exact bound runtime-native task ID, verify cancellation, and report once in Simplified Chinese.
3. If another run owns a valid lease, remain silent or show the single Chinese waiting line defined below. Do not dispatch. If the lease belongs to the current `active_run_id`, recover or continue only through the durable Step protocol.
4. Otherwise create or resume one `run_id`; Main acquires/renews the Cycle Run lease, persists the next direct child's `active_step`, input artifacts, deterministic result path, and finite deadline, then dispatches it.
5. Validate its returned envelope against the durable result file and input/output hashes. Atomically persist `next_step` plus `step_handoff`, then dispatch the next direct peer only when `continue_now=true`.
6. Repeat step 4 sequentially until the batch finishes, waits for remote state, reaches the bounded R1/R2/R3 limit, or blocks. Never have two Step Workers running concurrently for the same MR.
7. On `queued`, keep looping without enqueueing again. On `merged`, `closed_unmerged`, or terminal `blocked`, cancel the exact task ID and report once.

Main owns only loop/orchestration metadata: native schedule, lease, phase, active Step publication, compact handoff, Chinese rendering, and stop. It still does not read MR bodies/diffs/logs, run Git/bytedcli business operations, judge findings, modify code, reply, operate CI, or merge.

Typical comment-batch peers are:

```text
intake_rebase -> review_r1 -> fix_batch -> review_r2
              -> optional final_fix -> optional review_r3
              -> commit_reply
```

CI and merge use direct `ci_diagnose_fix` and `merge_gate` Steps. A code-changing CI Step returns `next_step=review_r2` or another persisted review phase; it does not create a Reviewer itself.

## Direct Step Worker preference

Use the first available option:

1. **Runtime-native direct subagent** created by Main with no inherited conversation history beyond scope, phase, and artifact paths.
2. **Runtime-native isolated task/container** created by Main with the same minimal prompt and compact result contract.
3. **Explicitly selected external adapter** where Main creates one peer worker and receives the same compact envelope. For botmux, use [botmux-adapter.md](botmux-adapter.md).

If none is available, fail closed; do not make Main perform MR/Git work. Never reuse a Step Worker conversation for a later phase or tick. Never accept a worker-created Reviewer or fixer.

## Direct Step Worker prompt contract

Main gives the worker only:

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
Review Skill：review-guard at <package root>, digest <package digest>
所有自然语言字段使用简体中文。只返回紧凑的 Step Result Envelope；详细信息写入运行目录。
```

For a Claude child session, use `/codebase-mr-autopilot` instead of `$codebase-mr-autopilot` when slash-skill syntax is required. A Review Step invokes `/review-guard` itself; it still may not delegate.

If a Step Worker receives any instruction to create another worker, it must not comply. It records `blocked_nested_delegation` with a Chinese explanation and returns control to Main.

## Chinese progress and reporting

All user-visible text must use Simplified Chinese: runtime commentary, botmux reports, blockers, terminal summaries, and Codebase thread replies. Code symbols, commands, IDs, paths, SHAs, `review-guard` verdicts, and internal enums may remain literal.

Main never prints raw JSON or English enum values as the report. It renders the envelope's Chinese fields. Recommended concise lines:

- `检测到 4 条待处理评论，正在同步目标分支并准备首轮评审。`
- `首轮评审完成，确认 2 个问题，正在集中修复。`
- `修复后评审通过，正在提交并逐条回复评论。`
- `已进入 rebase merge 队列，继续监听直到 MR 真正合并。`
- `自动处理已停止：<中文原因>。详细证据：<artifact_path>`

No-change ticks stay silent. A long-running active turn may emit one Chinese line when entering a material phase, but must not stream raw worker reasoning, diffs, logs, or envelopes.

If a material Step envelope lacks usable Chinese `summary_zh`/`next_action_zh`, Main must not forward its English text or raw JSON. Persist `blocked_output_contract` and render the local Chinese fallback `自动处理已停止：子任务没有返回符合中文输出契约的结果。`.

Status rendering:

| Internal status | User-visible Chinese |
|---|---|
| `idle` | 当前没有新的评论或待处理动作。 |
| `changed` | 已完成本轮修复并推送。 |
| `waiting` | 正在等待流水线、审批或合并队列状态更新。 |
| `blocked` | 自动处理已停止：`summary_zh`。 |
| `queued` | 已进入 rebase merge 队列，继续监听。 |
| `merged` | MR 已合并，监听已停止。 |
| `closed_unmerged` | MR 已关闭但未合并，监听已停止。 |

Idle/waiting ticks do not produce verbose reports. Terminal state must be persisted, the exact owned lease released, and the exact native task cancelled and verified before the one final Chinese report. Never archive/delete a runtime session, container, or adapter-owned topic unless the user separately requests it.

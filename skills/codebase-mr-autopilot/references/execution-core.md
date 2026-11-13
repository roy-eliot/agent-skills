# 共享执行核心

`once` 与 `loop` 共用同一个有界 `Cycle Run`。模式只决定 Cycle Run 运行一次还是由原生 scheduler 重复唤醒；评论、评审、修复、CI、rebase 和合并语义不得分叉。运行时与 scheduler 细节见 [supervisor-and-runtimes.md](supervisor-and-runtimes.md)，持久化结构见 [contracts-and-state.md](contracts-and-state.md)。

## Cycle Run 边界

一次 Cycle Run 从轻量探针开始，在以下任一边界结束：

- 当前指纹没有变化，或没有可执行工作；
- 已完成一次内聚评论/修复/回复批次并需要等待远端 CI、审批或 Reviewer；
- 已触发一次 CI 操作并需要等待结果；
- 已进入 merge queue；
- 达到评审、修复或 CI 重试预算；
- MR 已合并、已关闭或进入终止阻塞。

Cycle Run 不是一个中间父 Agent。它只是主 Agent 持有的状态和 lease；所有业务阶段仍由主 Agent 直接创建的同级叶子 Worker 执行。

## 轻量只读探针

主 Agent 每次开始 Cycle Run 时执行：

`once` 且磁盘上没有 `last_probe_fingerprint`（首次处理该 MR）时**跳过探针**，直接进入 `intake_sync`：此时探针必然返回“有变化”，而 `intake_sync` 会重新读取完整 MR 状态，5 次 bytedcli 调用是纯浪费。其余情况（`loop` 的每次唤醒、`once` 的后续调用）都必须执行探针。

```text
scripts/probe.py <MR_URL> --raw-dir <state-root>/runs/<run-id>/probe --last <last_probe_fingerprint>
```

脚本调用 `bytedcli --json`，把原始响应只写入 `--raw-dir`，stdout 只输出规范 probe 对象和组合 `fingerprint`。原始 JSON 不得进入主 Agent 上下文或用户报告。fingerprint 绑定 `mr_state + source_head + target_head + patchset + reviewer_activity.high_watermark + approval_fingerprint + required_checks_fingerprint + queue_fingerprint`。

退出码即路由：

- `10`（与 `last_probe_fingerprint` 相同）：不得创建业务 Worker。`loop` 静默等待下一次唤醒；`once` 返回“当前状态无变化，无需处理”。
- `0`：首次运行或 fingerprint 变化，进入完整 intake。上次运行未完成时同样进入 intake。
- `2`：探针失败。执行一次有界重试；仍失败则返回中文阻塞/等待结果，不得把“读取失败”解释为“没有工作”。字段定位失败也走这条路径，绝不静默产出 fingerprint。

轻量探针是主 Agent 唯一允许的 MR 读取。任何需要评论正文、diff、日志、具体审批人、失败详情或问题判断的读取，都必须交给直接 Worker。

## 共享阶段

当探针需要继续时，主 Agent 获取 Cycle Run lease，并按持久化阶段串行派发：

```text
intake_sync
  ├── comments -> review_r1 -> fix_batch -> review_r2
  │                           -> optional final_fix -> optional review_r3
  │                           -> commit_reply
  ├── failed CI -> ci_diagnose_fix
  ├── merge-ready -> merge_gate
  └── idle / waiting / queued / terminal
```

`intake_sync` 把完整路由与初始 rebase 合并为一个阶段：它读取最新 MR 状态；存在符合处理条件的评论时同步 source/target 并在专用 worktree rebase，然后输出 R1 请求。这样每个活跃评论批次少创建一个 Worker，同时仍保证先 rebase、后 R1。完整 intake 的路由判定顺序见 [contracts-and-state.md](contracts-and-state.md)。

存在工作时，主 Agent 根据 `continue_now=true` 在同一个 active turn 中继续派发下一同级 Worker，不等待 scheduler。只有到达 Cycle Run 边界才释放 lease。

## 主 Agent 执行序列

主 Agent 只执行以下序列：

1. 读取 execution mode、持久化阶段、`active_step`/`step_handoff`、probe fingerprint 和 lease 元数据。
2. 执行上述轻量探针。指纹不变且没有未完成 run 时，不获取 lease、不创建业务 Worker。
3. 如果 MR 已是终止状态：持久化；`loop` 取消并验证精确 task，`once` 不接触 scheduler；输出一次中文报告。
4. 如果另一 run 持有有效 lease，保持静默或输出一行中文等待信息，不派发。属于当前 `active_run_id` 时，只按持久化步骤恢复。
5. 否则创建/恢复 `run_id`，获取 Cycle Run lease，持久化直接 Worker 的 `active_step`、输入产物、结果路径和有限 deadline，然后派发。
6. 用 `scripts/check-envelope.py <result.json> --active-step <active_step.json>` 校验持久化结果：身份、输入/输出 hash、中文字段和迁移 allowlist。退出码 `4` 记为 `blocked_output_contract`，`5` 记为 `blocked_invalid_step_transition`。通过后原子持久化 `next_step`/`step_handoff`；只有 `continue_now=true` 才立即派发下一个同级 Worker。
7. 串行推进直到 Cycle Run 边界，释放 lease，记录 invocation 结果。
8. `once` 输出结果并退出；`loop` 在非终止结果后等待下一次原生唤醒。

主 Agent 只持有运行模式、scheduler、轻量 probe、lease、phase、active Step 发布、紧凑交接、中文渲染和停止。它不读取详细问题、评论正文、diff 或日志，不执行 Git 操作，不判断/修改代码，不回复，不操作 CI，也不入队合并。

会修改代码的 CI Worker 返回一个允许的后续评审阶段，由主 Agent 创建该评审 Worker；不得自行创建 Reviewer。

## 评审范围

- **R1：** 始终是完成初始 rebase 后的完整预期 MR 发现型评审，同时充当评论聚合窗口。
- **R2：** 默认评审本轮修复 delta、被修改符号的直接调用/实现契约和相关测试；仍要绑定完整 prospective MR 的 target/source/worktree digest。命中回退条件时改为完整预期 MR 评审。
- **R3：** 仅验证 R2 已接受 fingerprint、最后修复 delta 和受影响契约；不再触发第三次修复或第四次评审。

增量 R2 不是只看几行 patch。`fix_batch` 必须生成影响闭包 manifest。回退条件清单、影响闭包构建步骤和 R3 覆盖证明由 [comments-and-review.md](comments-and-review.md) 定义，评审步骤以该文为准。Reviewer 可随时根据证据把 R2 升级为全量，但不得把全量降级为更窄范围。

## no-op rebase 的验证复用

提交前仍必须 fetch target 并执行 rebase 门禁。只有同时证明以下全部不变时，才能复用此前验证结果：

- fetched target SHA 与评审/验证绑定的 target SHA 相同；
- rebase 明确为 no-op，`HEAD` 未变化；
- index、working tree、untracked 路径及内容 hash 未变化；
- prospective patch、受影响包/模块集合和 review-guard digest 未变化；
- 验证命令不是依赖实时网络、时间、外部服务或易变生成状态的检查；仓库规则未要求每次 commit 前强制重跑。

把复用的每条命令、原结果、输入 digest 和复用理由写入 validation manifest。任一条件不成立、证据缺失或命令属性未知时，重新运行受影响验证。target 前进时旧评审和验证绑定均失效，按剩余预算 rebase、验证并重新评审。

## 评审结论复用

评审是全流程最贵的一步，输入内容一致时不得重复执行。缓存键只绑定评审真正的输入内容，**不绑定 commit 身份**：

```text
prospective_patch_sha256 + review_guard_digest
```

`source_head` 前进本身不是重新评审的理由。频繁 commit、amend、force-push、纯 rebase 都会改变 `source_head`，其中大部分不改变待评审内容，或只是无关追加；把 `source_head` 写进缓存键会让同一份代码被反复全量评审。

### 完全复用：零评审调用

同键的已完成评审结论可以整体复用，条件全部成立：

- 缓存记录来自同一个不可变范围（同一 MR、同一 worktree 绑定、同一 review-guard package digest）；
- 当前重算的 `prospective_patch_sha256` 与缓存值相等（`source_head` 是否变化不影响该判定）；
- 自缓存以来的 target 变化全部通过 [git-ci-and-merge.md](git-ci-and-merge.md) 的空交集判据，即 `overlap` 始终为空且 rebase 无冲突；
- 原生报告和证据产物仍存在且 hash 匹配。

命中时跳过对应评审步骤，把缓存结论写入新的 review manifest，并记录 `reused_from`（原步骤 result 路径）、原 digest 对、原 `source_head` 和复用理由；不消耗评审轮次。

### 增量复用：只评审新增 delta

`prospective_patch_sha256` 变了，但变化完全来自 source 分支上的追加 commit 时，先算 source delta：

```text
source_delta = git diff <cached_source_head> <current_source_head>
delta_closure = source_delta 修改路径 + 直接契约路径 + 测试路径
```

以下全部成立时，R1 降级为 `scope_mode=incremental_source_delta`，只评审 `source_delta` 及其影响闭包，缓存中的既有发现集原样保留：

- `cached_source_head` 到当前 head 是快进，历史未被改写（无 amend、无丢弃 commit）；
- rebase 到最新 target 无冲突，且与 target 变化的 `overlap` 为空；
- `delta_closure` 与缓存结论中所有未解决 finding 的路径/符号无交集；
- review-guard package digest 未变；
- 影响闭包按 [comments-and-review.md](comments-and-review.md) 的构建步骤可证明，且未命中该文的全量回退条件清单。

任一条件不成立、历史被改写、证据缺失，或 target 出现实质 churn 时，回退为完整 R1。增量 R1 与完整 R1 同样计一次评审轮次——它省的是评审范围和耗时，不是预算。

复用判定必须写入 review manifest：缓存键、`cached_source_head`、当前 `source_head`、命中的复用档位（`full|incremental|none`）和判定证据。证据不全时按 `none` 处理。

## 模式外壳

### once

1. 初始化并把 `execution.mode=once`、`scheduler.status=not_applicable` 持久化。
2. 立即执行一个完整 Cycle Run。
3. 在 `idle|changed|waiting|queued|merged|closed_unmerged|blocked` 返回时释放 lease 并输出一次简洁中文结果。
4. `idle|changed|waiting|queued` 不写入 MR 终止状态；以后可再次以 once 或 loop 恢复。

### loop

1. 初始化并把 `execution.mode=loop`、固定 interval 持久化；先执行一个完整 Cycle Run。
2. 若没有进入 MR 终止状态，再创建或复用精确匹配的运行时原生 scheduler task。
3. 每次唤醒执行相同 Cycle Run。指纹不变时零业务 Worker、零冗长输出。
4. 只有 `merged|closed_unmerged|blocked_*` 才取消并验证精确 task；`queued` 仍继续监听。

从已结束的 `once` 切换到 `loop`，或停止旧 loop 后切换到 `once` 时，可以复用同一专用 worktree 和已验证的非终止状态，但必须创建新的 invocation/run 记录；不得篡改历史结果或复用过期 lease。已有 active loop 时要求“立即执行一次”，只触发该主 Agent 的一个 Cycle Run，不创建第二个 invocation。

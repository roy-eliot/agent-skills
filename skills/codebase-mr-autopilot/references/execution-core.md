# 共享执行核心

`once` 与 `loop` 共用同一个有界 `Cycle Run`。模式只决定 Cycle Run 运行一次还是由原生 scheduler 重复唤醒；评论、评审、修复、CI、rebase 和合并语义不得分叉。

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

主 Agent 每次开始 Cycle Run 时，只读取足以判断“MR 外部状态是否变化”的机器字段。通过 `bytedcli --json` 和确定性的本地投影，把原始响应收敛为：

```json
{
  "mr_state": "open|merged|closed",
  "source_head": "sha",
  "target_head": "sha",
  "patchset": "id-or-null",
  "reviewer_activity": {
    "open_thread_count": 0,
    "high_watermark": "stable-hash-of-thread-id-comment-id-updated-at-author"
  },
  "approval_fingerprint": "stable-hash",
  "required_checks_fingerprint": "stable-hash",
  "queue_fingerprint": "stable-hash"
}
```

探针可以调用 `mr get`、`mr status`、`reviewer list`、open `comment list` 和 `queue entries`，但在结果进入主 Agent 上下文前必须剔除评论正文、diff、日志、描述和其他自由文本。主 Agent 只保留规范投影、组合 fingerprint、时间戳和命令是否成功；原始 JSON 不得出现在长期上下文或用户报告中。

如果当前运行时无法保证机器输出先被确定性投影，再返回主 Agent，则派发一个最小的直接 `intake_probe` 叶子 Worker。该 Worker 只读取上述字段、不加载评审或 Git 参考、不获取写 lease，并返回同一探针对象。不得退回每次空闲 tick 都加载完整 Autopilot 上下文的旧路由 Worker。

组合 fingerprint 至少绑定：

```text
mr_state + source_head + target_head + patchset
+ reviewer_activity.high_watermark
+ approval_fingerprint + required_checks_fingerprint + queue_fingerprint
```

- 与 `last_probe_fingerprint` 相同：不得创建业务 Worker。`loop` 静默等待下一次唤醒；`once` 返回“当前状态无变化，无需处理”。
- 首次运行、fingerprint 变化或上次运行未完成：进入完整 intake。
- 仅时间戳变化而规范字段未变，不算变化。
- 探针失败：执行一次有界重试；仍失败则返回中文阻塞/等待结果，不得把“读取失败”解释为“没有工作”。

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

`intake_sync` 把完整路由与初始 rebase 合并为一个阶段：它读取最新 MR 状态；存在符合处理条件的评论时同步 source/target 并在专用 worktree rebase，然后输出 R1 请求。这样每个活跃评论批次少创建一个 Worker，同时仍保证先 rebase、后 R1。

存在工作时，主 Agent 根据 `continue_now=true` 在同一个 active turn 中继续派发下一同级 Worker，不等待 scheduler。只有到达 Cycle Run 边界才释放 lease。

## 评审范围优化

- **R1：** 始终是完成初始 rebase 后的完整预期 MR 发现型评审，同时充当评论聚合窗口。
- **R2：** 默认评审本轮修复 delta、被修改符号的直接调用/实现契约和相关测试；仍要绑定完整 prospective MR 的 target/source/worktree digest。
- **R2 全量回退：** 发生下列任一条件时，改为完整预期 MR 评审：公共 API/接口、跨模块调用、并发/事务、鉴权/隔离、持久化/schema、IDL/生成物、配置/部署、依赖升级、文件移动/大量重命名；修复触碰 R1 范围外路径；R1 问题跨越多个行为组；target 变化；无法证明影响闭包；增量证据缺失或 hash 不匹配。
- **R3：** 仅验证 R2 已接受 fingerprint、最后修复 delta 和受影响契约；不再触发第三次修复或第四次评审。

增量 R2 不是只看几行 patch。`fix_batch` 必须生成影响闭包 manifest，包含修复前后完整 prospective patch digest、last-fix delta、修改路径/符号、直接契约路径、测试路径和选择增量/全量的理由。Reviewer 可随时根据证据把 R2 升级为全量，但不得把全量降级为更窄范围。

## no-op rebase 的验证复用

提交前仍必须 fetch target 并执行 rebase 门禁。只有同时证明以下全部不变时，才能复用此前验证结果：

- fetched target SHA 与评审/验证绑定的 target SHA 相同；
- rebase 明确为 no-op，`HEAD` 未变化；
- index、working tree、untracked 路径及内容 hash 未变化；
- prospective patch、受影响包/模块集合和 review-guard digest 未变化；
- 验证命令不是依赖实时网络、时间、外部服务或易变生成状态的检查；仓库规则未要求每次 commit 前强制重跑。

把复用的每条命令、原结果、输入 digest 和复用理由写入 validation manifest。任一条件不成立、证据缺失或命令属性未知时，重新运行受影响验证。target 前进时旧评审和验证绑定均失效，按剩余预算 rebase、验证并重新评审。

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

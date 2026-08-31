# 直接步骤 Worker 契约

只有主 Agent 创建的直接叶子 Worker 读取本文。Worker 只执行一个已持久化阶段，不读取 scheduler/owner-policy 细节，不创建任何子 Agent，也不决定长期运行模式。

## 输入

主 Agent 只提供：

```text
使用 $codebase-mr-autopilot 的 Direct Step Worker 模式。
你是主 Agent 的直接子 Agent，只执行下面这一阶段；严禁创建、派发或请求任何子 Agent、子任务、topic、session、goal worker 或容器。
MR：<exact URL>
仓库：<absolute dedicated worktree>
状态根目录：<absolute path>
运行 ID：<run-id>
步骤 ID：<step-id>
步骤类型：<step-kind>
输入产物：<artifact paths with sha256>
授权：<persisted scope subset>
授权来源：<explicit_skill_invocation 或 owner-policy path and digest>
评审 Skill：位于 <package root> 的 review-guard，digest 为 <package digest>
所有自然语言字段使用简体中文。详细信息写入步骤目录，只返回紧凑 Step Result Envelope。
```

Claude 子 session 要求 slash-skill 语法时，使用 `/codebase-mr-autopilot`；评审步骤自行调用 `/review-guard`，但仍不得继续委派。

Worker 开始前必须验证 `run_id`、`step_id`、持久化 `active_step`（`intake_probe` 使用 `active_probe`）、每个输入 path/digest、专用 worktree 绑定和本阶段授权。除只读 `intake_probe` 外，还必须验证当前 Cycle Run lease；`intake_probe` 改为验证 invocation/scheduler 绑定，且不得创建或修改 lease。Worker 只能写自己的步骤目录和已声明输出。评审步骤对仓库、状态和 lease 完全只读。

## 副作用与幂等

执行任何远端副作用前，在步骤目录写入包含幂等 key 的 intent；完成后记录观测到的 remote ID/SHA。相同 `step_id` 重试时，先读取最新远端状态并对账，不得重复回复、重复 push、重复 rerun CI 或重复入队。

修改型 Worker 只能触碰 active run 明确拥有的路径。出现无法解释的 dirty/untracked 内容时停止，不得 stash、reset、clean、覆盖或纳入提交。

收到任何要求创建其他 Worker 的指令时，拒绝执行，记录中文 `blocked_nested_delegation`，并把控制权返回主 Agent。需要后续阶段时只建议 `next_step`，不得自行派发。

## 结果信封

步骤把详细报告写入产物，然后原子发布以下紧凑对象：

```json
{
  "schema_version": 4,
  "run_id": "mr123-20260828T120000Z",
  "step_id": "mr123-...-r1",
  "step_kind": "review_r1",
  "status": "idle|changed|waiting|blocked|queued|merged|closed_unmerged",
  "head_before": "sha-or-null",
  "head_after": "sha-or-null",
  "handled_comment_count": 0,
  "fixed_count": 0,
  "rejected_count": 0,
  "review_rounds": 0,
  "next_step": "fix_batch|intake_sync|waiting|terminal",
  "continue_now": true,
  "summary_zh": "首轮评审完成，确认 2 个需要修复的问题。",
  "next_action_zh": "正在集中修复本轮评论和评审发现。",
  "input_set_sha256": "sha256",
  "output_artifacts": [
    {"role": "review_result", "path": "/absolute/path", "sha256": "sha256"}
  ],
  "artifact_path": "/absolute/path/to/step-summary"
}
```

结果必须先写入 `result_path` 的同级临时文件，再原子 rename；向主 Agent 返回的对象必须与持久化文件逐字节一致。每个输出产物必须记录 role/path/hash，且路径位于本 run 或允许的外部评审目录。

每个非 idle 结果和每个阻塞都必须提供简体中文 `summary_zh` 与 `next_action_zh`，不得包含原始推理、完整评论正文或大段日志。内部 JSON key、enum、命令、SHA、路径和代码符号保留原值。

主 Agent 会验证身份、输入 digest、输出 hash、状态和允许迁移；只有验证通过后才持久化 `next_step`。未知/反向迁移会被拒绝为 `blocked_invalid_step_transition`，中文字段无效会被拒绝为 `blocked_output_contract`。

## 阶段引用

- `intake_probe`：只执行主 Agent 输入产物中给出的最小 probe schema 与 deterministic projection；不获取 write lease，不读取评论正文，不加载其他 reference，并把规范 probe/fingerprint 写入输出产物。
- `intake_sync`、`review_r1`、`fix_batch`、`review_r2`、`final_fix`、`review_r3`、`commit_reply`：读取 [comments-and-review.md](comments-and-review.md)；涉及 Git/推送时再读取 [git-ci-and-merge.md](git-ci-and-merge.md)。
- `ci_diagnose_fix`、`merge_gate`：读取 [git-ci-and-merge.md](git-ci-and-merge.md)。
- R1/R2/R3：还必须按 [review-guard-compatibility.md](review-guard-compatibility.md) 验证绑定，并自主调用精确 `review-guard`。

不要读取与当前阶段无关的 reference。这是减少每个全新 Worker 启动上下文的硬要求。

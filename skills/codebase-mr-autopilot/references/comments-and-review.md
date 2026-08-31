# 评论与有界评审

只有直接评论/评审步骤才读取本文。下面每个步骤都由主控作为自己的直接子级派发。任何步骤都不能派发下一个步骤。

## 批次状态机

```text
主控获取 Cycle Run lease
主控 -> intake_sync：刷新完整 MR 状态；有评论时同步/rebase source
主控 -> review_r1：通过 review-guard 执行全新的只读完整 MR 评审
主控 -> fix_batch：重新读取评论、合并/去重、分类、修复/驳回，
                    执行一次补充扫描、冻结 cutoff、验证，
                    末尾强制 fetch+rebase 到最新 target，
                    再构建 R2 影响闭包和规范证据
主控 -> review_r2：通过 review-guard 全新只读评审修复影响范围，
                    命中回退条件时评审完整预期最终版本
主控 -> final_fix：可选的第二次、也是最后一次修复，并构建 R3 证据
主控 -> review_r3：可选的全新只读定向验证
主控 -> commit_reply：提交前 rebase、验证、有变更时 commit/push，
                       并在每个相关 Codebase 线程中回复
```

所有箭头都通过紧凑步骤结果信封返回。评审步骤与修复/修改步骤互为同级。修复步骤不得创建 Reviewer，评审步骤也不得创建修复者。

R1 本身就是有效工作，同时充当评论聚合窗口。不要固定等待三分钟，也不要假设 R1 一定持续三分钟。R1 后读取和补充扫描共同提供覆盖。

## 符合处理条件的评论

使用精确 MR URL 列出 open 线程：

```text
bytedcli --json codebase mr comment list <MR_URL> --status open
```

识别 Reviewer 新增/编辑的内容，并与 [contracts-and-state.md](contracts-and-state.md) 中已处理线程记录比较。符合处理条件是指：没有 Agent 回复、有更新的 Reviewer 活动、修复证据已失效，或修复 commit 已不存在。Agent 自己的回复不能作为触发事件。

open 不代表尚未修复。Reviewer 是否关闭线程与 Agent 是否完成处理相互独立。

## Review Guard 依赖与适配

所有 R1/R2/R3 调用都使用不可变范围中绑定的精确兼容 `review-guard` 包。应用 [review-guard-compatibility.md](review-guard-compatibility.md)，包括每轮证明。如果依赖缺失、被拒绝、存在歧义、不兼容，或在监听器生命周期内发生变化，返回终止状态 `blocked_review_dependency`；不得在非评审步骤中模仿或复制其评审逻辑。

每轮都由主控启动一个新的直接只读评审步骤，不携带修复者推理、预期方案或历史评审结论。prompt 以 `使用 $review-guard` 开头；运行时要求 slash-skill 语法时，以 `/review-guard` 开头。向其提供：

- MR URL 和仓库路径。
- 轮次名称、精确 target/source head、patchset、worktree diff hash 和所需评审边界。
- 仓库评审规则（如果存在）。
- 位于 worktree 和 Git common directory 之外的临时评审目录，用于存放原生报告和规范证据。
- 应用 `review-guard` 问题准入门槛，只报告当前范围内置信度至少 7/10 的 P0-P2 缺陷。不要请求其可选可维护性/重构评审。
- 明确说明它是主控的直接子级，不得委派、创建、派发或请求其他 Agent；这个已全新的评审步骤自行串行完成分组评审。

评审步骤必须保持只读：不得编辑、写入式格式化、stash、clean、commit、push、reply、resolve、操作 CI、approve 或 merge。`review-guard` 允许的安全聚焦测试仍可执行。原生中文报告和适配器对象只能写入外部临时评审目录。只向主控返回带 `artifact_path` 的紧凑步骤结果信封；主控不加载问题内容，直接把该路径传给后续直接修改步骤。该修改步骤验证对象，把不可变报告/证据复制到 Git 私有 run 产物中，并在应用任何问题前记录归档路径。

```json
{
  "review_guard_verdict": "Needs changes|可以合并，但建议跟进|LGTM|无法完成可靠 Review",
  "review_skill_package_root": "/canonical/review-guard/root",
  "review_skill_digest_before": "sha256",
  "review_skill_digest_after": "sha256",
  "scope": {
    "scope_mode": "prospective_rebased_mr|incremental_fix_impact|prospective_final_mr|targeted_fix_delta",
    "observed_remote_patchset": "host-patchset-id",
    "target_head_sha": "sha",
    "source_head_sha": "sha",
    "worktree_diff_hash": "hash"
  },
  "evidence": {
    "manifest_sha256": "sha256",
    "prospective_patch_sha256": "sha256",
    "last_fix_delta_sha256": "sha256-or-null",
    "impact_closure_manifest_sha256": "sha256-or-null",
    "scope_reason": "选择增量、全量或定向范围的中文理由",
    "required_fingerprints": [],
    "fingerprint_coverage": []
  },
  "findings": [],
  "validation": [
    {"command": "精确命令", "result": "pass|fail|blocked|not_run", "reason": "简短证据"}
  ],
  "limitations": ["缺失的外部事实；没有则为空"],
  "native_report_path": "/absolute/external-temp/review-guard-rN.md"
}
```

每个 `findings` 项使用以下 `review-guard` 原生问题契约映射：

```json
{
  "finding_id": "stable-id",
  "severity": "P0|P1|P2",
  "confidence": 9,
  "file": "path",
  "line_start": 42,
  "line_end": 42,
  "trigger": "具体输入、状态、时序、调用方或部署条件",
  "impact": "可观察后果",
  "evidence": "当前代码路径、复现或测试证据",
  "action": "针对根因的最小修复方向",
  "scope": "introduced|exposed|materially_worsened",
  "fingerprint": "规范化值"
}
```

主控只验证紧凑信封和产物路径边界。接收结果的直接修改步骤加载适配器对象并重新计算 `review_skill_digest_received`。只有规范 root、before/after/received digest 和不可变范围绑定全部匹配时才能接受，否则返回 `blocked_review_dependency`。应用任何问题前，以及提交前和推送前门禁，都要重复 digest 检查。当范围绑定过时/缺失、结论为 `无法完成可靠 Review`、原生报告不存在，或任何已接受问题不满足 `review-guard` 问题准入门槛时，单独返回 `blocked_review_incomplete`。可选重构、样式偏好、低于 7/10 的推测候选项和无关历史债务绝不能进入自动修复集。

## R1 Reviewer 契约

R1 在 `intake_sync` 初始 rebase 后、评论聚合完成前运行。其边界从明确 target SHA 到完成 rebase 的精确私有 worktree head。由于这个预期 head 可能尚未成为远端 MR patchset，不要让 `review-guard` 根据 MR URL 推断 ref；应使用明确 base/head 范围调用，单独记录观测到的远端 patchset，并且只有这些本地 SHA 和 diff hash 保持不变时才能应用结果。R1 是发现型评审，但不是全仓审计或可维护性评审。派发 R1 前先按 [execution-core.md](execution-core.md) 的评审结论复用检查缓存：`source_head`、`review_guard_digest` 和 `prospective_patch_sha256` 三者未变且期间没有实质 target churn 时，复用上一轮 R1 发现集，不重复执行完整评审。

## R2 影响闭包、全量回退与 R3 覆盖

R2 默认只评审本轮修复 delta、被修改符号的直接调用/实现契约和相关测试，但它必须绑定完整预期最终 MR。完整预期 MR 同时包含已提交 MR 历史和 active run 的 staged、unstaged、untracked 文件；不得只以 base/head 或只以 working-tree 作为绑定证据。

直接 `fix_batch` 步骤在外部评审目录构建两类规范证据，不得仅为了评审而 stage 仓库文件：

1. 验证每个 dirty/untracked 路径都属于 active run；无法解释的路径会阻塞批次。
2. 解析精确 target SHA、当前 worktree `HEAD` 以及它们的 merge base。要求 target 关系符合 rebase 后预期。
3. 从该 merge base 到当前 working tree 生成一个支持 rename 的 binary diff，包含 committed、staged 和 unstaged tracked 变更。
4. 使用 `git ls-files --others --exclude-standard -z` 枚举 untracked 文件，并为每个本轮拥有的 untracked 路径追加 binary `/dev/null` diff，同时保持 NUL-safe 路径处理。
5. 生成 last-fix delta，并通过符号引用、直接调用者/实现、同一数据/并发/鉴权/持久化契约和相关测试，构建有限的影响闭包。记录每个纳入/排除路径的理由。
6. 写入 manifest，包含轮次、target SHA、committed HEAD、merge base、porcelain-v2 status hash、完整 prospective patch hash、last-fix delta hash、排序后的完整路径、影响闭包路径/符号、untracked 内容 hash，以及 R2 mode/reason。
7. 先评估全量回退条件：公共 API/接口、跨模块调用、并发/事务、鉴权/隔离、持久化/schema、IDL/生成物、配置/部署、依赖升级、文件移动/大量重命名；修复触碰 R1 范围外路径；R1 问题跨多个行为组；target 变化；无法证明影响闭包；任一证据缺失或 hash 不匹配。命中任一项时设置 `scope_mode=prospective_final_mr`；否则设置 `scope_mode=incremental_fix_impact`。
8. 把完整 prospective patch、last-fix delta 和 manifest 都交给全新的直接 `review_r2` Worker。它验证当前文件字节/status，并按 manifest mode 评审。Reviewer 可以把增量模式升级为全量，不得把全量模式降级。

增量 R2 不是只检查评论涉及的几行，也不是只确认原问题消失。它仍要寻找修复在影响闭包中引入的新 P0-P2 问题。只有 R1 已全量覆盖、target 未变、影响闭包完整且 digest 稳定时，才允许节省重复的全 MR 扫描。

应用 R2 最终修复前，保留 R2 manifest/patch，并对完整 R2 预期文件集中的每个路径做快照，而不只是问题提到的文件。如果计划中的修复必须触碰额外路径，在首次写入前为该路径做快照，并加入允许的最终修复路径集。修复后重建完整预期证据，并针对完整前后快照集生成 binary last-fix delta，包含新增、修改、删除和 mode 变化。

R3 前比较修复后 status/path 集与允许的快照集。任何已变更路径缺少写入前快照，都表示 delta 不可信：返回 `blocked_review_incomplete`，隔离批次，不得重建、commit 或 push。

R3 接收：

- 每个已接受 R2 问题的 fingerprint；
- 修复前后预期 manifest digest；
- last-fix-delta patch 和 hash；
- 最终修复改变的精确路径/符号。

R3 的适配器结果必须把 `required_fingerprints` 设为该精确列表，并为每一项提供一条 `fingerprint_coverage` 记录，包含 `resolved|still_present|not_reproducible`、当前证据和受影响位置。它还必须回显已评审的预期 patch 和 last-fix-delta hash。coverage 缺失/重复或 digest 不匹配时，返回 `blocked_review_incomplete`。

## 合并评论与 Review Guard 问题

R1 完成后，再次获取 open 评论。按文件、符号/区域和事实主张规范化每条 Codebase 评论与 `review-guard` 问题。

- 两个来源是同一问题：只修复一次，以 Codebase 线程作为外部回复锚点。
- 多个 Codebase 线程是同一问题：只修复一次，但在每个线程分别回复。
- 仅内部发现且被 `review-guard` 接受的 P0-P2 问题：范围内应修复；不要新建会触发监听器自身的 MR 评论。

所有已接受的 P0-P2 问题都进入统一问题集，因为本 Autopilot 已被明确要求修复评审发现的问题。如果即使最小 P2 修复也需要实质重新设计或扩展范围，将其分类为 `unclear`、发布澄清回复并阻止合并，不得忽略问题或擅自扩大 MR；这不构成 MR 级终止。

## 事实处理结论

必须且只能分配一个：

- `confirmed_unfixed`：当前 head 能复现或证明问题；实施聚焦修复。
- `confirmed_already_fixed`：当前 head 已满足要求；不修改代码，但用当前证据回复。
- `partially_confirmed`：只有明确子集事实成立；修复该子集，并解释被驳回部分。
- `false_positive`：主张与当前代码/行为/测试证据冲突；用证据驳回。
- `duplicate`：本批次其他项已覆盖；关联到同一个修复 commit。
- `unclear`：不同理解会实质改变实现；提出澄清问题并阻止合并，不得猜测。该线程记为 `needs_clarification` 并正常发布澄清回复，本批次其余线程照常修复和回复；批次以 `waiting` 结束，`loop` 继续监听 Reviewer 回答。只有整批零可处理项且连澄清回复都无法发布时，才使用 `blocked_ambiguous_feedback`。

## 判断 open 评论是否已修复

1. 把旧行锚点、符号、场景或不变量映射到当前 source head。
2. 检查当前执行路径，不要只看原始 patch 位置。
3. 可行时复现所报告故障，或运行聚焦的已有/新增测试。
4. 确认声称的修复 commit 仍在当前 source 历史中，且行为没有回归。
5. 保存具体证据：当前代码位置、命令、结果和 commit/head。

线程状态绝不能替代这些证据。

## 修复与补充扫描

把所有已接受的 R1/评论问题作为一个内聚批次修复。可行时，优先编写或运行能在修复前因所报告行为失败、修复后通过的聚焦测试。

提交前，恰好再获取一次 open 评论：

- 纳入晚于 R1 后快照的 Reviewer 活动。
- 立即分类和处理这些评论；不再执行完整 R1，也不等待。
- 把扫描时间戳/comment high-water mark 记录为批次 cutoff。
- cutoff 后到达的评论留给下一次 Cycle Run。

补充评论产生的变更纳入 R2。

### 修复末尾的强制 rebase

冻结 cutoff 之后、构建 R2 证据之前，`fix_batch` 必须执行一次强制 fetch + rebase，把批次绑定到当时最新的 target：

```text
git fetch <target-remote> +refs/heads/<target-branch>:refs/codebase-mr-autopilot/<mr-key>/target
git rebase --autostash refs/codebase-mr-autopilot/<mr-key>/target
```

这样 R2/R3 评审的就是最接近提交形态的版本，`commit_reply` 的提交门禁 rebase 大概率成为 no-op。规则：

- rebase 后把 `target_bound` 置为本次 fetch 得到的 target SHA，R2 证据全部基于 rebase 后的 worktree 重建。
- 这次 rebase **不消耗**评审轮次或重绑定配额——它发生在 R2 绑定之前，还没有绑定可作废。
- 冲突按 `blocked_rebase_conflict` 处理，不得猜测解决。
- rebase 改变了任何已修复文件的内容时，重新运行受影响验证，不得沿用 rebase 前的结果。

`commit_reply` 仍保留强制提交门禁 rebase，仍按三级判据处理 target 前进；只是命中实质 churn 的窗口从整个 R2+R3 期间缩短为 R2 之后。

## 有界收敛

主控持有并持久化每批次的两个**相互独立**的预算。每个同级步骤只能消耗分配给自己的额度：

**评审预算 `review_budget`（3 轮）——只服务于收敛修复质量**

| 轮次 | 范围 | 是否可触发修复？ |
|---|---|---|
| R1 | 批次修复前，由全新 `review-guard` 执行完整 MR 发现型评审 | 是，第一次修复 |
| R2 | 默认评审修复影响闭包；命中回退条件时评审完整预期最终 MR | 是，一次最终修复 |
| R3 | 由全新 `review-guard` 定向验证 R2 问题和最后修复 delta | 不再触发自动修复/评审循环 |

**重绑定配额 `rebind_budget`（默认 2 次）——只服务于 target 前进后的重新绑定**

重绑定评审复用 `review_r2`/`review_r3` 步骤类型，但计入 `rebind_passes`，不消耗 `review_budget`；它同样不得触发新一轮自动修复。两个预算绝不能互相借用或互相抵扣。

规则：

- 最多三次收敛评审调用和两次自动修复；重绑定另计，最多两次。
- 每轮都使用不同的全新直接子级评审步骤，以及同一个已绑定 `review-guard` package digest。
- 如果 R1 除误报/已修复评论外没有发现问题，且代码未变化，跳过 R2/R3，由 `fix_batch` 直接迁移到 `commit_reply`。
- 同一 fingerprint 在修复尝试后仍存在时立即阻塞；不得重复同一变更。
- 如果 R3 返回任何未解决/新增、置信度至少 7/10 的 P0-P2 问题，不得提交已知有问题的工作。记录 `blocked_review_nonconvergent`。
- target head 变化**不必然**使评审绑定失效。先按 [git-ci-and-merge.md](git-ci-and-merge.md) 的三级判据计算 `overlap`：空交集只重跑受影响验证并推进 `target_bound`，不消耗任何额度；非空交集才消耗一次重绑定配额。`commit_reply` 步骤把最早未使用的 `review_r2` 或 `review_r3` 返回给主控；它绝不自行创建评审步骤。
- `rebind_budget` 耗尽后 target 再次实质移动：保留已知批次 diff，记录 `blocked_target_churn`。`review_budget` 耗尽而问题仍未收敛：记录 `blocked_review_nonconvergent`。绝不能把两者混用，也不得静默重启任一预算。
- 上述任一阻塞发生且未提交变更**可由本 run 完整解释**时，按 [contracts-and-state.md](contracts-and-state.md) 写出批次交接产物并持久化 `dirty_owned:<run-id>`，交由下一个 Cycle Run 续做。只有变更无法解释时才持久化 `dirty_quarantined:<run-id>` 并要求人工恢复。两种情况都绝不能用 stash/reset 隐藏状态。

把每个评审结果绑定到：

```text
target_head_sha + source_head_sha + worktree_diff_hash
```

## 线程回复

使用精确 `thread_id` 回复：

```text
bytedcli codebase mr comment reply <MR_URL> \
  --thread-id <thread-id> \
  --body-file <reply-file>
```

非简单回复正文应使用文件，避免 shell 引号错误。

- **已修复：** 事实结论、聚焦变更、已推送 commit SHA 和相关验证。
- **已经修复：** 当前代码/head，以及证明问题不再发生的证据。
- **部分成立：** 已接受子集、附证据的驳回子集、commit/test。
- **误报：** 简洁驳回原因和当前代码/测试证据。
- **重复：** 引用共享修复 commit 和验证。
- **不明确：** 提出最小澄清问题；不得宣称已修复。

直接 `commit_reply` 步骤只有在 push 且确认 remote head 后才发布修复回复。如果批次没有代码变更，在证据完整后直接回复，不创建空 commit。用户可见回复正文必须使用简体中文；有帮助时保留原样代码、命令、ID 和 SHA。

绝不能调用 `mr comment resolve` 或 `unresolve`。记录回复 ID，确保已回复但仍 open 的线程不会重复处理，除非 Reviewer 继续跟进，或 source head 使原证据失效。

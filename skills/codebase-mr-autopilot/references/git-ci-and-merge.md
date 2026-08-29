# Git、CI 与合并

执行任何仓库修改、回复、CI 操作或合并决策时读取本文。命令以 bytedcli 0.136.0 为准；命令界面可能变化，因此实时写操作前必须验证当前 `--help`。

## 仓库预检

只能在通过 [owner-policy-and-worktree.md](owner-policy-and-worktree.md) 创建或验证、且已授权的专用 worktree 中工作。source/primary checkout 仅用于发现，可以是脏的。

1. 验证 worktree 的 Git common directory 和 Codebase remote 与不可变 MR 范围匹配。
2. 使用 `bytedcli --json codebase mr get <MR_URL>` 读取 MR，并记录 source branch/head 和 target branch/head。
3. 确认本地分支是已记录的私有 `codebase-mr-autopilot/...` 分支，其 base 是预期 MR source head，且不存在无关用户变更。私有本地分支不需要与远端 MR source 分支同名。
4. 按需确认 push 权限和分支保护。
5. 如果 checkout 因未知/崩溃 run 而为脏，停止。不得 stash、discard 或覆盖无法解释的工作。
6. 绝不能在 `source_repo_path` 中运行修改命令；使用 `git -C <repo_path>`，或把直接步骤 Worker 的工作目录明确设为专用 worktree。

## 初始 rebase 与提交门禁 rebase

评论或代码修复批次开始时：

```text
git fetch <remote> \
  +refs/heads/<target-branch>:refs/codebase-mr-autopilot/<mr-key>/target \
  +refs/heads/<source-branch>:refs/codebase-mr-autopilot/<mr-key>/source
git rebase refs/codebase-mr-autopilot/<mr-key>/target
```

当 source 和 target remote 不同时，使用 MR 权威 remote。私有 ref 可避免非标准 remote fetch 配置留下过期 remote-tracking ref。rebase 前确认 fetch 得到的 SHA 等于最新 MR 元数据。

批次修复完成后，只 stage 明确属于该批次的路径，包括所有新测试文件，并检查 staged diff。如果仍有无关/无法解释的 untracked 文件，应阻塞，而不是假设 autostash 会保护它们。

每次 commit 前立即再次 fetch，并始终运行：

```text
git fetch <target-remote> \
  +refs/heads/<target-branch>:refs/codebase-mr-autopilot/<mr-key>/target
git rebase --autostash refs/codebase-mr-autopilot/<mr-key>/target
```

只有预期批次路径均已 stage 且完成核对后，才能使用 `--autostash`。把 fetch 得到的 target head 与最近一次有效评审绑定的 head 比较。rebase 后，在测试或 commit 前验证预期 staged 变更已恢复。

- target 未变化：所需提交前 rebase 应为 no-op。只有 [execution-core.md](execution-core.md) 的 no-op 复用条件全部成立时，才复用已绑定验证；否则重新运行受影响验证。
- target 已前进：rebase 会使旧评审绑定失效。直接 `commit_reply` 步骤重新运行受影响验证、计算新的 worktree diff hash、写入重新绑定请求产物，并把最早未使用的 `review_r2` 或 `review_r3` 返回给主控。主控直接派发该评审步骤。如果没有足够的评审槽位，保留已知批次 diff，不提交，并返回 `blocked_target_churn`。
- 发生冲突：检查冲突。只有意图无歧义且能完整测试时才解决；否则 abort rebase、保存证据，并返回 `blocked_rebase_conflict`。

已知 source 分支落后于 target 分支时，绝不能 commit。

## 验证与提交

执行：

- 对每个已确认问题执行复现/定向测试。
- 受影响模块测试。
- 仓库要求的 lint、build、静态检查或生成文件检查。
- 每次 rebase 后重新验证输入绑定。target/HEAD/worktree/命令属性任一变化时重新执行受影响验证；只有可证明的 no-op 才按 [execution-core.md](execution-core.md) 记录并复用结果。

验证结果必须写入 manifest，至少包含命令、结果、target/HEAD/prospective patch/worktree digest、受影响包或模块集合、是否依赖网络/时间/外部服务、以及 `executed|reused`。复用时还要记录原结果路径/hash 和复用理由。缺少这些证据时不得复用。

commit 前检查精确 staged 文件列表和 staged diff。不得使用可能纳入无关文件的宽泛 add。

整个评论/评审批次优先使用一个内聚 commit。对于只有误报、重复或已修复问题的批次，不要创建空 commit。

push 前，确认远端 MR source head 仍等于预期的推送前 head。使用明确 refspec，把私有本地 `HEAD` push 到精确记录的 MR source 分支；绝不能依赖 upstream 默认值。

- 历史为 fast-forward 时，使用普通 `git push <remote> HEAD:<source-branch>`。
- rebase 改写了已授权 source 分支时，把 lease 绑定到此前观测到的精确 remote SHA：

  ```text
  git push --force-with-lease=<source-branch>:<expected-old-sha> \
    <remote> HEAD:<source-branch>
  ```

- 不得使用缺少精确 ref 和预期 SHA 的简写 `--force-with-lease`。
- 绝不能使用 `--force`。
- 发送修复回复前，重新读取 MR，确认已 push commit 就是 remote source head。

## bytedcli MR 与评论

机器可读操作优先使用精确 MR URL selector 和 JSON：

```text
bytedcli --json codebase mr get <MR_URL>
bytedcli --json codebase mr status <MR_URL> --page-size 100
bytedcli --json codebase mr reviewer list <MR_URL>
bytedcli --json codebase mr comment list <MR_URL> --status open
bytedcli codebase mr comment reply <MR_URL> --thread-id <id> --body-file <file>
```

不得调用 `mr review --approve`；合并门禁只观察人工审批。不得调用 comment resolve/unresolve。

## CI 诊断

先查看远端失败；不要先运行无关的本地全量测试。

```text
bytedcli --json codebase mr status <MR_URL> --page-size 100
bytedcli --json codebase checks list --mr <MR_URL> --page-size 100
bytedcli --json codebase checks get -R <repo> --id <check-run-id>
bytedcli codebase checks log -R <repo> --check-run-id <check-run-id>
```

大型日志写入当前 run 产物，并用 `rg` 搜索；不要粘贴到主控上下文。

对失败分类：

- `code_or_test_defect`：使用相同 rebase、验证和有界评审规则启动全新修复循环。
- `flaky`：只有具体不稳定证据时才 rerun。
- `infrastructure`：只有日志表明代码不应负责时才 rerun。
- `unknown`：收集更多证据或阻塞；不得猜测/反复 rerun。

## Check 操作与流水线重试

Check-run operation 是动态的。检查 JSON 中当前 `Operations` 数组，并选择 label/description 确实表示 rerun 的当前 operation：

```text
bytedcli --json codebase checks list -R <repo> --mr <MR_URL> --page-size 100
bytedcli codebase checks operate -R <repo> \
  --payload-json '{"CheckRunId":"<id>","OperationId":"<current-operation-id>"}'
```

绝不能硬编码通用 rerun operation ID。

对于 git-backed pipeline，运行前先发现其名称：

```text
bytedcli --json codebase pipeline list -R <repo> --branch <source-branch>
bytedcli --json codebase pipeline status -R <repo> --branch <source-branch> --pipeline <name>
bytedcli codebase pipeline run -R <repo> --branch <source-branch> --pipeline <name>
```

重试前记录 `HEAD + check/pipeline + failure fingerprint`。默认同一 fingerprint 最多重试一次。重复失败时返回 `blocked_ci_nonconvergent`，不再触发下一次运行。

## 合并门禁

入队前立即读取最新状态。必须同时满足：

- MR 为 open。
- 已满足人工审批要求。
- 不存在符合处理条件的评论或等待澄清 blocker。Agent 用证据回复后线程可以仍为 open，因为关闭权属于 Reviewer。
- required check 全部成功；没有 required pending/running check。
- MR 可合并。
- remote source head 等于已评审、已测试、已 push 的 head。
- source 不落后于 target；执行最终 target-head 比较/rebase 门禁。
- 授权包含 `merge_rebase`。

然后精确执行：

```text
bytedcli codebase mr queue enqueue <MR_URL> --merge-method rebase_merge
```

入队前查询 queue entry。如果当前 MR/head 已存在 active entry，返回 `queued`，不再次入队。新入队后使用以下命令确认 queue 状态：

```text
bytedcli --json codebase mr queue entries <MR_URL>
bytedcli --json codebase mr status <MR_URL> --page-size 100
```

进入 queue 是 `queued`，不是 `merged`。直接 `merge_gate` 步骤持久化结果并返回主 Agent，随后释放 Cycle Run lease。`once` 在报告“已入队但未合并”后结束本次执行；`loop` 继续原生唤醒，并且只有后续 probe/`intake_sync` 确认 MR 报告 `merged` 时才停止。

如果 MR 关闭但未合并，持久化 `closed_unmerged`。如果 queue/check 状态变化或收到新的 Reviewer 反馈，主控在再次尝试入队前，把下一次 Cycle Run 路由到对应直接评论/CI 步骤。

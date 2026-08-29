# Finding and Report Contract

## 1. Finding Gate

A reportable finding must have all of these:

- **Current scope:** the problem exists in the pinned patchset or requested local/full-file scope.
- **Changed behavior:** it is introduced, exposed, or made materially worse by the change. For a full-file/repository audit, it lies inside the explicit audit boundary.
- **Trigger:** a concrete input, state, ordering, caller, deployment condition, or attack path.
- **Impact:** an observable correctness, security, compatibility, operations, test-reliability, or material performance consequence.
- **Anchor:** exact repository-relative file and current line or smallest useful line range.
- **Action:** the smallest fix direction that addresses the root cause without redesigning unrelated code.
- **Confidence:** normally at least 7/10 after direct-context verification.

Validation output alone is not a finding. A failing check becomes a finding only after it is attributed to the reviewed change rather than environment, stale generation, unrelated local work, or pre-existing failure.

## 2. Severity and Confidence

| Severity | Meaning |
|---|---|
| `P0` | Definite or highly probable security breach, data corruption/loss, core-path crash/outage, or irreversible failure; blocks merge/release. |
| `P1` | Concrete correctness, concurrency, compatibility, rollback, isolation, or operational failure under a named condition; should be fixed before merge. |
| `P2` | Real lower-impact defect or defensive gap with a demonstrated path; may be followed up when merge risk is acceptable. |

Keep confidence independent from severity:

- `9-10`: proven from code or reproduced directly
- `7-8`: strong evidence with a small runtime/environment dependency
- `5-6`: plausible but missing a material fact; do not present as a finding
- `1-4`: speculation; drop

Do not inflate severity to make a concern visible. Put missing external facts in limitations or assumptions, not in the defect list.

## 3. Prioritization

Default to at most five findings, sorted by severity then confidence. Never omit a verified `P0` merely to satisfy the limit; if more than five root causes remain, retain all `P0` findings and the highest-risk others, and state that lower-risk findings were not expanded.

De-duplicate by root cause. When one defect appears at several lines, choose the line where the fix belongs and mention affected paths in the evidence.

## 4. Verdict

- `Needs changes`: at least one verified `P0` or `P1`.
- `可以合并，但建议跟进`: only verified `P2` findings remain.
- `LGTM`: no reportable finding remains within the reviewed scope.
- `无法完成可靠 Review`: scope/evidence is insufficient; state exactly what is missing.

Passing tests do not upgrade `Needs changes` when the finding concerns an untested contract. Missing or blocked tests do not automatically downgrade a code-based finding if its trigger is already proven.

## 5. Chinese Report Shape

Lead with the outcome. Omit empty sections except `范围与限制`.

```markdown
## 结论

Needs changes — [一句话说明最大风险]

## 问题

### [P1][置信度 9/10] `path/file.go:42` 标题

- 触发条件：[具体输入、时序或调用路径]
- 问题与影响：[发生什么，用户/数据/兼容性/运维后果是什么]
- 证据：[关键代码关系、复现或验证结果]
- 建议：[最小修复方向；不替作者重做无关设计]

## 验证

- `go test ./path/...`：通过
- `go test -race -count=1 ./path/...`：未运行；原因是……

## 范围与限制

- 范围：`<base-sha>...<source-sha>`，patchset N
- 已检查：[文件/包/契约摘要]
- 限制：[未取得的外部事实、未运行的高成本检查；没有则写 `无`]
```

If no findings remain, say `本次范围内未发现需要报告的 P0-P2 问题` and still disclose the exact range and validation coverage.

Do not pad the report with generic praise, a replay of the workflow, or a checklist full of unevidenced `PASS` values.

When the user requested maintainability, simplification, architecture, refactoring, or fix-ready depth, apply [maintainability-and-refactoring.md](maintainability-and-refactoring.md). Put concrete non-defect observations under `建议项（不影响合并结论）`; never use them to downgrade `LGTM` or inflate P0-P2 issue counts. Provide replacement code or a focused diff only when the user asks to see or apply a fix.

## 6. Comment-Ready Wording

When the user asks for pasteable comments, provide the exact current location and concise Chinese wording:

```markdown
`path/file.go:42`

[P1] 这里从 `context.Background()` 派生超时会切断请求取消和 request-scoped trace/tenant 值；客户端断开后存储调用仍会继续。建议改为 `context.WithTimeout(r.Context(), ...)`，并补一个取消传播回归测试。
```

Publishing those comments is a separate authorized action governed by [scope-and-permissions.md](scope-and-permissions.md).

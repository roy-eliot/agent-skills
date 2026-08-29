# Maintainability and Refactoring Pass

Read this reference only when the user requests a complete/deep review, architecture or code-quality assessment, simplification, refactoring guidance, or fix-ready output. This pass complements defect review; it does not relax the finding gate.

## 1. Separate Defects From Recommendations

Classify an observation as a P0-P2 finding only when it satisfies the trigger, impact, anchor, action, and confidence requirements in `finding-and-report-contract.md`.

Put useful non-defect improvements in a separate `建议项` section. They do not block the merge verdict. Do not invent a P3 tier merely to make preferences look like defects.

A recommendation should still be concrete:

- name the current maintenance cost or change risk
- anchor it to a function, type, package, or repeated behavior
- explain the smallest simplifying move
- state whether it belongs in the current change or a follow-up

Drop generic advice such as “improve naming,” “add comments,” “use a design pattern,” or “increase test coverage” without a specific reason and location.

## 2. Prefer the Smallest Behavior-Preserving Change

Unless the user explicitly authorizes a behavior or contract change:

- preserve public APIs, wire formats, persisted data, error semantics, side-effect ordering, and repository conventions
- prefer deletion, consolidation, early returns, clearer names, or extraction of a cohesive helper over a broad rewrite
- avoid new interfaces, factories, registries, reflection, generics, configuration layers, or dependencies unless they remove a demonstrated source of change cost
- split a larger refactor into safe stages when the final shape cannot be validated atomically
- identify compatibility and rollout work before recommending cross-boundary restructuring

Do not recommend a rewrite merely because a different design is cleaner in isolation.

## 3. Structure and Responsibility

Review structure through concrete change pressure rather than textbook layering.

- Does one function or type own unrelated reasons to change?
- Is a business rule duplicated across handlers, services, repositories, jobs, or adapters and already at risk of divergence?
- Does the change bypass an established boundary or force callers to understand an implementation detail?
- Is a public abstraction broader than its actual consumers, or is repeated switching evidence that one stable seam is missing?
- Are orchestration, policy, I/O, mapping, and persistence mixed in a way that makes failures or tests difficult to isolate?
- Would merging, moving, or deleting code reduce concepts without hiding behavior?

Recommend splitting or abstraction only when it improves a named caller, change path, ownership boundary, or test seam. Recommend merging or deletion when indirection carries no distinct contract.

## 4. Clarity and Simplification

Look for maintainability costs that are visible in the current scope:

- duplicated branches or conversions that can drift
- deep nesting that obscures the main path or cleanup behavior
- long functions containing multiple independently changing policies
- booleans, positional parameters, names, or implicit defaults that make calls ambiguous
- hidden mutation, global state, magic values, or temporal coupling
- dead compatibility paths, redundant wrappers, or comments that contradict code

Prefer changes in this order when they solve the demonstrated problem:

1. delete obsolete or redundant code
2. merge duplicated behavior at its owning boundary
3. use guard clauses or direct control flow
4. extract a cohesive rule or side effect
5. improve names and make dependencies explicit
6. introduce an interface or pattern only if simpler options do not preserve the required variation

## 5. Design-Pattern Gate

Do not recommend a named pattern by default. A pattern recommendation must answer all of these:

- What recurring variation or coupling exists now?
- Which callers or future changes are already affected?
- Why is a function, direct composition, or data-driven mapping insufficient?
- Which concepts or branches disappear after the change?
- What new indirection and maintenance cost does the pattern introduce?

If the result is not materially simpler, explicitly recommend keeping the direct design.

## 6. Testability

Assess testability as the ability to prove supported behavior, not as dependency-injection or coverage theater.

- identify the behavior and layer that should own the test
- isolate nondeterministic inputs such as time, randomness, concurrency, network, filesystem, or global process state only when they block reliable proof
- prefer pure helpers or narrow seams over broad mock-heavy interfaces
- cover material normal, error, boundary, cancellation, retry, idempotency, and concurrency paths activated by the change
- ensure assertions observe the contract rather than implementation call counts unless ordering or invocation count is itself the contract

A missing-test recommendation must name a concrete regression the test would catch.

## 7. Fix-Ready Output

Review remains read-only unless the user explicitly asks for code changes. Distinguish three requests:

- **Review only:** report findings and concise repair directions; do not emit a large replacement implementation.
- **Show a possible fix:** provide the smallest focused diff or snippet, label assumptions, and preserve existing contracts unless a change is explicitly requested.
- **Apply the fix:** re-check scope and permissions, edit only authorized files, run proportional validation, and report actual changes separately from the original findings.

Do not mix speculative cleanup into a correctness fix. When a refactor is optional, keep it separable from the defect repair.

## 8. Optional Report Shape

Append only the sections that contain material information:

````markdown
## 建议项（不影响合并结论）

### `path/file.go:88` 收敛重复的状态映射

- 当前成本：三个分支分别维护同一组状态映射，本次已经出现一个分支遗漏。
- 最小调整：把映射收敛到拥有该业务规则的包内函数，调用方保留现有控制流。
- 时机：建议随本次修改处理，因为当前变更正在增加第四个分支。

## 可选修复示例

```diff
...
```
````

Never add empty architecture, design-pattern, refactoring, or testing sections.

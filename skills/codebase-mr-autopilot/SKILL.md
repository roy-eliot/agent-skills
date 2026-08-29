---
name: codebase-mr-autopilot
description: Supervise one authorized Codebase Go merge request until it is merged with one Main Agent directly dispatching peer leaf subagents and Simplified Chinese progress. Use when the user explicitly asks for ongoing MR comment monitoring/autopilot that uses the companion review-guard Skill, fixes factual feedback, rebases before commits, replies in threads, recovers CI, and enqueues a rebase merge. Works directly in compatible agent runtimes or containers and supports optional external adapters. Do not use for a one-shot/read-only review or a non-Go repository.
---

# Codebase MR Autopilot

Run one long-lived, low-context Main/Supervisor Agent per MR. It delegates every MR read, review, repository mutation, reply, CI action, and merge action directly to fresh peer subagents. The topology is strictly two layers: one Main Agent plus one or more direct-child Step Workers. A Step Worker never creates, dispatches, or talks through another subagent. Continue until Codebase reports `merged` or a terminal blocker is recorded.

Requires Git, `bytedcli` with Codebase access, the separately discoverable `review-guard` Skill, and an agent runtime/container with a verified native recurring loop plus a fresh-worker mechanism. Use an existing dedicated MR checkout or create one from a trusted machine-local owner policy. External session/worker adapters are optional, never core dependencies.

## Select a mode

- **Start/bootstrap**: the user asks to create the listener. Load the machine-local owner policy, validate inputs and the exact compatible `review-guard` package, automatically provision the dedicated worktree when authorized, run one Supervisor tick, then arm its native loop. Create an external session only when the user explicitly selected an adapter. Read [owner-policy-and-worktree.md](references/owner-policy-and-worktree.md), [review-guard-compatibility.md](references/review-guard-compatibility.md), [supervisor-and-runtimes.md](references/supervisor-and-runtimes.md), and [contracts-and-state.md](references/contracts-and-state.md).
- **Main/Supervisor**: keep only the native loop, lease/phase check, direct-child dispatch, compact Step Result Envelope, Chinese progress rendering, and stop state in context. It is the only agent allowed to dispatch subagents. Read only [supervisor-and-runtimes.md](references/supervisor-and-runtimes.md) and [contracts-and-state.md](references/contracts-and-state.md).
- **Direct Step Worker**: perform exactly one persisted phase such as intake/rebase, R1/R2/R3 review, fix, commit/reply, CI, or merge gate. It receives the phase and artifact paths from Main, returns one compact envelope, and must not dispatch or request another subagent. Read [contracts-and-state.md](references/contracts-and-state.md), then load [comments-and-review.md](references/comments-and-review.md) or [git-ci-and-merge.md](references/git-ci-and-merge.md) only for the assigned phase. Review Steps explicitly invoke `review-guard`; non-review Steps never substitute their own review.

## Required start inputs

Require all of these before creating a live listener:

- Exact Codebase MR URL. Prefer the URL directly in every `bytedcli` command.
- Runtime/container identity, verified native loop start/stop mechanism, and a verified way to create fresh workers. Adapter-specific selectors are optional.
- A discoverable `review-guard` package that a fresh direct Review Step is allowed to invoke autonomously without delegating. Persist its package root and digest; do not silently fall back to generic review.
- A dedicated checkout/worktree binding. It may be supplied explicitly or provisioned automatically under a valid machine-local owner policy.
- Authorization for worktree creation, replies, repository changes, commit/push, CI operations, and `rebase_merge`. Accept either authorization stated in the current request or a valid machine-local owner policy; persist its source and granted subset. Automatic Skill discovery is not mutation authorization.

When a valid owner policy grants the required actions, do not ask the user to repeat the authorization or clean the primary checkout. If an input or permission is still missing, stop before dispatching a mutating worker.

An explicit request to start this Autopilot authorizes Main to create the documented direct-child Step Workers, including read-only Review Steps. It never authorizes a Step Worker to create another agent. It does not authorize any repository or remote mutation beyond the separately persisted mutation scope.

## Non-negotiable invariants

1. One MR, one Main/Supervisor, one Main-owned Cycle Run lease. Never run two mutating workers concurrently.
2. The topology is exactly two layers. Only Main may dispatch. Every Step Worker must refuse nested delegation and must perform its own assigned phase without creating a child agent, task, topic, session, or container.
3. Main does not run `bytedcli` MR reads, inspect diffs/logs, or touch Git. It advances the durable phase machine by dispatching fresh direct-child Step Workers and consuming only compact envelopes.
4. Do not use `watch.py`, cron, a background watcher, or an external workflow loop as the recurring mechanism. Use the selected agent runtime's native loop.
5. Never stash, reset, clean, switch, rebase, or otherwise mutate the user's primary checkout. Auto-provision and bind a dedicated worktree before any MR mutation.
6. When comments are eligible, rebase first and use R1 full review as the comment-coalescing window. Do not add a fixed three-minute sleep.
7. Before the batch commit, perform one supplemental comment scan. Comments after its cutoff belong to the next cycle.
8. Rebase before every commit. If the target head moves after review, rebase and revalidate within the remaining review budget.
9. Every review call uses a fresh direct-child Review Step invoking `review-guard`. A batch allows at most three review calls and two automatic fix passes. No fourth review and no internal fallback reviewer.
10. Reply on each relevant Codebase thread. Never resolve or close a reviewer comment; the reviewer owns closure.
11. Diagnose CI before operating it. Retry the same `HEAD + check + failure fingerprint` at most once by default.
12. Never use an unprotected force push. Use an explicit source-ref `--force-with-lease=<branch>:<expected-sha>` only when rebase rewrote the authorized MR branch.
13. Approval is observed, not manufactured. Never self-approve to satisfy the merge gate.
14. Enqueue only `rebase_merge`, then keep monitoring until the MR itself reports `merged`.
15. All user-visible progress, blockers, summaries, terminal reports, and Codebase thread replies must use Simplified Chinese. Internal JSON keys and status enums may remain English, but Main must never expose raw envelopes as the user-facing report.

## Terminal outcomes

Stop the native loop, release the lease, persist terminal state, and report compactly on:

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
- runtime loop expiry without a safe re-arm path

Do not claim completion for merge-queue entry, a successful push, an Agent reply, or a green local test alone.

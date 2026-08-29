# Comments and Bounded Review

Read this reference only for direct comment/review Steps. Main dispatches every Step below as its own direct child. No Step dispatches the next one.

## Batch state machine

```text
Main acquires the Cycle Run lease
Main -> intake_rebase: synchronize/rebase source
Main -> review_r1: fresh read-only full-MR review through review-guard
Main -> fix_batch: re-read comments, merge/deduplicate, classify, fix/reject,
                   perform one supplemental scan, freeze cutoff, validate,
                   and build canonical R2 evidence
Main -> review_r2: fresh read-only prospective-final review through review-guard
Main -> final_fix: optional second and final fix pass plus R3 evidence
Main -> review_r3: optional fresh read-only targeted verification
Main -> commit_reply: pre-commit rebase, validate, commit/push if changed,
                      and reply on every relevant Codebase thread
```

All arrows return through a compact Step Result Envelope. Review Steps and fix/mutation Steps are peers. A fix Step must not create a Reviewer, and a Review Step must not create a fixer.

R1 is useful work and the comment-coalescing window. Do not sleep for three minutes and do not assume R1 lasts three minutes. The post-R1 read and supplemental scan provide coverage.

## Eligible comments

List open threads with the exact MR URL:

```text
bytedcli --json codebase mr comment list <MR_URL> --status open
```

Identify reviewer-authored additions/edits and compare them with the handled-thread record in [contracts-and-state.md](contracts-and-state.md). Eligible means: no Agent reply, newer reviewer activity, invalidated fix evidence, or missing fix commit. Ignore the Agent's own replies as triggers.

Open does not mean unfixed. Reviewer closure is independent of Agent completion.

## Review-guard dependency and adapter

All R1/R2/R3 calls use the exact compatible `review-guard` package bound in immutable scope. Apply [review-guard-compatibility.md](review-guard-compatibility.md), including its per-round attestation. If the dependency is missing, denied, ambiguous, incompatible, or changes during the listener lifetime, return terminal `blocked_review_dependency`; do not imitate or copy its review logic inside a non-review Step.

Main starts a new direct read-only Review Step for every round with no fixer's reasoning, intended solution, or prior review conclusion. Its prompt begins with `Use $review-guard` or `/review-guard` when the runtime requires slash-skill syntax. Give it:

- MR URL and repository path.
- Round name and exact target/source heads, patchset, worktree diff hash, and requested review boundary.
- Repository review rules if present.
- A temporary review directory outside both the worktree and Git common directory for its native report and canonical evidence.
- Instruction to apply `review-guard`'s finding gate and report only current-scope P0-P2 defects with confidence at least 7/10. Do not request its optional maintainability/refactoring pass.
- Instruction that it is a direct child of Main and must not delegate, spawn, dispatch, or request another agent; this already-fresh Review Step performs its grouped review sequentially.

The Review Step must remain read-only: no edit, format-write, stash, clean, commit, push, reply, resolve, CI operation, approval, or merge. Safe focused tests permitted by `review-guard` remain allowed. Write its native Chinese report and the adapter object only in the external temporary review directory. Return to Main only the compact Step Result Envelope with `artifact_path`; Main passes that path to the following direct mutation Step without loading the findings. That mutation Step validates the object, copies immutable report/evidence into the Git-private run artifact, and records the archived path before applying any finding.

```json
{
  "review_guard_verdict": "Needs changes|可以合并，但建议跟进|LGTM|无法完成可靠 Review",
  "review_skill_package_root": "/canonical/review-guard/root",
  "review_skill_digest_before": "sha256",
  "review_skill_digest_after": "sha256",
  "scope": {
    "scope_mode": "prospective_rebased_mr|prospective_final_mr|targeted_fix_delta",
    "observed_remote_patchset": "host-patchset-id",
    "target_head_sha": "sha",
    "source_head_sha": "sha",
    "worktree_diff_hash": "hash"
  },
  "evidence": {
    "manifest_sha256": "sha256",
    "prospective_patch_sha256": "sha256",
    "last_fix_delta_sha256": "sha256-or-null",
    "required_fingerprints": [],
    "fingerprint_coverage": []
  },
  "findings": [],
  "validation": [
    {"command": "exact command", "result": "pass|fail|blocked|not_run", "reason": "short evidence"}
  ],
  "limitations": ["missing external fact or empty"],
  "native_report_path": "/absolute/external-temp/review-guard-rN.md"
}
```

Each `findings` item uses this mapping of `review-guard`'s native finding contract:

```json
{
  "finding_id": "stable-id",
  "severity": "P0|P1|P2",
  "confidence": 9,
  "file": "path",
  "line_start": 42,
  "line_end": 42,
  "trigger": "concrete input, state, ordering, caller, or deployment condition",
  "impact": "observable consequence",
  "evidence": "current code path, reproduction, or test evidence",
  "action": "smallest root-cause fix direction",
  "scope": "introduced|exposed|materially_worsened",
  "fingerprint": "normalized value"
}
```

Main validates only the compact envelope and artifact containment. The receiving direct mutation Step loads the adapter object and recomputes `review_skill_digest_received`. Reject as `blocked_review_dependency` unless the canonical root, before/after/received digests, and immutable scope binding all match. Repeat the digest check before applying any finding and at the pre-commit and pre-push gates. Separately return `blocked_review_incomplete` when the scope binding is stale/missing, the verdict is `无法完成可靠 Review`, the native report is absent, or any accepted finding fails the `review-guard` finding gate. Optional refactoring, style preference, speculative candidates below 7/10, and unrelated historical debt never enter the automatic fix set.

## R1 reviewer contract

R1 runs after the initial rebase and before comment aggregation finishes. Its boundary is the explicit target SHA through the exact rebased private-worktree head. Because that prospective head may not yet be the remote MR patchset, do not ask `review-guard` to infer refs from the MR URL: invoke its explicit base/head scope, record the observed remote patchset separately, and apply the result only while those local SHAs and diff hash remain unchanged. It is a discovery review, but not a repository-wide audit or maintainability pass.

## R2 composite evidence and R3 coverage

R2 reviews a prospective final MR that combines committed MR history with the active run's staged, unstaged, and untracked files. Do not call `review-guard` in only base/head mode or only working-tree mode, because either view is incomplete.

The direct `fix_batch` Step builds canonical R2 evidence in the external review directory without staging repository files solely for review:

1. Verify every dirty/untracked path is owned by the active run; unexplained paths block the batch.
2. Resolve the exact target SHA, current worktree `HEAD`, and their merge base. Require the target relationship expected after rebase.
3. Generate one binary rename-aware diff from that merge base to the current working tree. This includes committed, staged, and unstaged tracked changes.
4. Enumerate untracked files with `git ls-files --others --exclude-standard -z` and append a binary `/dev/null` diff for every owned untracked path, preserving NUL-safe path handling.
5. Write a manifest containing round, target SHA, committed HEAD, merge base, porcelain-v2 status hash, sorted included paths, untracked path/content hashes, prospective patch SHA-256, and resulting worktree diff hash.
6. Give both patch and manifest to the fresh direct `review_r2` Step. It invokes `review-guard`, verifies current file bytes/status still match the manifest, and treats this explicit prospective change set as canonical evidence.

Before applying R2's final fix pass, preserve the R2 manifest/patch and snapshot every path in the complete R2 prospective file set, not only files named by findings. If the planned fix must touch an additional path, snapshot that path before its first write and add it to the allowed final-fix path set. After the fix, rebuild the complete prospective evidence and generate a binary last-fix delta across the full before/after snapshot set, including additions, modifications, deletions, and mode changes.

Compare the post-fix status/path set with the allowed snapshot set before R3. Any changed path that lacks a pre-write snapshot means the delta is not trustworthy: return `blocked_review_incomplete`, quarantine the batch, and do not reconstruct, commit, or push it.

R3 receives:

- every accepted R2 finding fingerprint;
- the before/after prospective manifest digests;
- the last-fix-delta patch and hash;
- the exact paths/symbols changed by the final fix.

R3's adapter result must set `required_fingerprints` to that exact list and provide one `fingerprint_coverage` record per item with `resolved|still_present|not_reproducible`, current evidence, and affected location. It must also echo the reviewed prospective patch and last-fix-delta hashes. Missing/duplicate coverage or a digest mismatch returns `blocked_review_incomplete`.

## Merge comments and Review Guard findings

After R1 completes, fetch open comments again. Normalize each Codebase comment and `review-guard` finding by file, symbol/region, and factual claim.

- Same issue in both sources: one fix, Codebase thread is the external reply anchor.
- Same issue across multiple Codebase threads: one fix, separate reply on every thread.
- Internal-only P0-P2 finding accepted by `review-guard`: fix it when in scope; do not create a new MR comment that would trigger the listener itself.

All accepted P0-P2 findings enter the unified problem set because this Autopilot was explicitly asked to fix issues discovered by review. If even the smallest P2 action would require a material redesign or scope expansion, classify it as `unclear` and block for direction rather than ignoring it or broadening the MR.

## Factual dispositions

Assign exactly one:

- `confirmed_unfixed`: current head reproduces or proves the issue; implement a focused fix.
- `confirmed_already_fixed`: current head satisfies the requirement; do not change code, but reply with current evidence.
- `partially_confirmed`: only a precise subset is factual; fix that subset and explain the rejected portion.
- `false_positive`: the claim conflicts with current code/behavior/test evidence; reject with evidence.
- `duplicate`: another item in this batch covers it; attach it to the same fix commit.
- `unclear`: multiple interpretations would materially change the implementation; ask for clarification and block merge without guessing.

## Determine whether an open comment is already fixed

1. Map its old line anchor, symbol, scenario, or invariant to the current source head.
2. Inspect the current execution path, not only the original patch location.
3. Reproduce the reported failure when practical, or run a targeted existing/new test.
4. Confirm any claimed fix commit remains in current source history and the behavior has not regressed.
5. Save concrete evidence: current code location, command, result, and commit/head.

Thread state never substitutes for this evidence.

## Fix pass and supplemental scan

Implement all accepted R1/comment findings as one coherent batch. Prefer focused tests that fail for the reported behavior before the fix and pass after it when practical.

Before committing, fetch open comments exactly once more:

- Include reviewer activity newer than the post-R1 snapshot.
- Classify and handle those comments immediately; do not run another full R1 and do not wait.
- Record the scan timestamp/comment high-water mark as the batch cutoff.
- Leave comments arriving after cutoff for the next Cycle Run.

The changes from supplemental comments are included in R2.

## Bounded convergence

Main owns and persists this fixed budget per batch. Individual peer Steps may consume only the round/pass assigned to them:

| Round | Scope | May lead to a fix? |
|---|---|---|
| R1 | Fresh `review-guard` full-MR discovery review before the batch fix | Yes, first fix pass |
| R2 | Fresh `review-guard` review of the full prospective final MR diff, including the owned working-tree batch and new files | Yes, one final fix pass |
| R3 | Fresh `review-guard` targeted verification of R2 findings and the last fix delta | No further automatic fix/review cycle |

Rules:

- Maximum three review calls and two automatic fix passes.
- Every round uses a different fresh direct-child Review Step and the same bound `review-guard` package digest.
- If R1 finds nothing beyond false/already-fixed comments and code does not change, skip R2/R3.
- A repeated fingerprint that survives its fix attempt blocks immediately; do not retry the same change.
- If R3 returns any unresolved/new P0-P2 finding with confidence at least 7/10, do not commit known-bad work. Record `blocked_review_nonconvergent`.
- If target head changes, review binding is invalid. Rebase and re-review only within remaining budget. The `commit_reply` Step returns to Main with the earliest unused `review_r2` or `review_r3`; it never creates the Review Step itself. That round becomes a full rebind review of the rebased prospective final diff. When only R3 remains, it still cannot lead to another automatic fix pass.
- If target moves again after the last valid review slot, preserve the known batch diff and record `blocked_target_churn`; do not commit or silently restart an unlimited review budget.
- For either blocking case with uncommitted changes, quarantine the checkout exactly as defined in [contracts-and-state.md](contracts-and-state.md): capture patches/status in the run artifact, persist `dirty_quarantined:<run-id>`, and require explicit human recovery. Never hide the state with stash/reset or hand the dirty checkout to another automatic worker.

Bind each review result to:

```text
target_head_sha + source_head_sha + worktree_diff_hash
```

## Thread replies

Reply using the exact `thread_id`:

```text
bytedcli codebase mr comment reply <MR_URL> \
  --thread-id <thread-id> \
  --body-file <reply-file>
```

Use a file for nontrivial reply bodies to avoid shell quoting mistakes.

- **Fixed**: factual conclusion, focused change, pushed commit SHA, and relevant verification.
- **Already fixed**: current code/head and evidence proving the issue no longer occurs.
- **Partially confirmed**: accepted subset, rejected subset with evidence, commit/test.
- **False positive**: concise rejection reason and current code/test evidence.
- **Duplicate**: reference the shared fix commit and verification.
- **Unclear**: ask the minimum clarifying question; do not assert a fix.

The direct `commit_reply` Step publishes fix replies only after push and remote-head confirmation. If the batch has no code change, it replies after evidence is complete without creating an empty commit. User-visible reply prose must use Simplified Chinese; keep code, commands, IDs, and SHAs literal when useful.

Never call `mr comment resolve` or `unresolve`. Record reply IDs so an open but answered thread is not reprocessed unless the reviewer follows up or the source head invalidates the evidence.

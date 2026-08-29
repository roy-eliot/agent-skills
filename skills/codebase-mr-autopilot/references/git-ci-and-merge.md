# Git, CI, and Merge

Read this reference for any repository mutation, reply execution, CI action, or merge decision. Commands reflect bytedcli 0.136.0; verify current `--help` before a live write because the command surface may change.

## Repository preflight

Work only in the authorized dedicated worktree created or validated through [owner-policy-and-worktree.md](owner-policy-and-worktree.md). The source/primary checkout is discovery-only and may be dirty.

1. Verify the worktree's Git common directory and Codebase remote match the immutable MR scope.
2. Read the MR with `bytedcli --json codebase mr get <MR_URL>` and record source branch/head and target branch/head.
3. Confirm the local branch is the recorded private `codebase-mr-autopilot/...` branch, its base is the expected MR source head, and no unrelated user changes exist. The private local branch need not have the same name as the remote MR source branch.
4. Confirm push permission and branch protection as needed.
5. If the checkout is dirty from an unknown/crashed run, stop. Do not stash, discard, or overwrite unexplained work.
6. Never run mutation commands in `source_repo_path`; use `git -C <repo_path>` or set the direct Step Worker working directory to the dedicated worktree explicitly.

## Initial and commit-gate rebase

At the start of a comment or code-fix batch:

```text
git fetch <remote> \
  +refs/heads/<target-branch>:refs/codebase-mr-autopilot/<mr-key>/target \
  +refs/heads/<source-branch>:refs/codebase-mr-autopilot/<mr-key>/source
git rebase refs/codebase-mr-autopilot/<mr-key>/target
```

Use the MR-authoritative source and target remotes when they differ. The private refs prevent nonstandard remote fetch configuration from leaving stale remote-tracking refs. Confirm their fetched SHAs equal the fresh MR metadata before rebasing.

After the batch is fixed, stage only the explicitly intended batch paths, including any new test files, and inspect the staged diff. If unrelated/unexplained untracked files remain, block instead of assuming autostash will protect them.

Immediately before every commit, fetch again and always run:

```text
git fetch <target-remote> \
  +refs/heads/<target-branch>:refs/codebase-mr-autopilot/<mr-key>/target
git rebase --autostash refs/codebase-mr-autopilot/<mr-key>/target
```

Use `--autostash` only after the intended batch paths are staged and accounted for. Compare the fetched target head with the head bound to the latest valid review. After rebase, verify the intended staged changes were restored before testing or committing.

- Unchanged target: the required pre-commit rebase should be a no-op; rerun the affected validation after it.
- Advanced target: the rebase invalidates the old review binding. The direct `commit_reply` Step reruns affected validation, recomputes the worktree diff hash, writes a rebind request artifact, and returns to Main with the earliest unused `review_r2` or `review_r3`. Main directly dispatches that Review Step. If no adequate review slot remains, preserve the known batch diff and return `blocked_target_churn` without committing.
- Conflict: inspect it. Resolve only when intent is unambiguous and fully testable; otherwise abort the rebase, preserve evidence, and return `blocked_rebase_conflict`.

Never commit while the source branch is known to be behind the target branch.

## Validation and commit

Run:

- Reproduction/targeted test for every confirmed issue.
- Affected module tests.
- Repository-required lint, build, static checks, or generated-file checks.
- The affected validation again after any rebase.

Before commit, inspect the exact staged file list and staged diff. Do not use a broad add that could capture unrelated files.

Prefer one coherent commit for the whole comment/review batch. Do not create an empty commit for false-positive, duplicate, or already-fixed-only batches.

Before push, confirm the remote MR source head still equals the expected pre-push head. Push the private local `HEAD` to the exact recorded MR source branch with an explicit refspec; never rely on upstream defaults.

- Use ordinary `git push <remote> HEAD:<source-branch>` when history is fast-forward.
- When rebase rewrote the authorized source branch, bind the lease to the exact previously observed remote SHA:

  ```text
  git push --force-with-lease=<source-branch>:<expected-old-sha> \
    <remote> HEAD:<source-branch>
  ```

- Do not use the shorthand `--force-with-lease` without the exact ref and expected SHA.
- Never use `--force`.
- Re-read the MR and confirm the pushed commit is the remote source head before sending fixed replies.

## bytedcli MR and comments

Prefer exact MR URL selectors and JSON for machine-readable reads:

```text
bytedcli --json codebase mr get <MR_URL>
bytedcli --json codebase mr status <MR_URL> --page-size 100
bytedcli --json codebase mr reviewer list <MR_URL>
bytedcli --json codebase mr comment list <MR_URL> --status open
bytedcli codebase mr comment reply <MR_URL> --thread-id <id> --body-file <file>
```

Do not call `mr review --approve`; the merge gate observes human approval. Do not call comment resolve/unresolve.

## CI diagnosis

Use the remote failure first; do not begin by running an unrelated full local suite.

```text
bytedcli --json codebase mr status <MR_URL> --page-size 100
bytedcli --json codebase checks list --mr <MR_URL> --page-size 100
bytedcli --json codebase checks get -R <repo> --id <check-run-id>
bytedcli codebase checks log -R <repo> --check-run-id <check-run-id>
```

Write large logs into the current run artifact and search them with `rg`; do not paste them into the Supervisor context.

Classify the failure:

- `code_or_test_defect`: start a fresh fix cycle with the same rebase, validation, and bounded-review rules.
- `flaky`: rerun only with concrete instability evidence.
- `infrastructure`: rerun only when logs indicate the code is not responsible.
- `unknown`: gather more evidence or block; do not guess/rerun repeatedly.

## Check operation and pipeline retry

Check-run operations are dynamic. Inspect the current `Operations` array from JSON and select a current operation whose label/description actually means rerun:

```text
bytedcli --json codebase checks list -R <repo> --mr <MR_URL> --page-size 100
bytedcli codebase checks operate -R <repo> \
  --payload-json '{"CheckRunId":"<id>","OperationId":"<current-operation-id>"}'
```

Never hard-code a universal rerun operation ID.

For a git-backed pipeline, discover its name before running it:

```text
bytedcli --json codebase pipeline list -R <repo> --branch <source-branch>
bytedcli --json codebase pipeline status -R <repo> --branch <source-branch> --pipeline <name>
bytedcli codebase pipeline run -R <repo> --branch <source-branch> --pipeline <name>
```

Record `HEAD + check/pipeline + failure fingerprint` before a retry. Default maximum is one retry for the same fingerprint. A repeated failure returns `blocked_ci_nonconvergent`; it does not trigger another run.

## Merge gate

Read fresh state immediately before enqueue. Require all:

- MR is open.
- Human approval requirements are satisfied.
- No eligible comment or clarification blocker exists. Threads may remain open after an evidence-backed Agent reply because the reviewer owns closure.
- Required checks are successful; no required pending/running check remains.
- MR is mergeable.
- Remote source head equals the reviewed, tested, pushed head.
- Source is not behind target; perform the final target-head comparison/rebase gate.
- Authorization includes `merge_rebase`.

Then enqueue exactly:

```text
bytedcli codebase mr queue enqueue <MR_URL> --merge-method rebase_merge
```

Before enqueue, query queue entries. If an active entry already exists for this MR/head, return `queued` without enqueueing again. After a new enqueue, confirm queue state with:

```text
bytedcli --json codebase mr queue entries <MR_URL>
bytedcli --json codebase mr status <MR_URL> --page-size 100
```

Queue entry is `queued`, not `merged`. The direct `merge_gate` Step persists its result and returns to Main. Main releases the Cycle Run lease, continues native-loop ticks, and stops only when a fresh direct `intake_route` Step reports `merged`.

If the MR is closed without merge, persist `closed_unmerged`. If queue/check state changes or new reviewer feedback arrives, Main routes the next Cycle Run through the corresponding direct comment/CI Steps before attempting enqueue again.

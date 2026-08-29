# Optional Botmux Adapter

Read this reference only when the user explicitly selects botmux to create/bridge the Main/Supervisor session, start a direct Step Worker, or return compact Chinese reports. The core Skill runs without botmux.

## Strict two-layer topology

Botmux must preserve this exact topology:

```text
one Main/Supervisor bot session
└── one or more fresh direct Step Worker sessions/goals
```

Main creates every Step Worker itself. A Step Worker may not call `botmux dispatch`, `botmux goal run`, `@mention` another agent, create a child topic/session, or ask Main to treat a worker-created session as its child. Reject any adapter configuration that requires `Main -> Cycle Worker -> Reviewer`.

## Adapter preflight

Confirm the installed botmux version and current `--help` before live dispatch. Persist botmux identifiers only inside adapter configuration; do not add them to the portable core scope.

Use one Main listener topic/session per MR. The brief contains only the immutable scope, Skill invocation, Chinese-output requirement, compact-report requirement, and instruction to run one immediate Main tick before arming the runtime-native loop. Never paste the MR diff, comments, CI logs, or English raw envelopes into it.

## Create or bridge the Main session

For a stable bot app already bound to the correct repository:

```text
botmux dispatch --title "MR <id> 自动跟进" \
  --bot-app <larkAppId:role> \
  --brief-file <absolute-brief-file>
```

Current botmux does not support `--repo` with `--bot-app`. Do not combine them.

For a trusted same-machine legacy bot that needs an explicit working directory:

```text
botmux dispatch --title "MR <id> 自动跟进" \
  --bot <open_id:name:role> \
  --repo <absolute-repo-path> \
  --brief-file <absolute-brief-file>
```

## Inject a Claude native loop

Allow only the required slash command on the selected bot:

```json
{
  "tuiSlashAllow": ["/loop"]
}
```

After one immediate Main tick, inject the runtime-native loop into the same idle Main session:

```text
botmux slash "/loop 1m /codebase-mr-autopilot supervisor <MR_URL>"
```

Botmux transports the slash command; Claude still owns the loop. Capture Claude's returned 8-character scheduled-task ID in core scope. On terminal state Claude must delete that exact task ID and verify it no longer appears in its task list. Do not replace it with a botmux workflow loop.

## Start one fresh direct Step Worker

Prefer the target runtime's native direct subagent. If unavailable, Main itself may use the selected botmux adapter to run one fresh peer goal worker:

```text
botmux goal run --goal-file <step-goal-file> \
  --run-id <stable-step-id> \
  --working-dir <absolute-repo-path> \
  --json
```

The goal file must contain the Direct Step Worker prompt contract from [supervisor-and-runtimes.md](supervisor-and-runtimes.md), including the ban on nested delegation and the requirement that every natural-language envelope field be Simplified Chinese. Reuse a Step ID only for the same canonical Step. If goal execution is unavailable, Main may directly create one visible child topic/session, but that topic is still a leaf and must return only the compact Step Result Envelope.

Never let a fix worker create an R1/R2/R3 worker. Main receives the fix result first and then creates the Reviewer as a separate peer.

## Report and stop

- Material progress or a terminal outcome may use one compact `botmux report`, written in Simplified Chinese.
- Main renders `summary_zh` and `next_action_zh`; it never forwards raw JSON or English enum values as a human report.
- Idle/waiting ticks do not produce verbose topic messages.
- Persist terminal state and release the owned lease before cancelling and verifying the exact bound runtime-native task ID.
- Never archive/delete the botmux topic unless the user separately requests it.

# Review Guard Compatibility

Read this reference during bootstrap and before every R1/R2/R3 dispatch. `review-guard` is a required sibling Skill, not an optional adapter.

## Compatible package

This Autopilot release accepts exactly these `review-guard` package digests:

```text
bbdabb72ffc1e6e86a8e35c4a2df5377ac05644a97383d4c98108b8c27dbe7ef
```

Compute SHA-256 over regular package files sorted by relative POSIX path. For each file feed `UTF-8 path`, NUL, raw bytes, then NUL. Exclude `.git`, `.DS_Store`, `__pycache__`, and `*.pyc`.

A new Review Guard release requires an intentional Autopilot compatibility update and a new dual-Skill bundle. Do not accept an arbitrary same-name package.

## Unambiguous discovery

1. Enumerate every `review-guard` candidate exposed by the current runtime and its user/project Skill discovery roots.
2. Resolve symlinks and deduplicate candidates that share the same canonical real path. If supported, also compare filesystem identity.
3. Require exactly one distinct canonical package root.
4. Validate `SKILL.md` frontmatter name is `review-guard` and the package digest is in the compatible list.
5. Confirm a fresh direct-child Review Step can autonomously invoke that exact candidate without delegating again. A same-name nested directory inside Autopilot is not a discoverable sibling Skill.

Zero candidates, multiple distinct candidates, an incompatible digest, or a deny rule returns terminal `blocked_review_dependency`. Never choose the first search-path match.

## Per-round attestation

The digest check is not bootstrap-only:

1. The immediately preceding direct Step records the canonical package digest in the review request artifact before Main dispatches the Review Step; Main transports only the artifact path.
2. The direct Review Step checks after loading `SKILL.md` and all referenced resources needed by that round, then records `review_skill_digest_before`.
3. The Review Step checks again immediately before returning and records `review_skill_digest_after`.
4. Main validates only the compact envelope and artifact containment. The receiving direct mutation Step loads the attestation and recomputes `review_skill_digest_received` before applying any finding; `commit_reply` checks again at the pre-commit and pre-push gates.
5. Require every observed digest to equal the immutable scope digest and one another.

Any mismatch returns `blocked_review_dependency`; quarantine owned uncommitted changes under the normal blocker rules. Do not use findings produced across a dependency change.

This detects ordinary package updates or replacement during a live review. A process intentionally swapping the complete package and restoring identical bytes between every attestation is outside the trusted local-user threat model.

# Go Review Checks

Use this as a risk map, not a quota. Report only problems supported by the current change and its direct contracts.

## 1. Determine Language and Project Semantics

Read the relevant `go.mod`, `go.work`, `toolchain` directive, build tags, generated-code commands, and CI checks before applying version-sensitive advice.

- Do not report historical range-variable capture behavior when the module's Go language version has per-iteration variables.
- Do not recommend a new standard-library API that the module's supported Go version cannot use.
- Respect repository patterns when multiple Go designs are equivalent.
- A path named `generated`, `mocks`, `thrift_gen`, or `*_gen.go` is not proof of provenance. Determine whether the file is truly generated and whether its source definition was updated.

## 2. Intent and Cross-File Contracts

Start from behavior, not isolated hunks.

- Follow changed entrypoints through direct callers and implementations.
- When an interface, exported symbol, request/response type, error, event, config key, schema, or IDL changes, check producers and consumers that share the contract.
- Check generated outputs only after finding the owning schema/generator contract.
- Check config defaults across Go structs, examples, Helm/manifests, environment bindings, and docs when the config surface changes.
- Check migrations, rollback, mixed-version rollout, and stored-data compatibility when persistence or wire formats change.
- Distinguish deletion of unsupported behavior from accidental compatibility loss.

## 3. Correctness and State

Trace a concrete execution path.

- nil and zero-value behavior: pointers, maps, slices, funcs, interfaces containing typed nils, optional dependencies, and zero-value structs
- slice/map ownership: subslice and `append` aliasing, returned internal slices/maps, mutation after channel send, pooled-object reset
- conversions and arithmetic: narrowing, overflow, signed/unsigned boundaries, unit mismatches, division by zero, duration/timestamp precision
- state machines: invalid transitions, partial updates, duplicate side effects, idempotency, retry behavior, cache/source consistency
- control flow: shadowed variables, wrong early return, stale value use, incorrect error/status mapping, unordered map iteration where order is contractual
- time: caller clock assumptions, timer/ticker lifecycle, deadline composition, timezone and duration units

Do not report a nil or boundary risk without an actual input source or reachable state. If every current caller proves the precondition, the issue is at most a lower-severity defensive concern.

## 4. Errors, Resources, and Context

- Preserve error identity where callers use `errors.Is`/`errors.As`; use `%w` only when wrapping is part of the contract.
- Do not both log and return the same error at multiple layers unless the repository has an explicit ownership rule.
- Check ignored errors, especially transaction commit/rollback, buffered writes, close/flush, goroutines, callbacks, and deferred cleanup.
- Ensure resource acquisition has cleanup on every path; a `defer` inside a long loop may retain resources until function return.
- Derive new contexts from the caller's context. `context.Background()` inside request or job paths can sever cancellation, deadlines, tracing, auth, or tenant identity.
- Ensure created cancel functions are called. Do not store request contexts in long-lived structs.
- Timeout changes must preserve the tighter caller deadline and map timeout/cancellation errors correctly.

## 5. Concurrency and Lifecycle

Reason about ownership, ordering, shutdown, and failure, not just the presence of a mutex.

- `WaitGroup.Add` happens before the goroutine can race with `Wait`; every started unit calls `Done` exactly once.
- Goroutines have bounded lifetime, cancellation, error propagation, and panic policy appropriate to the repository.
- Channel close ownership is singular; receivers do not close a producer-owned data channel.
- Blocking sends and receives can exit on cancellation where shutdown requires it.
- Locks protect the full invariant, not merely individual fields. Check lock ordering, callbacks while locked, copy-after-first-use of mutex-bearing values, and check-then-act windows.
- Maps and shared slice backing arrays are not concurrently mutated without synchronization.
- Atomics preserve the full multi-field invariant; race-free code can still be logically inconsistent.
- Background workers, timers, tickers, subscriptions, streams, and leases are stopped and drained according to their contract.

Use `go test -race` when the affected package has meaningful concurrent execution. A passing race run does not prove lifecycle or ordering correctness.

## 6. Security and Isolation

- Trace authentication and authorization from identity source through verification, decision, resource, and side effect.
- Verify resource ownership, tenant/workspace/session boundaries, not just resource existence.
- Check SQL/command/template injection, path traversal, SSRF and redirect policy, unsafe deserialization, archive extraction, upload type validation, and unbounded payloads.
- Check secret/token handling in config, logs, errors, URLs, persistence, telemetry, and downstream requests.
- Validate cryptographic algorithm, randomness, key lifecycle, comparison, and protocol use; do not invent custom crypto fixes.
- Treat external input size, recursion, fan-out, and decompression ratios as resource-exhaustion surfaces.
- For filesystem and network destinations, prove canonicalization and allow/deny policy at the point of use.

Security severity depends on a realistic attack path and impact. External-system assumptions lower confidence until verified.

## 7. Persistence, Compatibility, and Operations

- Transactions cover the complete invariant and use the intended isolation/locking behavior.
- Retry and idempotency semantics prevent duplicate durable effects.
- API/IDL/config/data changes preserve old callers or include an explicit migration and rollout plan.
- Rolling upgrade works with mixed versions; rollback does not leave unreadable state or remove required defaults.
- Startup/shutdown ordering releases leases, drains work, closes resources, and does not turn cooperative cancellation into data loss.
- Logs, metrics, and traces identify material new failure paths without leaking sensitive data or creating unbounded cardinality.
- Health/readiness semantics reflect actual dependency readiness and degradation policy.

## 8. Performance

Report performance only with a credible hot path, scale condition, or measured regression.

- unbounded goroutine/task creation, queues, reads, or response aggregation
- N+1 storage/network calls and repeated serialization
- large avoidable allocation/copy/retention, including small subslices retaining large buffers
- lock contention or blocking I/O inside critical sections
- missing backpressure, pagination limits, timeouts, or batch bounds
- algorithmic growth that is material for expected input size

Do not report micro-optimizations, arbitrary channel buffer sizes, or alternative data structures without evidence.

## 9. Tests and Validation Evidence

Judge tests as executable proof of supported behavior, not a coverage-number target.

A missing-test finding must name:

1. the changed supported contract
2. the layer that owns the proof
3. a material wrong implementation the test would catch
4. the smallest architecture-preserving test action

For tests already in the diff, check observable behavior, assertion ownership, determinism, isolation, cleanup, race/flakiness risk, over-mocking, and whether failure is attributed to the correct subtest/helper.

Do not require table-driven tests, `t.Parallel`, a particular mocking library, or file naming solely as personal preference. Apply such rules only when the repository contract requires them or the current form causes a concrete reliability problem.

Recommended validation selection:

- formatting: read-only `gofmt -d` or repository formatter check
- compile/unit: focused `go test` on affected packages
- concurrency: focused `go test -race -count=1`
- static analysis: repository lint/vet target, or focused `go vet`
- integration/schema/deployment: only when touched and safe; honor build tags and required fixtures
- full suite: when proportional and repository-native, not as a substitute for focused failure reproduction

Record exact commands, outcomes, skipped checks, and environmental failures separately from code findings.

## 10. False-Positive Filter

Drop a candidate when any is true:

- it exists only in deleted old code
- the current patchset already fixes it
- the location is outside the requested scope and the change does not activate it
- it is merely a valid alternative design, naming preference, formatting issue handled by tooling, or educational note
- it assumes nil, concurrency, scale, external behavior, or caller misuse without evidence
- it duplicates the same root cause
- its line number or source revision is stale
- the suggested fix would broaden scope without necessity


# Public Goal/thread board

`goal-thread-board` is the owner-local, read-only publication surface that a
dashboard may use for one exact Goal and one exact master thread. It is a
derived projection; it does not become Goal, branch, participant, runtime, or
acceptance authority.

```bash
python3 scripts/aoa_session_memory.py goal-thread-board \
  --aoa-root /path/to/workspace/.aoa \
  --goal-ref <exact-thread-goal-ref> \
  --master-thread-id <exact-master-thread-id> \
  --page-size 50 \
  --owner-observation /path/to/typed-owner-observation.json
```

`goal_ref` and `master_thread_id` are exact equality bindings. Arbitrary
non-empty opaque bindings are accepted; host-shaped bindings are represented
by a stable public-safe digest before publication. A mismatch is `invalid`;
the command never falls back to a selected Goal, a fuzzy title, a task DAG, a
filename, a parent id, or a timestamp.

The optional owner observation is a sanitized adapter input assembled from
read-only Codex app-server methods:

- `thread/goal/get` for the exact Goal status and bounded timestamps;
- `thread/read` with `includeTurns=false` for exact thread status and direct
  `parentThreadId`/`forkedFromId` observations;
- paginated `thread/items/list` for immutable item ids and typed item kinds;
- paginated `thread/list` for explicitly returned direct parent/fork relations.

The adapter emits only immutable ids, typed kinds, source-page order, bounded
status, and logical evidence coordinates. It withholds prompts, transcript or
message bodies, objectives, commands, tool arguments/results, cwd/path,
process/model/actor metadata, and private response fields. `reviewed_public_safe`
means the owner publisher's deterministic allowlist/privacy review; it is not a
human review or semantic acceptance verdict.

If an owner method is unavailable or its response cannot be admitted, the
method remains `unknown`, `missing`, `deferred`, `stale`, or `invalid` in the
owner read. The publisher does not turn that into an empty complete page. A
current index item can still be rendered when its own source is current, while
the owner page remains incomplete.

The session-memory owner index can contribute allowlisted Goal lifecycle
markers (`goal_created`, `goal_updated`, `goal_blocked`, and related indexed
kinds) when the complete generated index set is current and the exact Goal and
thread match. Their order is explicitly `owner_index_order`, not a semantic
event sequence.

The response uses the same bounded source-snapshot read budget as the Goal
catalog and exposes the read attempts, retry exhaustion, stable-source flag,
and live-capture watermark. It preserves an immutable snapshot digest, source
watermark, page digest, opaque pagination cursors, owner-page completeness, and separate
`current`, `missing`, `unknown`, `stale`, `deferred`, and `invalid` states. A
missing Codex branch publisher is represented as:

```json
{
  "branch": {
    "state": "missing",
    "branch_ref": null,
    "lifecycle_state": null,
    "reason": "no_canonical_goal_branch_publisher"
  },
  "ordering": {
    "event_ordering": {
      "state": "missing",
      "kind": "unavailable",
      "reason": "codex_app_server_has_no_replayable_event_sequence"
    }
  }
}
```

Direct parent and history-fork relations remain structural observations. They
do not establish a semantic branch, trajectory, author, participant, or
lifecycle. `nextCursor` is a page cursor, not an event watermark; a null
cursor closes only that exact query page.

Source degradation diagnostics are published as bounded codes only; session
IDs, raw paths, response errors, and other suffixes are omitted. The owner
method list is also allowlisted, so an adapter cannot turn an arbitrary path or
private method name into a public join key.

The dashboard must preserve these negative states and claim limits. It may
render the safe board items and relations, but it must not reconstruct omitted
text or promote the projection into owner truth.

---
schema_version: local_eval_report_note_v1
owner_repo: aoa-session-memory
status: reviewed
authority_boundary: no verdict, scoring, regression, or proof doctrine authority
---

# Session-memory skill-system controlled comparison

## Result

The candidate system did not demonstrate a correctness improvement over the
no-skill or previous-skill conditions on the selected public-safe import,
replay, reindex, and doctor task. All five conditions satisfied the bounded
artifact criteria:

- no skill;
- previous skills supplied directly;
- candidate skills supplied directly as a composition;
- one candidate skill supplied directly;
- candidate skills found through two-stage retrieval and task planning.

The mechanisms therefore remain `experimental`. This report records
owner-local pressure and reviewed observations; it is not an `aoa-evals`
benefit, regression, promotion, or proof verdict.

## What was measured

Every condition used the same four-line, 732-byte synthetic Codex history
fixture with SHA-256
`068b7d3430d7d95e94adaef581d8deba8503041e520b1007dcfd9e9be0ca015b`.
Acceptance required preview without archive creation, one import, idempotent
replay, targeted reindex, byte-identical raw preservation, two raw blocks, and
an ordinary green doctor.

The replacement no-skill trial used Codex CLI 0.144.6 with
`gpt-5.6-sol`, `xhigh` reasoning, an ephemeral thread, and skills, plugins,
apps, hooks, memories, and multi-agent execution disabled. A prompt-input
probe contained no skill instruction catalogue, and all 20 skill bodies in the
disposable workspace remained unreadable. The trial issued seven substantive
owner CLI calls; all returned zero, without `--force`, manual repair,
intervention, or recovery.

Independent owner review re-opened its five receipts and final archive. Import
preview planned one session while creating none; apply imported one; replay
reported `skipped_existing`; reindex preview planned one; reindex apply
reported four events, two segments, and two raw blocks. Doctor was current,
the raw-block audit resolved 3/3 sampled refs, and source and archived raw were
byte-identical.

The four skill-bearing collaboration conditions did not expose their model
identity or token counts. Their artifact outcomes remain usable observations,
but the five-condition comparison is not a model-controlled causal estimate.
Timing is incomplete and is not used as a benefit claim.

Both reviewed local suite sidecars were JIT-valid before execution. The first
routing-suite owner/apply attempt failed closed because the environment omitted
the pinned `aoa-skills` owner binding. With the already merged owner revision
`6f53e97cecb74877cf1d91432d685a72cf6771b8` supplied explicitly, the routing
suite passed 12/12 and the behavioral sandbox passed 14/14; both sidecars
remained `ready` before and after. The adjacent JSON records the failed routing
attempt and both successful receipt digests. These receipts record
execution only and carry no
proof or promotion authority.

## Required comparisons

| Comparison | Observed result |
|---|---|
| No skill vs candidate | Both passed; no correctness lift established |
| Previous direct vs candidate direct | Both passed; no correctness lift established |
| Candidate direct vs retrieval | Both passed; retrieval found a ready plan but did not improve correctness |
| Single skill vs composition | Both passed; no composition lift established on this task |
| Compact description vs full contract | Hook-status case improved from rank 5 to rank 1 |
| Flat set vs semantic routing | Both reached 22/22 top-1; visible catalogue fell from 20 skills/3897 bytes to 2 skills/532 bytes |
| Compatible vs incompatible set | Compatible DAG was ready; the injected version-incompatible set was blocked |
| Isolated vs coexistence | Expected rank stayed unchanged for all 22 positive cases |

The two-stage router was slower than flat compact ranking in one local
microbenchmark. Its supported value here is reduced initial context and one
demonstrated full-contract disambiguation, not latency or general task lift.

## Routing and collision pressure

- 22/22 positive and paraphrase cases reached the expected skill at rank 1.
- 4/4 unrelated-owner queries abstained before deep retrieval.
- 5/5 near-neighbor cases selected the expected candidate.
- No protected near-neighbor exclusion collided.
- Compatible ABI composition produced ordered stages and a verifier.
- The injected version-incompatible pair produced an explicit blocker.

## Failures converted into contract repairs

One candidate composed-direct trial used an intentional `--no-tests` runtime
install. Ordinary doctor rejected it because no owner-bound marker
distinguished that shape from accidental test-tree loss.

The repair writes a runtime-only install profile bound to the selected
workspace and AoA root. Doctor accepts a wholly absent tests tree only when the
profile explicitly records `include_tests=false`. A missing marker, a partial
tree, or test loss from a full install remains an error. Completion audit checks
that source/export test files exist; the full suite is executed separately by
the source/export/standalone closeout route.

A rejected no-skill rehearsal also exposed cwd-dependent archive refs after
relative CLI roots. Relative workspace, AoA, and history roots are now
canonicalized before archive writes, with a regression that imports from one
working directory and reindexes from another. The rejected rehearsal is
failure evidence only and is not counted among the five successful conditions.

## Owner-local eval execution

Both reviewed sidecars were JIT-validated as `ready` before execution. The
first routing attempt stopped at collection because its runtime lacked the
required `AOA_SKILLS_ROOT` owner binding; the sidecar remained `ready`, so the
failure was retained as environment evidence rather than treated as a source
regression. With the exact landed `aoa-skills` owner revision bound, routing
passed 12 tests and behavioral sandboxing passed 14 tests. Both sidecars were
still `ready` after execution.

GitHub CI later exposed an environment-dependent 25 GiB headroom assumption in
an existing SQLite compact-copy test. The test now sets an explicit zero
headroom only for its disposable fixture; the production default is unchanged.
Both suites were JIT-revalidated and rerun successfully on source revision
`cafa4e247303351dc3db32b550179a951d0ddb1e`.

The execution receipts capture interpreter, platform, dependency inventory,
pytest configuration refs, selected environment, sidecar digests, and JIT
state. They remain owner-local execution evidence with no verdict, regression,
promotion, proof-acceptance, or runtime-reproducibility authority.

## Claim boundary

Supported locally:

- reduced prompt-visible bytes with all current curated positive routes
  retained;
- one demonstrated full-contract reranking improvement;
- compatible/incompatible typed-composition gating;
- stable coexistence ranks on the current corpus;
- exact raw and artifact preservation across the five accepted synthetic
  executions;
- a strictly isolated successful no-skill execution.

Not supported:

- general behavioral lift;
- a model-controlled causal lift across all five conditions;
- token savings;
- stable latency improvement;
- cross-runtime equivalence;
- lifecycle promotion.

Raw agent traces and disposable receipts are not committed. The adjacent JSON
records public-safe fixture, prompt-probe, and receipt digests without host
paths. `aoa-evals` retains proof, scoring, regression, benefit, and promotion
authority.

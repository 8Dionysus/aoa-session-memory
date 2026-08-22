# Incremental projection comparison

On the `167 MB` live-equivalent fixture, one diagnostic same-fixture run reduced
cold wall time from `720.26 s` serial to `323.50 s` with identical semantic
digests: a `2.23x` speedup. Three independent parallel runs then established a
repeatable p50 of `382.54 s` and p95 of `392.71 s`.

Against the owner-supplied `756.366 s` full live maintenance baseline, the
diagnostic parallel result is `2.34x` faster and the conservative parallel p95
is `1.93x` faster. The scopes differ: the baseline is a full maintenance cycle,
while this benchmark isolates the session projection core. These ratios are
therefore directional comparison evidence, not an identical-scope equivalence.

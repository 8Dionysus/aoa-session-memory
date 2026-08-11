# Incremental projection: local landing

The incremental-core result lands only through the local ref
`local/session-memory-incremental-core-landing-20260811`. That ref must resolve
to the commit containing the machine receipt beside this file.

The tested source revision is
`5f58221cdf2141cc5928c0a7f03c8932e3a3439f`: `1,328` source tests passed,
the final clean portable export passed public-safety and standalone validation,
and all `57` decision records and `6` generated indexes are current.

This landing does not advance the canonical checked-out branch, mutate the live
installation, or write to GitHub. The existing fail-closed push freeze remains
in force.

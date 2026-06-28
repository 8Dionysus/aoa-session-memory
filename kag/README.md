# aoa-session-memory Local KAG Provider

`kag/` exposes the current `aoa-session-memory` provider packet as portable
source-linked records.

## Operating Card

| Field | Route |
| --- | --- |
| role | local KAG provider for portable session-memory archive, route atlas, and session manifest surfaces |
| records | `nodes/`, `edges/`, `indexes/`, `projections/`, `receipts/` |
| manifest | `manifest.json` |
| source route | `README.md`, `PIPELINE.md`, `READINESS.md`, `schemas/session.manifest.schema.json`, `maps/README.md` |
| consumer route | `aoa-kag` registry/composition, `abyss-stack`, MCP resources |
| owner return | `README.md` and `PIPELINE.md` |

## Record Classes

| Class | Current record |
| --- | --- |
| node | portable kernel route and session manifest schema |
| edge | archive route returns to the owner route |
| index | source surface inventory over local records |
| projection | MCP-readable source-return packet |
| receipt | validation receipt for the current owner route |

Git carries compact provider records and source-return handles. Runtime
archives, search indexes, graph stores, diagnostics, and local serving state
route to `.aoa` or the runtime owner named by the consumer.

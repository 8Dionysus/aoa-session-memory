# MCP and CLI evidence routes

Prefer the exact read-only MCP tool when the current registry exposes it:

| Need | Tool |
|---|---|
| transport preflight | `aoa_session_transport_preflight` |
| access-plane health | `aoa_session_access_plane_preflight` |
| literal plan | `aoa_session_literal_query_plan` |
| entity dossier | `aoa_session_entity_dossier` |
| usage chain | `aoa_session_entity_usage_chain` |
| entity inventory | `aoa_session_entity_inventory` |
| registry lookup | `aoa_session_entity_registry` |
| usage audit | `aoa_session_entity_usage_audit` |
| usage neighborhood | `aoa_session_entity_usage_neighborhood` |
| hook receipts | `aoa_session_hook_receipts` |
| graph neighborhood | `aoa_session_graph_neighborhood` |
| graph bridge | `aoa_session_graph_bridge` |
| graph cooccurrence | `aoa_session_graph_cooccurrence` |
| projection status | `aoa_session_projection_status` |
| search pressure | `aoa_session_search_pressure_decision_packet` |
| route rollup | `aoa_session_route_rollup_query` |
| direct event rollup | `aoa_session_direct_event_rollup_query` |
| live scenario | `aoa_session_live_scenario_audit` |
| reviewed corpus check | `aoa_session_live_scenario_corpus_check` |

If an exact tool returns `Transport closed`, run transport preflight when it is
still callable. A configured green stdio plane with no fresh child in the
current session requires runtime reload; name the CLI fallback meanwhile.

Equivalent portable commands use the resolved `<aoa-root>`:

```bash
cd <aoa-root>
python3 scripts/aoa_session_memory.py usage-chain <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-dossier <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-usage-audit <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-usage-neighborhood <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-registry --lookup <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py literal-query-plan "<query>" --kind auto
python3 scripts/aoa_session_memory.py projection-status
python3 scripts/aoa_session_memory.py graph-neighborhood <anchor> --kind <kind> --session <session-if-known> --limit 12 --edge-limit 48
python3 scripts/aoa_session_memory.py graph-bridge <source> <target> --source-kind <kind> --target-kind <kind>
python3 scripts/aoa_session_memory.py live-scenario-corpus list
python3 scripts/aoa_session_memory.py live-scenario-corpus check --case-limit 1
```

For a fresh transport diagnosis, resolve an `abyss-stack` checkout and use the
service-owned preflight/validator there. Do not embed one host checkout path in
this portable skill.

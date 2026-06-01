# Muscles MCP

Model Context Protocol adapter for Muscles.

This package should expose a Muscles application to AI tools through MCP without
copying application logic into the adapter.

## Concept Guardrails

- Muscles remains the source of truth for actions, schemas, rules, context, and
  permissions.
- MCP tools/resources must be generated from the Muscles application contract.
- The adapter must not invent its own routing, validation, auth, or business
  model.
- A use case implemented once in Muscles should become available through MCP
  without rewriting the use case.
- Machine-readable metadata is a product feature, not an internal detail.

## Initial Goal

Expose a minimal Muscles app as MCP tools and resources, backed by
`muscles inspect --json` compatible contract data.

## Current Stage (Issue #1)

Implemented MCP adapter baseline from Muscles inspect contract:

- `list_tools()` from contract `actions`;
- `list_resources()` for canonical MCP URIs:
  - `muscles://app/inspect`
  - `muscles://app/actions`
  - `muscles://app/routes`
  - `muscles://app/schemas`
  - `muscles://app/rules`
- `read_resource(uri)` returns stable JSON payload per resource;
- `call_tool()` delegates to Muscles action handler (no business-logic copy);
- tool input validation is derived from action `input_schema`;
- permission/rule denial is returned as structured MCP error.

### Run tests

```bash
python -m pytest -q
```
